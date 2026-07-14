from __future__ import annotations

import dramatiq

from pharma_api.core.config import get_settings
from pharma_api.core.logging import configure_logging, get_logger
from pharma_worker.broker import configure_broker

broker = configure_broker()
configure_logging(get_settings().app_log_level)
logger = get_logger(__name__)


@dramatiq.actor(queue_name="system", max_retries=3, min_backoff=1_000)
def system_ping(message: str = "pong") -> str:
    logger.info("worker_system_ping", message=message)
    return message


__all__ = ["broker", "system_ping"]
