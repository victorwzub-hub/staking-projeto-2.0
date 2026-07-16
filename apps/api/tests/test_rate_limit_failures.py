from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import RedisError

from pharma_api.application.auth.rate_limit import (
    LoginRateLimiter,
    PublicAuthRateLimiter,
    RateLimitKey,
)
from pharma_api.core.config import Settings
from pharma_api.core.errors import AppError


class FailingPipelineContext:
    async def __aenter__(self) -> MagicMock:
        raise RedisError("unavailable")

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.mark.asyncio
async def test_login_rate_limiter_allows_below_threshold_and_clears() -> None:
    redis = MagicMock()
    redis.ttl = AsyncMock(return_value=30)
    redis.get = AsyncMock(return_value=b"2")
    redis.delete = AsyncMock(return_value=1)
    limiter = LoginRateLimiter(redis, Settings(login_max_attempts=5, _env_file=None))
    key = RateLimitKey(email_hash="email", ip_hash=None)

    await limiter.ensure_allowed(key)
    await limiter.clear(key)

    redis.delete.assert_awaited_once_with(key.redis_key)


@pytest.mark.asyncio
async def test_login_rate_limiter_rejects_threshold_with_retry_after() -> None:
    redis = MagicMock()
    redis.ttl = AsyncMock(return_value=42)
    redis.get = AsyncMock(return_value=b"5")
    limiter = LoginRateLimiter(redis, Settings(login_max_attempts=5, _env_file=None))

    with pytest.raises(AppError) as error:
        await limiter.ensure_allowed(RateLimitKey("email", "ip"))

    assert error.value.status_code == 429
    assert error.value.details == {"retry_after_seconds": 42}


@pytest.mark.asyncio
async def test_login_rate_limiter_fails_closed_when_redis_is_unavailable() -> None:
    redis = MagicMock()
    redis.ttl = AsyncMock(side_effect=RedisError("unavailable"))
    limiter = LoginRateLimiter(redis, Settings(_env_file=None))

    with pytest.raises(AppError) as error:
        await limiter.ensure_allowed(RateLimitKey("email", "ip"))

    assert error.value.status_code == 503
    assert error.value.code == "authentication_temporarily_unavailable"


@pytest.mark.asyncio
async def test_login_rate_limiter_logging_paths_do_not_raise() -> None:
    redis = MagicMock()
    redis.eval = AsyncMock(side_effect=RedisError("unavailable"))
    redis.delete = AsyncMock(side_effect=RedisError("unavailable"))
    limiter = LoginRateLimiter(redis, Settings(_env_file=None))
    key = RateLimitKey("email", "ip")

    await limiter.record_failure(key)
    await limiter.clear(key)


@pytest.mark.asyncio
async def test_public_rate_limiter_fails_closed_when_redis_is_unavailable() -> None:
    redis = MagicMock()
    redis.pipeline.return_value = FailingPipelineContext()
    limiter = PublicAuthRateLimiter(redis, Settings(_env_file=None))

    with pytest.raises(AppError) as error:
        await limiter.consume(action="register", subject_hash="email", ip_hash="ip")

    assert error.value.status_code == 503
