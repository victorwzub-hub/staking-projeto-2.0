from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from pharma_api.api.dependencies import CSRFProtectedAuth, DBSession, require_permission
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import (
    create_economic_group,
    update_economic_group,
)
from pharma_api.infrastructure.db.models.organizations import EconomicGroup
from pharma_api.schemas.common import MessageResponse
from pharma_api.schemas.organizations import (
    ArchiveRequest,
    EconomicGroupCreateRequest,
    EconomicGroupResponse,
    EconomicGroupUpdateRequest,
)

router = APIRouter(prefix="/economic-groups", tags=["economic-groups"])
Reader = Annotated[AuthContext, Depends(require_permission("company.read"))]
Creator = Annotated[AuthContext, Depends(require_permission("company.create"))]
Writer = Annotated[AuthContext, Depends(require_permission("company.update"))]
Deleter = Annotated[AuthContext, Depends(require_permission("company.delete"))]


@router.get("", response_model=list[EconomicGroupResponse])
async def list_economic_groups(session: DBSession, auth: Reader) -> list[EconomicGroupResponse]:
    groups = (
        await session.scalars(
            select(EconomicGroup)
            .where(EconomicGroup.tenant_id == auth.tenant_id)
            .order_by(EconomicGroup.name)
        )
    ).all()
    return [EconomicGroupResponse.model_validate(group) for group in groups]


@router.post("", response_model=EconomicGroupResponse, status_code=201)
async def post_economic_group(
    payload: EconomicGroupCreateRequest,
    request: Request,
    session: DBSession,
    auth: Creator,
    _csrf: CSRFProtectedAuth,
) -> EconomicGroupResponse:
    group = await create_economic_group(
        session,
        auth=auth,
        name=payload.name,
        correlation_id=request.state.correlation_id,
    )
    return EconomicGroupResponse.model_validate(group)


@router.patch("/{group_id}", response_model=EconomicGroupResponse)
async def patch_economic_group(
    group_id: UUID,
    payload: EconomicGroupUpdateRequest,
    request: Request,
    session: DBSession,
    auth: Writer,
    _csrf: CSRFProtectedAuth,
) -> EconomicGroupResponse:
    group = await update_economic_group(
        session,
        auth=auth,
        group_id=group_id,
        name=payload.name,
        status=payload.status,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return EconomicGroupResponse.model_validate(group)


@router.delete("/{group_id}", response_model=MessageResponse)
async def archive_economic_group(
    group_id: UUID,
    payload: ArchiveRequest,
    request: Request,
    session: DBSession,
    auth: Deleter,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await update_economic_group(
        session,
        auth=auth,
        group_id=group_id,
        name=None,
        status="archived",
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Economic group archived.")
