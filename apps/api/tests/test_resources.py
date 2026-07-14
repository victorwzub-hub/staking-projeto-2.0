from __future__ import annotations

import pytest

from pharma_api.infrastructure.cache import redis as redis_module
from pharma_api.infrastructure.db import session as session_module


class FakeEngine:
    def __init__(self) -> None:
        self.dispose_calls = 0

    async def dispose(self) -> None:
        self.dispose_calls += 1


class FakeRedis:
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_close_engine_disposes_and_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(session_module, "_engine", engine)

    await session_module.close_engine()
    await session_module.close_engine()

    assert engine.dispose_calls == 1
    assert session_module._engine is None


@pytest.mark.asyncio
async def test_close_redis_client_closes_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = FakeRedis()
    monkeypatch.setattr(redis_module, "_redis_client", redis_client)

    await redis_module.close_redis_client()
    await redis_module.close_redis_client()

    assert redis_client.close_calls == 1
    assert redis_module._redis_client is None
