from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from pharma_api.application.auth.profile import list_security_events, update_profile
from pharma_api.application.auth.types import AuthContext
from pharma_api.application.email.service import (
    EmailCommand,
    enqueue_email,
    invitation_email,
    password_reset_email,
    verification_email,
)
from pharma_api.core.config import Settings
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.identity import (
    EmailVerificationToken,
    PasswordResetToken,
    SecurityEvent,
    Session,
    User,
    UserProfile,
)


def _auth_context(profile: UserProfile | None = None) -> AuthContext:
    user_id = uuid4()
    tenant_id = uuid4()
    company_id = uuid4()
    branch_id = uuid4()
    return AuthContext(
        user=User(id=user_id, email="user@example.test", normalized_email="user@example.test"),
        profile=profile
        or UserProfile(
            user_id=user_id,
            display_name="Old Name",
            locale="pt-BR",
            timezone="America/Sao_Paulo",
            version=1,
        ),
        session=Session(
            id=uuid4(),
            user_id=user_id,
            token_hash="test-token-hash",  # noqa: S106
            csrf_token_hash="test-csrf-hash",  # noqa: S106
            active_tenant_id=tenant_id,
            active_company_id=company_id,
            active_branch_id=branch_id,
            created_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        membership=None,
        permission_keys=frozenset({"tenant.read"}),
    )


def test_auth_context_exposes_only_server_authorized_scope() -> None:
    auth = _auth_context()

    assert auth.tenant_id == auth.session.active_tenant_id
    assert auth.company_id == auth.session.active_company_id
    assert auth.branch_id == auth.session.active_branch_id


@pytest.mark.parametrize(
    "model",
    [UserProfile, EmailVerificationToken, PasswordResetToken, Session],
)
def test_identity_dependents_reference_users_in_orm(model: type[object]) -> None:
    user_id = model.__table__.c.user_id  # type: ignore[attr-defined]
    assert {foreign_key.target_fullname for foreign_key in user_id.foreign_keys} == {"users.id"}


def test_email_commands_build_safe_frontend_links_and_enqueue() -> None:
    settings = Settings(frontend_base_url="https://app.example.test", _env_file=None)

    verification = verification_email("user@example.test", "token", "id-1", settings)
    reset = password_reset_email("user@example.test", "token", "id-2", settings)
    invitation = invitation_email("user@example.test", "token", "id-3", settings)

    assert verification.variables["verification_url"].startswith(
        "https://app.example.test/verify-email?token="
    )
    assert reset.variables["reset_url"].startswith("https://app.example.test/reset-password?token=")
    assert invitation.variables["accept_url"].startswith(
        "https://app.example.test/invitations/accept?token="
    )
    with patch("pharma_api.application.email.service.deliver_email.send") as send:
        enqueue_email(
            EmailCommand("user@example.test", "Subject", "template", {"key": "value"}, "idem")
        )
    send.assert_called_once_with(
        "user@example.test", "Subject", "template", {"key": "value"}, "idem"
    )


@pytest.mark.asyncio
async def test_update_profile_changes_fields_and_writes_audit() -> None:
    auth = _auth_context()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=auth.profile)

    with patch(
        "pharma_api.application.auth.profile.append_audit_event", new_callable=AsyncMock
    ) as append:
        result = await update_profile(
            session,
            auth=auth,
            display_name="New Name",
            locale=None,
            timezone="UTC",
            expected_version=1,
            correlation_id="corr",
        )

    assert result.display_name == "New Name"
    assert result.timezone == "UTC"
    assert result.version == 2
    append.assert_awaited_once()
    audit_call = append.await_args
    assert audit_call is not None
    assert audit_call.args[1].changed_fields == ["display_name", "timezone"]


@pytest.mark.asyncio
async def test_update_profile_rejects_missing_and_stale_profile() -> None:
    auth = _auth_context()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):
        await update_profile(
            session,
            auth=auth,
            display_name=None,
            locale=None,
            timezone=None,
            expected_version=1,
            correlation_id=None,
        )

    session.scalar = AsyncMock(return_value=auth.profile)
    with pytest.raises(AppError) as error:
        await update_profile(
            session,
            auth=auth,
            display_name=None,
            locale=None,
            timezone=None,
            expected_version=99,
            correlation_id=None,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_list_security_events_returns_materialized_results() -> None:
    event = SecurityEvent(
        id=uuid4(),
        user_id=uuid4(),
        event_type="login",
        outcome="success",
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    scalar_result = MagicMock()
    scalar_result.all.return_value = [event]
    session = MagicMock()
    session.scalars = AsyncMock(return_value=scalar_result)

    result = await list_security_events(session, user_id=event.user_id, limit=10, offset=0)

    assert result == [event]
