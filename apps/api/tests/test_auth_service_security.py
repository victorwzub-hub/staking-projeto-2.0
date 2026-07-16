from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pharma_api.application.auth.rate_limit import LoginRateLimiter
from pharma_api.application.auth.service import (
    RequestMetadata,
    _hash_account_password,
    authenticate_user,
    register_user,
)
from pharma_api.cli import bootstrap_admin
from pharma_api.core.config import Settings
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.identity import (
    AuthenticationAttempt,
    EmailVerificationToken,
    SecurityEvent,
    User,
    UserProfile,
)


def _settings(**overrides: object) -> Settings:
    return Settings(
        app_env="test",
        argon2_memory_cost_kib=19456,
        argon2_time_cost=2,
        argon2_parallelism=1,
        _env_file=None,
        **overrides,
    )


def _metadata() -> RequestMetadata:
    return RequestMetadata(
        correlation_id="test-correlation",
        ip_address="192.0.2.10",
        user_agent="pytest",
    )


def test_password_policy_failure_is_a_controlled_client_error() -> None:
    with pytest.raises(AppError) as captured:
        _hash_account_password("Short123", _settings(password_min_length=12))

    assert captured.value.status_code == 422
    assert captured.value.code == "password_policy_violation"
    assert captured.value.details == {"reason": "Password must contain at least 12 characters"}


@pytest.mark.asyncio
async def test_registration_rejects_password_below_configured_policy_without_persisting() -> None:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)

    with pytest.raises(AppError, match="configured security policy") as captured:
        await register_user(
            session,
            email="person@example.test",
            password="Short12345",  # noqa: S106
            display_name="Test Person",
            metadata=_metadata(),
            settings=_settings(password_min_length=12),
        )

    assert captured.value.status_code == 422
    session.add_all.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_registration_flushes_user_before_adding_dependent_identity_records() -> None:
    events: list[tuple[str, object]] = []
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)

    def record_add(value: object) -> None:
        events.append(("add", value))

    async def record_flush() -> None:
        events.append(("flush", None))

    def record_add_all(values: list[object]) -> None:
        events.append(("add_all", values))

    session.add.side_effect = record_add
    session.flush = AsyncMock(side_effect=record_flush)
    session.add_all.side_effect = record_add_all

    result = await register_user(
        session,
        email="ordered@example.test",
        password="Ordered-Password-123",  # noqa: S106
        display_name="Ordered User",
        metadata=_metadata(),
        settings=_settings(),
    )

    assert result.email_command is not None
    assert isinstance(events[0][1], User)
    assert events[1] == ("flush", None)
    assert events[2][0] == "add_all"
    dependents = events[2][1]
    assert isinstance(dependents, list)
    assert {type(item) for item in dependents} == {UserProfile, EmailVerificationToken}
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limited_login_creates_attempt_and_security_event() -> None:
    session = MagicMock()
    limiter = MagicMock(spec=LoginRateLimiter)
    limiter.ensure_allowed = AsyncMock(
        side_effect=AppError(
            code="too_many_attempts",
            message="Too many authentication attempts. Try again later.",
            status_code=429,
        )
    )

    with pytest.raises(AppError) as captured:
        await authenticate_user(
            session,
            email="person@example.test",
            password="AnyPassword123",  # noqa: S106
            metadata=_metadata(),
            rate_limiter=limiter,
            settings=_settings(),
        )

    assert captured.value.code == "too_many_attempts"
    added = [call.args[0] for call in session.add.call_args_list]
    attempt = next(item for item in added if isinstance(item, AuthenticationAttempt))
    event = next(item for item in added if isinstance(item, SecurityEvent))
    assert attempt.succeeded is False
    assert attempt.failure_reason == "rate_limited"
    assert event.event_type == "login_blocked"
    assert event.outcome == "denied"
    assert event.metadata_json == {"reason": "rate_limited"}


@pytest.mark.asyncio
async def test_bootstrap_rejects_password_policy_failure_without_exposing_password() -> None:
    settings = _settings(
        bootstrap_enabled=True,
        bootstrap_admin_email="admin@example.test",
        bootstrap_admin_password="too-short-1",  # noqa: S106
        password_min_length=20,
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = None
    factory = MagicMock(return_value=context)

    with (
        patch.object(bootstrap_admin, "get_settings", return_value=settings),
        patch.object(bootstrap_admin, "get_session_factory", return_value=factory),
        pytest.raises(SystemExit) as captured,
    ):
        await bootstrap_admin.bootstrap()

    message = str(captured.value)
    assert message == "Bootstrap password does not satisfy the configured security policy."
    assert settings.bootstrap_admin_password.get_secret_value() not in message
