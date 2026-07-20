from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update

from pharma_api.api.dependencies import CSRFProtectedAuth, DBSession, require_permission
from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.identity import Session, User, UserProfile
from pharma_api.infrastructure.db.models.organizations import Tenant
from pharma_api.schemas.common import Page
from pharma_api.schemas.organizations import TenantResponse
from pharma_api.schemas.platform import PlatformUserResponse, PlatformUserStatusRequest

router = APIRouter(prefix="/platform", tags=["platform-administration"])
PlatformAdmin = Annotated[AuthContext, Depends(require_permission("platform.admin"))]


@router.get("/tenants", response_model=Page[TenantResponse])
async def list_platform_tenants(
    session: DBSession,
    _auth: PlatformAdmin,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TenantResponse]:
    total = int(await session.scalar(select(func.count()).select_from(Tenant)) or 0)
    tenants = (
        await session.scalars(
            select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return Page(
        items=[TenantResponse.model_validate(item) for item in tenants],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users", response_model=Page[PlatformUserResponse])
async def list_platform_users(
    session: DBSession,
    _auth: PlatformAdmin,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PlatformUserResponse]:
    total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    rows = (
        await session.execute(
            select(User, UserProfile)
            .join(UserProfile, UserProfile.user_id == User.id)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page(
        items=[
            PlatformUserResponse(
                id=user.id,
                email=user.email,
                display_name=profile.display_name,
                status=user.status,
                email_verified_at=user.email_verified_at,
                is_platform_admin=user.is_platform_admin,
                version=user.version,
                created_at=user.created_at,
            )
            for user, profile in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}/status", response_model=PlatformUserResponse)
async def update_platform_user_status(
    user_id: UUID,
    payload: PlatformUserStatusRequest,
    request: Request,
    session: DBSession,
    auth: PlatformAdmin,
    _csrf: CSRFProtectedAuth,
) -> PlatformUserResponse:
    user = await session.get(User, user_id, with_for_update=True)
    profile = await session.get(UserProfile, user_id)
    if user is None or profile is None:
        raise AppError(code="not_found", message="Resource not found", status_code=404)
    if user.id == auth.user.id and payload.status == "suspended":
        raise AppError(
            code="self_suspension_forbidden",
            message="A platform administrator cannot suspend the current account",
            status_code=409,
        )
    if user.is_platform_admin and payload.status == "suspended":
        remaining = int(
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.is_platform_admin.is_(True),
                    User.status == "active",
                    User.id != user.id,
                )
            )
            or 0
        )
        if remaining == 0:
            raise AppError(
                code="last_platform_admin",
                message="The final active platform administrator cannot be suspended",
                status_code=409,
            )
    if user.version != payload.expected_version:
        raise AppError(
            code="version_conflict",
            message="The user was modified by another request",
            status_code=409,
        )
    previous = user.status
    user.status = payload.status
    user.version += 1
    if payload.status == "suspended":
        now = datetime.now(UTC)
        await session.execute(
            update(Session)
            .where(Session.user_id == user.id, Session.revoked_at.is_(None))
            .values(revoked_at=now, revocation_reason="account_suspended")
        )
    await append_audit_event(
        session,
        AuditRecord(
            action="platform.user.status_changed",
            category="platform_administration",
            outcome="success",
            actor_user_id=auth.user.id,
            effective_user_id=auth.user.id,
            resource_type="user",
            resource_id=str(user.id),
            correlation_id=request.state.correlation_id,
            changed_fields=["status"],
            justification=payload.reason,
            metadata={"previous_status": previous, "new_status": user.status},
        ),
    )
    return PlatformUserResponse(
        id=user.id,
        email=user.email,
        display_name=profile.display_name,
        status=user.status,
        email_verified_at=user.email_verified_at,
        is_platform_admin=user.is_platform_admin,
        version=user.version,
        created_at=user.created_at,
    )
