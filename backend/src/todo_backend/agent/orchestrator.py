from dataclasses import dataclass, field
from typing import Any, Protocol

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.agent.tools import TOOL_SCHEMAS, AgentTools

MAX_TOOL_ITERATIONS = 8
HISTORY_LIMIT = 20

_SYSTEM_PROMPTS = {
    "zh-CN": (
        "你是 TodoList 应用的待办助手。当前本地时间：{now}。\n"
        "规则：\n"
        "1. 创建、修改或删除任务时，必须调用对应的 propose_ 工具生成提议，"
        "不要声称已直接执行。\n"
        "2. 所有时间使用本地时间，格式 YYYY-MM-DDTHH:MM。\n"
        "3. 使用与用户最近一条消息相同的语言回复。\n"
        "4. 需要了解现有任务时，先调用 list_tasks 查询。\n"
        "当前待用户确认的提议：\n{pending}"
    ),
    "en": (
        "You are the todo assistant inside the TodoList app. Current local time: {now}.\n"
        "Rules:\n"
        "1. To create, update, or delete tasks you MUST call the matching propose_ tool; "
        "never claim you did it directly.\n"
        "2. All times are local, formatted YYYY-MM-DDTHH:MM.\n"
        "3. Reply in the language of the user's latest message.\n"
        "4. Call list_tasks first whenever you need existing tasks.\n"
        "Proposals awaiting user confirmation:\n{pending}"
    ),
}

_FALLBACK = {
    "zh-CN": "分析过程超出了处理上限，请换个方式描述需求。",
    "en": "The analysis exceeded the processing limit. Please rephrase your request.",
}


class _Ark(Protocol):
    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ArkChatResult: ...


@dataclass(frozen=True)
class AgentTurn:
    content: str
    proposal_ids: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    tool_trace: list[dict[str, Any]] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    capped: bool = False


class AgentOrchestrator:
    def __init__(
        self,
        ark: _Ark,
        tools: AgentTools,
        *,
        language: str,
        now_local: str,
        pending_summary: str,
    ) -> None:
        self._ark = ark
        self._tools = tools
        self._language = language
        self._now_local = now_local
        self._pending_summary = pending_summary

    def system_prompt(self) -> str:
        template = _SYSTEM_PROMPTS.get(self._language, _SYSTEM_PROMPTS["en"])
        return template.format(now=self._now_local, pending=self._pending_summary or "无")

    def run(self, messages: list[dict[str, Any]]) -> AgentTurn:
        trace: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ITERATIONS):
            result = self._ark.chat(messages, tools=TOOL_SCHEMAS)
            if not result.tool_calls:
                return AgentTurn(
                    content=result.content,
                    proposal_ids=list(self._tools.created_proposal_ids),
                    tool_trace=trace,
                )
            messages.append(result.raw_message)
            for call in result.tool_calls:
                output = self._tools.execute(call.name, call.arguments)
                trace.append(
                    {"name": call.name, "arguments": call.arguments, "output": output}
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": output}
                )
        return AgentTurn(
            content=_FALLBACK.get(self._language, _FALLBACK["en"]),
            proposal_ids=list(self._tools.created_proposal_ids),
            tool_trace=trace,
            capped=True,
        )
