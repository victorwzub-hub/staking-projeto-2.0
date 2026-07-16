from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from pharma_api.application.audit.service import AuditRecord, append_audit_event, sanitize_metadata


def test_sanitize_metadata_redacts_nested_secrets_and_bounds_values() -> None:
    value = {
        "password": "secret",
        "nested": {"token": "raw", "safe": "x" * 1200},
        "items": ({"authorization": "bearer"}, object()),
    }

    sanitized = sanitize_metadata(value)

    assert sanitized["password"] == "[REDACTED]"  # noqa: S105
    assert sanitized["nested"]["token"] == "[REDACTED]"  # noqa: S105
    assert len(sanitized["nested"]["safe"]) == 1000
    assert sanitized["items"][0]["authorization"] == "[REDACTED]"
    assert isinstance(sanitized["items"][1], str)


@pytest.mark.asyncio
async def test_append_audit_event_adds_sanitized_append_only_record() -> None:
    session = MagicMock()
    record = AuditRecord(
        action="test.event",
        category="test",
        outcome="success",
        actor_user_id=uuid4(),
        metadata={"password": "secret", "safe": 1},
    )

    event = await append_audit_event(session, record)

    session.add.assert_called_once_with(event)
    assert event.action == "test.event"
    assert event.metadata_json == {"password": "[REDACTED]", "safe": 1}
