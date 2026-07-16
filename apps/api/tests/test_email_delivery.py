from __future__ import annotations

import json

from pharma_api.core.config import Settings
from pharma_api.infrastructure.email.delivery import EmailMessage, deliver_development_email


def test_development_email_is_spooled_without_external_delivery(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(app_env="test", email_spool_directory=tmp_path, _env_file=None)
    target = deliver_development_email(
        EmailMessage(
            recipient="person@example.test",
            subject="Security notification",
            template="security_notice",
            variables={"event": "password_changed"},
        ),
        settings,
    )

    assert target.parent == tmp_path
    payload = json.loads(target.read_text())
    assert payload == {
        "recipient": "person@example.test",
        "subject": "Security notification",
        "template": "security_notice",
        "variables": {"event": "password_changed"},
    }
