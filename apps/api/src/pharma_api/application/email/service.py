from __future__ import annotations

from dataclasses import dataclass

from pharma_api.core.config import Settings, get_settings
from pharma_api.infrastructure.email.tasks import deliver_email


@dataclass(frozen=True, slots=True)
class EmailCommand:
    recipient: str
    subject: str
    template: str
    variables: dict[str, str]
    idempotency_key: str


def enqueue_email(command: EmailCommand) -> None:
    deliver_email.send(
        command.recipient,
        command.subject,
        command.template,
        command.variables,
        command.idempotency_key,
    )


def verification_email(
    recipient: str, token: str, token_id: str, settings: Settings | None = None
) -> EmailCommand:
    config = settings or get_settings()
    return EmailCommand(
        recipient=recipient,
        subject="Confirme seu e-mail",
        template="verify_email",
        variables={"verification_url": f"{config.frontend_base_url}/verify-email?token={token}"},
        idempotency_key=f"verify:{token_id}",
    )


def password_reset_email(
    recipient: str, token: str, token_id: str, settings: Settings | None = None
) -> EmailCommand:
    config = settings or get_settings()
    return EmailCommand(
        recipient=recipient,
        subject="Redefina sua senha",
        template="password_reset",
        variables={"reset_url": f"{config.frontend_base_url}/reset-password?token={token}"},
        idempotency_key=f"password-reset:{token_id}",
    )


def invitation_email(
    recipient: str, token: str, invitation_id: str, settings: Settings | None = None
) -> EmailCommand:
    config = settings or get_settings()
    return EmailCommand(
        recipient=recipient,
        subject="Convite para o Pharma Intelligence",
        template="invitation",
        variables={"accept_url": f"{config.frontend_base_url}/invitations/accept?token={token}"},
        idempotency_key=f"invitation:{invitation_id}",
    )
