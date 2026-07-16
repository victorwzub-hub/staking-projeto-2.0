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
async def test_api_uses_opaque_cookie_and_enforces_csrf(
    db_session: AsyncSession,
    integration_client: TestClient,
    integration_settings: Settings,
    redis_client: Redis,
) -> None:
    del redis_client
    email = f"cookie-{uuid4()}@example.com"
    password = "Cookie-Integration-Password-123"  # noqa: S105
    result = await register_user(
        db_session,
        email=email,
        password=password,
        display_name="Cookie User",
        metadata=RequestMetadata("cookie-setup", "192.0.2.20", "pytest"),
        settings=integration_settings,
    )
    assert result.email_command is not None
    token = parse_qs(urlsplit(result.email_command.variables["verification_url"]).query)["token"][0]
    await db_session.commit()
    await verify_email_token(
        db_session,
        raw_token=token,
        metadata=RequestMetadata("cookie-verify", "192.0.2.20", "pytest"),
        settings=integration_settings,
    )
    await db_session.commit()

    login = integration_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    assert integration_settings.session_cookie_name in integration_client.cookies
    assert integration_settings.csrf_cookie_name in integration_client.cookies
    assert "opaque" not in login.text.lower()

    me = integration_client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email

    rejected = integration_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": password, "new_password": "Changed-Password-456"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_validation_failed"

    csrf = integration_client.cookies[integration_settings.csrf_cookie_name]
    accepted = integration_client.post(
        "/api/v1/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={"current_password": password, "new_password": "Changed-Password-456"},
    )
    assert accepted.status_code == 200
