# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Any
from unittest.mock import MagicMock

import pytest

from todo_backend.agent.ark_client import ArkClient, ArkUnavailableError


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
    function = MagicMock()
    function.name = "list_tasks"
    function.arguments = '{"status": "active"}'
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function = function
    sdk = MagicMock()
    sdk.chat.completions.create.return_value = _completion(None, [tool_call])
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
    parts = kwargs["messages"][0]["content"]
    assert parts[0] == {
        "type": "input_audio",
        "input_audio": {"data": "QUJD", "format": "wav"},
    }


def test_api_errors_become_ark_unavailable() -> None:
    sdk = MagicMock()
    sdk.chat.completions.create.side_effect = RuntimeError("boom")
    client = ArkClient("sk-x", "chat-model", "audio-model", client=sdk)

    with pytest.raises(ArkUnavailableError):
        client.chat([{"role": "user", "content": "hi"}])
