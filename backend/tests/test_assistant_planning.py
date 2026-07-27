# pyright: reportUnknownArgumentType=false

import json
from typing import Any

import pytest
from pydantic import ValidationError

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.agent.planning import (
    SUBMIT_PLAN_TOOL,
    ArkPlanner,
    IntentPlan,
    PlannedMutation,
    PlanValidationError,
    TargetQuery,
)
from todo_backend.models import PlannedFields


class ScriptedPlanner:
    def __init__(
        self,
        plans: list[dict[str, Any]] | None = None,
        chat_results: list[ArkChatResult] | None = None,
    ) -> None:
        self._plans = list(plans) if plans else []
        self._chat_results = list(chat_results) if chat_results else []
        self.calls: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def plan(
        self,
        messages: list[dict[str, Any]],
        submit_plan_tool: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((messages, submit_plan_tool))
        return self._plans.pop(0)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: str = "disabled",
    ) -> ArkChatResult:
        return self._chat_results.pop(0)


def test_planner_fields_allow_end_only_before_overlay() -> None:
    fields = PlannedFields(time_end="2026-07-22T17:00")

    assert fields.model_fields_set == {"time_end"}


def test_update_requires_target_and_non_empty_changes() -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate(
            {
                "kind": "mutations",
                "evidence": "改一下",
                "items": [{"action": "update", "fields": {}}],
            }
        )


@pytest.mark.parametrize(
    "item",
    [
        {"action": "create", "fields": {}},
        {
            "action": "create",
            "target_query": {"title": "旧任务"},
            "fields": {"text": "新任务"},
        },
        {
            "action": "create",
            "reference": "proposal-1",
            "fields": {"text": "新任务"},
        },
        {"action": "delete", "target_query": {"title": "任务"}, "fields": {"notes": None}},
        {
            "action": "update",
            "target_query": {"title": "任务"},
            "reference": "proposal-1",
            "fields": {"text": "新标题"},
        },
    ],
)
def test_mutation_shape_rejects_invalid_action_specific_fields(
    item: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate(
            {"kind": "mutations", "evidence": "请求", "items": [item]}
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "query", "evidence": "查看", "query": "任务", "unexpected": True},
        {
            "kind": "mutations",
            "evidence": "添加任务",
            "items": [{"action": "create", "fields": {"text": 1}}],
        },
        {
            "kind": "mutations",
            "evidence": "删除任务",
            "items": [{"action": "delete", "target_query": {"title": "任务", "extra": 1}}],
        },
    ],
)
def test_plan_models_are_strict_and_forbid_extra_fields(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate(payload)


def test_target_query_requires_a_selector() -> None:
    with pytest.raises(ValidationError):
        TargetQuery()


def test_pending_reference_is_an_alternative_to_real_task_target() -> None:
    plan = IntentPlan(
        kind="mutations",
        evidence="把刚才那个改成四点",
        items=[
            PlannedMutation(
                action="update",
                reference="proposal-7",
                fields=PlannedFields(time_start="2026-07-22T16:00"),
            )
        ],
    )

    assert plan.items[0].reference == "proposal-7"
    assert plan.items[0].target_query is None


def test_query_rejects_mutation_items() -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate(
            {
                "kind": "query",
                "evidence": "查看",
                "query": "查看任务",
                "items": [{"action": "create", "fields": {"text": "x"}}],
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "query", "evidence": "查看"},
        {"kind": "mutations", "evidence": "新建", "query": "新建任务", "items": []},
        {"kind": "mutations", "evidence": "新建", "items": []},
    ],
)
def test_plan_kind_requires_its_own_shape(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        IntentPlan.model_validate(payload)


def test_plan_once_returns_one_stable_schema_validation_error() -> None:
    ark = ScriptedPlanner(
        [{"kind": "mutations", "evidence": "新建任务", "items": []}]
    )
    planner = ArkPlanner(ark)

    with pytest.raises(PlanValidationError) as raised:
        planner.plan_once("新建任务", [], validation_code=None)

    assert raised.value.code == "INVALID_PLAN_SCHEMA"
    assert ark.call_count == 1


def test_submit_plan_tool_uses_the_strict_intent_schema() -> None:
    function = SUBMIT_PLAN_TOOL["function"]

    assert function["name"] == "submit_plan"
    assert function["parameters"] == IntentPlan.model_json_schema()
    assert function["parameters"]["additionalProperties"] is False


def test_planner_prompt_defines_reference_and_card_confirmation_policy() -> None:
    ark = ScriptedPlanner(
        [{"kind": "query", "evidence": "查看任务", "query": "查看任务"}]
    )

    ArkPlanner(ark).plan_once(
        "查看任务", [{"role": "user", "content": "查看任务"}], validation_code=None
    )

    messages, tool = ark.calls[0]
    prompt = messages[0]["content"]
    assert "exact pending proposal ID" in prompt
    assert "never copy a phrase such as" in prompt
    assert tool is SUBMIT_PLAN_TOOL


def test_planner_prompt_covers_midnight_ambiguity_and_capability_boundary() -> None:
    ark = ScriptedPlanner(
        [{"kind": "query", "evidence": "查看任务", "query": "查看任务"}]
    )

    ArkPlanner(ark).plan_once(
        "查看任务", [{"role": "user", "content": "查看任务"}], validation_code=None
    )

    prompt = ark.calls[0][0][0]["content"]
    # D7：日期边界歧义必须澄清
    assert "晚上12点" in prompt
    assert "kind=query" in prompt
    # D8：能力边界说明（更新为正面清单）
    assert "YOU CANNOT do these" in prompt
    assert "completed" in prompt


def test_repair_prompt_contains_only_code_and_original_request() -> None:
    ark = ScriptedPlanner(
        [{"kind": "query", "evidence": "查看任务", "query": "查看任务"}]
    )

    ArkPlanner(ark).plan_once(
        "查看任务",
        [{"role": "user", "content": "查看任务"}],
        validation_code="INVALID_PLAN_SCHEMA",
    )

    messages, _ = ark.calls[0]
    assert messages[-1] == {
        "role": "user",
        "content": (
            "Return one corrected plan.\n"
            "Failure context:\n"
            "INVALID_PLAN_SCHEMA\n\n"
            "Original user request: 查看任务"
        ),
    }
    assert ark.call_count == 1


def test_analyze_returns_clarify_for_vague_input() -> None:
    from todo_backend.agent.ark_client import ArkToolCall
    ark = ScriptedPlanner(
        chat_results=[
            ArkChatResult(
                content="",
                tool_calls=[
                    ArkToolCall(
                        id="call_1",
                        name="submit_analysis",
                        arguments={
                            "intent": "clarify",
                            "reasoning": "用户说'几个'，数量不明确",
                            "missing_info": "请问您需要创建几个任务？",
                        },
                    )
                ],
            )
        ]
    )
    planner = ArkPlanner(ark)
    result = planner.analyze("新建几个任务", [{"role": "user", "content": "新建几个任务"}])
    assert result.intent == "clarify"
    assert result.reasoning == "用户说'几个'，数量不明确"
    assert result.missing_info == "请问您需要创建几个任务？"


def test_analyze_returns_mutations_for_clear_create() -> None:
    from todo_backend.agent.ark_client import ArkToolCall
    ark = ScriptedPlanner(
        chat_results=[
            ArkChatResult(
                content="",
                tool_calls=[
                    ArkToolCall(
                        id="call_1",
                        name="submit_analysis",
                        arguments={
                            "intent": "mutations",
                            "reasoning": "用户明确要求创建任务，标题清晰",
                            "missing_info": None,
                        },
                    )
                ],
            )
        ]
    )
    planner = ArkPlanner(ark)
    result = planner.analyze("新建买菜任务", [{"role": "user", "content": "新建买菜任务"}])
    assert result.intent == "mutations"
    assert result.reasoning == "用户明确要求创建任务，标题清晰"
    assert result.missing_info is None


def test_analyze_fallback_clarify_on_parse_failure() -> None:
    ark = ScriptedPlanner(
        chat_results=[
            ArkChatResult(content="not valid json{{{")
        ]
    )
    planner = ArkPlanner(ark)
    result = planner.analyze("随便说点啥", [{"role": "user", "content": "随便说点啥"}])
    assert result.intent == "clarify"
    assert "parse failure" in result.reasoning
