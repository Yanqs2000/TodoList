# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from todo_backend.agent.ark_client import ArkChatResult
from todo_backend.agent.planning import (
    IntentPlan,
    PlannedMutation,
    PlanValidationError,
    TargetQuery,
)
from todo_backend.agent.turn_graph import AssistantTurnWorkflow, TurnGraphDependencies
from todo_backend.config import Settings
from todo_backend.database import Database
from todo_backend.models import (
    AssistantAttachment,
    AssistantConversationDetail,
    CreateTaskCommand,
    LocalDateTime,
    PlannedFields,
    Task,
    TimeField,
)
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import ProposalBatchesRepository
from todo_backend.repositories.tasks import TaskRepository
from todo_backend.services.assistant import AssistantService
from todo_backend.services.tasks import TaskService


class FakePlanner:
    def __init__(self) -> None:
        self.results: list[IntentPlan] = []
        self.errors: list[str] = []
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def plan_once(
        self,
        user_text: str,
        messages: list[dict[str, Any]],
        validation_code: str | None,
    ) -> IntentPlan:
        self.calls.append(
            {
                "user_text": user_text,
                "messages": messages,
                "validation_code": validation_code,
            }
        )
        if self.errors:
            raise PlanValidationError(self.errors.pop(0))
        return self.results.pop(0)


class FakeArk:
    def __init__(self) -> None:
        self.results: list[ArkChatResult] = []
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: str = "disabled",
    ) -> ArkChatResult:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "thinking": thinking,
            }
        )
        return self.results.pop(0)


class FakeApplyWorkflow:
    def __init__(self) -> None:
        self.start_calls: list[str] = []
        self.failures_remaining = 0

    def start(self, batch_id: str) -> None:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("review initialization failed")
        self.start_calls.append(batch_id)


class NoWriteTaskRepository(TaskRepository):
    def __init__(self) -> None:
        self.create_calls = 0
        self.update_calls = 0
        self.delete_calls = 0

    def create(self, connection: Any, command: Any) -> Task:
        self.create_calls += 1
        raise AssertionError("turn graph must not create real tasks")

    def update(self, connection: Any, task_id: str, command: Any) -> Task:
        self.update_calls += 1
        raise AssertionError("turn graph must not update real tasks")

    def delete(self, connection: Any, task_id: str) -> None:
        self.delete_calls += 1
        raise AssertionError("turn graph must not delete real tasks")


@dataclass
class TurnFixture:
    database: Database
    conversations: ConversationsRepository
    batches: ProposalBatchesRepository
    task_service: TaskService
    task_repository: NoWriteTaskRepository
    planner: FakePlanner
    ark: FakeArk
    apply: FakeApplyWorkflow
    workflow: AssistantTurnWorkflow
    conversation_id: str
    uploads_dir: Path

    def create_task(
        self,
        text: str,
        *,
        start: LocalDateTime | None = None,
        end: LocalDateTime | None = None,
    ) -> Task:
        command = CreateTaskCommand(
            text=text,
            priority="medium",
            category="other",
            time=TimeField(start=start, end=end) if start is not None else None,
        )
        with self.database.transaction() as connection:
            return TaskRepository().create(connection, command)

    def run_user_turn(
        self,
        turn_id: str,
        content: str,
        attachments: list[AssistantAttachment] | None = None,
    ):
        with self.database.transaction() as connection:
            user = self.conversations.insert_message(
                connection,
                self.conversation_id,
                "user",
                content,
                attachments or [],
                turn_id=turn_id,
            )
            assistant = self.conversations.insert_message(
                connection,
                self.conversation_id,
                "assistant",
                "",
                [],
                status="pending",
                turn_id=turn_id,
            )
            self.conversations.insert_turn(
                connection,
                turn_id,
                self.conversation_id,
                user.id,
                assistant.id,
                f"fingerprint:{turn_id}",
            )
        return self.workflow.run(turn_id)

    def run_with_plan(self, turn_id: str, content: str, plan: IntentPlan):
        self.planner.results.append(plan)
        return self.run_user_turn(turn_id, content)

    def detail(self) -> AssistantConversationDetail:
        with self.database.transaction() as connection:
            return AssistantConversationDetail(
                conversation=self.conversations.get_conversation(
                    connection, self.conversation_id
                ),
                messages=self.conversations.list_messages(
                    connection, self.conversation_id
                ),
                proposalBatches=self.batches.list_for_conversation(
                    connection, self.conversation_id
                ),
            )


@pytest.fixture
def graph_fixture(tmp_path: Path) -> TurnFixture:
    database = Database(
        tmp_path / "todo.sqlite3", Path(__file__).parents[1] / "migrations"
    )
    database.initialize()
    conversations = ConversationsRepository()
    batches = ProposalBatchesRepository()
    task_repository = NoWriteTaskRepository()
    task_service = TaskService(database, repository=task_repository)
    planner = FakePlanner()
    ark = FakeArk()
    apply = FakeApplyWorkflow()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO app_settings (id, theme, muted, shortcut, language)"
            " VALUES (1, 'workspace-light', 0, 'Cmd+Alt+KeyT', 'zh-CN')"
        )
        conversation = conversations.create_conversation(connection, "测试")

    settings = Settings(database.path, "127.0.0.1", 8000, "test-token")
    message_service = AssistantService(database, settings)
    workflow = AssistantTurnWorkflow(
        TurnGraphDependencies(
            database=database,
            conversations=conversations,
            batches=batches,
            tasks=task_service,
            planner=planner,
            ark=ark,
            apply_workflow=apply,
            build_ark_messages=message_service._build_ark_messages,
        ),
        InMemorySaver(),
    )
    return TurnFixture(
        database=database,
        conversations=conversations,
        batches=batches,
        task_service=task_service,
        task_repository=task_repository,
        planner=planner,
        ark=ark,
        apply=apply,
        workflow=workflow,
        conversation_id=conversation.id,
        uploads_dir=tmp_path / "assistant_uploads",
    )


def mutation_plan(items: list[PlannedMutation]) -> IntentPlan:
    return IntentPlan(kind="mutations", evidence="测试请求", items=items)


def planned_create(text: str, **changes: object) -> PlannedMutation:
    return PlannedMutation(
        action="create",
        fields=PlannedFields.model_validate({"text": text, **changes}),
    )


def planned_update(
    target: TargetQuery | None = None,
    *,
    reference: str | None = None,
    **changes: object,
) -> PlannedMutation:
    return PlannedMutation(
        action="update",
        target_query=target,
        reference=reference,
        fields=PlannedFields.model_validate(changes),
    )


def create_plan(text: str, **changes: object) -> IntentPlan:
    return mutation_plan([planned_create(text, **changes)])


def update_plan(target: TargetQuery, fields: PlannedFields) -> IntentPlan:
    return mutation_plan(
        [PlannedMutation(action="update", target_query=target, fields=fields)]
    )


def test_explicit_create_never_updates_duplicate_title(
    graph_fixture: TurnFixture,
) -> None:
    existing = graph_fixture.create_task("团队会议")
    graph_fixture.planner.results = [create_plan("团队会议")]

    result = graph_fixture.run_user_turn("turn-1", "新建一个团队会议")

    proposal = result.proposal_batches[0].proposals[0]
    assert proposal.action == "create"
    assert proposal.target_task_id is None
    assert graph_fixture.task_service.list_all() == [existing]


def test_update_resolves_target_and_exposes_before_after(
    graph_fixture: TurnFixture,
) -> None:
    target = graph_fixture.create_task(
        "团队会议", start="2026-07-22T15:00", end="2026-07-22T16:00"
    )
    graph_fixture.planner.results = [
        update_plan(
            TargetQuery(title="团队会议"),
            PlannedFields(time_end="2026-07-22T17:00"),
        )
    ]

    result = graph_fixture.run_user_turn("turn-2", "把团队会议结束时间改成五点")

    proposal = result.proposal_batches[0].proposals[0]
    assert proposal.target_task_id == target.id
    assert proposal.before_snapshot == target
    assert proposal.payload is not None
    assert proposal.payload.time_start == "2026-07-22T15:00"
    assert proposal.payload.time_end == "2026-07-22T17:00"


def test_correction_supersedes_old_batch_atomically(
    graph_fixture: TurnFixture,
) -> None:
    first = graph_fixture.run_with_plan(
        "turn-1",
        "新建下午三点的会议",
        mutation_plan(
            [planned_create("开会", time_start="2026-07-22T15:00")]
        ),
    )
    old_batch = first.proposal_batches[0]
    old_proposal = old_batch.proposals[0]

    second = graph_fixture.run_with_plan(
        "turn-2",
        "把刚才那个改成四点",
        mutation_plan(
            [
                planned_update(
                    reference=old_proposal.id,
                    time_start="2026-07-22T16:00",
                )
            ]
        ),
    )

    detail = graph_fixture.detail()
    stored_old = next(
        batch for batch in detail.proposal_batches if batch.id == old_batch.id
    )
    assert stored_old.status == "superseded"
    assert second.proposal_batches[0].supersedes_batch_id == old_batch.id
    replacement = second.proposal_batches[0].proposals[0]
    assert replacement.action == "create"
    assert replacement.target_task_id is None
    assert replacement.payload is not None
    assert replacement.payload.time_start == "2026-07-22T16:00"
    assert [batch.status for batch in detail.proposal_batches].count("pending") == 1


def test_pending_update_correction_keeps_original_target_and_snapshot(
    graph_fixture: TurnFixture,
) -> None:
    target = graph_fixture.create_task(
        "团队会议", start="2026-07-22T15:00", end="2026-07-22T16:00"
    )
    first = graph_fixture.run_with_plan(
        "turn-update-first",
        "把团队会议结束时间改到五点",
        update_plan(
            TargetQuery(title="团队会议"),
            PlannedFields(time_end="2026-07-22T17:00"),
        ),
    )
    pending = first.proposal_batches[0].proposals[0]

    second = graph_fixture.run_with_plan(
        "turn-update-second",
        "把刚才那个修改为带备注",
        mutation_plan([planned_update(reference=pending.id, notes="带会议纪要")]),
    )

    replacement = second.proposal_batches[0].proposals[0]
    assert replacement.action == "update"
    assert replacement.target_task_id == target.id
    assert replacement.before_snapshot == target
    assert replacement.payload is not None
    assert replacement.payload.time_start == "2026-07-22T15:00"
    assert replacement.payload.time_end == "2026-07-22T17:00"
    assert replacement.payload.notes == "带会议纪要"


def test_pending_correction_copies_unmentioned_siblings(
    graph_fixture: TurnFixture,
) -> None:
    first = graph_fixture.run_with_plan(
        "turn-siblings-first",
        "新建 A 和新增 B",
        mutation_plan([planned_create("A"), planned_create("B")]),
    )
    first_proposal = first.proposal_batches[0].proposals[0]

    second = graph_fixture.run_with_plan(
        "turn-siblings-second",
        "把刚才的 A 修改为带备注",
        mutation_plan(
            [planned_update(reference=first_proposal.id, notes="只修改 A")]
        ),
    )

    replacements = second.proposal_batches[0].proposals
    assert len(replacements) == 2
    assert [proposal.payload.text for proposal in replacements if proposal.payload] == [
        "A",
        "B",
    ]
    assert replacements[0].payload is not None
    assert replacements[0].payload.notes == "只修改 A"


def test_low_target_score_returns_clarification_without_proposal(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.create_task("买菜")
    graph_fixture.planner.results = [
        update_plan(
            TargetQuery(title="季度财务复盘"),
            PlannedFields(time_end="2026-07-22T17:00"),
        )
    ]

    result = graph_fixture.run_user_turn(
        "turn-3", "把季度财务复盘改到五点"
    )

    assert result.proposal_batches == []
    assert "具体任务" in result.message.content


def test_query_route_uses_bounded_tasks_without_tools(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.create_task("买菜")
    graph_fixture.planner.results = [
        IntentPlan(kind="query", evidence="用户询问", query="今天有哪些任务")
    ]
    graph_fixture.ark.results = [ArkChatResult(content="今天有 1 项任务：买菜。")]

    result = graph_fixture.run_user_turn("turn-query", "今天有哪些任务？")

    assert result.message.content == "今天有 1 项任务：买菜。"
    assert result.proposal_batches == []
    assert graph_fixture.ark.calls[0]["tools"] is None
    assert graph_fixture.ark.calls[0]["thinking"] == "disabled"
    assert "买菜" in json.dumps(
        graph_fixture.ark.calls[0]["messages"], ensure_ascii=False
    )


def test_query_answer_rejects_mutation_completion_claim(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.planner.results = [
        IntentPlan(kind="query", evidence="用户询问", query="今天有哪些任务")
    ]
    graph_fixture.ark.results = [ArkChatResult(content="已删除这个任务。")]

    result = graph_fixture.run_user_turn("turn-answer-invalid", "今天有哪些任务？")

    assert result.message.status == "failed"
    with graph_fixture.database.transaction() as connection:
        turn = graph_fixture.conversations.get_turn(
            connection, "turn-answer-invalid"
        )
    assert turn.status == "failed"
    assert turn.last_error == "ANSWER_VERIFICATION_FAILED"


def test_invalid_plan_stops_after_two_graph_repairs(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.planner.errors = ["INVALID_PLAN", "INVALID_PLAN", "INVALID_PLAN"]

    result = graph_fixture.run_user_turn("turn-invalid", "改一下")

    assert result.message.status == "failed"
    assert graph_fixture.planner.call_count == 3
    state = graph_fixture.workflow.graph.get_state(
        graph_fixture.workflow.config("turn-invalid")
    ).values
    assert state["repair_count"] == 2


def test_proposal_validation_can_repair_once(graph_fixture: TurnFixture) -> None:
    graph_fixture.planner.results = [
        create_plan("开会", time_end="2026-07-22T16:00"),
        create_plan(
            "开会",
            time_start="2026-07-22T15:00",
            time_end="2026-07-22T16:00",
        ),
    ]

    result = graph_fixture.run_user_turn("turn-repair", "新建下午三点的会议")

    assert result.message.status == "done"
    assert graph_fixture.planner.call_count == 2
    assert graph_fixture.planner.calls[1]["validation_code"] == "TIME_END_REQUIRES_START"


def test_unknown_pending_reference_repairs_then_fails(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.planner.results = [
        mutation_plan([planned_update(reference="missing", notes="x")]),
        mutation_plan([planned_update(reference="missing", notes="x")]),
        mutation_plan([planned_update(reference="missing", notes="x")]),
    ]

    result = graph_fixture.run_user_turn("turn-missing", "把刚才那个改一下")

    assert result.message.status == "failed"
    assert graph_fixture.planner.call_count == 3
    assert graph_fixture.planner.calls[1]["validation_code"] == "PENDING_REFERENCE_NOT_FOUND"


def test_retry_after_terminal_failure_reuses_messages_without_duplicate_batch(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.planner.errors = ["INVALID_PLAN", "INVALID_PLAN", "INVALID_PLAN"]
    first = graph_fixture.run_user_turn("turn-retry", "新建买菜")
    assert first.message.status == "failed"

    graph_fixture.planner.results = [create_plan("买菜")]
    second = graph_fixture.workflow.run("turn-retry")
    repeated = graph_fixture.workflow.run("turn-retry")

    detail = graph_fixture.detail()
    assert second.message.status == "done"
    assert repeated.proposal_batches == second.proposal_batches
    assert len(detail.messages) == 2
    assert len(detail.proposal_batches) == 1
    assert graph_fixture.apply.start_calls == [second.proposal_batches[0].id]


def test_retry_resumes_failed_review_initialization_without_duplicate_rows(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.apply.failures_remaining = 1
    graph_fixture.planner.results = [create_plan("买菜")]

    first = graph_fixture.run_user_turn("turn-review-retry", "新建买菜")
    second = graph_fixture.workflow.run("turn-review-retry")

    assert first.message.status == "failed"
    assert second.message.status == "done"
    assert len(second.proposal_batches) == 1
    assert graph_fixture.apply.start_calls == [second.proposal_batches[0].id]
    assert len(graph_fixture.detail().proposal_batches) == 1


def test_attachments_are_transient_and_reach_planner(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.uploads_dir.mkdir()
    (graph_fixture.uploads_dir / "image.png").write_bytes(b"PNG-DATA")
    attachments = [
        AssistantAttachment(
            fileId="image.png",
            kind="image",
            name="image.png",
            mime="image/png",
        ),
        AssistantAttachment(
            fileId="notes.txt",
            kind="document",
            name="notes.txt",
            mime="text/plain",
            extractedText="文档中的秘密事项",
        ),
        AssistantAttachment(
            fileId="voice.wav",
            kind="audio",
            name="voice.wav",
            mime="audio/wav",
            extractedText="音频中的秘密事项",
        ),
    ]
    graph_fixture.planner.results = [
        IntentPlan(kind="query", evidence="附件问题", query="概括附件")
    ]
    graph_fixture.ark.results = [ArkChatResult(content="附件已概括。")]

    result = graph_fixture.run_user_turn(
        "turn-attachments", "请概括", attachments
    )

    assert result.message.status == "done"
    planner_history = json.dumps(
        graph_fixture.planner.calls[0]["messages"], ensure_ascii=False
    )
    assert "data:image/png;base64," in planner_history
    assert "文档中的秘密事项" in planner_history
    assert "音频中的秘密事项" in planner_history
    state = graph_fixture.workflow.graph.get_state(
        graph_fixture.workflow.config("turn-attachments")
    ).values
    serialized_state = json.dumps(state, ensure_ascii=False)
    assert "PNG-DATA" not in serialized_state
    assert "文档中的秘密事项" not in serialized_state
    assert "音频中的秘密事项" not in serialized_state
    assert "attachments" not in state["context_summary"]


def test_turn_graph_never_calls_real_task_write_methods(
    graph_fixture: TurnFixture,
) -> None:
    graph_fixture.planner.results = [create_plan("买菜")]

    result = graph_fixture.run_user_turn("turn-no-write", "新建买菜")

    assert result.message.content == "已生成 1 项提议，请检查确认卡。"
    assert graph_fixture.task_repository.create_calls == 0
    assert graph_fixture.task_repository.update_calls == 0
    assert graph_fixture.task_repository.delete_calls == 0


def test_english_mutation_message_is_deterministic(
    graph_fixture: TurnFixture,
) -> None:
    with graph_fixture.database.transaction() as connection:
        connection.execute("UPDATE app_settings SET language = 'en' WHERE id = 1")
    graph_fixture.planner.results = [create_plan("Buy milk")]

    result = graph_fixture.run_user_turn("turn-english", "Create a buy milk task")

    assert result.message.content == (
        "Created 1 proposals. Review the confirmation card."
    )
    assert "?" not in result.message.content
