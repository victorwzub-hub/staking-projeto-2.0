from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.application.auth.rate_limit import LoginRateLimiter, PublicAuthRateLimiter
from pharma_api.application.auth.service import RequestMetadata
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import AppError
from pharma_api.core.security import (
    constant_time_equal,
    hash_sensitive_identifier,
    hash_session_token,
    safe_user_agent,
)
from pharma_api.infrastructure.cache.redis import get_redis_client
from pharma_api.infrastructure.db.context import RLSContext, apply_rls_context
from pharma_api.infrastructure.db.models.identity import SecurityEvent, Session, User, UserProfile
from pharma_api.infrastructure.db.models.organizations import Membership
from pharma_api.infrastructure.db.models.rbac import (
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
)
from pharma_api.infrastructure.db.session import get_session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DBSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_request_metadata(request: Request) -> RequestMetadata:
    return RequestMetadata(
        correlation_id=request.state.correlation_id
        if hasattr(request.state, "correlation_id")
        else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


async def _resolve_permissions(
    session: AsyncSession,
    *,
    user: User,
    membership: Membership | None,
    auth_session: Session,
) -> frozenset[str]:
    if user.is_platform_admin:
        keys = await session.scalars(select(Permission.key))
        return frozenset(keys.all())
    if membership is None or auth_session.active_tenant_id is None:
        return frozenset()

    statement = (
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(RoleAssignment, RoleAssignment.role_id == Role.id)
        .where(
            RoleAssignment.membership_id == membership.id,
            RoleAssignment.tenant_id == auth_session.active_tenant_id,
            or_(
                RoleAssignment.company_id.is_(None),
                RoleAssignment.company_id == auth_session.active_company_id,
            ),
            or_(
                RoleAssignment.branch_id.is_(None),
                RoleAssignment.branch_id == auth_session.active_branch_id,
            ),
        )
        .distinct()
    )
    return frozenset((await session.scalars(statement)).all())


def _record_session_security_event(
    session: AsyncSession,
    *,
    request: Request,
    user_id: UUID | None,
    event_type: str,
    reason: str,
) -> None:
    session.add(
        SecurityEvent(
            id=uuid4(),
            user_id=user_id,
            event_type=event_type,
            outcome="revoked",
            correlation_id=getattr(request.state, "correlation_id", None),
            ip_hash=hash_sensitive_identifier(request.client.host if request.client else None),
            user_agent=safe_user_agent(request.headers.get("User-Agent")),
            metadata_json={"reason": reason},
            created_at=datetime.now(UTC),
        )
    )


async def get_auth_context(
    request: Request,
    session: DBSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    cookie_token = request.cookies.get(settings.session_cookie_name)
    if not cookie_token:
        raise AppError(
            code="authentication_required", message="Authentication required", status_code=401
        )

    token_hash = hash_session_token(cookie_token, settings)
    auth_session = await session.scalar(
        select(Session).where(Session.token_hash == token_hash).with_for_update()
    )
    now = datetime.now(UTC)
    if auth_session is None or auth_session.revoked_at is not None:
        raise AppError(
            code="invalid_session", message="Session is invalid or expired", status_code=401
        )
    if auth_session.expires_at <= now or (
        auth_session.last_seen_at + timedelta(seconds=settings.session_idle_timeout_seconds) <= now
    ):
        auth_session.revoked_at = now
        auth_session.revocation_reason = "expired"
        _record_session_security_event(
            session,
            request=request,
            user_id=auth_session.user_id,
            event_type="session_expired",
            reason="expired_or_idle_timeout",
        )
        await session.commit()
        raise AppError(
            code="session_expired", message="Session is invalid or expired", status_code=401
        )

    user = await session.get(User, auth_session.user_id)
    profile = await session.get(UserProfile, auth_session.user_id)
    if user is None or profile is None or user.status != "active":
        auth_session.revoked_at = now
        auth_session.revocation_reason = "account_unavailable"
        _record_session_security_event(
            session,
            request=request,
            user_id=auth_session.user_id if user is not None else None,
            event_type="session_revoked",
            reason="account_unavailable",
        )
        await session.commit()
        raise AppError(
            code="invalid_session", message="Session is invalid or expired", status_code=401
        )

    await apply_rls_context(
        session,
        RLSContext(
            user_id=user.id,
            tenant_id=auth_session.active_tenant_id,
            is_platform_admin=user.is_platform_admin,
        ),
    )

    membership: Membership | None = None
    if auth_session.active_tenant_id is not None and not user.is_platform_admin:
        membership = await session.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.tenant_id == auth_session.active_tenant_id,
            )
        )
        if membership is None or membership.status != "active":
            revoked_tenant_id = auth_session.active_tenant_id
            auth_session.active_tenant_id = None
            auth_session.active_company_id = None
            auth_session.active_branch_id = None
            await append_audit_event(
                session,
                AuditRecord(
                    action="context.access_revoked",
                    category="authorization",
                    outcome="denied",
                    actor_user_id=user.id,
                    effective_user_id=user.id,
                    tenant_id=revoked_tenant_id,
                    correlation_id=request.state.correlation_id,
                ),
            )
            await session.commit()
            raise AppError(
                code="tenant_access_revoked",
                message="Access to the selected context is no longer available",
                status_code=403,
            )

    if now - auth_session.last_seen_at > timedelta(minutes=1):
        auth_session.last_seen_at = now

    permissions = await _resolve_permissions(
        session,
        user=user,
        membership=membership,
        auth_session=auth_session,
    )
    return AuthContext(
        user=user,
        profile=profile,
        session=auth_session,
        membership=membership,
        permission_keys=permissions,
    )


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]


async def require_csrf(
    request: Request,
    auth: CurrentAuth,
    session: DBSession,
    settings: Annotated[Settings, Depends(get_settings)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    if not csrf_cookie or not csrf_header or not constant_time_equal(csrf_cookie, csrf_header):
        await append_audit_event(
            session,
            AuditRecord(
                action="csrf.denied",
                category="authorization",
                outcome="denied",
                actor_user_id=auth.user.id,
                effective_user_id=auth.user.id,
                tenant_id=auth.tenant_id,
                company_id=auth.company_id,
                branch_id=auth.branch_id,
                correlation_id=request.state.correlation_id,
            ),
        )
        await session.commit()
        raise AppError(
            code="csrf_validation_failed", message="CSRF validation failed", status_code=403
        )
    if not constant_time_equal(
        hash_session_token(csrf_header, settings), auth.session.csrf_token_hash
    ):
        await append_audit_event(
            session,
            AuditRecord(
                action="csrf.denied",
                category="authorization",
                outcome="denied",
                actor_user_id=auth.user.id,
                effective_user_id=auth.user.id,
                tenant_id=auth.tenant_id,
                company_id=auth.company_id,
                branch_id=auth.branch_id,
                correlation_id=request.state.correlation_id,
            ),
        )
        await session.commit()
        raise AppError(
            code="csrf_validation_failed", message="CSRF validation failed", status_code=403
        )
    return auth


CSRFProtectedAuth = Annotated[AuthContext, Depends(require_csrf)]


def require_permission(
    permission_key: str,
) -> Callable[[CurrentAuth, Request, DBSession], Awaitable[AuthContext]]:
    async def dependency(auth: CurrentAuth, request: Request, session: DBSession) -> AuthContext:
        if permission_key not in auth.permission_keys:
            await append_audit_event(
                session,
                AuditRecord(
                    action="authorization.denied",
                    category="authorization",
                    outcome="denied",
                    actor_user_id=auth.user.id,
                    effective_user_id=auth.user.id,
                    tenant_id=auth.tenant_id,
                    company_id=auth.company_id,
                    branch_id=auth.branch_id,
                    correlation_id=request.state.correlation_id,
                    metadata={"permission": permission_key},
                ),
            )
            await session.commit()
            raise AppError(
                code="forbidden",
                message="You do not have permission to perform this action",
                status_code=403,
            )
        return auth

    return dependency


async def get_login_rate_limiter() -> LoginRateLimiter:
    return LoginRateLimiter(get_redis_client())


async def get_public_auth_rate_limiter() -> PublicAuthRateLimiter:
    return PublicAuthRateLimiter(get_redis_client())
