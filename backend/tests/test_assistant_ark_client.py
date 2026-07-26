# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import base64
import gzip
import io
import json
import struct
import wave
from typing import Any
from unittest.mock import MagicMock

import pytest

from todo_backend.agent.ark_client import ArkClient, ArkUnavailableError

SUBMIT_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "parameters": {"type": "object"},
    },
}


def _completion(content: str | None, tool_calls: list[Any] | None = None) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    message.model_dump.return_value = {"role": "assistant", "content": content}
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _tool_call(tool_name: str, arguments: str) -> MagicMock:
    function = MagicMock()
    function.name = tool_name
    function.arguments = arguments
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function = function
    return tool_call


def fake_completion(tool_name: str, arguments: str) -> MagicMock:
    return _completion(None, [_tool_call(tool_name, arguments)])


def ark_client_with(responses: list[Any]) -> tuple[ArkClient, MagicMock]:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = responses
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)
    return client, sdk


def test_chat_returns_text_when_no_tool_calls() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("你好")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    result = client.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])

    assert result.content == "你好"
    assert result.tool_calls == []
    _, kwargs = sdk.chat.completions.create.call_args
    assert kwargs["model"] == "chat-model"
    assert kwargs["tools"] == [{"type": "function"}]
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_chat_parses_tool_calls() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = fake_completion(
        "list_tasks", '{"status": "active"}'
    )
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    result = client.chat([{"role": "user", "content": "hi"}])

    assert result.tool_calls[0].name == "list_tasks"
    assert result.tool_calls[0].arguments == {"status": "active"}
    assert result.raw_message["role"] == "assistant"


def test_chat_omits_tools_when_not_provided() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("ok")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    client.chat([{"role": "user", "content": "hi"}])

    _, kwargs = sdk.chat.completions.create.call_args
    assert "tools" not in kwargs


def test_transcribe_uses_audio_model_and_input_audio_part() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("明天下午三点开会")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    text = client.transcribe("QUJD", "wav")

    assert text == "明天下午三点开会"
    _, kwargs = sdk.chat.completions.create.call_args
    assert kwargs["model"] == "audio-model"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    parts = kwargs["messages"][0]["content"]
    assert parts[0] == {
        "type": "input_audio",
        "input_audio": {"data": "QUJD", "format": "wav"},
    }


def test_agent_plan_transcribe_uses_seed_asr_and_normalizes_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def response_packet(payload: dict[str, Any], *, sequence: int, last: bool) -> bytes:
        compressed = gzip.compress(json.dumps(payload).encode())
        flags = 0b0011 if last else 0b0001
        return (
            bytes([0x11, (0b1001 << 4) | flags, 0x11, 0x00])
            + struct.pack(">iI", sequence, len(compressed))
            + compressed
        )

    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[bytes] = []
            self.responses = [
                response_packet({}, sequence=1, last=False),
                response_packet(
                    {"result": {"text": "完整文本"}},
                    sequence=-2,
                    last=True,
                ),
            ]

        def __enter__(self) -> "FakeWebSocket":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, data: bytes) -> None:
            self.sent.append(data)

        def recv(self, timeout: float) -> bytes:
            del timeout
            return self.responses.pop(0)

    source = io.BytesIO()
    with wave.open(source, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(3)
        wav.setframerate(44100)
        wav.writeframes(b"\x00\x00\x00\x00\x00\x00" * 4410)

    websocket = FakeWebSocket()
    connect_calls: list[tuple[str, dict[str, Any]]] = []

    def fake_connect(url: str, **kwargs: Any) -> FakeWebSocket:
        connect_calls.append((url, kwargs))
        return websocket

    monkeypatch.setattr("websockets.sync.client.connect", fake_connect)
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion("错误接口")
    client = ArkClient(
        "sk-agent-plan",
        "chat-model",
        "doubao-seed-2.0-lite",
        "https://ark.cn-beijing.volces.com/api/plan/v3",
        client=sdk,
    )

    text = client.transcribe(base64.b64encode(source.getvalue()).decode(), "wav")

    assert text == "完整文本"
    assert sdk.chat.completions.create.call_count == 0
    url, kwargs = connect_calls[0]
    assert url == "wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream"
    assert kwargs["additional_headers"]["X-Api-Key"] == "sk-agent-plan"
    assert kwargs["additional_headers"]["X-Api-Resource-Id"] == (
        "volc.seedasr.sauc.duration"
    )
    normalized = b"".join(
        gzip.decompress(packet[12 : 12 + struct.unpack(">I", packet[8:12])[0]])
        for packet in websocket.sent[1:]
    )
    with wave.open(io.BytesIO(normalized), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2


def test_agent_plan_transcribe_distinguishes_audio_without_recognized_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compressed = gzip.compress(json.dumps({}).encode())

    class FakeWebSocket:
        def __init__(self) -> None:
            self.responses = [
                bytes([0x11, 0x91, 0x11, 0x00])
                + struct.pack(">iI", 1, len(compressed))
                + compressed,
                bytes([0x11, 0x93, 0x11, 0x00])
                + struct.pack(">iI", -2, len(compressed))
                + compressed,
            ]

        def __enter__(self) -> "FakeWebSocket":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, _data: bytes) -> None:
            return None

        def recv(self, timeout: float) -> bytes:
            del timeout
            return self.responses.pop(0)

    monkeypatch.setattr(
        "websockets.sync.client.connect",
        lambda *_args, **_kwargs: FakeWebSocket(),
    )
    client = ArkClient(
        "sk-agent-plan",
        "chat-model",
        "doubao-seed-2.0-lite",
        "https://ark.cn-beijing.volces.com/api/plan/v3",
        client=MagicMock(),
    )

    with pytest.raises(ArkUnavailableError) as error:
        client.transcribe("UklGRiQAAABXQVZF", "wav")

    assert type(error.value).__name__ == "ArkAudioNotRecognizedError"


def test_api_errors_become_ark_unavailable() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = RuntimeError("boom")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    with pytest.raises(ArkUnavailableError):
        client.chat([{"role": "user", "content": "hi"}])


def test_malformed_tool_call_arguments_become_ark_unavailable() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = fake_completion("list_tasks", "{not json")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    with pytest.raises(ArkUnavailableError, match="malformed tool call arguments"):
        client.chat([{"role": "user", "content": "hi"}])


def test_chat_rejects_non_object_tool_call_arguments() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = fake_completion("list_tasks", "[]")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    with pytest.raises(ArkUnavailableError, match="tool call arguments must be an object"):
        client.chat([{"role": "user", "content": "hi"}])


def test_plan_forces_submit_plan_and_disables_thinking() -> None:
    completion = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport = ark_client_with([completion])

    plan = client.plan([{"role": "user", "content": "有哪些任务"}], SUBMIT_PLAN_TOOL)

    assert plan == {"kind": "query"}
    request = transport.chat.completions.create.call_args.kwargs
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert request["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_plan"},
    }


def test_plan_generic_error_does_not_trigger_fallback() -> None:
    client, transport = ark_client_with([RuntimeError("timeout")])

    with pytest.raises(ArkUnavailableError, match="chat completion failed"):
        client.plan([], SUBMIT_PLAN_TOOL)

    assert transport.chat.completions.create.call_count == 1


@pytest.mark.parametrize("arguments", ["[]", '"text"', "null", "{"])
def test_plan_rejects_non_object_or_malformed_arguments(arguments: str) -> None:
    client, _transport = ark_client_with(
        [fake_completion(tool_name="submit_plan", arguments=arguments)]
    )

    with pytest.raises(ArkUnavailableError):
        client.plan([], SUBMIT_PLAN_TOOL)


@pytest.mark.parametrize(
    "completion",
    [
        _completion(None),
        fake_completion(tool_name="other_tool", arguments="{}"),
        _completion(
            None,
            [
                _tool_call("submit_plan", "{}"),
                _tool_call("submit_plan", "{}"),
            ],
        ),
    ],
)
def test_plan_requires_exactly_one_submit_plan_call(completion: MagicMock) -> None:
    client, _transport = ark_client_with([completion])

    with pytest.raises(ArkUnavailableError, match="planner did not submit exactly one plan"):
        client.plan([], SUBMIT_PLAN_TOOL)
