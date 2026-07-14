from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from pharma_api.core.config import get_settings


def configure_broker() -> RedisBroker:
    broker = RedisBroker(url=get_settings().redis_url)  # type: ignore[no-untyped-call]
    dramatiq.set_broker(broker)
    return broker
