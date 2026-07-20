from __future__ import annotations

from typing import Any

import pytest

from pharma_api.application.auth.rate_limit import LoginRateLimiter, RateLimitKey
from pharma_api.core.config import Settings


class FakeRedis:
    def __init__(self) -> None:
        self.arguments: tuple[Any, ...] | None = None

    async def eval(self, *arguments: Any) -> int:
        self.arguments = arguments
        return 1


@pytest.mark.asyncio
async def test_login_failure_uses_progressive_bounded_backoff() -> None:
    redis = FakeRedis()
    settings = Settings(
        app_env="test",
        login_lockout_seconds=60,
        login_max_lockout_seconds=3600,
        _env_file=None,
    )
    limiter = LoginRateLimiter(redis, settings)  # type: ignore[arg-type]
    key = RateLimitKey(email_hash="email", ip_hash="ip")

    await limiter.record_failure(key)

    assert redis.arguments is not None
    assert redis.arguments[1:] == (1, key.redis_key, 60, 3600)
    assert "2 ^ math.max" in redis.arguments[0]
