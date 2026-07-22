import pytest

from todo_backend.agent.planning import (
    IntentPlan,
    PlannedMutation,
    TargetQuery,
)
from todo_backend.agent.proposals import (
    ProposalVerificationError,
    ResolvedMutation,
    build_batch_drafts,
    verify_drafts,
)
from todo_backend.models import (
    AssistantProposal,
    AssistantProposalBatch,
    Category,
    LocalDateTime,
    PlannedFields,
    Priority,
    ProposalAction,
    ProposalCardFields,
    ProposalStatus,
    Task,
    TimeField,
)
from todo_backend.repositories.proposal_batches import BatchDraft, ProposalDraft


def task(
    task_id: str,
    text: str,
    *,
    start: LocalDateTime | None = None,
    end: LocalDateTime | None = None,
    priority: Priority = "medium",
    category: Category = "other",
    notes: str | None = None,
) -> Task:
    return Task(
        id=task_id,
        text=text,
        completed=False,
        priority=priority,
        createdAt=1,
        time=TimeField(start=start, end=end) if start is not None else None,
        category=category,
        notes=notes,
    )


def card(
    text: str,
    *,
    priority: Priority = "medium",
    category: Category = "other",
    time_start: LocalDateTime | None = None,
    time_end: LocalDateTime | None = None,
    notes: str | None = None,
) -> ProposalCardFields:
    return ProposalCardFields(
        text=text,
        priority=priority,
        category=category,
        time_start=time_start,
        time_end=time_end,
        notes=notes,
    )


def pending_proposal(
    proposal_id: str,
    batch_id: str,
    action: ProposalAction,
    payload: ProposalCardFields,
    *,
    target: Task | None = None,
    status: ProposalStatus = "pending",
) -> AssistantProposal:
    return AssistantProposal.model_validate(
        {
            "id": proposal_id,
            "messageId": "message-old",
            "batchId": batch_id,
            "action": action,
            "targetTaskId": target.id if target is not None else None,
            "beforeSnapshot": target,
            "payload": payload,
            "resultTaskId": None,
            "status": status,
            "lastError": None,
            "createdAt": 1,
        }
    )


def pending_batch(
    batch_id: str, proposals: list[AssistantProposal]
) -> AssistantProposalBatch:
    return AssistantProposalBatch(
        id=batch_id,
        messageId="message-old",
        status="pending",
        supersedesBatchId=None,
        proposals=proposals,
        createdAt=1,
        resolvedAt=None,
    )


def pending_create_batch(
    items: list[tuple[str, str]],
    *,
    batch_id: str,
    hour: int | None = None,
) -> AssistantProposalBatch:
    time_start = (
        f"2026-07-22T{hour:02d}:00" if hour is not None else None
    )
    return pending_batch(
        batch_id,
        [
            pending_proposal(
                proposal_id,
                batch_id,
                "create",
                card(text, time_start=time_start),
            )
            for proposal_id, text in items
        ],
    )


def pending_update_batch(
    batch_id: str = "b-old", proposal_id: str = "p-old"
) -> AssistantProposalBatch:
    current = task(
        "t1",
        "会议",
        start="2026-07-22T15:00",
        end="2026-07-22T16:00",
        priority="high",
        category="work",
    )
    proposal = pending_proposal(
        proposal_id,
        batch_id,
        "update",
        card(
            "会议（已改）",
            priority="high",
            category="work",
            time_start="2026-07-22T15:00",
            time_end="2026-07-22T16:00",
        ),
        target=current,
    )
    return pending_batch(batch_id, [proposal])


def pending_delete_batch(
    batch_id: str, proposal_id: str, task_id: str
) -> AssistantProposalBatch:
    current = task(task_id, "待删除")
    return pending_batch(
        batch_id,
        [
            pending_proposal(
                proposal_id,
                batch_id,
                "delete",
                card(current.text),
                target=current,
            )
        ],
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


def planned_delete(
    target: TargetQuery | None = None, *, reference: str | None = None
) -> PlannedMutation:
    return PlannedMutation(
        action="delete",
        target_query=target,
        reference=reference,
    )


def create_plan(text: str, **changes: object) -> IntentPlan:
    return mutation_plan([planned_create(text, **changes)])


def update_plan(target: TargetQuery, fields: PlannedFields) -> IntentPlan:
    return mutation_plan(
        [PlannedMutation(action="update", target_query=target, fields=fields)]
    )


def test_update_end_only_preserves_snapshot_start() -> None:
    current = task(
        "t1", "会议", start="2026-07-22T15:00", end="2026-07-22T16:00"
    )
    plan = update_plan(
        TargetQuery(title="会议"), PlannedFields(time_end="2026-07-22T17:00")
    )

    drafts = build_batch_drafts(
        "turn-1", plan, [ResolvedMutation(task=current)], superseded_batch=None
    )

    proposal = drafts[0].proposals[0]
    assert proposal.before_snapshot == current
    assert proposal.payload.time_start == "2026-07-22T15:00"
    assert proposal.payload.time_end == "2026-07-22T17:00"


def test_clearing_start_also_clears_snapshot_end() -> None:
    current = task(
        "t1", "会议", start="2026-07-22T15:00", end="2026-07-22T16:00"
    )
    plan = update_plan(
        TargetQuery(title="会议"), PlannedFields(time_start=None)
    )

    drafts = build_batch_drafts(
        "turn-1", plan, [ResolvedMutation(task=current)], superseded_batch=None
    )

    assert drafts[0].proposals[0].payload.time_start is None
    assert drafts[0].proposals[0].payload.time_end is None


def test_create_and_update_share_one_batch_but_deletes_are_isolated() -> None:
    current = task("t1", "旧任务")
    second = task("t2", "第二个旧任务")
    plan = mutation_plan(
        [
            planned_create("新任务"),
            planned_update(TargetQuery(referenced_task_id="t1"), text="已修改"),
            planned_delete(TargetQuery(referenced_task_id="t1")),
            planned_delete(TargetQuery(referenced_task_id="t2")),
        ]
    )

    drafts = build_batch_drafts(
        "turn-1",
        plan,
        [
            ResolvedMutation(),
            ResolvedMutation(task=current),
            ResolvedMutation(task=current),
            ResolvedMutation(task=second),
        ],
        superseded_batch=None,
    )

    assert [len(batch.proposals) for batch in drafts] == [2, 1, 1]
    assert [proposal.action for proposal in drafts[0].proposals] == [
        "create",
        "update",
    ]
    assert all(
        batch.proposals[0].action == "delete" for batch in drafts[1:]
    )


def test_create_has_complete_default_payload() -> None:
    drafts = build_batch_drafts(
        "turn-1", create_plan("买菜"), [ResolvedMutation()], superseded_batch=None
    )

    assert drafts[0].proposals[0].payload == card("买菜")


def test_create_overlays_every_explicit_field() -> None:
    drafts = build_batch_drafts(
        "turn-1",
        create_plan(
            "项目复盘",
            priority="high",
            category="work",
            time_start="2026-07-22T15:00",
            time_end="2026-07-22T16:00",
            notes="准备纪要",
        ),
        [ResolvedMutation()],
        superseded_batch=None,
    )

    assert drafts[0].proposals[0].payload == card(
        "项目复盘",
        priority="high",
        category="work",
        time_start="2026-07-22T15:00",
        time_end="2026-07-22T16:00",
        notes="准备纪要",
    )


def test_update_overlays_every_explicit_field() -> None:
    current = task("t1", "旧任务", notes="旧备注")
    plan = update_plan(
        TargetQuery(title="旧任务"),
        PlannedFields(
            text="新任务",
            priority="high",
            category="work",
            time_start="2026-07-22T15:00",
            time_end="2026-07-22T16:00",
            notes="新备注",
        ),
    )

    drafts = build_batch_drafts(
        "turn-1", plan, [ResolvedMutation(task=current)], superseded_batch=None
    )

    assert drafts[0].proposals[0].payload == card(
        "新任务",
        priority="high",
        category="work",
        time_start="2026-07-22T15:00",
        time_end="2026-07-22T16:00",
        notes="新备注",
    )


def test_update_reference_to_pending_create_builds_superseding_create() -> None:
    old_batch = pending_create_batch(
        [("p-old", "开会")], batch_id="b-old", hour=15
    )
    pending = old_batch.proposals[0]
    plan = mutation_plan(
        [planned_update(reference="p-old", time_start="2026-07-22T16:00")]
    )

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [ResolvedMutation(pending=pending)],
        superseded_batch=old_batch,
    )

    proposal = drafts[0].proposals[0]
    assert proposal.action == "create"
    assert proposal.target_task_id is None
    assert proposal.payload.text == "开会"
    assert proposal.payload.time_start == "2026-07-22T16:00"
    assert proposal.source_batch_id == "b-old"
    assert proposal.source_proposal_id == "p-old"
    assert drafts[0].supersedes_batch_id == "b-old"


def test_update_reference_to_pending_update_retains_original_snapshot() -> None:
    old_batch = pending_update_batch()
    pending = old_batch.proposals[0]
    plan = mutation_plan(
        [planned_update(reference="p-old", notes="补充说明")]
    )

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [ResolvedMutation(pending=pending)],
        superseded_batch=old_batch,
    )

    proposal = drafts[0].proposals[0]
    assert proposal.action == "update"
    assert proposal.target_task_id == pending.target_task_id
    assert proposal.before_snapshot == pending.before_snapshot
    assert proposal.payload.text == "会议（已改）"
    assert proposal.payload.notes == "补充说明"


def test_delete_reference_to_pending_delete_reproduces_complete_draft() -> None:
    old_batch = pending_delete_batch("b-old", "p-old", "t1")
    pending = old_batch.proposals[0]
    plan = mutation_plan([planned_delete(reference="p-old")])

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [ResolvedMutation(pending=pending)],
        superseded_batch=old_batch,
    )

    proposal = drafts[0].proposals[0]
    assert proposal.action == "delete"
    assert proposal.target_task_id == "t1"
    assert proposal.before_snapshot == pending.before_snapshot
    assert proposal.payload == pending.payload
    assert drafts[0].supersedes_batch_id == "b-old"


def test_referenced_edit_copies_unmentioned_pending_sibling() -> None:
    old_batch = pending_create_batch(
        [("p-a", "A"), ("p-b", "B")], batch_id="b-old"
    )
    plan = mutation_plan(
        [planned_update(reference="p-a", notes="只修改 A")]
    )

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [ResolvedMutation(pending=old_batch.proposals[0])],
        superseded_batch=old_batch,
    )

    assert [proposal.payload.text for proposal in drafts[0].proposals] == [
        "A",
        "B",
    ]
    assert drafts[0].proposals[0].payload.notes == "只修改 A"
    assert drafts[0].proposals[1].payload == old_batch.proposals[1].payload
    assert drafts[0].proposals[1].source_proposal_id == "p-b"
    assert drafts[0].supersedes_batch_id == old_batch.id


def test_copy_forward_skips_sibling_that_is_no_longer_pending() -> None:
    old_batch = pending_create_batch(
        [("p-a", "A"), ("p-b", "B")], batch_id="b-old"
    )
    accepted = old_batch.proposals[1].model_copy(update={"status": "accepted"})
    old_batch = old_batch.model_copy(
        update={"proposals": [old_batch.proposals[0], accepted]}
    )
    plan = mutation_plan([planned_update(reference="p-a", notes="只修改 A")])

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [ResolvedMutation(pending=old_batch.proposals[0])],
        superseded_batch=old_batch,
    )

    assert [proposal.payload.text for proposal in drafts[0].proposals] == ["A"]


def test_unrelated_group_does_not_steal_supersedes_link() -> None:
    old_delete = pending_delete_batch("b-old", "p-old", "t1")
    plan = mutation_plan(
        [planned_create("无关新任务"), planned_delete(reference="p-old")]
    )

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [
            ResolvedMutation(),
            ResolvedMutation(pending=old_delete.proposals[0]),
        ],
        superseded_batch=old_delete,
    )

    assert drafts[0].proposals[0].action == "create"
    assert drafts[0].supersedes_batch_id is None
    assert drafts[1].proposals[0].action == "delete"
    assert drafts[1].supersedes_batch_id == "b-old"


def test_pending_correction_and_new_create_share_replacement_batch() -> None:
    old_batch = pending_create_batch(
        [("p-a", "A"), ("p-b", "B")], batch_id="b-old"
    )
    plan = mutation_plan(
        [
            planned_update(reference="p-a", notes="修正 A"),
            planned_create("C"),
        ]
    )

    drafts = build_batch_drafts(
        "turn-2",
        plan,
        [ResolvedMutation(pending=old_batch.proposals[0]), ResolvedMutation()],
        superseded_batch=old_batch,
    )

    assert len(drafts) == 1
    assert [item.payload.text for item in drafts[0].proposals] == ["A", "B", "C"]
    assert drafts[0].supersedes_batch_id == "b-old"


def test_update_noop_is_rejected() -> None:
    current = task("t1", "会议")

    with pytest.raises(ProposalVerificationError, match="UPDATE_HAS_NO_CHANGES"):
        build_batch_drafts(
            "turn-1",
            update_plan(
                TargetQuery(title="会议"), PlannedFields(text="会议")
            ),
            [ResolvedMutation(task=current)],
            superseded_batch=None,
        )


def test_stable_ids_repeat_for_same_turn() -> None:
    first = build_batch_drafts(
        "turn-1", create_plan("买菜"), [ResolvedMutation()], superseded_batch=None
    )
    second = build_batch_drafts(
        "turn-1", create_plan("买菜"), [ResolvedMutation()], superseded_batch=None
    )

    assert first[0].id == second[0].id
    assert first[0].proposals[0].id == second[0].proposals[0].id


def test_blank_title_is_rejected() -> None:
    with pytest.raises(ProposalVerificationError, match="CREATE_TITLE_REQUIRED"):
        build_batch_drafts(
            "turn-1", create_plan("   "), [ResolvedMutation()], superseded_batch=None
        )


def test_end_without_start_is_rejected() -> None:
    with pytest.raises(
        ProposalVerificationError, match="TIME_END_REQUIRES_START"
    ):
        build_batch_drafts(
            "turn-1",
            create_plan("会议", time_end="2026-07-22T17:00"),
            [ResolvedMutation()],
            superseded_batch=None,
        )


def test_end_before_start_is_rejected() -> None:
    with pytest.raises(ProposalVerificationError, match="TIME_END_BEFORE_START"):
        build_batch_drafts(
            "turn-1",
            create_plan(
                "会议",
                time_start="2026-07-22T17:00",
                time_end="2026-07-22T16:00",
            ),
            [ResolvedMutation()],
            superseded_batch=None,
        )


@pytest.mark.parametrize(
    "item",
    [
        planned_update(TargetQuery(title="会议"), text="新会议"),
        planned_delete(TargetQuery(title="会议")),
    ],
)
def test_real_update_and_delete_require_resolved_targets(
    item: PlannedMutation,
) -> None:
    with pytest.raises(ProposalVerificationError, match="TARGET_REQUIRED"):
        build_batch_drafts(
            "turn-1",
            mutation_plan([item]),
            [ResolvedMutation()],
            superseded_batch=None,
        )


def test_delete_contains_complete_before_snapshot_and_payload() -> None:
    current = task(
        "t1",
        "会议",
        start="2026-07-22T15:00",
        end="2026-07-22T16:00",
        priority="high",
        category="work",
        notes="纪要",
    )
    plan = mutation_plan([planned_delete(TargetQuery(title="会议"))])

    drafts = build_batch_drafts(
        "turn-1", plan, [ResolvedMutation(task=current)], superseded_batch=None
    )

    proposal = drafts[0].proposals[0]
    assert proposal.before_snapshot == current
    assert proposal.payload == card(
        "会议",
        priority="high",
        category="work",
        time_start="2026-07-22T15:00",
        time_end="2026-07-22T16:00",
        notes="纪要",
    )


@pytest.mark.parametrize(
    ("item", "old_batch"),
    [
        (
            planned_update(reference="p-old", notes="不兼容"),
            pending_delete_batch("b-delete", "p-old", "t1"),
        ),
        (
            planned_delete(reference="p-old"),
            pending_create_batch(
                [("p-old", "A")], batch_id="b-create"
            ),
        ),
        (
            planned_delete(reference="p-old"),
            pending_update_batch("b-update", "p-old"),
        ),
    ],
)
def test_pending_reference_action_mismatch_is_rejected(
    item: PlannedMutation, old_batch: AssistantProposalBatch
) -> None:
    with pytest.raises(
        ProposalVerificationError, match="PENDING_REFERENCE_ACTION_MISMATCH"
    ):
        build_batch_drafts(
            "turn-2",
            mutation_plan([item]),
            [ResolvedMutation(pending=old_batch.proposals[0])],
            superseded_batch=old_batch,
        )


def test_references_spanning_old_batches_are_rejected() -> None:
    first = pending_create_batch([("p-a", "A")], batch_id="b-a")
    second = pending_create_batch([("p-b", "B")], batch_id="b-b")
    plan = mutation_plan(
        [
            planned_update(reference="p-a", notes="改 A"),
            planned_update(reference="p-b", notes="改 B"),
        ]
    )

    with pytest.raises(
        ProposalVerificationError, match="MULTIPLE_SUPERSEDED_BATCHES"
    ):
        build_batch_drafts(
            "turn-2",
            plan,
            [
                ResolvedMutation(pending=first.proposals[0]),
                ResolvedMutation(pending=second.proposals[0]),
            ],
            superseded_batch=first,
        )


def test_verify_drafts_rejects_duplicate_proposal_ids() -> None:
    proposal = ProposalDraft(
        id="duplicate",
        action="create",
        target_task_id=None,
        before_snapshot=None,
        payload=card("A"),
    )

    with pytest.raises(ProposalVerificationError, match="DUPLICATE_PROPOSAL"):
        verify_drafts(
            [
                BatchDraft(
                    id="batch",
                    supersedes_batch_id=None,
                    proposals=[proposal, proposal],
                )
            ]
        )


def test_verify_drafts_rejects_delete_mixed_with_other_actions() -> None:
    current = task("t1", "删除")
    delete = ProposalDraft(
        id="delete",
        action="delete",
        target_task_id=current.id,
        before_snapshot=current,
        payload=card(current.text),
    )
    create = ProposalDraft(
        id="create",
        action="create",
        target_task_id=None,
        before_snapshot=None,
        payload=card("新增"),
    )

    with pytest.raises(
        ProposalVerificationError, match="DELETE_BATCH_NOT_ISOLATED"
    ):
        verify_drafts(
            [
                BatchDraft(
                    id="batch",
                    supersedes_batch_id=None,
                    proposals=[delete, create],
                )
            ]
        )
