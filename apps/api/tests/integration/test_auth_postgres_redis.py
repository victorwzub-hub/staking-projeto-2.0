from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.auth.rate_limit import LoginRateLimiter
from pharma_api.application.auth.service import (
    RequestMetadata,
    authenticate_user,
    register_user,
    request_password_reset,
    verify_email_token,
)
from pharma_api.core.config import Settings
from pharma_api.core.security import hash_session_token
from pharma_api.infrastructure.db.models.identity import (
    EmailVerificationToken,
    PasswordResetToken,
    Session,
    User,
    UserProfile,
)

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


@pytest.mark.asyncio
async def test_registration_flush_is_atomic_and_rollback_removes_user_and_dependents(
    db_session: AsyncSession,
    integration_settings: Settings,
) -> None:
    email = f"rollback-{uuid4()}@example.test"
    metadata = RequestMetadata("integration-rollback", "192.0.2.11", "pytest-integration")

    result = await register_user(
        db_session,
        email=email,
        password="Rollback-Password-123",  # noqa: S106
        display_name="Rollback User",
        metadata=metadata,
        settings=integration_settings,
    )
    assert result.email_command is not None
    await db_session.flush()

    user = await db_session.scalar(select(User).where(User.normalized_email == email))
    assert user is not None
    user_id = user.id
    assert await db_session.get(UserProfile, user_id) is not None
    assert (
        await db_session.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )
        is not None
    )

    try:
        raise RuntimeError("controlled failure after flush")
    except RuntimeError:
        await db_session.rollback()

    assert await db_session.get(User, user_id) is None
    assert await db_session.get(UserProfile, user_id) is None
    assert (
        await db_session.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id)
        )
        is None
    )


@pytest.mark.asyncio
async def test_email_verification_token_cannot_be_persisted_without_user(
    db_session: AsyncSession,
) -> None:
    token_id = uuid4()
    db_session.add(
        EmailVerificationToken(
            id=token_id,
            user_id=uuid4(),
            token_hash=f"orphan-{uuid4().hex}",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            created_at=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    assert await db_session.get(EmailVerificationToken, token_id) is None


@pytest.mark.asyncio
async def test_password_reset_token_uses_existing_persisted_user(
    db_session: AsyncSession,
    integration_settings: Settings,
) -> None:
    email = f"reset-{uuid4()}@example.test"
    metadata = RequestMetadata("integration-reset", "192.0.2.12", "pytest-integration")
    registration = await register_user(
        db_session,
        email=email,
        password="Reset-Password-123",  # noqa: S106
        display_name="Reset User",
        metadata=metadata,
        settings=integration_settings,
    )
    assert registration.email_command is not None
    await db_session.commit()

    raw_verification_token = _token_from_url(
        registration.email_command.variables["verification_url"]
    )
    user = await verify_email_token(
        db_session,
        raw_token=raw_verification_token,
        metadata=metadata,
        settings=integration_settings,
    )
    await db_session.commit()

    reset = await request_password_reset(
        db_session,
        email=email,
        metadata=metadata,
        settings=integration_settings,
    )
    assert reset.email_command is not None
    await db_session.commit()

    persisted = await db_session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    assert persisted is not None
