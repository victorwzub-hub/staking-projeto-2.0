from __future__ import annotations

from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.auth.service import RequestMetadata, register_user, verify_email_token
from pharma_api.core.config import Settings

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_identity_onboarding_organizations_rbac_audit_and_logout_vertical_flow(
    db_session: AsyncSession,
    integration_client: TestClient,
    integration_settings: Settings,
    redis_client: Redis,
) -> None:
    del redis_client
    suffix = str(uuid4())
    email = f"owner-{suffix}@example.test"
    password = "Phase2-Integration-Password-123"  # noqa: S105
    setup_metadata = RequestMetadata("phase2-setup", "192.0.2.30", "pytest")

    registration = await register_user(
        db_session,
        email=email,
        password=password,
        display_name="Phase 2 Owner",
        metadata=setup_metadata,
        settings=integration_settings,
    )
    assert registration.email_command is not None
    verification_token = parse_qs(
        urlsplit(registration.email_command.variables["verification_url"]).query
    )["token"][0]
    await db_session.commit()
    await verify_email_token(
        db_session,
        raw_token=verification_token,
        metadata=setup_metadata,
        settings=integration_settings,
    )
    await db_session.commit()

    login = integration_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    assert login.json()["onboarding_required"] is True
    csrf = integration_client.cookies[integration_settings.csrf_cookie_name]
    headers = {"X-CSRF-Token": csrf, "X-Correlation-ID": f"phase2-{suffix}"}

    terms = integration_client.get("/api/v1/onboarding/terms")
    assert terms.status_code == 200
    terms_id = terms.json()[0]["id"]

    onboarding = integration_client.post(
        "/api/v1/onboarding/complete",
        headers=headers,
        json={
            "tenant_name": f"Tenant {suffix}",
            "tenant_slug": f"tenant-{suffix}",
            "economic_group_name": f"Group {suffix}",
            "company_legal_name": f"Company {suffix} Ltda",
            "company_trade_name": f"Company {suffix}",
            "company_slug": f"company-{suffix}",
            "branch_name": f"Branch {suffix}",
            "branch_slug": f"branch-{suffix}",
            "terms_version_id": terms_id,
            "accept_terms": True,
        },
    )
    assert onboarding.status_code == 200, onboarding.text
    onboarding_body = onboarding.json()

    # The endpoint is idempotent and returns the same resource identifiers.
    onboarding_again = integration_client.post(
        "/api/v1/onboarding/complete",
        headers=headers,
        json={
            "tenant_name": f"Tenant {suffix}",
            "tenant_slug": f"tenant-{suffix}",
            "economic_group_name": f"Group {suffix}",
            "company_legal_name": f"Company {suffix} Ltda",
            "company_trade_name": f"Company {suffix}",
            "company_slug": f"company-{suffix}",
            "branch_name": f"Branch {suffix}",
            "branch_slug": f"branch-{suffix}",
            "terms_version_id": terms_id,
            "accept_terms": True,
        },
    )
    assert onboarding_again.status_code == 200
    assert onboarding_again.json() == onboarding_body

    me = integration_client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["contexts"][0]["tenant_id"] == onboarding_body["tenant_id"]
    assert "company.create" in me.json()["permissions"]
    assert "role.assign" in me.json()["permissions"]
    assert "platform.admin" not in me.json()["permissions"]

    company = integration_client.post(
        "/api/v1/companies",
        headers=headers,
        json={
            "legal_name": f"Second Company {suffix} Ltda",
            "trade_name": f"Second Company {suffix}",
            "slug": f"second-company-{suffix}",
            "economic_group_id": None,
        },
    )
    assert company.status_code == 201, company.text
    company_id = company.json()["id"]

    branch = integration_client.post(
        "/api/v1/branches",
        headers=headers,
        json={
            "company_id": company_id,
            "name": f"Second Branch {suffix}",
            "slug": f"second-branch-{suffix}",
        },
    )
    assert branch.status_code == 201, branch.text

    roles = integration_client.get("/api/v1/roles")
    assert roles.status_code == 200
    assert any(item["slug"] == "tenant_owner" for item in roles.json())

    audit = integration_client.get("/api/v1/audit-events")
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert "onboarding.completed" in actions
    assert "company.created" in actions
    assert "branch.created" in actions

    logout = integration_client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert integration_client.get("/api/v1/me").status_code == 401
