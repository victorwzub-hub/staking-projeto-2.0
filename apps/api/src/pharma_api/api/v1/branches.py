from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from pharma_api.api.dependencies import CSRFProtectedAuth, DBSession, require_permission
from pharma_api.application.auth.scope_filters import branch_visibility_filter
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.organizations.service import (
    archive_branch,
    create_branch,
    update_branch,
)
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.organizations import Branch
from pharma_api.schemas.common import MessageResponse
from pharma_api.schemas.organizations import (
    ArchiveRequest,
    BranchCreateRequest,
    BranchResponse,
    BranchUpdateRequest,
)

router = APIRouter(prefix="/branches", tags=["branches"])
Reader = Annotated[AuthContext, Depends(require_permission("branch.read"))]
Creator = Annotated[AuthContext, Depends(require_permission("branch.create"))]
Writer = Annotated[AuthContext, Depends(require_permission("branch.update"))]
Deleter = Annotated[AuthContext, Depends(require_permission("branch.delete"))]


@router.get("", response_model=list[BranchResponse])
async def list_branches(
    session: DBSession, auth: Reader, company_id: UUID | None = None
) -> list[BranchResponse]:
    statement = select(Branch).where(branch_visibility_filter(auth, "branch.read"))
    if company_id is not None:
        statement = statement.where(Branch.company_id == company_id)
    branches = (await session.scalars(statement.order_by(Branch.name))).all()
    return [BranchResponse.model_validate(branch) for branch in branches]


@router.get("/{branch_id}", response_model=BranchResponse)
async def get_branch(branch_id: UUID, session: DBSession, auth: Reader) -> BranchResponse:
    branch = await session.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            branch_visibility_filter(auth, "branch.read"),
        )
    )
    if branch is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    return BranchResponse.model_validate(branch)


@router.post("", response_model=BranchResponse, status_code=201)
async def post_branch(
    payload: BranchCreateRequest,
    request: Request,
    session: DBSession,
    auth: Creator,
    _csrf: CSRFProtectedAuth,
) -> BranchResponse:
    branch = await create_branch(
        session,
        auth=auth,
        company_id=payload.company_id,
        name=payload.name,
        slug=payload.slug,
        correlation_id=request.state.correlation_id,
    )
    return BranchResponse.model_validate(branch)


@router.patch("/{branch_id}", response_model=BranchResponse)
async def patch_branch(
    branch_id: UUID,
    payload: BranchUpdateRequest,
    request: Request,
    session: DBSession,
    auth: Writer,
    _csrf: CSRFProtectedAuth,
) -> BranchResponse:
    branch = await update_branch(
        session,
        auth=auth,
        branch_id=branch_id,
        name=payload.name,
        status=payload.status,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return BranchResponse.model_validate(branch)


@router.delete("/{branch_id}", response_model=MessageResponse)
async def delete_branch(
    branch_id: UUID,
    payload: ArchiveRequest,
    request: Request,
    session: DBSession,
    auth: Deleter,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await archive_branch(
        session,
        auth=auth,
        branch_id=branch_id,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Branch archived.")
