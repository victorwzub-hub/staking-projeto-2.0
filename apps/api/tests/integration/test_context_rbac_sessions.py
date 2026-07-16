from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pharma_api.core.config import Settings
from pharma_api.core.security import hash_session_token

pytestmark = [pytest.mark.integration, pytest.mark.negative_security]


@dataclass(frozen=True, slots=True)
class SeededIdentity:
    user_id: UUID
    tenant_id: UUID
    membership_id: UUID | None
    role_assignment_id: UUID | None
    session_id: UUID
    raw_session_token: str
    raw_csrf_token: str


async def _seed_identity(
    settings: Settings,
    *,
    membership_status: str | None = "active",
    role_slug: str = "viewer",
    session_expires_at: datetime | None = None,
) -> SeededIdentity:
    user_id = uuid4()
    tenant_id = uuid4()
    membership_id = uuid4() if membership_status is not None else None
    assignment_id = uuid4() if membership_id is not None else None
    session_id = uuid4()
    raw_session_token = f"session-{uuid4()}-{uuid4()}"
    raw_csrf_token = f"csrf-{uuid4()}-{uuid4()}"
    now = datetime.now(UTC)
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            role_id = (
                await connection.execute(
                    text("SELECT id FROM roles WHERE slug = :slug AND is_system = true"),
                    {"slug": role_slug},
                )
            ).scalar_one()
            await connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,email,normalized_email,password_hash,status,email_verified_at,"
                    "is_platform_admin,created_at,updated_at,version) "
                    "VALUES (:id,:email,:email,'not-used','active',:now,false,:now,:now,1)"
                ),
                {"id": user_id, "email": f"identity-{user_id}@example.test", "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO user_profiles "
                    "(user_id,display_name,locale,timezone,created_at,updated_at,version) "
                    "VALUES (:id,'Integration User','pt-BR','America/Sao_Paulo',:now,:now,1)"
                ),
                {"id": user_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO tenants "
                    "(id,name,slug,status,created_by_user_id,created_at,updated_at,version) "
                    "VALUES (:id,'Integration Tenant',:slug,'active',:user_id,:now,:now,1)"
                ),
                {
                    "id": tenant_id,
                    "slug": f"integration-{tenant_id}",
                    "user_id": user_id,
                    "now": now,
                },
            )
            if membership_id is not None and membership_status is not None:
                await connection.execute(
                    text(
                        "INSERT INTO memberships "
                        "(id,tenant_id,user_id,status,joined_at,created_at,updated_at,version) "
                        "VALUES (:id,:tenant_id,:user_id,:status,:now,:now,:now,1)"
                    ),
                    {
                        "id": membership_id,
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "status": membership_status,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO role_assignments "
                        "(id,tenant_id,membership_id,role_id,assigned_by_user_id,"
                        "created_at,updated_at) "
                        "VALUES (:id,:tenant_id,:membership_id,:role_id,:user_id,:now,:now)"
                    ),
                    {
                        "id": assignment_id,
                        "tenant_id": tenant_id,
                        "membership_id": membership_id,
                        "role_id": role_id,
                        "user_id": user_id,
                        "now": now,
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(id,user_id,token_hash,csrf_token_hash,active_tenant_id,created_at,last_seen_at,"
                    "expires_at,ip_hash,user_agent) "
                    "VALUES (:id,:user_id,:token_hash,:csrf_hash,:tenant_id,:now,:now,:expires_at,"
                    "'integration-ip','pytest')"
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "token_hash": hash_session_token(raw_session_token, settings),
                    "csrf_hash": hash_session_token(raw_csrf_token, settings),
                    "tenant_id": tenant_id,
                    "now": now,
                    "expires_at": session_expires_at or now + timedelta(hours=1),
                },
            )
    finally:
        await engine.dispose()
    return SeededIdentity(
        user_id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        role_assignment_id=assignment_id,
        session_id=session_id,
        raw_session_token=raw_session_token,
        raw_csrf_token=raw_csrf_token,
    )


def _set_auth_cookies(client: TestClient, settings: Settings, identity: SeededIdentity) -> None:
    client.cookies.set(settings.session_cookie_name, identity.raw_session_token)
    client.cookies.set(settings.csrf_cookie_name, identity.raw_csrf_token)


@pytest.mark.asyncio
async def test_suspended_membership_clears_context_and_persists_denied_audit(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    identity = await _seed_identity(integration_settings, membership_status="suspended")
    _set_auth_cookies(integration_client, integration_settings, identity)

    response = integration_client.get("/api/v1/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_access_revoked"
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            active_tenant_id = (
                await connection.execute(
                    text("SELECT active_tenant_id FROM sessions WHERE id = :id"),
                    {"id": identity.session_id},
                )
            ).scalar_one()
            audit_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM audit_events "
                        "WHERE action = 'context.access_revoked' AND actor_user_id = :user_id"
                    ),
                    {"user_id": identity.user_id},
                )
            ).scalar_one()
        assert active_tenant_id is None
        assert audit_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_removed_role_loses_permission_on_next_request(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    identity = await _seed_identity(integration_settings)
    assert identity.role_assignment_id is not None
    _set_auth_cookies(integration_client, integration_settings, identity)

    allowed = integration_client.get("/api/v1/tenants/current")
    assert allowed.status_code == 200

    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM role_assignments WHERE id = :id"),
                {"id": identity.role_assignment_id},
            )
    finally:
        await engine.dispose()

    denied = integration_client.get("/api/v1/tenants/current")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_context_switch_rejects_tenant_without_membership(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    identity = await _seed_identity(integration_settings)
    _set_auth_cookies(integration_client, integration_settings, identity)
    foreign_tenant_id = uuid4()
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO tenants "
                    "(id,name,slug,status,created_by_user_id,created_at,updated_at,version) "
                    "VALUES (:id,'Foreign Tenant',:slug,'active',:user_id,now(),now(),1)"
                ),
                {
                    "id": foreign_tenant_id,
                    "slug": f"foreign-{foreign_tenant_id}",
                    "user_id": identity.user_id,
                },
            )
    finally:
        await engine.dispose()

    response = integration_client.post(
        "/api/v1/me/context",
        headers={"X-CSRF-Token": identity.raw_csrf_token},
        json={"tenant_id": str(foreign_tenant_id), "company_id": None, "branch_id": None},
    )

    assert response.status_code == 404
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            active_tenant_id = (
                await connection.execute(
                    text("SELECT active_tenant_id FROM sessions WHERE id = :id"),
                    {"id": identity.session_id},
                )
            ).scalar_one()
            denied_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM audit_events "
                        "WHERE action = 'context.switch_denied' AND actor_user_id = :user_id"
                    ),
                    {"user_id": identity.user_id},
                )
            ).scalar_one()
        assert active_tenant_id == identity.tenant_id
        assert denied_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_cannot_revoke_another_users_session(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    actor = await _seed_identity(integration_settings)
    other = await _seed_identity(integration_settings)
    _set_auth_cookies(integration_client, integration_settings, actor)

    response = integration_client.delete(
        f"/api/v1/sessions/{other.session_id}",
        headers={"X-CSRF-Token": actor.raw_csrf_token},
    )

    assert response.status_code == 404
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            revoked_at = (
                await connection.execute(
                    text("SELECT revoked_at FROM sessions WHERE id = :id"),
                    {"id": other.session_id},
                )
            ).scalar_one()
            denied_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM audit_events "
                        "WHERE action = 'session.revoke_denied' AND actor_user_id = :user_id"
                    ),
                    {"user_id": actor.user_id},
                )
            ).scalar_one()
        assert revoked_at is None
        assert denied_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_session_is_revoked_and_records_security_event(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    identity = await _seed_identity(
        integration_settings, session_expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    _set_auth_cookies(integration_client, integration_settings, identity)

    response = integration_client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_expired"
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            session_row = (
                await connection.execute(
                    text("SELECT revoked_at, revocation_reason FROM sessions WHERE id = :id"),
                    {"id": identity.session_id},
                )
            ).one()
            event_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM security_events "
                        "WHERE event_type = 'session_expired' AND user_id = :user_id"
                    ),
                    {"user_id": identity.user_id},
                )
            ).scalar_one()
        assert session_row.revoked_at is not None
        assert session_row.revocation_reason == "expired"
        assert event_count == 1
    finally:
        await engine.dispose()
