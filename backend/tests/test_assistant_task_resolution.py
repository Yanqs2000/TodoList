import pytest
from pydantic import ValidationError

from todo_backend.agent.planning import TargetQuery
from todo_backend.agent.task_resolution import (
    TARGET_THRESHOLD,
    TITLE_FUZZY_THRESHOLD,
    resolve_target,
)
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


def test_duplicate_titles_require_clarification() -> None:
    older, newer = task("old", "团队会议", 1), task("new", "团队会议", 2)

    result = resolve_target(
        TargetQuery(title="团队会议"), [older, newer], recent_task_ids=[]
    )

    assert result.task is None
    assert result.error == "TASK_TARGET_AMBIGUOUS"


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


def test_low_similarity_title_only_is_not_found() -> None:
    result = resolve_target(
        TargetQuery(title="季度财务复盘"),
        [task("a", "买菜", 1), task("b", "晨跑", 2)],
        recent_task_ids=[],
    )

    assert result.task is None
    assert result.score < TITLE_FUZZY_THRESHOLD
    assert result.error == "TASK_TARGET_NOT_FOUND"


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


def test_title_only_similar_title_is_not_found() -> None:
    """D4/DEL-005：删除不存在的“火星会议”不得误指向“地球会议”。"""
    result = resolve_target(
        TargetQuery(title="火星会议"),
        [task("a", "地球会议", 1)],
        recent_task_ids=[],
    )

    assert result.task is None
    assert result.error == "TASK_TARGET_NOT_FOUND"


def test_title_only_exact_match_ignores_case_and_whitespace() -> None:
    """D4 回归：归一化（casefold、去空白）后精确命中直接返回。"""
    expected = task("a", "整理发票", 1)

    result = resolve_target(
        TargetQuery(title="整理 发票"), [expected], recent_task_ids=[]
    )

    assert result.task == expected
    assert result.error is None
    assert result.score == 1.0


def test_title_only_typo_below_strict_threshold_is_not_found() -> None:
    """D4：仅标题模糊匹配需越过更高门槛（0.75 相似 < 0.85）。"""
    result = resolve_target(
        TargetQuery(title="整理发漂"),
        [task("a", "整理发票", 1)],
        recent_task_ids=[],
    )

    assert result.task is None
    assert result.score < TITLE_FUZZY_THRESHOLD
    assert result.error == "TASK_TARGET_NOT_FOUND"


def test_same_title_same_time_requires_clarification() -> None:
    """D6/UPD-008：同名同时间双候选必须澄清而非猜测。"""
    older = task("old", "同步会", 1, start="2026-07-23T10:00")
    newer = task("new", "同步会", 2, start="2026-07-23T10:00")

    result = resolve_target(
        TargetQuery(title="同步会"), [older, newer], recent_task_ids=[]
    )

    assert result.task is None
    assert result.error == "TASK_TARGET_AMBIGUOUS"


def test_same_title_different_time_with_time_start_hits_unique() -> None:
    """D6 回归：同名不同时间，附加正确 time_start 时唯一命中。"""
    morning = task("a", "项目会", 2, start="2026-07-23T10:00")
    expected = task("b", "项目会", 1, start="2026-07-23T16:00")

    result = resolve_target(
        TargetQuery(title="项目会", time_start="2026-07-23T16:00"),
        [morning, expected],
        recent_task_ids=[],
    )

    assert result.task == expected
    assert result.error is None


def test_single_task_title_hit_is_unaffected() -> None:
    """D6 回归：单条任务的正常标题命中不受歧义检查影响。"""
    expected = task("a", "买菜", 1)

    result = resolve_target(
        TargetQuery(title="买菜"), [expected], recent_task_ids=[]
    )

    assert result.task == expected
    assert result.error is None
