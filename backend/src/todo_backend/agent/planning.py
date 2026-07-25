from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from todo_backend.models import Category, LocalDateTime, PlannedFields, ProposalAction

PlanKind = Literal["query", "mutations"]


class PlanPolicyError(ValueError):
    pass


class PlanValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TargetQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str | None = None
    time_start: LocalDateTime | None = None
    category: Category | None = None
    referenced_task_id: str | None = None

    @model_validator(mode="after")
    def require_one_selector(self) -> "TargetQuery":
        if not any((self.title, self.time_start, self.referenced_task_id)):
            raise ValueError("target query requires title, time, or a real referenced task")
        return self


class PlannedMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: ProposalAction
    target_query: TargetQuery | None = None
    fields: PlannedFields = Field(default_factory=PlannedFields)
    reference: str | None = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: Literal["query", "clarify", "mutations", "chat"]
    reasoning: str  # Why this intent? What's ambiguous? What's clear?
    missing_info: str | None = None  # What the model needs to ask the user


class IntentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: PlanKind
    evidence: str
    query: str | None = None
    items: list[PlannedMutation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> "IntentPlan":
        if self.kind == "query" and (self.items or not self.query):
            raise ValueError("query requires query text and no mutations")
        if self.kind == "mutations" and not self.items:
            raise ValueError("mutation plan requires items")
        if self.kind == "mutations" and self.query is not None:
            raise ValueError("mutation plan cannot contain query text")
        for item in self.items:
            if item.action == "create":
                if (
                    item.target_query is not None
                    or item.reference is not None
                    or not item.fields.text
                ):
                    raise ValueError("create requires text and no target")
            elif item.target_query is None and item.reference is None:
                raise ValueError("update/delete require a target or pending reference")
            if item.target_query is not None and item.reference is not None:
                raise ValueError("mutation target must be unambiguous")
            if item.action == "update" and not item.fields.model_fields_set:
                raise ValueError("update requires changes")
            if item.action == "delete" and item.fields.model_fields_set:
                raise ValueError("delete cannot change fields")
        return self


SUBMIT_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "提交唯一的结构化待办意图计划，不执行写操作",
        "parameters": IntentPlan.model_json_schema(),
    },
}

ANALYZE_PROMPT = """You analyze user messages for a TodoList agent. Output one AnalysisResult.

Intent types:
- "query": The user is asking a factual question about their tasks (what tasks do I have? when is X?).
- "chat": The user is making casual conversation or asking a question that is NOT about
  their todo list (e.g. "你是什么模型", "今天天气怎么样", "讲个笑话", "你好").
  Use this for greetings, chit-chat, questions about the assistant itself, or any
  message that does NOT ask about or modify tasks.
- "clarify": The user's request is incomplete, ambiguous, or needs more info.
  Use this when: the task title is missing (for creates), quantities are vague
  ("几个","一些"), dates are impossible (Feb 29 non-leap-year), time is already
  past, date format is ambiguous (08/09 could be Aug 9 or Sep 8), target cannot
  be uniquely identified among the existing tasks, or there are multiple candidates.
  NOTE: time/date is optional for creates — do NOT clarify just because the user
  didn't specify a time. The user can add a time later via update.

  ⚠️  IMPORTANT — when you use "clarify", write missing_info as ONE specific,
  friendly, conversational question. Like a real person asking for clarification.
  Be warm and natural, NOT robotic or formal. Examples:
  - BAD: "请提供更多信息"  GOOD: "你是想创建「英语课」还是「数学课」呀？"
  - BAD: "请指定任务标题"  GOOD: "好的，这个任务你想叫什么名字呢？"
  - BAD: "日期格式不明确"  GOOD: "你指的8/9是8月9号还是9月8号呀？"

- "mutations": The user clearly requests create/update/delete of tasks with enough info.

⚠️  FOLLOW-UP RESPONSES — If the conversation history shows that the assistant JUST
asked a clarification question and the user's current message is responding to it:
re-evaluate the FULL context (original request + clarification answer). Be more
aggressive about finding a match. If the combined information now makes the intent
clear, use "mutations" directly. Do NOT keep asking follow-up clarifications
unless there's genuinely new ambiguity.

IMPORTANT: Only use "query" or "mutations" when the message is genuinely about the
user's todo tasks. Greetings, small talk, and off-topic questions should use "chat".
Messages like "你好", "谢谢", "你是谁", "你是什么模型" → "chat".

Capabilities — you CAN do ALL of these:
- CREATE a new task (needs title; time/priority/category are optional)
- UPDATE an existing task's text, time, priority, category, or notes
- DELETE an existing task
The only things you CANNOT do: mark tasks as completed, set location, add participants,
or set reminder lead time.

Rules:
- For creates where the task title is present, use "mutations".
- For updates/deletes: look at the EXISTING TASKS list. If the user references a task
  that exists (by title, time, or context), use "mutations" to update/delete it.
  The confirmation card IS the confirmation — do NOT use "clarify" to double-check.
- When the user says "换成7点" or "改到明天" or "改成高优先级" about a recently
  discussed task, that IS an update — use "mutations", not "clarify".
- Use "clarify" only when: title is missing, target truly cannot be identified,
  time is impossible or already past, quantities are vague, or genuine ambiguity.
- When in doubt between clarify and mutations, prefer "mutations" if any task in
  the existing tasks list plausibly matches what the user is referring to.
- CRITICAL — confirmation words: When the user sends a standalone confirmation word
  like "确认", "好的", "行", "可以", "ok", "yes", "sure", "confirm", "reject", "拒绝"
  and the conversation context shows pending proposal cards: use "clarify" and tell
  the user to click the 确认/拒绝 buttons on the card itself. Do NOT classify as
  "mutations" — the text channel cannot confirm or reject proposals."""


_PLANNER_SYSTEM_PROMPT = """You are the structured intent planner for TodoList.
Submit exactly one plan through submit_plan and never perform a write operation.
Use kind=mutations with one item per requested mutation and no query text.
Each item must keep the action explicitly requested by the user.

YOU CAN DO ALL OF THESE:
- action="create": requires fields.text (title), no target_query or reference.
  time/priority/category/notes are optional.
- action="update": requires target_query (to find the existing task) OR reference
  (pending proposal ID). Supply only the fields that should change in PlannedFields.
  You CAN update: text, time_start, time_end, priority, category, notes.
- action="delete": requires target_query or reference. No fields needed.

CATEGORY — always infer and set category on every create. Never leave it null.
Choose the single best fit from the four values below:
- "work":    job duties, meetings, projects, deadlines, clients, business.
             Keywords: 工作 上班 开会 项目 报告 客户 出差 面试 加班 合同 预算
- "study":   learning, classes, courses, homework, exams, reading, training.
             Keywords: 学习 上课 作业 考试 读书 课程 培训 论文 笔记 英语课 数学
- "life":    daily chores, shopping, health, family, social, entertainment.
             Keywords: 购物 买菜 健身 家务 看病 聚会 旅行 电影 做饭 缴费 搬家
- "other":   only when the task genuinely does not fit work / study / life.

Infer the category from the task title and the user's wording. Examples:
"英语课" → study, "项目周会" → work, "买菜" → life, "修水管" → life,
"背单词" → study, "写周报" → work, "去医院复查" → life, "交论文" → study.

A reference is the exact pending proposal ID copied from the supplied pending context.
For reference, never copy a phrase such as "刚才那个" as the value.

When the user says "换成7点", "改到明天", "改成高优先级" about a task — that is an
UPDATE. Find the task via target_query (by title or time) and use action="update".

When relative time expressions resolve to a time_start already in the past (< current time),
use kind=query to ask the user whether they want today or a future date.
Evidence must identify the user's wording that supports the plan.
Date-boundary expressions such as "晚上12点/午夜/夜里12点/凌晨" are ambiguous: use kind=query.

YOU CANNOT do these: mark tasks as completed, set location, add participants,
set reminder lead time. When asked for these, use kind=query to explain the limit."""


class _ArkPlanner(Protocol):
    def plan(
        self,
        messages: list[dict[str, Any]],
        submit_plan_tool: dict[str, Any],
    ) -> dict[str, Any]: ...
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: Literal["enabled", "disabled"] = "disabled",
    ) -> Any: ...


class ArkPlanner:
    def __init__(self, ark: _ArkPlanner) -> None:
        self._ark = ark

    def plan_once(
        self,
        user_text: str,
        messages: list[dict[str, Any]],
        validation_code: str | None,
    ) -> IntentPlan:
        planning_messages = [
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            *messages,
        ]
        if validation_code is not None:
            planning_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Return one corrected plan.\n"
                        f"Failure context:\n{validation_code}\n\n"
                        f"Original user request: {user_text}"
                    ),
                }
            )

        raw_plan = self._ark.plan(planning_messages, SUBMIT_PLAN_TOOL)
        try:
            plan = IntentPlan.model_validate(raw_plan)
        except ValidationError as error:
            raise PlanValidationError("INVALID_PLAN_SCHEMA") from error
        return plan

    def analyze(self, user_text: str, messages: list[dict[str, Any]]) -> AnalysisResult:
        tool = {
            "type": "function",
            "function": {
                "name": "submit_analysis",
                "description": "提交意图分析结果",
                "parameters": AnalysisResult.model_json_schema(),
            },
        }
        choice = {"type": "function", "function": {"name": "submit_analysis"}}
        from todo_backend.agent.ark_client import ArkUnavailableError
        try:
            result = self._ark.chat(
                [{"role": "system", "content": ANALYZE_PROMPT}, *messages[-10:],
                 {"role": "user", "content": user_text}],
                tools=[tool],
                tool_choice=choice,
                thinking="disabled",
            )
        except ArkUnavailableError:
            raise
        except Exception:
            return _default_analysis()
        if len(result.tool_calls) != 1 or result.tool_calls[0].name != "submit_analysis":
            return _default_analysis()
        arguments = result.tool_calls[0].arguments
        if not isinstance(arguments, dict):
            return _default_analysis()
        from pydantic import ValidationError
        try:
            return AnalysisResult.model_validate(arguments)
        except ValidationError:
            return _default_analysis()


def _default_analysis() -> AnalysisResult:
    return AnalysisResult(intent="clarify", reasoning="analysis parse failure", missing_info="请问您需要什么帮助？")
