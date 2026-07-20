from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from pharma_api.core.config import Settings
from pharma_api.core.security import hash_one_time_token, hash_session_token

pytestmark = [pytest.mark.integration, pytest.mark.negative_security]


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: UUID
    membership_id: UUID
    session_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class Hierarchy:
    tenant_id: UUID
    company_a: UUID
    company_b: UUID
    branch_a1: UUID
    branch_a2: UUID
    branch_b1: UUID


async def _role_id(connection: AsyncConnection, slug: str) -> UUID:
    return (
        await connection.execute(
            text("SELECT id FROM roles WHERE slug = :slug AND is_system = true"),
            {"slug": slug},
        )
    ).scalar_one()


async def _insert_user(
    connection: AsyncConnection,
    *,
    email: str,
    display_name: str,
    now: datetime,
) -> UUID:
    user_id = uuid4()
    await connection.execute(
        text(
            "INSERT INTO users "
            "(id,email,normalized_email,password_hash,status,email_verified_at,"
            "is_platform_admin,created_at,updated_at,version) "
            "VALUES (:id,:email,:email,'not-used','active',:now,false,:now,:now,1)"
        ),
        {"id": user_id, "email": email, "now": now},
    )
    await connection.execute(
        text(
            "INSERT INTO user_profiles "
            "(user_id,display_name,locale,timezone,created_at,updated_at,version) "
            "VALUES (:id,:name,'pt-BR','America/Sao_Paulo',:now,:now,1)"
        ),
        {"id": user_id, "name": display_name, "now": now},
    )
    return user_id


async def _insert_membership(
    connection: AsyncConnection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    now: datetime,
) -> UUID:
    membership_id = uuid4()
    await connection.execute(
        text(
            "INSERT INTO memberships "
            "(id,tenant_id,user_id,status,joined_at,created_at,updated_at,version) "
            "VALUES (:id,:tenant_id,:user_id,'active',:now,:now,:now,1)"
        ),
        {
            "id": membership_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "now": now,
        },
    )
    return membership_id


async def _assign_role(
    connection: AsyncConnection,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    role_id: UUID,
    assigned_by_user_id: UUID,
    company_id: UUID | None = None,
    branch_id: UUID | None = None,
    now: datetime,
) -> UUID:
    assignment_id = uuid4()
    await connection.execute(
        text(
            "INSERT INTO role_assignments "
            "(id,tenant_id,membership_id,role_id,company_id,branch_id,assigned_by_user_id,"
            "created_at,updated_at) "
            "VALUES (:id,:tenant_id,:membership_id,:role_id,:company_id,:branch_id,"
            ":assigned_by_user_id,:now,:now)"
        ),
        {
            "id": assignment_id,
            "tenant_id": tenant_id,
            "membership_id": membership_id,
            "role_id": role_id,
            "company_id": company_id,
            "branch_id": branch_id,
            "assigned_by_user_id": assigned_by_user_id,
            "now": now,
        },
    )
    return assignment_id


async def _insert_session(
    connection: AsyncConnection,
    *,
    settings: Settings,
    user_id: UUID,
    tenant_id: UUID | None,
    company_id: UUID | None,
    branch_id: UUID | None,
    now: datetime,
) -> tuple[str, str]:
    session_token = f"session-{uuid4()}-{uuid4()}"
    csrf_token = f"csrf-{uuid4()}-{uuid4()}"
    await connection.execute(
        text(
            "INSERT INTO sessions "
            "(id,user_id,token_hash,csrf_token_hash,active_tenant_id,active_company_id,"
            "active_branch_id,created_at,last_seen_at,expires_at,ip_hash,user_agent) "
            "VALUES (:id,:user_id,:token_hash,:csrf_hash,:tenant_id,:company_id,:branch_id,"
            ":now,:now,:expires_at,'integration-ip','pytest')"
        ),
        {
            "id": uuid4(),
            "user_id": user_id,
            "token_hash": hash_session_token(session_token, settings),
            "csrf_hash": hash_session_token(csrf_token, settings),
            "tenant_id": tenant_id,
            "company_id": company_id,
            "branch_id": branch_id,
            "now": now,
            "expires_at": now + timedelta(hours=1),
        },
    )
    return session_token, csrf_token


async def _seed_hierarchy(
    connection: AsyncConnection, creator_id: UUID, now: datetime
) -> Hierarchy:
    hierarchy = Hierarchy(
        tenant_id=uuid4(),
        company_a=uuid4(),
        company_b=uuid4(),
        branch_a1=uuid4(),
        branch_a2=uuid4(),
        branch_b1=uuid4(),
    )
    await connection.execute(
        text(
            "INSERT INTO tenants "
            "(id,name,slug,status,created_by_user_id,created_at,updated_at,version) "
            "VALUES (:id,'Scoped Tenant',:slug,'active',:creator,:now,:now,1)"
        ),
        {
            "id": hierarchy.tenant_id,
            "slug": f"scoped-{hierarchy.tenant_id}",
            "creator": creator_id,
            "now": now,
        },
    )
    for company_id, label in ((hierarchy.company_a, "A"), (hierarchy.company_b, "B")):
        await connection.execute(
            text(
                "INSERT INTO companies "
                "(id,tenant_id,legal_name,trade_name,slug,status,created_at,updated_at,version) "
                "VALUES (:id,:tenant_id,:legal,:trade,:slug,'active',:now,:now,1)"
            ),
            {
                "id": company_id,
                "tenant_id": hierarchy.tenant_id,
                "legal": f"Company {label} Ltda",
                "trade": f"Company {label}",
                "slug": f"company-{label.lower()}-{company_id}",
                "now": now,
            },
        )
    for branch_id, company_id, label in (
        (hierarchy.branch_a1, hierarchy.company_a, "A1"),
        (hierarchy.branch_a2, hierarchy.company_a, "A2"),
        (hierarchy.branch_b1, hierarchy.company_b, "B1"),
    ):
        await connection.execute(
            text(
                "INSERT INTO branches "
                "(id,tenant_id,company_id,name,slug,status,created_at,updated_at,version) "
                "VALUES (:id,:tenant_id,:company_id,:name,:slug,'active',:now,:now,1)"
            ),
            {
                "id": branch_id,
                "tenant_id": hierarchy.tenant_id,
                "company_id": company_id,
                "name": f"Branch {label}",
                "slug": f"branch-{label.lower()}-{branch_id}",
                "now": now,
            },
        )
    return hierarchy


async def _seed_actor(
    connection: AsyncConnection,
    *,
    settings: Settings,
    hierarchy: Hierarchy,
    role_slug: str,
    company_id: UUID | None,
    branch_id: UUID | None,
    now: datetime,
) -> Actor:
    user_id = await _insert_user(
        connection,
        email=f"actor-{uuid4()}@example.com",
        display_name=f"Actor {role_slug}",
        now=now,
    )
    membership_id = await _insert_membership(
        connection,
        tenant_id=hierarchy.tenant_id,
        user_id=user_id,
        now=now,
    )
    role_id = await _role_id(connection, role_slug)
    await _assign_role(
        connection,
        tenant_id=hierarchy.tenant_id,
        membership_id=membership_id,
        role_id=role_id,
        assigned_by_user_id=user_id,
        company_id=company_id,
        branch_id=branch_id,
        now=now,
    )
    session_token, csrf_token = await _insert_session(
        connection,
        settings=settings,
        user_id=user_id,
        tenant_id=hierarchy.tenant_id,
        company_id=company_id,
        branch_id=branch_id,
        now=now,
    )
    return Actor(user_id, membership_id, session_token, csrf_token)


def _authenticate(client: TestClient, settings: Settings, actor: Actor) -> None:
    client.cookies.set(settings.session_cookie_name, actor.session_token)
    client.cookies.set(settings.csrf_cookie_name, actor.csrf_token)


@pytest.mark.asyncio
async def test_company_and_branch_roles_cannot_cross_scope(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            creator = await _insert_user(
                connection,
                email=f"creator-{uuid4()}@example.com",
                display_name="Creator",
                now=now,
            )
            hierarchy = await _seed_hierarchy(connection, creator, now)
            company_actor = await _seed_actor(
                connection,
                settings=integration_settings,
                hierarchy=hierarchy,
                role_slug="company_admin",
                company_id=hierarchy.company_a,
                branch_id=None,
                now=now,
            )
            branch_actor = await _seed_actor(
                connection,
                settings=integration_settings,
                hierarchy=hierarchy,
                role_slug="branch_manager",
                company_id=hierarchy.company_a,
                branch_id=hierarchy.branch_a1,
                now=now,
            )
            company_admin_role = await _role_id(connection, "company_admin")
            branch_manager_role = await _role_id(connection, "branch_manager")
            for company_id, branch_id, label in (
                (hierarchy.company_a, hierarchy.branch_a1, "Visible A1"),
                (hierarchy.company_a, hierarchy.branch_a2, "Visible A2"),
                (hierarchy.company_b, hierarchy.branch_b1, "Hidden B1"),
            ):
                user_id = await _insert_user(
                    connection,
                    email=f"member-{uuid4()}@example.com",
                    display_name=label,
                    now=now,
                )
                membership_id = await _insert_membership(
                    connection,
                    tenant_id=hierarchy.tenant_id,
                    user_id=user_id,
                    now=now,
                )
                await _assign_role(
                    connection,
                    tenant_id=hierarchy.tenant_id,
                    membership_id=membership_id,
                    role_id=branch_manager_role,
                    assigned_by_user_id=creator,
                    company_id=company_id,
                    branch_id=branch_id,
                    now=now,
                )
            for company_id, branch_id, action in (
                (hierarchy.company_a, hierarchy.branch_a1, "visible.a1"),
                (hierarchy.company_a, hierarchy.branch_a2, "visible.a2"),
                (hierarchy.company_b, hierarchy.branch_b1, "hidden.b1"),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO audit_events "
                        "(id,actor_user_id,effective_user_id,tenant_id,company_id,branch_id,"
                        "action,category,outcome,changed_fields,metadata_json,created_at) "
                        "VALUES (:id,:actor,:actor,:tenant,:company,:branch,:action,'test',"
                        "'success','[]'::jsonb,'{}'::jsonb,:now)"
                    ),
                    {
                        "id": uuid4(),
                        "actor": creator,
                        "tenant": hierarchy.tenant_id,
                        "company": company_id,
                        "branch": branch_id,
                        "action": action,
                        "now": now,
                    },
                )
            for company_id, branch_id, email in (
                (hierarchy.company_a, hierarchy.branch_a1, f"visible-a1-{uuid4()}@example.com"),
                (hierarchy.company_a, hierarchy.branch_a2, f"visible-a2-{uuid4()}@example.com"),
                (hierarchy.company_b, hierarchy.branch_b1, f"hidden-b1-{uuid4()}@example.com"),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO invitations "
                        "(id,tenant_id,normalized_email,token_hash,role_id,company_id,branch_id,"
                        "status,expires_at,created_by_user_id,created_at,updated_at,version) "
                        "VALUES (:id,:tenant,:email,:token,:role,:company,:branch,'pending',"
                        ":expires,:creator,:now,:now,1)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": hierarchy.tenant_id,
                        "email": email,
                        "token": uuid4().hex + uuid4().hex,
                        "role": branch_manager_role,
                        "company": company_id,
                        "branch": branch_id,
                        "expires": now + timedelta(hours=1),
                        "creator": creator,
                        "now": now,
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO teams "
                    "(id,tenant_id,name,description,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,'Tenant Team',NULL,:now,:now,1)"
                ),
                {"id": uuid4(), "tenant": hierarchy.tenant_id, "now": now},
            )
            del company_admin_role
    finally:
        await engine.dispose()

    _authenticate(integration_client, integration_settings, company_actor)
    companies = integration_client.get("/api/v1/companies")
    assert companies.status_code == 200
    assert {item["id"] for item in companies.json()} == {str(hierarchy.company_a)}
    assert integration_client.get(f"/api/v1/companies/{hierarchy.company_b}").status_code == 404
    branches = integration_client.get("/api/v1/branches")
    assert branches.status_code == 200
    assert {item["id"] for item in branches.json()} == {
        str(hierarchy.branch_a1),
        str(hierarchy.branch_a2),
    }
    audit = integration_client.get("/api/v1/audit-events")
    assert audit.status_code == 200
    assert {item["action"] for item in audit.json()["items"]} == {"visible.a1", "visible.a2"}
    users = integration_client.get("/api/v1/users")
    assert users.status_code == 200
    assert {item["display_name"] for item in users.json()} == {
        "Actor company_admin",
        "Actor branch_manager",
        "Visible A1",
        "Visible A2",
    }
    invitations = integration_client.get("/api/v1/invitations")
    assert invitations.status_code == 200
    assert {item["company_id"] for item in invitations.json()} == {str(hierarchy.company_a)}
    roles = integration_client.get("/api/v1/roles")
    assert roles.status_code == 200
    assert "tenant_owner" not in {item["slug"] for item in roles.json()}
    assert {item["scope"] for item in roles.json()} <= {"company", "branch"}
    assignments = integration_client.get("/api/v1/roles/assignments")
    assert assignments.status_code == 200
    assert {item["company_id"] for item in assignments.json()} == {str(hierarchy.company_a)}
    assert integration_client.get("/api/v1/teams").status_code == 403

    integration_client.cookies.clear()
    _authenticate(integration_client, integration_settings, branch_actor)
    branch_companies = integration_client.get("/api/v1/companies")
    assert branch_companies.status_code == 200
    assert {item["id"] for item in branch_companies.json()} == {str(hierarchy.company_a)}
    branch_branches = integration_client.get("/api/v1/branches")
    assert branch_branches.status_code == 200
    assert {item["id"] for item in branch_branches.json()} == {str(hierarchy.branch_a1)}
    branch_audit = integration_client.get("/api/v1/audit-events")
    assert branch_audit.status_code == 200
    assert {item["action"] for item in branch_audit.json()["items"]} == {"visible.a1"}
    branch_users = integration_client.get("/api/v1/users")
    assert branch_users.status_code == 200
    assert {item["display_name"] for item in branch_users.json()} == {
        "Actor branch_manager",
        "Visible A1",
    }
    branch_invitations = integration_client.get("/api/v1/invitations")
    assert branch_invitations.status_code == 200
    assert {item["branch_id"] for item in branch_invitations.json()} == {str(hierarchy.branch_a1)}


@pytest.mark.asyncio
async def test_delegation_and_resend_cannot_cross_company_scope(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            actor_user = await _insert_user(
                connection,
                email=f"delegator-{uuid4()}@example.com",
                display_name="Company Delegator",
                now=now,
            )
            hierarchy = await _seed_hierarchy(connection, actor_user, now)
            membership_id = await _insert_membership(
                connection,
                tenant_id=hierarchy.tenant_id,
                user_id=actor_user,
                now=now,
            )
            company_admin_role = await _role_id(connection, "company_admin")
            custom_role_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO roles "
                    "(id,tenant_id,name,slug,scope,is_system,is_editable,description,"
                    "created_at,updated_at,version) "
                    "VALUES (:id,:tenant,'Company Delegator',:slug,'company',false,true,NULL,"
                    ":now,:now,1)"
                ),
                {
                    "id": custom_role_id,
                    "tenant": hierarchy.tenant_id,
                    "slug": f"company-delegator-{custom_role_id}",
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO role_permissions (role_id,permission_id) "
                    "SELECT :custom_role, permission_id FROM role_permissions "
                    "WHERE role_id = :company_admin_role"
                ),
                {
                    "custom_role": custom_role_id,
                    "company_admin_role": company_admin_role,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO role_permissions (role_id,permission_id) "
                    "SELECT :role_id,id FROM permissions WHERE key IN ('user.invite','role.assign')"
                ),
                {"role_id": custom_role_id},
            )
            await _assign_role(
                connection,
                tenant_id=hierarchy.tenant_id,
                membership_id=membership_id,
                role_id=custom_role_id,
                assigned_by_user_id=actor_user,
                company_id=hierarchy.company_a,
                now=now,
            )
            target_user = await _insert_user(
                connection,
                email=f"target-{uuid4()}@example.com",
                display_name="Target User",
                now=now,
            )
            target_membership = await _insert_membership(
                connection,
                tenant_id=hierarchy.tenant_id,
                user_id=target_user,
                now=now,
            )
            session_token, csrf_token = await _insert_session(
                connection,
                settings=integration_settings,
                user_id=actor_user,
                tenant_id=hierarchy.tenant_id,
                company_id=hierarchy.company_a,
                branch_id=None,
                now=now,
            )
            actor = Actor(actor_user, membership_id, session_token, csrf_token)
            hidden_invitation_id = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO invitations "
                    "(id,tenant_id,normalized_email,token_hash,role_id,company_id,branch_id,"
                    "status,expires_at,created_by_user_id,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:email,:token,:role,:company,NULL,'pending',:expires,"
                    ":creator,:now,:now,1)"
                ),
                {
                    "id": hidden_invitation_id,
                    "tenant": hierarchy.tenant_id,
                    "email": f"hidden-{uuid4()}@example.com",
                    "token": uuid4().hex + uuid4().hex,
                    "role": company_admin_role,
                    "company": hierarchy.company_b,
                    "expires": now + timedelta(hours=1),
                    "creator": actor_user,
                    "now": now,
                },
            )
    finally:
        await engine.dispose()

    _authenticate(integration_client, integration_settings, actor)
    headers = {"X-CSRF-Token": actor.csrf_token}
    allowed_invite = integration_client.post(
        "/api/v1/invitations",
        headers=headers,
        json={
            "email": f"allowed-{uuid4()}@example.com",
            "role_id": str(company_admin_role),
            "company_id": str(hierarchy.company_a),
            "branch_id": None,
        },
    )
    assert allowed_invite.status_code == 201, allowed_invite.text
    denied_invite = integration_client.post(
        "/api/v1/invitations",
        headers=headers,
        json={
            "email": f"denied-{uuid4()}@example.com",
            "role_id": str(company_admin_role),
            "company_id": str(hierarchy.company_b),
            "branch_id": None,
        },
    )
    assert denied_invite.status_code == 403
    allowed_assignment = integration_client.post(
        "/api/v1/roles/assignments",
        headers=headers,
        json={
            "membership_id": str(target_membership),
            "role_id": str(company_admin_role),
            "company_id": str(hierarchy.company_a),
            "branch_id": None,
        },
    )
    assert allowed_assignment.status_code == 201, allowed_assignment.text
    denied_assignment = integration_client.post(
        "/api/v1/roles/assignments",
        headers=headers,
        json={
            "membership_id": str(target_membership),
            "role_id": str(company_admin_role),
            "company_id": str(hierarchy.company_b),
            "branch_id": None,
        },
    )
    assert denied_assignment.status_code == 403
    denied_resend = integration_client.post(
        f"/api/v1/invitations/{hidden_invitation_id}/resend",
        headers=headers,
    )
    assert denied_resend.status_code == 403


@pytest.mark.asyncio
async def test_invitation_acceptance_revalidates_inviter_authority(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    now = datetime.now(UTC)
    raw_token = f"invitation-{uuid4()}-{uuid4()}"
    try:
        async with engine.begin() as connection:
            inviter = await _insert_user(
                connection,
                email=f"inviter-{uuid4()}@example.com",
                display_name="Inviter",
                now=now,
            )
            hierarchy = await _seed_hierarchy(connection, inviter, now)
            inviter_membership = await _insert_membership(
                connection,
                tenant_id=hierarchy.tenant_id,
                user_id=inviter,
                now=now,
            )
            tenant_owner_role = await _role_id(connection, "tenant_owner")
            inviter_assignment = await _assign_role(
                connection,
                tenant_id=hierarchy.tenant_id,
                membership_id=inviter_membership,
                role_id=tenant_owner_role,
                assigned_by_user_id=inviter,
                now=now,
            )
            invitee_email = f"invitee-{uuid4()}@example.com"
            invitee = await _insert_user(
                connection,
                email=invitee_email,
                display_name="Invitee",
                now=now,
            )
            company_admin_role = await _role_id(connection, "company_admin")
            await connection.execute(
                text(
                    "INSERT INTO invitations "
                    "(id,tenant_id,normalized_email,token_hash,role_id,company_id,branch_id,"
                    "status,expires_at,created_by_user_id,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:email,:token,:role,:company,NULL,'pending',:expires,"
                    ":creator,:now,:now,1)"
                ),
                {
                    "id": uuid4(),
                    "tenant": hierarchy.tenant_id,
                    "email": invitee_email,
                    "token": hash_one_time_token(raw_token, integration_settings),
                    "role": company_admin_role,
                    "company": hierarchy.company_a,
                    "expires": now + timedelta(hours=1),
                    "creator": inviter,
                    "now": now,
                },
            )
            await connection.execute(
                text("DELETE FROM role_assignments WHERE id = :id"),
                {"id": inviter_assignment},
            )
            session_token, csrf_token = await _insert_session(
                connection,
                settings=integration_settings,
                user_id=invitee,
                tenant_id=None,
                company_id=None,
                branch_id=None,
                now=now,
            )
            invitee_actor = Actor(invitee, uuid4(), session_token, csrf_token)
    finally:
        await engine.dispose()

    _authenticate(integration_client, integration_settings, invitee_actor)
    response = integration_client.post(
        "/api/v1/invitations/accept",
        headers={"X-CSRF-Token": invitee_actor.csrf_token},
        json={"token": raw_token},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_authority_revoked"


@pytest.mark.asyncio
async def test_database_rejects_mismatched_role_and_branch_scope() -> None:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            user_id = await _insert_user(
                connection,
                email=f"db-guard-{uuid4()}@example.com",
                display_name="DB Guard",
                now=now,
            )
            hierarchy = await _seed_hierarchy(connection, user_id, now)
            membership_id = await _insert_membership(
                connection,
                tenant_id=hierarchy.tenant_id,
                user_id=user_id,
                now=now,
            )
            branch_role = await _role_id(connection, "branch_manager")
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await _assign_role(
                        connection,
                        tenant_id=hierarchy.tenant_id,
                        membership_id=membership_id,
                        role_id=branch_role,
                        assigned_by_user_id=user_id,
                        company_id=hierarchy.company_b,
                        branch_id=hierarchy.branch_a1,
                        now=now,
                    )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_allows_only_one_concurrent_pending_invitation_per_tenant_email() -> None:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    now = datetime.now(UTC)
    creator_id: UUID
    hierarchy: Hierarchy
    role_id: UUID
    try:
        async with engine.begin() as connection:
            creator_id = await _insert_user(
                connection,
                email=f"concurrent-inviter-{uuid4()}@example.com",
                display_name="Concurrent inviter",
                now=now,
            )
            hierarchy = await _seed_hierarchy(connection, creator_id, now)
            role_id = await _role_id(connection, "viewer")

        async def insert_invitation(token_hash: str) -> None:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO invitations "
                        "(id,tenant_id,normalized_email,token_hash,role_id,status,expires_at,"
                        "created_by_user_id,created_at,updated_at,version) "
                        "VALUES (:id,:tenant,:email,:token,:role,'pending',:expires,:creator,"
                        ":now,:now,1)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": hierarchy.tenant_id,
                        "email": "one-pending-invitation@example.com",
                        "token": token_hash,
                        "role": role_id,
                        "expires": now + timedelta(hours=1),
                        "creator": creator_id,
                        "now": now,
                    },
                )

        results = await asyncio.gather(
            *(insert_invitation(f"token-{uuid4()}") for _ in range(8)),
            return_exceptions=True,
        )
        assert sum(isinstance(result, IntegrityError) for result in results) == 7
        assert sum(result is None for result in results) == 1
    finally:
        await engine.dispose()
