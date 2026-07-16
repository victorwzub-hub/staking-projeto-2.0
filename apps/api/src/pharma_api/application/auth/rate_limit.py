from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import AppError
from pharma_api.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitKey:
    email_hash: str
    ip_hash: str | None

    @property
    def redis_key(self) -> str:
        suffix = self.ip_hash or "unknown"
        return f"auth:login:{self.email_hash}:{suffix}"


class LoginRateLimiter:
    def __init__(self, redis: Redis, settings: Settings | None = None) -> None:
        self.redis = redis
        self.settings = settings or get_settings()

    async def ensure_allowed(self, key: RateLimitKey) -> None:
        try:
            ttl = await self.redis.ttl(key.redis_key)
            attempts = await self.redis.get(key.redis_key)
        except RedisError as exc:
            logger.error("login_rate_limit_unavailable", error_type=type(exc).__name__)
            raise AppError(
                code="authentication_temporarily_unavailable",
                message="Authentication is temporarily unavailable",
                status_code=503,
            ) from exc
        if attempts is not None and int(attempts) >= self.settings.login_max_attempts:
            raise AppError(
                code="too_many_attempts",
                message="Too many authentication attempts. Try again later.",
                status_code=429,
                details={"retry_after_seconds": max(ttl, 1)},
            )

    async def record_failure(self, key: RateLimitKey) -> None:
        script = """
        local count = redis.call('INCR', KEYS[1])
        local delay = tonumber(ARGV[1]) * (2 ^ math.max(0, count - 1))
        local maximum = tonumber(ARGV[2])
        if delay > maximum then delay = maximum end
        redis.call('EXPIRE', KEYS[1], math.floor(delay))
        return count
        """
        try:
            await self.redis.eval(
                script,
                1,
                key.redis_key,
                self.settings.login_lockout_seconds,
                self.settings.login_max_lockout_seconds,
            )
        except RedisError as exc:
            logger.error("login_rate_limit_record_failed", error_type=type(exc).__name__)

    async def clear(self, key: RateLimitKey) -> None:
        try:
            await self.redis.delete(key.redis_key)
        except RedisError as exc:
            logger.warning("login_rate_limit_clear_failed", error_type=type(exc).__name__)


class PublicAuthRateLimiter:
    """Fail-closed limiter for public token and e-mail based authentication actions."""

    def __init__(self, redis: Redis, settings: Settings | None = None) -> None:
        self.redis = redis
        self.settings = settings or get_settings()

    async def consume(self, *, action: str, subject_hash: str, ip_hash: str | None) -> None:
        suffix = ip_hash or "unknown"
        key = f"auth:public:{action}:{subject_hash}:{suffix}"
        try:
            async with self.redis.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, self.settings.public_auth_window_seconds, nx=True)
                count, _ = await pipeline.execute()
                ttl = await self.redis.ttl(key)
        except RedisError as exc:
            logger.error(
                "public_auth_rate_limit_unavailable", action=action, error_type=type(exc).__name__
            )
            raise AppError(
                code="authentication_temporarily_unavailable",
                message="Authentication is temporarily unavailable",
                status_code=503,
            ) from exc
        if int(count) > self.settings.public_auth_max_requests:
            raise AppError(
                code="too_many_requests",
                message="Too many requests. Try again later.",
                status_code=429,
                details={"retry_after_seconds": max(ttl, 1)},
            )
