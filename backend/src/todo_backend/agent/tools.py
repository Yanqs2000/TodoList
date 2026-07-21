import json
from typing import Any

from pydantic import ValidationError

from todo_backend.database import Database
from todo_backend.models import ProposalFields
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.reminders import ReminderRepository
from todo_backend.repositories.tasks import TaskRepository

_TASK_SUMMARY_CAP = 50

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "查询现有任务，可按完成状态、开始时间和标题关键词过滤",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "completed"],
                        "description": "完成状态过滤，默认 all",
                    },
                    "due_before": {
                        "type": "string",
                        "description": "本地时间 YYYY-MM-DDTHH:MM，只返回开始时间早于它的任务",
                    },
                    "due_after": {
                        "type": "string",
                        "description": "本地时间 YYYY-MM-DDTHH:MM，只返回开始时间晚于它的任务",
                    },
                    "search": {"type": "string", "description": "标题关键词"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task",
            "description": "读取单个任务的完整字段（含备注）",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_tasks",
            "description": "提议新建任务。只生成待用户确认的提议，不会直接创建任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "任务标题"},
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                                "category": {
                                    "type": "string",
                                    "enum": ["work", "study", "life", "other"],
                                },
                                "time_start": {
                                    "type": "string",
                                    "description": "开始时间，本地 YYYY-MM-DDTHH:MM",
                                },
                                "time_end": {
                                    "type": "string",
                                    "description": "结束时间，本地 YYYY-MM-DDTHH:MM",
                                },
                                "notes": {"type": "string"},
                            },
                            "required": ["text"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_update_task",
            "description": "提议修改现有任务字段。只生成待用户确认的提议。notes 和 time_start/time_end 设为 null 表示清除该字段；text/priority/category 必须提供值",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "changes": {
                        "type": "object",
                        "properties": {
                            "text": {"type": ["string", "null"]},
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                            },
                            "category": {
                                "type": "string",
                                "enum": ["work", "study", "life", "other"],
                            },
                            "time_start": {"type": ["string", "null"]},
                            "time_end": {"type": ["string", "null"]},
                            "notes": {"type": ["string", "null"]},
                        },
                    },
                },
                "required": ["task_id", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_delete_task",
            "description": "提议删除现有任务。只生成待用户确认的提议",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
]


class AgentTools:
    def __init__(
        self,
        database: Database,
        *,
        conversation_id: str,
        message_id: str,
        task_repository: TaskRepository | None = None,
        reminder_repository: ReminderRepository | None = None,
        conversations: ConversationsRepository | None = None,
    ) -> None:
        self._database = database
        self._conversation_id = conversation_id
        self._message_id = message_id
        self._tasks = task_repository or TaskRepository()
        self._reminders = reminder_repository or ReminderRepository()
        self._conversations = conversations or ConversationsRepository()
        self.created_proposal_ids: list[str] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        handlers = {
            "list_tasks": self._list_tasks,
            "get_task": self._get_task,
            "propose_create_tasks": self._propose_create,
            "propose_update_task": self._propose_update,
            "propose_delete_task": self._propose_delete,
        }
        handler = handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            return handler(arguments)
        except (ValidationError, ValueError, TypeError, KeyError) as error:
            return json.dumps({"error": f"invalid arguments: {type(error).__name__}"})

    def _list_tasks(self, arguments: dict[str, Any]) -> str:
        connection = self._database.connect()
        try:
            tasks = self._tasks.list_all(connection)
        finally:
            connection.close()
        status = arguments.get("status", "all")
        if status == "active":
            tasks = [t for t in tasks if not t.completed]
        elif status == "completed":
            tasks = [t for t in tasks if t.completed]
        if arguments.get("search"):
            needle = str(arguments["search"])
            tasks = [t for t in tasks if needle in t.text]
        if arguments.get("due_before"):
            bound = str(arguments["due_before"])
            tasks = [t for t in tasks if t.time and t.time.start < bound]
        if arguments.get("due_after"):
            bound = str(arguments["due_after"])
            tasks = [t for t in tasks if t.time and t.time.start > bound]
        summaries = [
            {
                "id": t.id,
                "text": t.text,
                "completed": t.completed,
                "priority": t.priority,
                "category": t.category,
                "time_start": t.time.start if t.time else None,
                "time_end": t.time.end if t.time else None,
            }
            for t in tasks[:_TASK_SUMMARY_CAP]
        ]
        return json.dumps(
            {"tasks": summaries, "truncated": len(tasks) > _TASK_SUMMARY_CAP},
            ensure_ascii=False,
        )

    def _get_task(self, arguments: dict[str, Any]) -> str:
        task_id = str(arguments["task_id"])
        connection = self._database.connect()
        try:
            tasks = {t.id: t for t in self._tasks.list_all(connection)}
        finally:
            connection.close()
        task = tasks.get(task_id)
        if task is None:
            return json.dumps({"error": "task not found"})
        return task.model_dump_json()

    def _propose_create(self, arguments: dict[str, Any]) -> str:
        items: list[Any] = arguments.get("items") or []
        if not items:
            return json.dumps({"error": "items must not be empty"})
        proposal_ids: list[str] = []
        with self._database.transaction() as connection:
            for item in items:
                fields = ProposalFields.model_validate(item)
                if fields.text is None:
                    raise ValueError("text is required")
                if fields.priority is None:
                    fields = fields.model_copy(update={"priority": "medium"})
                if fields.category is None:
                    fields = fields.model_copy(update={"category": "other"})
                proposal = self._conversations.insert_proposal(
                    connection, self._conversation_id, self._message_id,
                    "create", None, fields,
                )
                proposal_ids.append(proposal.id)
        self.created_proposal_ids.extend(proposal_ids)
        return json.dumps({"proposal_ids": proposal_ids})

    def _propose_update(self, arguments: dict[str, Any]) -> str:
        task_id = str(arguments["task_id"])
        if not self._task_exists(task_id):
            return json.dumps({"error": "task not found"})
        changes: dict[str, Any] = arguments.get("changes") or {}
        fields = ProposalFields.model_validate(changes)
        if not fields.model_fields_set:
            return json.dumps({"error": "changes must not be empty"})
        with self._database.transaction() as connection:
            proposal = self._conversations.insert_proposal(
                connection, self._conversation_id, self._message_id,
                "update", task_id, fields,
            )
        self.created_proposal_ids.append(proposal.id)
        return json.dumps({"proposal_ids": [proposal.id]})

    def _propose_delete(self, arguments: dict[str, Any]) -> str:
        task_id = str(arguments["task_id"])
        if not self._task_exists(task_id):
            return json.dumps({"error": "task not found"})
        with self._database.transaction() as connection:
            proposal = self._conversations.insert_proposal(
                connection, self._conversation_id, self._message_id,
                "delete", task_id, ProposalFields(),
            )
        self.created_proposal_ids.append(proposal.id)
        return json.dumps({"proposal_ids": [proposal.id]})

    def _task_exists(self, task_id: str) -> bool:
        connection = self._database.connect()
        try:
            return any(t.id == task_id for t in self._tasks.list_all(connection))
        finally:
            connection.close()
