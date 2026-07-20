# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import json
from pathlib import Path

import pytest

from todo_backend.agent.tools import TOOL_SCHEMAS, AgentTools
from todo_backend.database import Database
from todo_backend.models import CreateTaskCommand
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.tasks import TaskRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations")
    db.initialize()
    return db


@pytest.fixture
def seeded(database: Database) -> tuple[str, str]:
    conversations = ConversationsRepository()
    with database.transaction() as connection:
        conversation = conversations.create_conversation(connection, "测试")
        message = conversations.insert_message(
            connection, conversation.id, "assistant", "", [], status="pending"
        )
    return conversation.id, message.id


def _tools(database: Database, conversation_id: str, message_id: str) -> AgentTools:
    return AgentTools(database, conversation_id=conversation_id, message_id=message_id)


def test_tool_schemas_cover_five_tools() -> None:
    names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert names == {
        "list_tasks",
        "get_task",
        "propose_create_tasks",
        "propose_update_task",
        "propose_delete_task",
    }


def test_list_tasks_filters(database: Database, seeded: tuple[str, str]) -> None:
    conversation_id, message_id = seeded
    tasks = TaskRepository()
    with database.transaction() as connection:
        tasks.create(connection, CreateTaskCommand(text="写周报", priority="high"))
        tasks.create(connection, CreateTaskCommand(text="买菜", priority="low"))

    tools = _tools(database, conversation_id, message_id)
    all_tasks = json.loads(tools.execute("list_tasks", {}))
    searched = json.loads(tools.execute("list_tasks", {"search": "周报"}))

    assert len(all_tasks["tasks"]) == 2
    assert [t["text"] for t in searched["tasks"]] == ["写周报"]


def test_propose_create_persists_proposals_only(
    database: Database, seeded: tuple[str, str]
) -> None:
    conversation_id, message_id = seeded
    tools = _tools(database, conversation_id, message_id)

    result = json.loads(
        tools.execute(
            "propose_create_tasks",
            {
                "items": [
                    {
                        "text": "明天下午三点开会",
                        "priority": "high",
                        "category": "work",
                        "time_start": "2026-07-21T15:00",
                    }
                ]
            },
        )
    )

    conversations = ConversationsRepository()
    with database.transaction() as connection:
        proposals = conversations.list_pending_proposals(connection, conversation_id)
        real_tasks = TaskRepository().list_all(connection)

    assert len(result["proposal_ids"]) == 1
    assert real_tasks == []  # propose 不动真实任务
    assert proposals[0].payload.text == "明天下午三点开会"
    assert proposals[0].payload.time_start == "2026-07-21T15:00"
    assert proposals[0].message_id == message_id
    assert tools.created_proposal_ids == result["proposal_ids"]


def test_propose_create_rejects_invalid_item(
    database: Database, seeded: tuple[str, str]
) -> None:
    conversation_id, message_id = seeded
    tools = _tools(database, conversation_id, message_id)

    result = json.loads(
        tools.execute("propose_create_tasks", {"items": [{"priority": "high"}]})
    )

    assert "error" in result


def test_propose_update_and_delete_target_existing_task(
    database: Database, seeded: tuple[str, str]
) -> None:
    conversation_id, message_id = seeded
    with database.transaction() as connection:
        task = TaskRepository().create(
            connection, CreateTaskCommand(text="旧标题", priority="low")
        )
    tools = _tools(database, conversation_id, message_id)

    updated = json.loads(
        tools.execute(
            "propose_update_task",
            {"task_id": task.id, "changes": {"text": "新标题", "time_start": None}},
        )
    )
    deleted = json.loads(tools.execute("propose_delete_task", {"task_id": task.id}))
    missing = json.loads(tools.execute("propose_delete_task", {"task_id": "nope"}))
    unknown = json.loads(tools.execute("does_not_exist", {}))

    conversations = ConversationsRepository()
    with database.transaction() as connection:
        proposals = conversations.list_pending_proposals(connection, conversation_id)

    assert "error" not in updated and "error" not in deleted
    assert "error" in missing and "error" in unknown
    by_action = {p.action: p for p in proposals}
    assert by_action["update"].payload.text == "新标题"
    assert "time_start" in by_action["update"].payload.model_fields_set  # 显式清除时间
    assert by_action["delete"].task_id == task.id
