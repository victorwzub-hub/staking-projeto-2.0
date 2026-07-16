from __future__ import annotations

import dramatiq
from redis import Redis

from pharma_api.core.config import get_settings
from pharma_api.core.logging import configure_logging, get_logger
from pharma_api.infrastructure.email.delivery import EmailMessage, deliver_development_email
from pharma_api.infrastructure.messaging.broker import configure_broker

configure_broker()
configure_logging(get_settings().app_log_level)
logger = get_logger(__name__)


@dramatiq.actor(queue_name="email", max_retries=5, min_backoff=2_000, max_backoff=60_000)
def deliver_email(
    recipient: str,
    subject: str,
    template: str,
    variables: dict[str, str],
    idempotency_key: str,
) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    marker = f"email:delivered:{idempotency_key}"
    if not redis.set(marker, "1", nx=True, ex=86_400):
        logger.info("email_delivery_duplicate_suppressed", template=template)
        return

    try:
        if settings.email_backend in {"development", "test"}:
            deliver_development_email(
                EmailMessage(
                    recipient=recipient,
                    subject=subject,
                    template=template,
                    variables=variables,
                ),
                settings,
            )
        logger.info(
            "email_delivered", template=template, recipient_domain=recipient.rsplit("@", 1)[-1]
        )
    except Exception:
        redis.delete(marker)
        raise
    finally:
        redis.close()


@dramatiq.actor(queue_name="system", max_retries=3, min_backoff=1_000)
def system_ping(probe_key: str) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        redis.set(f"worker:probe:{probe_key}", "ok", ex=300)
        logger.info("worker_system_ping")
    finally:
        redis.close()


__all__ = ["deliver_email", "system_ping"]
