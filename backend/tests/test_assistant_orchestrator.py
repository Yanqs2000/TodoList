# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Any
from unittest.mock import MagicMock

from todo_backend.agent.ark_client import ArkChatResult, ArkToolCall
from todo_backend.agent.orchestrator import MAX_TOOL_ITERATIONS, AgentOrchestrator


class _ScriptedArk:
    def __init__(self, results: list[ArkChatResult]) -> None:
        self._results = list(results)
        self.calls: list[list[dict[str, Any]]] = []

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ArkChatResult:
        self.calls.append(list(messages))
        return self._results.pop(0)


def _final(text: str) -> ArkChatResult:
    return ArkChatResult(content=text, tool_calls=[], raw_message={"role": "assistant"})


def _tool_turn(call_id: str, name: str, arguments: dict[str, Any]) -> ArkChatResult:
    return ArkChatResult(
        content="",
        tool_calls=[ArkToolCall(id=call_id, name=name, arguments=arguments)],
        raw_message={
            "role": "assistant",
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": "{}"}}],
        },
    )


def _orchestrator(ark: _ScriptedArk) -> AgentOrchestrator:
    tools = MagicMock()
    tools.execute.return_value = '{"tasks": []}'
    tools.created_proposal_ids = ["p1"]
    return AgentOrchestrator(
        ark, tools, language="zh-CN",
        now_local="2026-07-20T09:30", pending_summary="- [p1] create: 买菜",
    )


def test_returns_final_text_when_model_stops() -> None:
    ark = _ScriptedArk([_final("好的")])
    turn = _orchestrator(ark).run([{"role": "user", "content": "你好"}])

    assert turn.content == "好的"
    assert turn.capped is False
    assert len(ark.calls) == 1


def test_tool_loop_appends_results_and_collects_proposals() -> None:
    ark = _ScriptedArk([_tool_turn("c1", "list_tasks", {}), _final("查到 0 条任务")])
    orchestrator = _orchestrator(ark)

    turn = orchestrator.run([{"role": "user", "content": "我有哪些任务"}])

    assert turn.content == "查到 0 条任务"
    assert turn.proposal_ids == ["p1"]
    assert turn.tool_trace == [{"name": "list_tasks", "arguments": {}, "output": '{"tasks": []}'}]
    second_call_messages = ark.calls[1]
    assert second_call_messages[-1] == {
        "role": "tool", "tool_call_id": "c1", "content": '{"tasks": []}',
    }
    assert second_call_messages[-2]["tool_calls"][0]["id"] == "c1"


def test_loop_is_capped_and_returns_fallback() -> None:
    ark = _ScriptedArk(
        [_tool_turn(f"c{i}", "list_tasks", {}) for i in range(MAX_TOOL_ITERATIONS)]
    )
    turn = _orchestrator(ark).run([{"role": "user", "content": "循环"}])

    assert turn.capped is True
    assert "上限" in turn.content
    assert len(ark.calls) == MAX_TOOL_ITERATIONS


def test_system_prompt_contains_time_and_pending_summary() -> None:
    prompt = _orchestrator(_ScriptedArk([])).system_prompt()

    assert "2026-07-20T09:30" in prompt
    assert "[p1] create: 买菜" in prompt
