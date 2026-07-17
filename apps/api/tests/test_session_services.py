from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from pharma_api.application.auth.sessions import (
    list_sessions,
    revoke_all_sessions,
    revoke_session,
    rotate_current_session,
)
from pharma_api.application.auth.types import AuthContext
from pharma_api.core.config import Settings
from pharma_api.core.errors import AppError
from pharma_api.infrastructure.db.models.identity import Session, User, UserProfile


def _context() -> AuthContext:
    user_id = uuid4()
    now = datetime.now(UTC)
    return AuthContext(
        user=User(id=user_id, email="user@example.test", normalized_email="user@example.test"),
        profile=UserProfile(
            user_id=user_id,
            display_name="User",
            locale="pt-BR",
            timezone="UTC",
            version=1,
        ),
        session=Session(
            id=uuid4(),
            user_id=user_id,
            token_hash="test-session-hash",  # noqa: S106
            csrf_token_hash="test-csrf-hash",  # noqa: S106
            active_tenant_id=uuid4(),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        membership=None,
        permission_grants=frozenset(),
    )


@pytest.mark.asyncio
async def test_list_sessions_materializes_current_users_sessions() -> None:
    auth = _context()
    scalar_result = MagicMock()
    scalar_result.all.return_value = [auth.session]
    session = MagicMock()
    session.scalars = AsyncMock(return_value=scalar_result)

    assert await list_sessions(session, auth) == [auth.session]


@pytest.mark.asyncio
async def test_revoke_session_marks_target_and_audits() -> None:
    auth = _context()
    target = Session(
        id=uuid4(),
        user_id=auth.user.id,
        token_hash="target-session-hash",  # noqa: S106
        csrf_token_hash="target-csrf-hash",  # noqa: S106
        created_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=target)

    with patch(
        "pharma_api.application.auth.sessions.append_audit_event", new_callable=AsyncMock
    ) as append:
        await revoke_session(session, auth=auth, session_id=target.id, correlation_id="corr")

    assert target.revoked_at is not None
    assert target.revocation_reason == "user_revoked"
    append.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_session_denial_is_committed_before_not_found() -> None:
    auth = _context()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    session.commit = AsyncMock()

    with (
        patch(
            "pharma_api.application.auth.sessions.append_audit_event",
            new_callable=AsyncMock,
        ) as append,
        pytest.raises(AppError) as error,
    ):
        await revoke_session(session, auth=auth, session_id=uuid4(), correlation_id="corr")

    assert error.value.status_code == 404
    append.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("include_current", "rowcount"), [(False, 2), (True, None)])
async def test_revoke_all_sessions_returns_effective_count(
    include_current: bool, rowcount: int | None
) -> None:
    auth = _context()
    execution = MagicMock()
    execution.rowcount = rowcount
    session = MagicMock()
    session.execute = AsyncMock(return_value=execution)

    with patch(
        "pharma_api.application.auth.sessions.append_audit_event", new_callable=AsyncMock
    ) as append:
        count = await revoke_all_sessions(
            session,
            auth=auth,
            include_current=include_current,
            correlation_id="corr",
        )

    assert count == (rowcount or 0)
    append.assert_awaited_once()


@pytest.mark.asyncio
async def test_rotate_current_session_replaces_hashes_and_expiration() -> None:
    auth = _context()
    previous_hash = auth.session.token_hash
    session = MagicMock()
    settings = Settings(
        session_ttl_seconds=1800,
        session_token_pepper="0123456789abcdef0123456789abcdef",  # noqa: S106
        one_time_token_pepper="abcdef0123456789abcdef0123456789",  # noqa: S106
        _env_file=None,
    )

    with patch(
        "pharma_api.application.auth.sessions.append_audit_event", new_callable=AsyncMock
    ) as append:
        rotated = await rotate_current_session(
            session,
            auth=auth,
            correlation_id="corr",
            settings=settings,
        )

    assert rotated.raw_session_token
    assert rotated.raw_csrf_token
    assert rotated.session.token_hash != previous_hash
    assert rotated.session.expires_at > datetime.now(UTC)
    append.assert_awaited_once()
