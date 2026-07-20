from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pharma_api.application.auth.rate_limit import PublicAuthRateLimiter
from pharma_api.core.config import Settings
from pharma_api.core.errors import AppError


class PipelineContext:
    def __init__(self, pipeline: MagicMock) -> None:
        self.pipeline = pipeline

    async def __aenter__(self) -> MagicMock:
        return self.pipeline

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.mark.asyncio
async def test_public_rate_limiter_allows_requests_within_limit() -> None:
    pipeline = MagicMock()
    pipeline.incr.return_value = pipeline
    pipeline.expire.return_value = pipeline
    pipeline.execute = AsyncMock(return_value=[1, True])
    redis = MagicMock()
    redis.pipeline.return_value = PipelineContext(pipeline)
    redis.ttl = AsyncMock(return_value=900)
    limiter = PublicAuthRateLimiter(redis, Settings(public_auth_max_requests=5))

    await limiter.consume(action="register", subject_hash="email", ip_hash="ip")

    pipeline.incr.assert_called_once_with("auth:public:register:email:ip")


@pytest.mark.asyncio
async def test_public_rate_limiter_rejects_excess_requests() -> None:
    pipeline = MagicMock()
    pipeline.incr.return_value = pipeline
    pipeline.expire.return_value = pipeline
    pipeline.execute = AsyncMock(return_value=[6, False])
    redis = MagicMock()
    redis.pipeline.return_value = PipelineContext(pipeline)
    redis.ttl = AsyncMock(return_value=120)
    limiter = PublicAuthRateLimiter(redis, Settings(public_auth_max_requests=5))

    with pytest.raises(AppError) as error:
        await limiter.consume(action="forgot", subject_hash="email", ip_hash=None)

    assert error.value.status_code == 429
    assert error.value.details == {"retry_after_seconds": 120}
