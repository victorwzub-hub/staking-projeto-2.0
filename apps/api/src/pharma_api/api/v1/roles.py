from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from pharma_api.api.dependencies import (
    CSRFProtectedAuth,
    DBSession,
    require_permission,
    require_tenant_permission,
)
from pharma_api.application.auth.scope_filters import role_assignment_visibility_filter
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.rbac.service import (
    assign_role,
    create_role,
    delete_role,
    list_roles,
    remove_role_assignment,
    update_role,
)
from pharma_api.infrastructure.db.models.rbac import RoleAssignment
from pharma_api.schemas.common import MessageResponse
from pharma_api.schemas.rbac import (
    RoleAssignmentRequest,
    RoleAssignmentResponse,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
)

router = APIRouter(prefix="/roles", tags=["roles"])
Reader = Annotated[AuthContext, Depends(require_permission("role.read"))]
Creator = Annotated[AuthContext, Depends(require_tenant_permission("role.create"))]
Updater = Annotated[AuthContext, Depends(require_tenant_permission("role.update"))]
Deleter = Annotated[AuthContext, Depends(require_tenant_permission("role.delete"))]
Assigner = Annotated[AuthContext, Depends(require_permission("role.assign"))]


@router.get("", response_model=list[RoleResponse])
async def get_roles(session: DBSession, auth: Reader) -> list[RoleResponse]:
    roles = await list_roles(session, auth)
    return [
        RoleResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            slug=role.slug,
            scope=role.scope,
            is_system=role.is_system,
            is_editable=role.is_editable,
            version=role.version,
            permissions=permissions,
        )
        for role, permissions in roles
    ]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def post_role(
    payload: RoleCreateRequest,
    request: Request,
    session: DBSession,
    auth: Creator,
    _csrf: CSRFProtectedAuth,
) -> RoleResponse:
    role = await create_role(
        session,
        auth=auth,
        name=payload.name,
        slug=payload.slug,
        scope=payload.scope,
        description=payload.description,
        permission_keys=payload.permission_keys,
        correlation_id=request.state.correlation_id,
    )
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        slug=role.slug,
        scope=role.scope,
        is_system=role.is_system,
        is_editable=role.is_editable,
        version=role.version,
        permissions=sorted(payload.permission_keys),
    )


@router.patch("/{role_id}", response_model=RoleResponse)
async def patch_role(
    role_id: UUID,
    payload: RoleUpdateRequest,
    request: Request,
    session: DBSession,
    auth: Updater,
    _csrf: CSRFProtectedAuth,
) -> RoleResponse:
    role = await update_role(
        session,
        auth=auth,
        role_id=role_id,
        name=payload.name,
        description=payload.description,
        permission_keys=payload.permission_keys,
        expected_version=payload.expected_version,
        correlation_id=request.state.correlation_id,
    )
    roles = {item.id: permissions for item, permissions in await list_roles(session, auth)}
    return RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        slug=role.slug,
        scope=role.scope,
        is_system=role.is_system,
        is_editable=role.is_editable,
        version=role.version,
        permissions=roles[role.id],
    )


@router.delete("/{role_id}", response_model=MessageResponse)
async def remove_role(
    role_id: UUID,
    request: Request,
    session: DBSession,
    auth: Deleter,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await delete_role(
        session,
        auth=auth,
        role_id=role_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Role deleted.")


@router.get("/assignments", response_model=list[RoleAssignmentResponse])
async def get_role_assignments(
    session: DBSession,
    auth: Reader,
    membership_id: UUID | None = None,
) -> list[RoleAssignmentResponse]:
    statement = select(RoleAssignment).where(role_assignment_visibility_filter(auth, "role.read"))
    if membership_id is not None:
        statement = statement.where(RoleAssignment.membership_id == membership_id)
    assignments = (await session.scalars(statement.order_by(RoleAssignment.created_at))).all()
    return [RoleAssignmentResponse.model_validate(item) for item in assignments]


@router.post("/assignments", response_model=MessageResponse, status_code=201)
async def post_role_assignment(
    payload: RoleAssignmentRequest,
    request: Request,
    session: DBSession,
    auth: Assigner,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await assign_role(
        session,
        auth=auth,
        membership_id=payload.membership_id,
        role_id=payload.role_id,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Role assigned.")


@router.delete("/assignments/{assignment_id}", response_model=MessageResponse)
async def delete_role_assignment(
    assignment_id: UUID,
    request: Request,
    session: DBSession,
    auth: Assigner,
    _csrf: CSRFProtectedAuth,
) -> MessageResponse:
    await remove_role_assignment(
        session,
        auth=auth,
        assignment_id=assignment_id,
        correlation_id=request.state.correlation_id,
    )
    return MessageResponse(message="Role assignment removed.")
