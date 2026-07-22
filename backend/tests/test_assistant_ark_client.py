# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import logging
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from openai import BadRequestError

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


def thinking_bad_request() -> BadRequestError:
    return BadRequestError(
        "thinking unsupported",
        response=httpx.Response(
            400,
            request=httpx.Request("POST", "https://ark.test"),
        ),
        body={"error": "unsupported"},
    )


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


def test_plan_forces_submit_plan_and_enables_thinking() -> None:
    completion = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport = ark_client_with([completion])

    plan = client.plan([{"role": "user", "content": "有哪些任务"}], SUBMIT_PLAN_TOOL)

    assert plan == {"kind": "query"}
    request = transport.chat.completions.create.call_args.kwargs
    assert request["extra_body"] == {"thinking": {"type": "enabled"}}
    assert request["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_plan"},
    }


def test_plan_retries_without_thinking_only_for_bad_request() -> None:
    completion = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport = ark_client_with([thinking_bad_request(), completion])

    assert client.plan([], SUBMIT_PLAN_TOOL) == {"kind": "query"}
    calls = transport.chat.completions.create.call_args_list
    assert calls[0].kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert calls[1].kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert client.planning_thinking_supported is False


def test_known_unsupported_thinking_skips_enabled_probe_and_duplicate_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fallback = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    next_plan = fake_completion(tool_name="submit_plan", arguments='{"kind":"query"}')
    client, transport = ark_client_with([thinking_bad_request(), fallback, next_plan])
    caplog.set_level(logging.INFO, logger="todo_backend.agent.ark_client")

    client.plan([], SUBMIT_PLAN_TOOL)
    client.plan([], SUBMIT_PLAN_TOOL)

    calls = transport.chat.completions.create.call_args_list
    assert [call.kwargs["extra_body"] for call in calls] == [
        {"thinking": {"type": "enabled"}},
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "disabled"}},
    ]
    capability_events = [
        record.getMessage()
        for record in caplog.records
        if record.name == "todo_backend.agent.ark_client"
    ]
    assert capability_events == ["assistant_planner_thinking_fallback"]


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
