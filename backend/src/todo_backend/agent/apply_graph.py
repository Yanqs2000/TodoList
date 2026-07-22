from typing import Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from todo_backend.models import (
    ConfirmProposalBatchCommand,
    ProposalBatchResolveResponse,
    ProposalReviewDecision,
)
from todo_backend.services.proposal_batches import (
    ProposalBatchExecutor,
    ProposalBatchNotConfirmableError,
)


class ProposalApplyState(TypedDict, total=False):
    batch_id: str
    review: dict[str, Any]
    result: dict[str, Any]


class ProposalApplyWorkflow:
    def __init__(
        self,
        executor: ProposalBatchExecutor,
        checkpointer: BaseCheckpointSaver[str],
    ) -> None:
        self._executor = executor
        builder = StateGraph(ProposalApplyState)
        builder.add_node("load_batch", self._load_batch)
        builder.add_node("interrupt_review", self._interrupt_review)
        builder.add_node("validate_review", self._validate_review)
        builder.add_node("apply_items", self._apply_items)
        builder.add_node("verify_results", self._verify_results)
        builder.add_node("persist_results", self._persist_results)
        builder.add_node("reject_batch", self._reject_batch)
        builder.add_edge(START, "load_batch")
        builder.add_edge("load_batch", "interrupt_review")
        builder.add_edge("interrupt_review", "validate_review")
        builder.add_conditional_edges(
            "validate_review",
            self._review_route,
            {
                "confirm": "apply_items",
                "reject": "reject_batch",
                "invalid": "interrupt_review",
            },
        )
        builder.add_edge("apply_items", "verify_results")
        builder.add_edge("verify_results", "persist_results")
        builder.add_conditional_edges(
            "persist_results",
            self._result_route,
            {"done": END, "review": "interrupt_review"},
        )
        builder.add_edge("reject_batch", END)
        self.graph = builder.compile(checkpointer=checkpointer)

    @staticmethod
    def config(batch_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": f"proposal:{batch_id}"}}

    def start(self, batch_id: str) -> ProposalBatchResolveResponse:
        config = self.config(batch_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            self.graph.invoke({"batch_id": batch_id}, config=config)
        return self._executor.current(batch_id)

    def confirm(
        self, batch_id: str, command: ConfirmProposalBatchCommand
    ) -> ProposalBatchResolveResponse:
        current = self._executor.current(batch_id)
        if current.batch.status == "superseded":
            raise ProposalBatchNotConfirmableError
        if not any(item.proposal.status == "pending" for item in current.items):
            return current

        self.start(batch_id)
        decision = ProposalReviewDecision(decision="confirm", items=command.items)
        self.graph.invoke(
            Command(resume=decision.model_dump(mode="json", by_alias=True)),
            config=self.config(batch_id),
        )
        return self._executor.current(batch_id)

    def reject(self, batch_id: str) -> ProposalBatchResolveResponse:
        current = self._executor.current(batch_id)
        if current.batch.status == "superseded":
            raise ProposalBatchNotConfirmableError
        if not any(item.proposal.status == "pending" for item in current.items):
            return current

        self.start(batch_id)
        decision = ProposalReviewDecision(decision="reject")
        self.graph.invoke(
            Command(resume=decision.model_dump(mode="json", by_alias=True)),
            config=self.config(batch_id),
        )
        return self._executor.current(batch_id)

    def _load_batch(self, state: ProposalApplyState) -> ProposalApplyState:
        current = self._executor.current(state["batch_id"])
        return {"result": self._dump(current)}

    def _interrupt_review(self, state: ProposalApplyState) -> ProposalApplyState:
        review = interrupt({"batchId": state["batch_id"]})
        return {"review": review if isinstance(review, dict) else {}}

    def _validate_review(self, state: ProposalApplyState) -> ProposalApplyState:
        try:
            decision = self._validated_decision(state["review"])
        except ValidationError:
            failed = self._executor.fail_pending(
                state["batch_id"], "INVALID_CONFIRMATION_PAYLOAD"
            )
            return {"review": {}, "result": self._dump(failed)}
        return {"review": decision.model_dump(mode="json", by_alias=True)}

    def _review_route(
        self, state: ProposalApplyState
    ) -> Literal["confirm", "reject", "invalid"]:
        try:
            return self._validated_decision(state["review"]).decision
        except ValidationError:
            return "invalid"

    def _apply_items(self, state: ProposalApplyState) -> ProposalApplyState:
        decision = self._validated_decision(state["review"])
        command = ConfirmProposalBatchCommand(items=decision.items)
        result = self._executor.confirm(state["batch_id"], command)
        return {"result": self._dump(result)}

    def _verify_results(self, state: ProposalApplyState) -> ProposalApplyState:
        result = self._executor.verify(state["batch_id"])
        return {"result": self._dump(result)}

    def _persist_results(self, state: ProposalApplyState) -> ProposalApplyState:
        result = self._executor.recompute(state["batch_id"])
        return {"result": self._dump(result)}

    def _result_route(
        self, state: ProposalApplyState
    ) -> Literal["done", "review"]:
        result = ProposalBatchResolveResponse.model_validate(state["result"])
        if result.batch.status in {"pending", "partially_applied"}:
            return "review"
        return "done"

    def _reject_batch(self, state: ProposalApplyState) -> ProposalApplyState:
        result = self._executor.reject(state["batch_id"])
        return {"result": self._dump(result)}

    @staticmethod
    def _validated_decision(review: dict[str, Any]) -> ProposalReviewDecision:
        decision = ProposalReviewDecision.model_validate(review)
        if decision.decision == "confirm":
            ConfirmProposalBatchCommand(items=decision.items)
        return decision

    @staticmethod
    def _dump(response: ProposalBatchResolveResponse) -> dict[str, Any]:
        return response.model_dump(mode="json", by_alias=True)
