from dataclasses import dataclass
from difflib import SequenceMatcher

from todo_backend.agent.planning import TargetQuery
from todo_backend.models import Task

TARGET_THRESHOLD = 0.68
TITLE_FUZZY_THRESHOLD = 0.85
AMBIGUITY_EPSILON = 0.02


@dataclass(frozen=True, slots=True)
class TargetResolution:
    task: Task | None
    score: float
    error: str | None = None


def _normalized(value: str) -> str:
    return "".join(value.casefold().split())


def _recency(task: Task, tasks: list[Task], recent_task_ids: list[str]) -> float:
    if task.id in recent_task_ids:
        return 1.0 / (recent_task_ids.index(task.id) + 1)
    ordered = sorted(tasks, key=lambda item: item.created_at, reverse=True)
    return 1.0 / (ordered.index(task) + 2)


def _score(
    query: TargetQuery, task: Task, tasks: list[Task], recent_task_ids: list[str]
) -> float:
    weighted = 0.05 * _recency(task, tasks, recent_task_ids)
    total_weight = 0.05
    if query.title:
        weighted += 0.65 * SequenceMatcher(
            None, _normalized(query.title), _normalized(task.text)
        ).ratio()
        total_weight += 0.65
    if query.time_start:
        weighted += 0.25 * float(
            task.time is not None and task.time.start == query.time_start
        )
        total_weight += 0.25
    if query.category:
        weighted += 0.05 * float(task.category == query.category)
        total_weight += 0.05
    return weighted / total_weight


def resolve_target(
    query: TargetQuery,
    tasks: list[Task],
    *,
    recent_task_ids: list[str],
    threshold: float = TARGET_THRESHOLD,
) -> TargetResolution:
    if query.referenced_task_id:
        referenced = next(
            (task for task in tasks if task.id == query.referenced_task_id), None
        )
        return (
            TargetResolution(referenced, 1.0)
            if referenced is not None
            else TargetResolution(None, 0.0, "TASK_TARGET_NOT_FOUND")
        )
    if not tasks:
        return TargetResolution(None, 0.0, "TASK_TARGET_NOT_FOUND")
    title = query.title
    if title is not None and query.time_start is None and query.category is None:
        # D4: title-only queries prefer an exact normalized match and require a
        # stricter fuzzy threshold; a miss means the target does not exist.
        normalized = _normalized(title)
        exact = [item for item in tasks if _normalized(item.text) == normalized]
        if len(exact) == 1:
            return TargetResolution(exact[0], 1.0)
        if exact:
            return TargetResolution(None, 1.0, "TASK_TARGET_AMBIGUOUS")
        effective_threshold = TITLE_FUZZY_THRESHOLD
        miss_error = "TASK_TARGET_NOT_FOUND"
    else:
        effective_threshold = threshold
        miss_error = "TASK_TARGET_AMBIGUOUS"
    ranked = sorted(
        ((_score(query, task, tasks, recent_task_ids), task) for task in tasks),
        key=lambda pair: (pair[0], pair[1].created_at),
        reverse=True,
    )
    score, task = ranked[0]
    if score < effective_threshold:
        return TargetResolution(None, score, miss_error)
    if len(ranked) > 1:
        # D6: multiple candidates clearing the threshold within epsilon are
        # indistinguishable (e.g. same title and time) and must be clarified.
        second_score = ranked[1][0]
        if second_score >= effective_threshold and score - second_score < AMBIGUITY_EPSILON:
            return TargetResolution(None, score, "TASK_TARGET_AMBIGUOUS")
    return TargetResolution(task, score)
