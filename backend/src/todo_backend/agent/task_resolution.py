from dataclasses import dataclass
from difflib import SequenceMatcher

from todo_backend.agent.planning import TargetQuery
from todo_backend.models import Task

TARGET_THRESHOLD = 0.68


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
    ranked = sorted(
        ((_score(query, task, tasks, recent_task_ids), task) for task in tasks),
        key=lambda pair: (pair[0], pair[1].created_at),
        reverse=True,
    )
    score, task = ranked[0]
    if score < threshold:
        return TargetResolution(None, score, "TASK_TARGET_AMBIGUOUS")
    return TargetResolution(task, score)
