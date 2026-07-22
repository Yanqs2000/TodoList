# pyright: reportUnknownArgumentType=false

from typing import Any

import pytest
from pydantic import ValidationError

from todo_backend.agent.planning import (
    SUBMIT_PLAN_TOOL,
    ArkPlanner,
    IntentPlan,
    PlannedMutation,
    PlanPolicyError,
    PlanValidationError,
    TargetQuery,
    explicit_actions,
    validate_explicit_actions,
)
from todo_backend.models import PlannedFields, ProposalAction


class ScriptedPlanner:
    def __init__(self, plans: list[dict[str, Any]]) -> None:
        self._plans = list(plans)
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


def test_planner_fields_allow_end_only_before_overlay() -> None:
    fields = PlannedFields(time_end="2026-07-22T17:00")

    assert fields.model_fields_set == {"time_end"}


@pytest.mark.parametrize("text", ["新建一个会议", "添加买菜任务", "add a task"])
def test_explicit_create_cannot_be_planned_as_update(text: str) -> None:
    plan = IntentPlan.model_validate(
        {
            "kind": "mutations",
            "evidence": text,
            "items": [
                {
                    "action": "update",
                    "target_query": {"title": "会议"},
                    "fields": {"text": "会议"},
                }
            ],
        }
    )

    with pytest.raises(PlanPolicyError, match="EXPLICIT_ACTION_MISMATCH"):
        validate_explicit_actions(text, plan)


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


def test_plan_once_returns_stable_policy_error_without_retrying() -> None:
    ark = ScriptedPlanner(
        [
            {
                "kind": "mutations",
                "evidence": "新建任务",
                "items": [
                    {
                        "action": "update",
                        "target_query": {"title": "任务"},
                        "fields": {"text": "任务"},
                    }
                ],
            }
        ]
    )

    with pytest.raises(PlanValidationError) as raised:
        ArkPlanner(ark).plan_once("新建任务", [], validation_code=None)

    assert raised.value.code == "EXPLICIT_ACTION_MISMATCH"
    assert ark.call_count == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("把会议改为四点", {"update"}),
        ("更改会议时间", {"update"}),
        ("加一个买菜任务", {"create"}),
        ("reschedule the meeting", {"update"}),
        ("不要删除会议，只修改时间", {"update"}),
        ("不要新建，改现有的", {"update"}),
        ("don't delete it; update the time", {"update"}),
    ],
)
def test_explicit_action_corpus_and_negation(
    text: str, expected: set[ProposalAction]
) -> None:
    assert explicit_actions(text) == expected


def test_multiple_explicit_actions_must_match_the_complete_planned_set() -> None:
    plan = IntentPlan(
        kind="mutations",
        evidence="新建会议并修改旧会议",
        items=[PlannedMutation(action="create", fields=PlannedFields(text="会议"))],
    )

    with pytest.raises(PlanPolicyError, match="EXPLICIT_ACTION_MISMATCH"):
        validate_explicit_actions("新建会议并修改旧会议", plan)


def test_unrequested_action_cannot_be_added_to_a_multi_action_plan() -> None:
    plan = IntentPlan(
        kind="mutations",
        evidence="新建会议并修改旧会议",
        items=[
            PlannedMutation(action="create", fields=PlannedFields(text="会议")),
            PlannedMutation(
                action="update",
                target_query=TargetQuery(title="旧会议"),
                fields=PlannedFields(text="新会议"),
            ),
            PlannedMutation(action="delete", target_query=TargetQuery(title="临时任务")),
        ],
    )

    with pytest.raises(PlanPolicyError, match="EXPLICIT_ACTION_MISMATCH"):
        validate_explicit_actions("新建会议并修改旧会议", plan)


@pytest.mark.parametrize("text", ["如何删除任务", "请问如何删除任务"])
def test_how_to_delete_is_query_not_delete_command(text: str) -> None:
    plan = IntentPlan(
        kind="mutations",
        evidence=text,
        items=[
            PlannedMutation(action="delete", target_query=TargetQuery(title="任务"))
        ],
    )

    with pytest.raises(PlanPolicyError, match="EXPLICIT_ACTION_MISMATCH"):
        validate_explicit_actions(text, plan)


def test_imperative_with_question_word_can_remain_a_mutation() -> None:
    plan = IntentPlan(
        kind="mutations",
        evidence="请帮我删除任务",
        items=[
            PlannedMutation(action="delete", target_query=TargetQuery(title="任务"))
        ],
    )

    validate_explicit_actions("请帮我删除任务", plan)


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
    assert "Cards are the only confirmation" in prompt
    assert "must not ask for confirmation" in prompt
    assert tool is SUBMIT_PLAN_TOOL


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
            "Validation code: INVALID_PLAN_SCHEMA\n"
            "Original user request: 查看任务"
        ),
    }
    assert ark.call_count == 1
