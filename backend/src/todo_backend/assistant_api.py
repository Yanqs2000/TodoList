# pyright: reportUnusedFunction=false

from fastapi import APIRouter, File, Response, UploadFile, status

from todo_backend.models import (
    AssistantConversationDetail,
    AssistantConversationListResponse,
    AssistantConversationSummary,
    AssistantProposalResolveResponse,
    AssistantSettingsPatchCommand,
    AssistantSettingsView,
    AssistantTurnResponse,
    ConfirmProposalBatchCommand,
    ProposalBatchResolveResponse,
    SendAssistantMessageCommand,
    TranscribeCommand,
    TranscribeResponse,
    UploadResponse,
)
from todo_backend.services.assistant import MAX_UPLOAD_BYTES, AssistantService


def build_assistant_router(service: AssistantService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/assistant/conversations",
        response_model=AssistantConversationSummary,
        status_code=status.HTTP_201_CREATED,
    )
    def _create_conversation() -> AssistantConversationSummary:
        return service.create_conversation()

    @router.get(
        "/assistant/conversations",
        response_model=AssistantConversationListResponse,
    )
    def _list_conversations() -> AssistantConversationListResponse:
        return AssistantConversationListResponse(
            conversations=service.list_conversations()
        )

    @router.get(
        "/assistant/conversations/{conversation_id}",
        response_model=AssistantConversationDetail,
    )
    def _get_conversation(conversation_id: str) -> AssistantConversationDetail:
        return service.get_conversation_detail(conversation_id)

    @router.delete("/assistant/conversations/{conversation_id}", status_code=204)
    def _delete_conversation(conversation_id: str) -> Response:
        service.delete_conversation(conversation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/assistant/conversations/{conversation_id}/messages",
        response_model=AssistantTurnResponse,
    )
    def _send_message(
        conversation_id: str, command: SendAssistantMessageCommand
    ) -> AssistantTurnResponse:
        return service.send_message(conversation_id, command)

    @router.post(
        "/assistant/uploads",
        response_model=UploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def _upload(file: UploadFile = File(...)) -> UploadResponse:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        attachment = service.save_upload(file.filename or "upload", data)
        return UploadResponse(
            fileId=attachment.file_id,
            kind=attachment.kind,
            name=attachment.name,
            mime=attachment.mime,
        )

    @router.post("/assistant/transcribe", response_model=TranscribeResponse)
    def _transcribe(command: TranscribeCommand) -> TranscribeResponse:
        return TranscribeResponse(text=service.transcribe(command))

    @router.post(
        "/assistant/proposal-batches/{batch_id}/confirm",
        response_model=ProposalBatchResolveResponse,
    )
    def _confirm_batch(
        batch_id: str, command: ConfirmProposalBatchCommand
    ) -> ProposalBatchResolveResponse:
        return service.confirm_proposal_batch(batch_id, command)

    @router.post(
        "/assistant/proposal-batches/{batch_id}/reject",
        response_model=ProposalBatchResolveResponse,
    )
    def _reject_batch(batch_id: str) -> ProposalBatchResolveResponse:
        return service.reject_proposal_batch(batch_id)

    @router.post(
        "/assistant/proposals/{proposal_id}/accept",
        response_model=AssistantProposalResolveResponse,
        response_model_exclude_none=True,
    )
    def _accept_proposal(proposal_id: str) -> AssistantProposalResolveResponse:
        proposal, task = service.accept_proposal(proposal_id)
        return AssistantProposalResolveResponse(proposal=proposal, task=task)

    @router.post(
        "/assistant/proposals/{proposal_id}/reject",
        response_model=AssistantProposalResolveResponse,
        response_model_exclude_none=True,
    )
    def _reject_proposal(proposal_id: str) -> AssistantProposalResolveResponse:
        return AssistantProposalResolveResponse(
            proposal=service.reject_proposal(proposal_id), task=None
        )

    @router.get("/assistant/settings", response_model=AssistantSettingsView)
    def _get_settings() -> AssistantSettingsView:
        return service.get_settings_view()

    @router.put("/assistant/settings", response_model=AssistantSettingsView)
    def _put_settings(command: AssistantSettingsPatchCommand) -> AssistantSettingsView:
        return service.patch_settings(command)

    return router
