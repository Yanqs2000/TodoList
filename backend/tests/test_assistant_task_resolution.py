import pytest
from pydantic import ValidationError

from todo_backend.agent.planning import TargetQuery
from todo_backend.agent.task_resolution import TARGET_THRESHOLD, resolve_target
from todo_backend.models import Category, LocalDateTime, Task, TimeField


def task(
    task_id: str,
    text: str,
    created_at: int,
    *,
    start: LocalDateTime | None = None,
    category: Category = "other",
) -> Task:
    return Task(
        id=task_id,
        text=text,
        completed=False,
        priority="medium",
        createdAt=created_at,
        time=TimeField(start=start) if start is not None else None,
        category=category,
    )


def test_exact_reference_wins_when_real_task_exists() -> None:
    older, newer = task("old", "会议", 1), task("new", "会议", 2)

    result = resolve_target(
        TargetQuery(referenced_task_id="old"), [newer, older], recent_task_ids=["new"]
    )

    assert result.task == older
    assert result.score == 1.0
    assert result.error is None


def test_pending_or_missing_reference_is_not_a_real_task() -> None:
    real_task = task("task-1", "会议", 1)

    result = resolve_target(
        TargetQuery(referenced_task_id="proposal-pending"),
        [real_task],
        recent_task_ids=["proposal-pending"],
    )

    assert result.task is None
    assert result.score == 0.0
    assert result.error == "TASK_TARGET_NOT_FOUND"


def test_duplicate_titles_choose_most_recent_task() -> None:
    older, newer = task("old", "团队会议", 1), task("new", "团队会议", 2)

    result = resolve_target(
        TargetQuery(title="团队会议"), [older, newer], recent_task_ids=[]
    )

    assert result.task == newer
    assert result.score >= TARGET_THRESHOLD


def test_title_time_and_category_choose_best_candidate() -> None:
    wrong_time = task(
        "a", "项目会议", 2, start="2026-07-22T10:00", category="work"
    )
    expected = task(
        "b", "项目会议", 1, start="2026-07-22T16:00", category="work"
    )

    result = resolve_target(
        TargetQuery(
            title="项目会议", time_start="2026-07-22T16:00", category="work"
        ),
        [wrong_time, expected],
        recent_task_ids=[],
    )

    assert result.task == expected


def test_exact_time_tie_is_broken_by_recent_context() -> None:
    older = task("old", "早期会议", 1, start="2026-07-22T16:00")
    newer = task("new", "最新会议", 2, start="2026-07-22T16:00")

    result = resolve_target(
        TargetQuery(time_start="2026-07-22T16:00"),
        [older, newer],
        recent_task_ids=["old"],
    )

    assert result.task == older
    assert result.score >= TARGET_THRESHOLD


def test_low_similarity_requires_clarification() -> None:
    result = resolve_target(
        TargetQuery(title="季度财务复盘"),
        [task("a", "买菜", 1), task("b", "晨跑", 2)],
        recent_task_ids=[],
    )

    assert result.task is None
    assert result.score < TARGET_THRESHOLD
    assert result.error == "TASK_TARGET_AMBIGUOUS"


def test_empty_task_list_returns_not_found() -> None:
    result = resolve_target(
        TargetQuery(title="会议"), [], recent_task_ids=[]
    )

    assert result.task is None
    assert result.score == 0.0
    assert result.error == "TASK_TARGET_NOT_FOUND"


def test_category_alone_is_not_a_target_selector() -> None:
    with pytest.raises(
        ValidationError,
        match="target query requires title, time, or a real referenced task",
    ):
        TargetQuery(category="work")
