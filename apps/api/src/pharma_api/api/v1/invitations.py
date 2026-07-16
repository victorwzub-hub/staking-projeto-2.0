from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from pharma_api.api.dependencies import CSRFProtectedAuth, DBSession, require_permission
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.email.service import EmailCommand, enqueue_email
from pharma_api.application.organizations.service import (
    accept_invitation,
    create_invitation,
    resend_invitation,
    revoke_invitation_record,
)
from pharma_api.core.logging import get_logger
from pharma_api.infrastructure.db.models.operations import Invitation
from pharma_api.schemas.common import MessageResponse
from pharma_api.schemas.organizations import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    InvitationResponse,
)

router = APIRouter(prefix="/invitations", tags=["invitations"])
Inviter = Annotated[AuthContext, Depends(require_permission("user.invite"))]
Reader = Annotated[AuthContext, Depends(require_permission("user.read"))]
logger = get_logger(__name__)


def _dispatch(command: EmailCommand) -> None:
    try:
        enqueue_email(command)
    except Exception as exc:
        logger.error("invitation_email_enqueue_failed", error_type=type(exc).__name__)


@router.get("", response_model=list[InvitationResponse])
async def list_invitations(session: DBSession, auth: Reader) -> list[InvitationResponse]:
    invitations = (
        await session.scalars(
            select(Invitation)
            .where(Invitation.tenant_id == auth.tenant_id)
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    return [InvitationResponse.model_validate(invitation) for invitation in invitations]


@router.post("", response_model=InvitationResponse, status_code=201)
async def post_invitation(
    payload: InvitationCreateRequest,
    request: Request,
    session: DBSession,
    auth: Inviter,
    _csrf: CSRFProtectedAuth,
) -> InvitationResponse:
    invitation, command = await create_invitation(
        session,
        auth=auth,
        email=str(payload.email),
        role_id=payload.role_id,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    _dispatch(command)
    return InvitationResponse.model_validate(invitation)


@router.post("/{invitation_id}/resend", response_model=InvitationResponse)
async def post_resend_invitation(
    invitation_id: UUID,
    request: Request,
    session: DBSession,
    auth: Inviter,
    _csrf: CSRFProtectedAuth,
) -> InvitationResponse:
    invitation, command = await resend_invitation(
        session,
        auth=auth,
        invitation_id=invitation_id,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    _dispatch(command)
    return InvitationResponse.model_validate(invitation)


@router.post("/accept", response_model=MessageResponse)
async def post_accept_invitation(
    payload: InvitationAcceptRequest,
    request: Request,
    session: DBSession,
    auth: CSRFProtectedAuth,
) -> MessageResponse:
    await accept_invitation(
        session,
        auth=auth,
        raw_token=payload.token,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Invitation accepted.")


@router.delete("/{invitation_id}", response_model=MessageResponse)
async def revoke_invitation(
    invitation_id: UUID,
    request: Request,
    session: DBSession,
    auth: Inviter,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await revoke_invitation_record(
        session,
        auth=auth,
        invitation_id=invitation_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Invitation revoked.")
