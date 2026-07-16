from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    require_permission,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import list_memberships, update_membership_status
from pharma_api.schemas.organizations import MembershipResponse, MembershipUpdateRequest

router = APIRouter(prefix="/memberships", tags=["memberships"])
Reader = Annotated[AuthContext, Depends(require_permission("user.read"))]
Manager = Annotated[AuthContext, Depends(require_permission("membership.manage"))]


@router.get("", response_model=list[MembershipResponse])
async def get_memberships(session: DBSession, auth: Reader) -> list[MembershipResponse]:
    return [
        MembershipResponse.model_validate(item) for item in await list_memberships(session, auth)
    ]


@router.patch("/{membership_id}", response_model=MembershipResponse)
async def patch_membership(
    membership_id: UUID,
    payload: MembershipUpdateRequest,
    request: Request,
    session: DBSession,
    auth: Manager,
    _csrf: CSRFProtectedAuth,
) -> MembershipResponse:
    await update_membership_status(
        session,
        auth=auth,
        membership_id=membership_id,
        status=payload.status,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    items = await list_memberships(session, auth)
    item = next(value for value in items if value["id"] == membership_id)
    return MembershipResponse.model_validate(item)
