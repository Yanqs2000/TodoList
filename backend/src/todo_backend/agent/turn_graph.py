import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, TypedDict, cast
from zoneinfo import ZoneInfo

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from todo_backend.agent.ark_client import ArkChatResult, ArkUnavailableError
from todo_backend.agent.planning import (
    AnalysisResult,
    IntentPlan,
    PlanValidationError,
)
from todo_backend.agent.proposals import (
    ProposalVerificationError,
    ResolvedMutation,
    build_batch_drafts,
    verify_drafts,
)
from todo_backend.agent.task_resolution import resolve_target
from todo_backend.database import Database
from todo_backend.models import (
    AssistantMessage,
    AssistantProposalBatch,
    AssistantTurnResponse,
    ProposalCardFields,
    ProposalAction,
    Task,
)
from todo_backend.repositories.conversations import ConversationsRepository
from todo_backend.repositories.proposal_batches import (
    BatchDraft,
    ProposalBatchNotFoundError,
    ProposalBatchesRepository,
    ProposalDraft,
    ProposalNotFoundError,
)
from todo_backend.services.tasks import TaskService


logger = logging.getLogger(__name__)

_CONTEXT_MESSAGE_LIMIT = 20
_CONTEXT_BATCH_LIMIT = 20
_QUERY_TASK_LIMIT = 100
_TIME_ZONE = ZoneInfo("Asia/Shanghai")
_WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_RELATIVE_TIME_RULES = (
    "相对时间规则：今天/明天/后天 = 当前日期 D0/D0+1/D0+2；"
    "下周一 = 下一个 ISO 周的星期一（不是未来最近的周一）；"
    "仅给月日而无年份时取最近一个尚未过去的该月日；"
    "只有开始时间时 time_end 必须为 null，不得假设时长；"
    "跨午夜的结束时间落到次日；"
    "上午7点/下午3点/晚上7点/9点半 = 07:00/15:00/19:00/09:30；"
    "晚点/下班后/傍晚等无约定分钟的表达必须用 kind=query 澄清，不得猜测分钟；"
    "若推算出的时间已过去（早于上述当前时间），必须用 kind=query 询问用户是否要今天还是未来日期。"
)
_REPAIRABLE_PROPOSAL_ERRORS = {
    "CREATE_TITLE_REQUIRED",
    "INVALID_PROPOSAL_FIELDS",
    "PENDING_REFERENCE_ACTION_MISMATCH",
    "PENDING_REFERENCE_NOT_FOUND",
    "TARGET_REQUIRED",
    "TASK_TARGET_NOT_FOUND",
    "TIME_END_BEFORE_START",
    "TIME_END_REQUIRES_START",
    "UPDATE_HAS_NO_CHANGES",
}
_MUTATION_COMPLETION_CLAIM = re.compile(
    r"(?:已|已经)(?:创建|新建|添加|更新|修改|删除|移除)"
    r"|\b(?:created|added|updated|modified|deleted|removed)\b",
    flags=re.IGNORECASE,
)


class AssistantTurnState(TypedDict, total=False):
    turn_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    language: str
    context_summary: dict[str, Any]
    analysis: dict[str, Any]
    plan: dict[str, Any]
    resolved_task_ids: list[str | None]
    resolved_pending_proposal_ids: list[str | None]
    candidate_scores: list[float]
    pending_batch_id: str | None
    draft_batches: list[dict[str, Any]]
    response_text: str
    repair_count: int
    validation_error: str | None
    error_code: str | None
    turn_memory: list[dict[str, Any]]


class PlannerProtocol(Protocol):
    def plan_once(
        self,
        user_text: str,
        messages: list[dict[str, Any]],
        validation_code: str | None,
    ) -> IntentPlan: ...
    def analyze(
        self, user_text: str, messages: list[dict[str, Any]]
    ) -> AnalysisResult: ...


class ArkClientProtocol(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: Literal["enabled", "disabled"] = "disabled",
    ) -> ArkChatResult: ...


class ProposalApplyWorkflowProtocol(Protocol):
    def start(self, batch_id: str) -> object: ...


class ArkMessageBuilderProtocol(Protocol):
    def __call__(
        self, messages: list[AssistantMessage], language: str
    ) -> list[dict[str, Any]]: ...


EventCallback = Callable[[str, dict[str, Any]], None] | None


@dataclass(frozen=True, slots=True)
class TurnGraphDependencies:
    database: Database
    conversations: ConversationsRepository
    batches: ProposalBatchesRepository
    tasks: TaskService
    planner: PlannerProtocol
    ark: ArkClientProtocol
    apply_workflow: ProposalApplyWorkflowProtocol
    build_ark_messages: ArkMessageBuilderProtocol
    on_event: EventCallback = None


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _render_current_time(now: datetime) -> str:
    return (
        f"当前时间：{now.isoformat(timespec='minutes')}"
        f"（{_WEEKDAY_LABELS[now.weekday()]}），时区 Asia/Shanghai。"
    )


class AssistantTurnWorkflow:
    def __init__(
        self,
        dependencies: TurnGraphDependencies,
        checkpointer: BaseCheckpointSaver[str],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._deps = dependencies
        self._checkpointer = checkpointer
        self._clock = clock or (lambda: datetime.now(_TIME_ZONE))
        self.graph = self._build_graph(checkpointer)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._deps.on_event is not None:
            self._deps.on_event(event_type, data)

    @staticmethod
    def config(turn_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": f"turn:{turn_id}"}}

    @staticmethod
    def conv_config(conversation_id: str) -> dict[str, dict[str, str]]:
        """Thread scoped to the conversation so state (turn_memory) persists across turns."""
        return {"configurable": {"thread_id": f"conv:{conversation_id}"}}

    def _build_graph(self, checkpointer: BaseCheckpointSaver[str]):
        builder = StateGraph(AssistantTurnState)
        builder.add_node("load_context", self._load_context)
        builder.add_node("analyze_intent", self._analyze_intent)
        builder.add_node("plan_intent", self._plan_intent)
        builder.add_node("repair_plan", self._repair_plan)
        builder.add_node("execute_read", self._execute_read)
        builder.add_node("verify_answer", self._verify_answer)
        builder.add_node("clarify_response", self._clarify_response)
        builder.add_node("resolve_targets", self._resolve_targets)
        builder.add_node("select_superseded", self._select_superseded)
        builder.add_node("build_proposals", self._build_proposals)
        builder.add_node("verify_proposals", self._verify_proposals)
        builder.add_node("reflect", self._reflect)
        builder.add_node("persist_batches", self._persist_batches)
        builder.add_node("initialize_reviews", self._initialize_reviews)
        builder.add_node("finalize", self._finalize)
        builder.add_node("finalize_error", self._finalize_error)
        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "analyze_intent")
        builder.add_conditional_edges(
            "analyze_intent",
            self._analyze_route,
            {
                "query": "execute_read",
                "clarify": "clarify_response",
                "mutations": "plan_intent",
            },
        )
        builder.add_conditional_edges(
            "plan_intent",
            self._intent_route,
            {
                "query": "execute_read",
                "mutation": "resolve_targets",
                "repair": "repair_plan",
                "error": "finalize_error",
            },
        )
        builder.add_edge("repair_plan", "plan_intent")
        builder.add_edge("execute_read", "verify_answer")
        builder.add_conditional_edges(
            "verify_answer",
            self._answer_route,
            {"valid": "finalize", "invalid": "finalize_error"},
        )
        builder.add_edge("clarify_response", "finalize")
        builder.add_edge("resolve_targets", "select_superseded")
        builder.add_conditional_edges(
            "select_superseded",
            self._resolution_route,
            {"resolved": "build_proposals", "clarify": "finalize"},
        )
        builder.add_edge("build_proposals", "verify_proposals")
        builder.add_conditional_edges(
            "verify_proposals",
            self._verification_route,
            {
                "valid": "reflect",
                "repair": "repair_plan",
                "error": "finalize_error",
            },
        )
        builder.add_conditional_edges(
            "reflect",
            self._reflect_route,
            {
                "ok": "persist_batches",
                "repair": "repair_plan",
                "error": "finalize_error",
            },
        )
        builder.add_edge("persist_batches", "initialize_reviews")
        builder.add_edge("initialize_reviews", "finalize")
        builder.add_edge("finalize", END)
        builder.add_edge("finalize_error", END)
        return builder.compile(checkpointer=checkpointer)

    def run(self, turn_id: str) -> AssistantTurnResponse:
        config = self.config(turn_id)
        with self._deps.database.transaction() as connection:
            turn = self._deps.conversations.get_turn(connection, turn_id)

        # Load cross-turn memory from the conversation-scoped checkpoint
        conv_config = self.conv_config(turn.conversation_id)
        conv_state = self.graph.get_state(conv_config)
        prev_memory = conv_state.values.get("turn_memory", []) if conv_state.values else []

        checkpoint = self._checkpointer.get_tuple(config)
        snapshot = self.graph.get_state(config)
        self._emit("step", {"node": "start", "status": "start", "text": "正在理解你的需求..."})
        try:
            if checkpoint is None:
                self.graph.invoke({"turn_id": turn_id, "turn_memory": prev_memory}, config=config)
            elif turn.status != "done":
                if snapshot.next:
                    self.graph.invoke(None, config=config)
                else:
                    self.graph.invoke({"turn_id": turn_id, "turn_memory": prev_memory}, config=config)
        except ArkUnavailableError:
            raise
        except Exception as exc:
            failed_snapshot = self.graph.get_state(config)
            error_type = type(exc).__name__
            logger.error(
                "turn graph failed node=%s error_type=%s",
                ",".join(failed_snapshot.next) or "unknown",
                error_type,
            )
            self._emit("error", {"code": "TURN_GRAPH_FAILED", "message": str(exc)})
            error_code = (
                "REVIEW_INITIALIZATION_FAILED"
                if "initialize_reviews" in failed_snapshot.next
                else "TURN_GRAPH_FAILED"
            )
            with self._deps.database.transaction() as connection:
                message = self._deps.conversations.get_message(
                    connection, turn.assistant_message_id
                )
                self._deps.conversations.update_message(
                    connection,
                    message.id,
                    content=message.content,
                    status="failed",
                    tool_trace=None,
                )
                self._deps.conversations.mark_turn(
                    connection, turn_id, "failed", error_code
                )

        # Save cross-turn memory to conversation checkpoint for next turn
        final_state = self.graph.get_state(config)
        if final_state.values:
            final_memory = final_state.values.get("turn_memory", [])
            if final_memory:
                self.graph.update_state(conv_config, {"turn_memory": final_memory})

        with self._deps.database.transaction() as connection:
            message = self._deps.conversations.get_message(
                connection, turn.assistant_message_id
            )
            batches = self._deps.batches.list_for_message(
                connection, turn.assistant_message_id
            )
        response = AssistantTurnResponse(message=message, proposalBatches=batches)
        self._emit("done", {
            "message": message.model_dump(mode="json", by_alias=True),
            "proposalBatches": [
                b.model_dump(mode="json", by_alias=True) for b in batches
            ],
        })
        return response

    def _load_context(self, state: AssistantTurnState) -> AssistantTurnState:
        turn_id = state["turn_id"]
        with self._deps.database.transaction() as connection:
            turn = self._deps.conversations.get_turn(connection, turn_id)
            messages = self._deps.conversations.list_messages(
                connection, turn.conversation_id
            )
            batches = self._deps.batches.list_for_conversation(
                connection, turn.conversation_id
            )
            language_row = connection.execute(
                "SELECT language FROM app_settings WHERE id = 1"
            ).fetchone()
            if language_row is None:
                raise RuntimeError("Application settings are not initialized")
            self._deps.conversations.mark_turn(connection, turn_id, "active", None)
            self._deps.conversations.update_message(
                connection,
                turn.assistant_message_id,
                content="",
                status="pending",
                tool_trace=None,
            )

        summary = {
            "turn": {
                "id": turn.id,
                "conversationId": turn.conversation_id,
                "userMessageId": turn.user_message_id,
                "assistantMessageId": turn.assistant_message_id,
                "status": "active",
            },
            "messages": [
                {
                    "id": message.id,
                    "role": message.role,
                    "status": message.status,
                    "turnId": message.turn_id,
                }
                for message in messages[-_CONTEXT_MESSAGE_LIMIT:]
            ],
            "proposalBatches": [
                self._batch_summary(batch)
                for batch in batches[-_CONTEXT_BATCH_LIMIT:]
            ],
        }
        return {
            "turn_id": turn.id,
            "conversation_id": turn.conversation_id,
            "user_message_id": turn.user_message_id,
            "assistant_message_id": turn.assistant_message_id,
            "language": cast(str, language_row["language"]),
            "context_summary": summary,
            "analysis": {},
            "plan": {},
            "resolved_task_ids": [],
            "resolved_pending_proposal_ids": [],
            "candidate_scores": [],
            "pending_batch_id": None,
            "draft_batches": [],
            "response_text": "",
            "repair_count": state.get("repair_count", 0),
            "turn_memory": state.get("turn_memory", []),
            "validation_error": None,
            "error_code": None,
        }

    def _analyze_intent(self, state: AssistantTurnState) -> AssistantTurnState:
        with self._deps.database.transaction() as conn:
            messages = self._deps.conversations.list_messages(conn, state["conversation_id"])
            user_message = self._deps.conversations.get_message(conn, state["user_message_id"])
        ark_messages = self._deps.build_ark_messages(messages, state["language"])
        # Inject current time context + existing tasks so the model knows what exists
        time_ctx = _render_current_time(self._clock())
        tasks = self._deps.tasks.list_all()
        task_summary = [
            {"text": t.text, "id": t.id, "priority": t.priority, "category": t.category,
             "time": t.time.model_dump(mode="json", by_alias=True) if t.time else None,
             "completed": t.completed}
            for t in tasks[:_QUERY_TASK_LIMIT]
        ]
        ark_messages.append({
            "role": "system",
            "content": (
                f"Current time: {time_ctx}\n"
                f"Existing tasks ({len(task_summary)} total):\n"
                + json.dumps(task_summary, ensure_ascii=False, separators=(",", ":"))
            ),
        })

        # Inject cross-turn memory — what the agent learned from previous turns
        memory = state.get("turn_memory", [])
        if memory:
            ark_messages.append({
                "role": "system",
                "content": (
                    "Cross-turn memory (what you learned from earlier turns in this conversation):\n"
                    + json.dumps(memory, ensure_ascii=False, separators=(",", ":"))
                ),
            })

        analysis = self._deps.planner.analyze(user_message.content, ark_messages)
        analysis_data = analysis.model_dump(mode="json")
        lang = state["language"]
        intent_labels = {"query": "查询", "clarify": "澄清", "mutations": "操作"} if lang == "zh-CN" else {"query": "query", "clarify": "clarify", "mutations": "mutation"}
        self._emit("step", {"node": "analyze", "status": "done",
            "text": f"分析意图：{intent_labels.get(analysis.intent, analysis.intent)}"})
        self._emit("analysis", {**analysis_data,
            "text": analysis.reasoning if analysis.reasoning else (analysis.missing_info or "")})
        return {"analysis": analysis_data}

    def _analyze_route(
        self, state: AssistantTurnState
    ) -> Literal["query", "clarify", "mutations"]:
        intent = state.get("analysis", {}).get("intent", "clarify")
        return intent if intent in ("query", "clarify", "mutations") else "clarify"

    def _clarify_response(self, state: AssistantTurnState) -> AssistantTurnState:
        analysis = state.get("analysis", {})
        missing = analysis.get("missing_info") or "请问您需要什么帮助？"
        return {"response_text": missing, "error_code": None}

    def _plan_intent(self, state: AssistantTurnState) -> AssistantTurnState:
        with self._deps.database.transaction() as connection:
            messages = self._deps.conversations.list_messages(
                connection, state["conversation_id"]
            )
            user_message = self._deps.conversations.get_message(
                connection, state["user_message_id"]
            )
            pending_batches = [
                batch
                for batch in self._deps.batches.list_for_conversation(
                    connection, state["conversation_id"]
                )
                if batch.status in {"pending", "partially_applied"}
                and any(item.status == "pending" for item in batch.proposals)
            ][-_CONTEXT_BATCH_LIMIT:]

        ark_messages = self._deps.build_ark_messages(messages, state["language"])
        # Inject cross-turn memory so the planner has context from earlier turns
        memory = state.get("turn_memory", [])
        memory_messages: list[dict[str, Any]] = []
        if memory:
            memory_messages.append({
                "role": "system",
                "content": (
                    "Cross-turn memory (what happened in earlier turns of this conversation):\n"
                    + json.dumps(memory, ensure_ascii=False, separators=(",", ":"))
                ),
            })
        pending_context = {
            "pendingProposalBatches": [
                batch.model_dump(mode="json", by_alias=True)
                for batch in pending_batches
            ]
        }
        planning_messages = [
            *ark_messages,
            *memory_messages,
            {
                "role": "system",
                "content": (
                    "Pending confirmation-card context (exact proposal IDs):\n"
                    + json.dumps(pending_context, ensure_ascii=False, separators=(",", ":"))
                ),
            },
            {
                "role": "system",
                "content": (
                    _render_current_time(self._clock()) + "\n" + _RELATIVE_TIME_RULES
                ),
            },
        ]
        validation_error = state.get("validation_error")
        validation_code: str | None = None
        if validation_error is not None:
            validation_code = self._build_repair_context(state, validation_error)
        try:
            plan = self._deps.planner.plan_once(
                user_message.content,
                planning_messages,
                validation_code,
            )
        except PlanValidationError as error:
            return self._planning_failure(error.code)
        plan_data = plan.model_dump(mode="json", exclude_unset=True)
        lang = state["language"]
        action_labels = {"create": "新建", "update": "修改", "delete": "删除"} if lang == "zh-CN" else {"create": "Create", "update": "Update", "delete": "Delete"}
        if plan.kind == "query" and plan.query:
            plan_text = plan.query[:200]
        elif plan.items:
            item_descs = []
            for item in plan.items:
                label = action_labels.get(item.action, item.action)
                item_text = item.fields.text if item.fields and item.fields.text else ""
                if item_text:
                    item_descs.append(f"{label}「{item_text}」" if lang == "zh-CN" else f'{label} "{item_text}"')
                else:
                    item_descs.append(f"{label}任务" if lang == "zh-CN" else f"{label} task")
            plan_text = ("生成计划：" if lang == "zh-CN" else "Plan: ") + "、".join(item_descs)
        else:
            plan_text = ""
        self._emit("step", {"node": "plan", "status": "done",
            "text": plan_text})
        self._emit("plan", {"kind": plan.kind, "items_count": len(plan.items), "query": plan.query,
            "evidence": plan.evidence, "text": plan_text})
        return {
            "plan": plan_data,
            "resolved_task_ids": [],
            "resolved_pending_proposal_ids": [],
            "candidate_scores": [],
            "pending_batch_id": None,
            "draft_batches": [],
            "response_text": "",
            "validation_error": None,
            "error_code": None,
        }

    def _intent_route(
        self, state: AssistantTurnState
    ) -> Literal["query", "mutation", "repair", "error"]:
        if state.get("validation_error") is not None:
            return "repair" if state.get("repair_count", 0) < 2 else "error"
        try:
            plan = IntentPlan.model_validate(state.get("plan", {}))
        except Exception:
            return "error"
        return "query" if plan.kind == "query" else "mutation"

    def _repair_plan(self, state: AssistantTurnState) -> AssistantTurnState:
        return {
            "plan": {},
            "resolved_task_ids": [],
            "resolved_pending_proposal_ids": [],
            "candidate_scores": [],
            "pending_batch_id": None,
            "response_text": "",
            "repair_count": state.get("repair_count", 0) + 1,
            "error_code": None,
        }

    def _execute_read(self, state: AssistantTurnState) -> AssistantTurnState:
        self._emit("step", {"node": "execute", "status": "start"})
        plan = IntentPlan.model_validate(state["plan"])
        task_payload = [
            task.model_dump(mode="json", by_alias=True)
            for task in self._deps.tasks.list_all()[:_QUERY_TASK_LIMIT]
        ]
        # Build conversation history so the model has context for pronouns/references
        with self._deps.database.transaction() as connection:
            messages = self._deps.conversations.list_messages(
                connection, state["conversation_id"]
            )
        ark_messages = self._deps.build_ark_messages(messages, state["language"])
        result = self._deps.ark.chat(
            [
                *ark_messages,
                {
                    "role": "system",
                    "content": (
                        _render_current_time(self._clock()) + "\n"
                        "Answer the read-only TodoList question only from the supplied task JSON. "
                        "Relative dates such as 今天/明天 refer to the current time above. "
                        "Do not claim to create, update, or delete a task."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "language": state["language"],
                            "query": plan.query,
                            "tasks": task_payload,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            tools=None,
            thinking="disabled",
        )
        # Record turn memory for query turns so later turns have context
        memory = state.get("turn_memory", [])
        user_question = ""
        try:
            with self._deps.database.transaction() as conn:
                user_msg = self._deps.conversations.get_message(
                    conn, state["user_message_id"]
                )
                user_question = user_msg.content
        except Exception:
            pass
        memory.append({
            "round": len(memory) + 1,
            "user_question": user_question,
            "assistant_summary": result.content[:500],
            "actions": ["query"],
            "task_texts": [],
            "count": 0,
        })
        if len(memory) > 10:
            memory = memory[-10:]
        return {
            "response_text": result.content,
            "error_code": None,
            "turn_memory": memory,
        }

    def _verify_answer(self, state: AssistantTurnState) -> AssistantTurnState:
        answer = state.get("response_text", "").strip()
        if not answer or _MUTATION_COMPLETION_CLAIM.search(answer):
            return {"error_code": "ANSWER_VERIFICATION_FAILED"}
        return {"response_text": answer, "error_code": None}

    def _answer_route(
        self, state: AssistantTurnState
    ) -> Literal["valid", "invalid"]:
        return (
            "invalid"
            if state.get("error_code") == "ANSWER_VERIFICATION_FAILED"
            else "valid"
        )

    def _resolve_targets(self, state: AssistantTurnState) -> AssistantTurnState:
        plan = IntentPlan.model_validate(state["plan"])
        tasks = self._deps.tasks.list_all()
        recent_task_ids = self._recent_task_ids(state.get("context_summary", {}))
        resolved_task_ids: list[str | None] = []
        resolved_pending_ids: list[str | None] = []
        candidate_scores: list[float] = []
        validation_error: str | None = None
        needs_clarification = False

        with self._deps.database.transaction() as connection:
            conversation_batch_ids = set(
                self._deps.batches.list_batch_ids(
                    connection, state["conversation_id"]
                )
            )
            for item in plan.items:
                if item.action == "create":
                    resolved_task_ids.append(None)
                    resolved_pending_ids.append(None)
                    candidate_scores.append(1.0)
                    continue
                if item.reference is not None:
                    try:
                        pending = self._deps.batches.get_proposal(
                            connection, item.reference
                        )
                        batch = self._deps.batches.get_batch(
                            connection, pending.batch_id
                        )
                    except (ProposalNotFoundError, ProposalBatchNotFoundError):
                        resolved_task_ids.append(None)
                        resolved_pending_ids.append(None)
                        candidate_scores.append(0.0)
                        validation_error = "PENDING_REFERENCE_NOT_FOUND"
                        continue
                    if (
                        pending.batch_id not in conversation_batch_ids
                        or pending.status != "pending"
                        or batch.status not in {"pending", "partially_applied"}
                    ):
                        resolved_task_ids.append(None)
                        resolved_pending_ids.append(None)
                        candidate_scores.append(0.0)
                        validation_error = "PENDING_REFERENCE_NOT_FOUND"
                        continue
                    resolved_task_ids.append(None)
                    resolved_pending_ids.append(pending.id)
                    candidate_scores.append(1.0)
                    continue

                if item.target_query is None:
                    resolved_task_ids.append(None)
                    resolved_pending_ids.append(None)
                    candidate_scores.append(0.0)
                    validation_error = "TARGET_REQUIRED"
                    continue
                resolution = resolve_target(
                    item.target_query,
                    tasks,
                    recent_task_ids=recent_task_ids,
                )
                resolved_task_ids.append(
                    resolution.task.id if resolution.task is not None else None
                )
                resolved_pending_ids.append(None)
                candidate_scores.append(resolution.score)
                if resolution.task is None:
                    needs_clarification = True

        if validation_error is not None:
            return self._resolution_failure(
                resolved_task_ids,
                resolved_pending_ids,
                candidate_scores,
                validation_error,
            )
        if needs_clarification:
            return {
                "resolved_task_ids": resolved_task_ids,
                "resolved_pending_proposal_ids": resolved_pending_ids,
                "candidate_scores": candidate_scores,
                "response_text": self._clarification(state["language"]),
                "validation_error": None,
                "error_code": None,
            }

        return {
            "resolved_task_ids": resolved_task_ids,
            "resolved_pending_proposal_ids": resolved_pending_ids,
            "candidate_scores": candidate_scores,
            "response_text": "",
            "validation_error": None,
            "error_code": None,
        }

    def _select_superseded(self, state: AssistantTurnState) -> AssistantTurnState:
        if state.get("validation_error") is not None or state.get("response_text"):
            return {"pending_batch_id": None}
        selected_ids = [
            proposal_id
            for proposal_id in state.get("resolved_pending_proposal_ids", [])
            if proposal_id is not None
        ]
        if not selected_ids:
            return {"pending_batch_id": None}
        with self._deps.database.transaction() as connection:
            try:
                proposals = [
                    self._deps.batches.get_proposal(connection, proposal_id)
                    for proposal_id in selected_ids
                ]
                proposal_batches = [
                    self._deps.batches.get_batch(connection, proposal.batch_id)
                    for proposal in proposals
                ]
            except (ProposalNotFoundError, ProposalBatchNotFoundError):
                return {
                    "pending_batch_id": None,
                    "validation_error": "PENDING_REFERENCE_NOT_FOUND",
                }
            conversation_batch_ids = set(
                self._deps.batches.list_batch_ids(
                    connection, state["conversation_id"]
                )
            )
        if any(
            proposal.status != "pending"
            or proposal.batch_id not in conversation_batch_ids
            or batch.status not in {"pending", "partially_applied"}
            for proposal, batch in zip(proposals, proposal_batches, strict=True)
        ):
            return {
                "pending_batch_id": None,
                "validation_error": "PENDING_REFERENCE_NOT_FOUND",
            }
        batch_ids = {proposal.batch_id for proposal in proposals}
        if len(batch_ids) != 1:
            return {
                "pending_batch_id": None,
                "error_code": "MULTIPLE_SUPERSEDED_BATCHES",
            }
        return {"pending_batch_id": next(iter(batch_ids)), "error_code": None}

    def _resolution_route(
        self, state: AssistantTurnState
    ) -> Literal["resolved", "clarify"]:
        return "clarify" if state.get("response_text") else "resolved"

    def _build_proposals(self, state: AssistantTurnState) -> AssistantTurnState:
        if state.get("validation_error") is not None or state.get("error_code") is not None:
            return {"draft_batches": []}
        plan = IntentPlan.model_validate(state["plan"])
        tasks_by_id = {task.id: task for task in self._deps.tasks.list_all()}
        with self._deps.database.transaction() as connection:
            pending_by_id = {
                proposal_id: self._deps.batches.get_proposal(connection, proposal_id)
                for proposal_id in state.get(
                    "resolved_pending_proposal_ids", []
                )
                if proposal_id is not None
            }
            superseded = (
                self._deps.batches.get_batch(connection, state["pending_batch_id"])
                if state.get("pending_batch_id") is not None
                else None
            )
        resolved: list[ResolvedMutation] = []
        for task_id, pending_id in zip(
            state.get("resolved_task_ids", []),
            state.get("resolved_pending_proposal_ids", []),
            strict=True,
        ):
            if task_id is not None and task_id not in tasks_by_id:
                return {
                    "draft_batches": [],
                    "validation_error": "TASK_TARGET_NOT_FOUND",
                }
            resolved.append(
                ResolvedMutation(
                    task=tasks_by_id.get(task_id) if task_id is not None else None,
                    pending=(
                        pending_by_id.get(pending_id)
                        if pending_id is not None
                        else None
                    ),
                )
            )
        try:
            drafts = build_batch_drafts(
                state["turn_id"],
                plan,
                resolved,
                superseded_batch=superseded,
            )
        except ProposalVerificationError as error:
            return {"draft_batches": [], "validation_error": str(error)}
        except ValidationError:
            return {"draft_batches": [], "validation_error": "INVALID_PROPOSAL_FIELDS"}
        return {
            "draft_batches": [self._dump_batch_draft(draft) for draft in drafts],
            "validation_error": None,
        }

    def _verify_proposals(self, state: AssistantTurnState) -> AssistantTurnState:
        if state.get("validation_error") is not None or state.get("error_code") is not None:
            return {}
        try:
            verify_drafts(
                [self._load_batch_draft(item) for item in state["draft_batches"]]
            )
        except ProposalVerificationError as error:
            return {"validation_error": str(error)}
        except ValidationError:
            return {"validation_error": "INVALID_PROPOSAL_FIELDS"}
        return {"validation_error": None, "error_code": None}

    def _verification_route(
        self, state: AssistantTurnState
    ) -> Literal["valid", "repair", "error"]:
        if state.get("error_code") is not None:
            return "error"
        validation_error = state.get("validation_error")
        if validation_error is None:
            return "valid"
        if (
            validation_error in _REPAIRABLE_PROPOSAL_ERRORS
            and state.get("repair_count", 0) < 2
        ):
            return "repair"
        return "error"

    def _reflect(self, state: AssistantTurnState) -> AssistantTurnState:
        if state.get("validation_error") is not None or state.get("error_code") is not None:
            return {}
        draft_batches = state.get("draft_batches", [])
        summary: list[dict[str, Any]] = []
        for draft in draft_batches:
            for prop in draft.get("proposals", []):
                payload = prop.get("payload")
                item: dict[str, Any] = {
                    "action": prop.get("action"),
                    "targetTaskId": prop.get("target_task_id"),
                }
                if isinstance(payload, dict):
                    item["text"] = payload.get("text")
                    item["time_start"] = payload.get("time_start")
                    item["time_end"] = payload.get("time_end")
                    item["notes"] = payload.get("notes")
                summary.append(item)
        try:
            result = self._deps.ark.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a proposal quality reviewer for a TodoList app. "
                            "Review the proposal drafts about to be persisted. "
                            "Respond ONLY with a JSON object: "
                            '{"ok": true} if all items are correct, or '
                            '{"ok": false, "issues": [{"item_index": 0, "problem": "description"}]} '
                            "if any item has a problem."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(summary, ensure_ascii=False),
                    },
                ],
                tools=None,
                thinking="disabled",
            )
            # Strip markdown fences and parse JSON
            raw = result.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3].strip()
            response = json.loads(raw)
            if not isinstance(response, dict):
                return {"validation_error": None, "error_code": None}
        except ArkUnavailableError:
            raise
        except Exception:
            # Parse/network failure: default to ok (don't block normal flow)
            return {"validation_error": None, "error_code": None}
        if response.get("ok"):
            # Record cross-turn memory of what was done this turn
            memory = state.get("turn_memory", [])
            actions = {item.get("action") for item in summary}
            texts = [item.get("text") for item in summary if item.get("text")]
            # Build natural-language summary for semantic context
            lang = state["language"]
            action_labels = (
                {"create": "新建", "update": "修改", "delete": "删除"}
                if lang == "zh-CN"
                else {"create": "Create", "update": "Update", "delete": "Delete"}
            )
            summary_parts: list[str] = []
            for item in summary:
                act = item.get("action", "")
                txt = item.get("text") or ""
                label = action_labels.get(act, act)
                if lang == "zh-CN":
                    summary_parts.append(f"{label}「{txt}」" if txt else f"{label}任务")
                else:
                    summary_parts.append(f'{label} "{txt}"' if txt else f"{label} task")
            sep = "；" if lang == "zh-CN" else "; "
            # Fetch user message for context
            user_question = ""
            try:
                with self._deps.database.transaction() as conn:
                    user_msg = self._deps.conversations.get_message(
                        conn, state["user_message_id"]
                    )
                    user_question = user_msg.content
            except Exception:
                pass
            memory.append({
                "round": len(memory) + 1,
                "user_question": user_question,
                "assistant_summary": sep.join(summary_parts),
                "actions": sorted(actions),
                "task_texts": texts,
                "count": len(summary),
            })
            # Keep only the last 10 rounds to avoid unbounded growth
            if len(memory) > 10:
                memory = memory[-10:]
            lang = state["language"]
            self._emit("step", {"node": "reflect", "status": "done",
                "text": "自检通过" if lang == "zh-CN" else "Self-check passed"})
            self._emit("reflect", {"ok": True,
                "text": "已生成 {} 项操作：{}".format(len(summary), sep.join(summary_parts)) if lang == "zh-CN" else "Generated {} items: {}".format(len(summary), sep.join(summary_parts))})
            return {"validation_error": None, "error_code": None, "turn_memory": memory}
        issues = response.get("issues", [])
        issue_lines = [
            f"Item {issue.get('item_index', '?')}: {issue.get('problem', 'unknown')}"
            for issue in issues
        ]
        return {
            "validation_error": "Reflect found issues:\n" + "\n".join(issue_lines),
            "error_code": None,
        }

    def _reflect_route(
        self, state: AssistantTurnState
    ) -> Literal["ok", "repair", "error"]:
        if state.get("error_code") is not None:
            return "error"
        validation_error = state.get("validation_error")
        if validation_error is None:
            return "ok"
        if state.get("repair_count", 0) < 2:
            return "repair"
        return "error"

    def _persist_batches(self, state: AssistantTurnState) -> AssistantTurnState:
        drafts = [
            self._load_batch_draft(item) for item in state.get("draft_batches", [])
        ]
        verify_drafts(drafts)
        with self._deps.database.transaction() as connection:
            existing = self._deps.batches.list_for_message(
                connection, state["assistant_message_id"]
            )
            if existing:
                batches = existing
            else:
                batches = self._deps.batches.insert_batches(
                    connection,
                    conversation_id=state["conversation_id"],
                    message_id=state["assistant_message_id"],
                    drafts=drafts,
                )
                if state.get("pending_batch_id"):
                    self._deps.batches.supersede(
                        connection, state["pending_batch_id"], _now_ms()
                    )
            self._deps.conversations.update_message(
                connection,
                state["assistant_message_id"],
                content=self._proposal_message(state["language"], batches),
                status="done",
                tool_trace=None,
            )
        return {
            "draft_batches": [
                batch.model_dump(mode="json", by_alias=True) for batch in batches
            ]
        }

    def _initialize_reviews(self, state: AssistantTurnState) -> AssistantTurnState:
        with self._deps.database.transaction() as connection:
            batch_ids = [
                batch.id
                for batch in self._deps.batches.list_for_message(
                    connection, state["assistant_message_id"]
                )
            ]
        for batch_id in batch_ids:
            self._deps.apply_workflow.start(batch_id)
        return {}

    def _finalize(self, state: AssistantTurnState) -> AssistantTurnState:
        with self._deps.database.transaction() as connection:
            batches = self._deps.batches.list_for_message(
                connection, state["assistant_message_id"]
            )
            content = state.get("response_text", "")
            if batches:
                content = self._proposal_message(state["language"], batches)
            self._deps.conversations.update_message(
                connection,
                state["assistant_message_id"],
                content=content,
                status="done",
                tool_trace=None,
            )
            self._deps.conversations.mark_turn(
                connection, state["turn_id"], "done", None
            )
        return {"response_text": content}

    def _finalize_error(self, state: AssistantTurnState) -> AssistantTurnState:
        error_code = (
            state.get("error_code")
            or state.get("validation_error")
            or "TURN_GRAPH_FAILED"
        )
        with self._deps.database.transaction() as connection:
            self._deps.conversations.update_message(
                connection,
                state["assistant_message_id"],
                content="",
                status="failed",
                tool_trace=None,
            )
            self._deps.conversations.mark_turn(
                connection, state["turn_id"], "failed", error_code
            )
        return {"error_code": error_code, "response_text": ""}

    def _build_repair_context(
        self, state: AssistantTurnState, error_code: str
    ) -> str:
        """Build rich failure context for the planner when repair is needed."""
        context_parts = [f"Error code: {error_code}"]

        # Include draft_batches summary if available (e.g., from _verify_proposals)
        draft_batches = state.get("draft_batches", [])
        if draft_batches:
            try:
                drafts_summary = []
                for draft in draft_batches:
                    for prop in draft.get("proposals", []):
                        payload = prop.get("payload")
                        drafts_summary.append(
                            {
                                "action": prop.get("action"),
                                "text": (
                                    payload.get("text")
                                    if isinstance(payload, dict)
                                    else None
                                ),
                                "targetTaskId": prop.get("target_task_id"),
                            }
                        )
                context_parts.append(
                    "Draft proposals: "
                    + json.dumps(drafts_summary, ensure_ascii=False)
                )
            except Exception:
                pass

        # Include available tasks for target resolution context
        try:
            tasks = self._deps.tasks.list_all()
            task_summary = [
                {"text": t.text, "id": t.id}
                for t in tasks[:_QUERY_TASK_LIMIT]
            ]
            context_parts.append(
                "Available tasks: "
                + json.dumps(task_summary, ensure_ascii=False)
            )
        except Exception:
            pass

        # Include pending batches from context
        try:
            context = state.get("context_summary", {})
            pending_batches = context.get("proposalBatches", [])
            if pending_batches:
                pending_summary = []
                for batch in pending_batches:
                    for prop in batch.get("proposals", []):
                        if prop.get("status") == "pending":
                            pending_summary.append(
                                {
                                    "id": prop.get("id"),
                                    "action": prop.get("action"),
                                    "targetTaskId": prop.get("targetTaskId"),
                                }
                            )
                if pending_summary:
                    context_parts.append(
                        "Pending proposals: "
                        + json.dumps(pending_summary, ensure_ascii=False)
                    )
        except Exception:
            pass

        context_parts.append(
            "The planner must correct the plan based on this failure context."
        )
        return "\n".join(context_parts)

    @staticmethod
    def _planning_failure(code: str) -> AssistantTurnState:
        return {
            "plan": {},
            "resolved_task_ids": [],
            "resolved_pending_proposal_ids": [],
            "candidate_scores": [],
            "pending_batch_id": None,
            "draft_batches": [],
            "response_text": "",
            "validation_error": code,
            "error_code": None,
        }

    @staticmethod
    def _resolution_failure(
        task_ids: list[str | None],
        pending_ids: list[str | None],
        scores: list[float],
        code: str,
    ) -> AssistantTurnState:
        return {
            "resolved_task_ids": task_ids,
            "resolved_pending_proposal_ids": pending_ids,
            "candidate_scores": scores,
            "response_text": "",
            "validation_error": code,
            "error_code": None,
        }

    @staticmethod
    def _batch_summary(batch: AssistantProposalBatch) -> dict[str, Any]:
        return {
            "id": batch.id,
            "messageId": batch.message_id,
            "status": batch.status,
            "supersedesBatchId": batch.supersedes_batch_id,
            "proposals": [
                {
                    "id": proposal.id,
                    "action": proposal.action,
                    "targetTaskId": proposal.target_task_id,
                    "resultTaskId": proposal.result_task_id,
                    "status": proposal.status,
                }
                for proposal in batch.proposals
            ],
        }

    @staticmethod
    def _recent_task_ids(context_summary: dict[str, Any]) -> list[str]:
        recent: list[str] = []
        raw_batches = context_summary.get("proposalBatches", [])
        if not isinstance(raw_batches, list):
            return recent
        for raw_batch in reversed(raw_batches):
            if not isinstance(raw_batch, dict):
                continue
            raw_proposals = raw_batch.get("proposals", [])
            if not isinstance(raw_proposals, list):
                continue
            for raw_proposal in reversed(raw_proposals):
                if not isinstance(raw_proposal, dict):
                    continue
                for field_name in ("resultTaskId", "targetTaskId"):
                    task_id = raw_proposal.get(field_name)
                    if isinstance(task_id, str) and task_id not in recent:
                        recent.append(task_id)
        return recent

    @staticmethod
    def _clarification(language: str) -> str:
        if language == "zh-CN":
            return "请说明要修改或删除的具体任务。"
        return "Please specify the task you want to update or delete."

    @staticmethod
    def _proposal_message(
        language: str, batches: list[AssistantProposalBatch]
    ) -> str:
        count = sum(len(batch.proposals) for batch in batches)
        if language == "zh-CN":
            action_labels = {"create": "新建", "update": "修改", "delete": "删除"}
        else:
            action_labels = {"create": "Create", "update": "Update", "delete": "Delete"}
        details: list[str] = []
        for batch in batches:
            for prop in batch.proposals:
                label = action_labels.get(prop.action, prop.action)
                if prop.payload is not None and prop.payload.text:
                    if language == "zh-CN":
                        details.append(f"{label}「{prop.payload.text}」")
                    else:
                        details.append(f'{label} "{prop.payload.text}"')
                else:
                    if language == "zh-CN":
                        details.append(f"{label}任务")
                    else:
                        details.append(f"{label} task")
        if language == "zh-CN":
            if details:
                return f"已生成 {count} 项提议：{'；'.join(details)}。请检查确认卡。"
            return f"已生成 {count} 项提议，请检查确认卡。"
        else:
            if details:
                return f"Created {count} proposals: {'; '.join(details)}. Review the confirmation card."
            return f"Created {count} proposals. Review the confirmation card."

    @staticmethod
    def _dump_batch_draft(draft: BatchDraft) -> dict[str, Any]:
        return {
            "id": draft.id,
            "supersedes_batch_id": draft.supersedes_batch_id,
            "proposals": [
                {
                    "id": proposal.id,
                    "action": proposal.action,
                    "target_task_id": proposal.target_task_id,
                    "before_snapshot": (
                        proposal.before_snapshot.model_dump(
                            mode="json", by_alias=True
                        )
                        if proposal.before_snapshot is not None
                        else None
                    ),
                    "payload": (
                        proposal.payload.model_dump(mode="json", by_alias=True)
                        if proposal.payload is not None
                        else None
                    ),
                    "source_batch_id": proposal.source_batch_id,
                    "source_proposal_id": proposal.source_proposal_id,
                }
                for proposal in draft.proposals
            ],
        }

    @staticmethod
    def _load_batch_draft(raw: dict[str, Any]) -> BatchDraft:
        raw_proposals = raw.get("proposals")
        if not isinstance(raw_proposals, list):
            raise ValueError("draft proposals must be a list")
        proposals: list[ProposalDraft] = []
        for item in raw_proposals:
            if not isinstance(item, dict):
                raise ValueError("proposal draft must be an object")
            before_raw = item.get("before_snapshot")
            payload_raw = item.get("payload")
            proposals.append(
                ProposalDraft(
                    id=cast(str, item["id"]),
                    action=cast(ProposalAction, item["action"]),
                    target_task_id=cast(str | None, item.get("target_task_id")),
                    before_snapshot=(
                        Task.model_validate(before_raw)
                        if before_raw is not None
                        else None
                    ),
                    payload=(
                        ProposalCardFields.model_validate(payload_raw)
                        if payload_raw is not None
                        else None
                    ),
                    source_batch_id=cast(
                        str | None, item.get("source_batch_id")
                    ),
                    source_proposal_id=cast(
                        str | None, item.get("source_proposal_id")
                    ),
                )
            )
        return BatchDraft(
            id=cast(str, raw["id"]),
            supersedes_batch_id=cast(
                str | None, raw.get("supersedes_batch_id")
            ),
            proposals=proposals,
        )
