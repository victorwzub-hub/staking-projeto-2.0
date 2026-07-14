from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import text

from pharma_api.core.config import get_settings
from pharma_api.infrastructure.cache.redis import get_redis_client
from pharma_api.infrastructure.db.session import get_engine
from pharma_api.schemas.health import DependencyStatus, ReadinessResponse

Check = Callable[[], Awaitable[None]]


async def check_database() -> None:
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis() -> None:
    await get_redis_client().ping()


async def _run_check(check: Check) -> DependencyStatus:
    timeout = get_settings().readiness_timeout_seconds
    try:
        await asyncio.wait_for(check(), timeout=timeout)
        return DependencyStatus(status="ok")
    except Exception as exc:
        return DependencyStatus(status="error", detail=type(exc).__name__)


async def probe_readiness() -> ReadinessResponse:
    database, redis = await asyncio.gather(
        _run_check(check_database),
        _run_check(check_redis),
    )
    checks = {"database": database, "redis": redis}
    is_ready = all(check.status == "ok" for check in checks.values())
    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
