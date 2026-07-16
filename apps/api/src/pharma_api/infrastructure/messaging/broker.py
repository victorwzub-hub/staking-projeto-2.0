from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from pharma_api.core.config import get_settings

_broker: RedisBroker | None = None


def configure_broker() -> RedisBroker:
    global _broker
    if _broker is None:
        _broker = RedisBroker(url=get_settings().redis_url)  # type: ignore[no-untyped-call]
        dramatiq.set_broker(_broker)
    return _broker
