from __future__ import annotations

from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.auth.rate_limit import LoginRateLimiter
from pharma_api.application.auth.service import (
    RequestMetadata,
    authenticate_user,
    register_user,
    verify_email_token,
)
from pharma_api.core.config import Settings
from pharma_api.core.security import hash_session_token
from pharma_api.infrastructure.db.models.identity import Session, User

pytestmark = pytest.mark.integration


def _token_from_url(url: str, parameter: str = "token") -> str:
    values = parse_qs(urlsplit(url).query)[parameter]
    return values[0]


@pytest.mark.asyncio
async def test_registration_verification_login_and_rate_limit_use_real_dependencies(
    db_session: AsyncSession,
    redis_client: Redis,
    integration_settings: Settings,
) -> None:
    email = f"integration-{uuid4()}@example.test"
    metadata = RequestMetadata("integration-auth", "192.0.2.10", "pytest-integration")
    registration = await register_user(
        db_session,
        email=email,
        password="Integration-Password-123",  # noqa: S106
        display_name="Integration User",
        metadata=metadata,
        settings=integration_settings,
    )
    assert registration.email_command is not None
    raw_verification_token = _token_from_url(
        registration.email_command.variables["verification_url"]
    )
    await db_session.commit()

    user = await verify_email_token(
        db_session,
        raw_token=raw_verification_token,
        metadata=metadata,
        settings=integration_settings,
    )
    await db_session.commit()
    assert user.status == "active"
    assert user.email_verified_at is not None

    result = await authenticate_user(
        db_session,
        email=email,
        password="Integration-Password-123",  # noqa: S106
        metadata=metadata,
        rate_limiter=LoginRateLimiter(redis_client, integration_settings),
        settings=integration_settings,
    )
    await db_session.commit()

    persisted = await db_session.scalar(select(Session).where(Session.id == result.session.id))
    assert persisted is not None
    assert persisted.token_hash == hash_session_token(
        result.raw_session_token, integration_settings
    )
    assert persisted.token_hash != result.raw_session_token
    assert await db_session.scalar(select(User).where(User.id == user.id)) is not None
