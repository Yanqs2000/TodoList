import re
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

_ACTION_MARKERS: dict[ProposalAction, tuple[str, ...]] = {
    "create": (
        r"\b(?:add|create|new)\b",
        r"(?:新建|创建|添加|新增|记一个|加一个|加个)",
    ),
    "update": (
        r"\b(?:update|change|move|rename|edit|reschedule|postpone)\b",
        r"(?:修改|改成|改到|改为|改一下|改现有的|更改|"
        r"调整|推迟|提前|重新安排)",
    ),
    "delete": (r"\b(?:delete|remove)\b", r"(?:删除|删掉|移除|取消任务)"),
}

_NEGATED_ACTION = re.compile(
    r"(?:不要|别|无需)\s*(?:新建|创建|添加|新增|加一个|加个|修改|改成|改到|"
    r"改为|改一下|改现有的|更改|调整|删除|删掉|移除)|(?:do\s+not|don't)\s+"
    r"(?:add|create|update|change|move|rename|edit|reschedule|delete|remove)",
    flags=re.IGNORECASE,
)
_QUERY_LIKE = re.compile(
    r"(?:如何|怎么|哪些|是否|有没有|\b(?:how|what|which|whether)\b)",
    flags=re.IGNORECASE,
)
_IMPERATIVE = re.compile(r"(?:请(?!问)|帮我|麻烦|\bplease\b)", flags=re.IGNORECASE)

_PLANNER_SYSTEM_PROMPT = """You are the structured intent planner for TodoList.
Submit exactly one plan through submit_plan and never perform a write operation.
Use kind=query with a non-empty query and no items for read-only requests.
Use kind=mutations with one item per requested mutation and no query text.
Each item must keep the action explicitly requested by the user.
Create requires a title in fields.text and has no target or reference.
Update and delete require either target_query for a real task or reference for a pending card.
A reference is the exact pending proposal ID copied from the supplied pending context.
For reference, never copy a phrase such as “刚才那个” as the value.
Cards are the only confirmation. The planner must not ask for confirmation in evidence or query.
Evidence must identify the user's wording that supports the plan."""


class _ArkPlanner(Protocol):
    def plan(
        self,
        messages: list[dict[str, Any]],
        submit_plan_tool: dict[str, Any],
    ) -> dict[str, Any]: ...


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
                        f"Validation code: {validation_code}\n"
                        f"Original user request: {user_text}"
                    ),
                }
            )

        raw_plan = self._ark.plan(planning_messages, SUBMIT_PLAN_TOOL)
        try:
            plan = IntentPlan.model_validate(raw_plan)
        except ValidationError as error:
            raise PlanValidationError("INVALID_PLAN_SCHEMA") from error
        try:
            validate_explicit_actions(user_text, plan)
        except PlanPolicyError as error:
            raise PlanValidationError(str(error)) from error
        return plan


def explicit_actions(text: str) -> set[ProposalAction]:
    sanitized = _NEGATED_ACTION.sub("", text)
    return {
        action
        for action, patterns in _ACTION_MARKERS.items()
        if any(re.search(pattern, sanitized, flags=re.IGNORECASE) for pattern in patterns)
    }


def validate_explicit_actions(text: str, plan: IntentPlan) -> None:
    if _QUERY_LIKE.search(text) and not _IMPERATIVE.search(text):
        if plan.kind != "query":
            raise PlanPolicyError("EXPLICIT_ACTION_MISMATCH")
        return
    expected = explicit_actions(text)
    planned = {item.action for item in plan.items}
    if expected and (plan.kind != "mutations" or planned != expected):
        raise PlanPolicyError("EXPLICIT_ACTION_MISMATCH")
