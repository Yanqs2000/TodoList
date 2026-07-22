from dataclasses import dataclass
from uuid import UUID, uuid5

from todo_backend.agent.planning import IntentPlan, PlannedMutation
from todo_backend.models import (
    AssistantProposal,
    AssistantProposalBatch,
    PlannedFields,
    ProposalCardFields,
    Task,
)
from todo_backend.repositories.proposal_batches import BatchDraft, ProposalDraft


_ID_NAMESPACE = UUID("8cd168ad-1114-4cb4-921a-18cd0ff0f395")


class ProposalVerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedMutation:
    task: Task | None = None
    pending: AssistantProposal | None = None

    def __post_init__(self) -> None:
        if self.task is not None and self.pending is not None:
            raise ValueError("resolved mutation has two targets")


def fields_from_task(task: Task) -> ProposalCardFields:
    return ProposalCardFields(
        text=task.text,
        priority=task.priority,
        category=task.category,
        time_start=task.time.start if task.time else None,
        time_end=task.time.end if task.time else None,
        notes=task.notes,
    )


def _overlay(
    before: ProposalCardFields, changes: PlannedFields
) -> ProposalCardFields:
    values = before.model_dump()
    for field_name in changes.model_fields_set:
        values[field_name] = getattr(changes, field_name)
    if "time_start" in changes.model_fields_set and changes.time_start is None:
        values["time_end"] = None
    return ProposalCardFields.model_validate(values)


def _stable_id(turn_id: str, kind: str, index: int) -> str:
    return uuid5(_ID_NAMESPACE, f"{turn_id}:{kind}:{index}").hex


def _single_source_batch(proposals: list[ProposalDraft]) -> str | None:
    source_ids = {
        proposal.source_batch_id
        for proposal in proposals
        if proposal.source_batch_id is not None
    }
    if len(source_ids) > 1:
        raise ProposalVerificationError("MULTIPLE_SUPERSEDED_BATCHES")
    return next(iter(source_ids), None)


def group_verified_drafts(
    turn_id: str,
    proposals: list[ProposalDraft],
) -> list[BatchDraft]:
    grouped: list[BatchDraft] = []
    editable = [proposal for proposal in proposals if proposal.action != "delete"]
    if editable:
        grouped.append(
            BatchDraft(
                id=_stable_id(turn_id, "batch", 0),
                supersedes_batch_id=_single_source_batch(editable),
                proposals=editable,
            )
        )
    for offset, proposal in enumerate(
        (item for item in proposals if item.action == "delete"),
        start=len(grouped),
    ):
        grouped.append(
            BatchDraft(
                id=_stable_id(turn_id, "batch", offset),
                supersedes_batch_id=proposal.source_batch_id,
                proposals=[proposal],
            )
        )
    return grouped


def _create_draft(
    proposal_id: str,
    item: PlannedMutation,
) -> ProposalDraft:
    text = item.fields.text
    if text is None:
        raise ProposalVerificationError("CREATE_TITLE_REQUIRED")
    payload = _overlay(
        ProposalCardFields(
            text=text,
            priority="medium",
            category="other",
            time_start=None,
            time_end=None,
            notes=None,
        ),
        item.fields,
    )
    return ProposalDraft(
        id=proposal_id,
        action="create",
        target_task_id=None,
        before_snapshot=None,
        payload=payload,
    )


def _real_target_draft(
    proposal_id: str,
    item: PlannedMutation,
    resolved: ResolvedMutation,
) -> ProposalDraft:
    if item.action == "create":
        return _create_draft(proposal_id, item)

    current = resolved.task
    if current is None:
        raise ProposalVerificationError("TARGET_REQUIRED")
    before = fields_from_task(current)
    if item.action == "update":
        return ProposalDraft(
            id=proposal_id,
            action="update",
            target_task_id=current.id,
            before_snapshot=current,
            payload=_overlay(before, item.fields),
        )
    return ProposalDraft(
        id=proposal_id,
        action="delete",
        target_task_id=current.id,
        before_snapshot=current,
        payload=before,
    )


def _pending_target_draft(
    proposal_id: str,
    item: PlannedMutation,
    pending: AssistantProposal,
) -> ProposalDraft:
    if (
        item.reference != pending.id
        or pending.status != "pending"
        or pending.payload is None
    ):
        raise ProposalVerificationError("PENDING_REFERENCE_ACTION_MISMATCH")

    if item.action == "update" and pending.action in {"create", "update"}:
        target_task_id = (
            None if pending.action == "create" else pending.target_task_id
        )
        before_snapshot = (
            None if pending.action == "create" else pending.before_snapshot
        )
        return ProposalDraft(
            id=proposal_id,
            action=pending.action,
            target_task_id=target_task_id,
            before_snapshot=before_snapshot,
            payload=_overlay(pending.payload, item.fields),
            source_batch_id=pending.batch_id,
            source_proposal_id=pending.id,
        )
    if item.action == "delete" and pending.action == "delete":
        return ProposalDraft(
            id=proposal_id,
            action="delete",
            target_task_id=pending.target_task_id,
            before_snapshot=pending.before_snapshot,
            payload=pending.payload,
            source_batch_id=pending.batch_id,
            source_proposal_id=pending.id,
        )
    raise ProposalVerificationError("PENDING_REFERENCE_ACTION_MISMATCH")


def _copied_pending_draft(
    proposal_id: str,
    pending: AssistantProposal,
) -> ProposalDraft:
    if pending.payload is None:
        raise ProposalVerificationError("TARGET_REQUIRED")
    return ProposalDraft(
        id=proposal_id,
        action=pending.action,
        target_task_id=pending.target_task_id,
        before_snapshot=pending.before_snapshot,
        payload=pending.payload,
        source_batch_id=pending.batch_id,
        source_proposal_id=pending.id,
    )


def build_batch_drafts(
    turn_id: str,
    plan: IntentPlan,
    resolved: list[ResolvedMutation],
    *,
    superseded_batch: AssistantProposalBatch | None,
) -> list[BatchDraft]:
    if plan.kind != "mutations":
        raise ValueError("proposal construction requires a mutation plan")
    if len(resolved) != len(plan.items):
        raise ValueError("resolved mutations must match planned items")

    referenced = [
        (item, resolution)
        for item, resolution in zip(plan.items, resolved, strict=True)
        if item.reference is not None
    ]
    unrelated = [
        (item, resolution)
        for item, resolution in zip(plan.items, resolved, strict=True)
        if item.reference is None
    ]
    referenced_pending = [
        resolution.pending
        for _, resolution in referenced
        if resolution.pending is not None
    ]
    source_batch_ids = {pending.batch_id for pending in referenced_pending}
    if superseded_batch is not None and referenced:
        source_batch_ids.add(superseded_batch.id)
    if len(source_batch_ids) > 1:
        raise ProposalVerificationError("MULTIPLE_SUPERSEDED_BATCHES")
    if referenced and (
        superseded_batch is None
        or len(referenced_pending) != len(referenced)
    ):
        raise ProposalVerificationError("TARGET_REQUIRED")

    proposals: list[ProposalDraft] = []

    def next_id() -> str:
        return _stable_id(turn_id, "proposal", len(proposals))

    for item, resolution in referenced:
        pending = resolution.pending
        if pending is None:
            raise ProposalVerificationError("TARGET_REQUIRED")
        proposals.append(_pending_target_draft(next_id(), item, pending))

    referenced_ids = {item.reference for item, _ in referenced}
    if superseded_batch is not None and referenced:
        for sibling in superseded_batch.proposals:
            if sibling.status == "pending" and sibling.id not in referenced_ids:
                proposals.append(_copied_pending_draft(next_id(), sibling))

    for item, resolution in unrelated:
        proposals.append(_real_target_draft(next_id(), item, resolution))

    source_ids = {
        proposal.source_batch_id
        for proposal in proposals
        if proposal.source_batch_id is not None
    }
    if len(source_ids) > 1:
        raise ProposalVerificationError("MULTIPLE_SUPERSEDED_BATCHES")

    drafts = group_verified_drafts(turn_id, proposals)
    verify_drafts(drafts)
    return drafts


def verify_drafts(drafts: list[BatchDraft]) -> None:
    proposal_ids: set[str] = set()
    source_proposal_ids: set[str] = set()
    source_batch_ids: set[str] = set()
    superseding_batches = 0

    for batch in drafts:
        if any(proposal.action == "delete" for proposal in batch.proposals) and (
            len(batch.proposals) != 1
            or batch.proposals[0].action != "delete"
        ):
            raise ProposalVerificationError("DELETE_BATCH_NOT_ISOLATED")

        batch_source_id = _single_source_batch(batch.proposals)
        if batch_source_id is not None:
            source_batch_ids.add(batch_source_id)
        if batch.supersedes_batch_id is not None:
            superseding_batches += 1
        if batch.supersedes_batch_id != batch_source_id:
            raise ProposalVerificationError("MULTIPLE_SUPERSEDED_BATCHES")

        for proposal in batch.proposals:
            if proposal.id in proposal_ids:
                raise ProposalVerificationError("DUPLICATE_PROPOSAL")
            proposal_ids.add(proposal.id)
            if proposal.source_proposal_id is not None:
                if proposal.source_proposal_id in source_proposal_ids:
                    raise ProposalVerificationError("DUPLICATE_PROPOSAL")
                source_proposal_ids.add(proposal.source_proposal_id)

            payload = proposal.payload
            if not payload.text.strip():
                raise ProposalVerificationError("CREATE_TITLE_REQUIRED")
            if proposal.action in {"update", "delete"} and (
                proposal.target_task_id is None
                or proposal.before_snapshot is None
            ):
                raise ProposalVerificationError("TARGET_REQUIRED")
            if payload.time_end is not None and payload.time_start is None:
                raise ProposalVerificationError("TIME_END_REQUIRES_START")
            if (
                payload.time_start is not None
                and payload.time_end is not None
                and payload.time_end < payload.time_start
            ):
                raise ProposalVerificationError("TIME_END_BEFORE_START")
            if (
                proposal.action == "update"
                and proposal.before_snapshot is not None
                and payload == fields_from_task(proposal.before_snapshot)
            ):
                raise ProposalVerificationError("UPDATE_HAS_NO_CHANGES")

    if len(source_batch_ids) > 1 or superseding_batches > 1:
        raise ProposalVerificationError("MULTIPLE_SUPERSEDED_BATCHES")
