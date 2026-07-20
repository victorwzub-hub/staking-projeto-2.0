from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pharma_api.core.config import Settings, get_settings
from pharma_api.main import create_app

_REQUIRED = ("TEST_ADMIN_DATABASE_URL", "TEST_DATABASE_URL", "TEST_REDIS_URL")
pytestmark = pytest.mark.integration


def integration_available() -> bool:
    return all(os.getenv(name) for name in _REQUIRED)


@pytest.fixture(scope="session", autouse=True)
def configure_integration_environment() -> Iterator[None]:
    if not integration_available():
        pytest.skip("real PostgreSQL and Redis URLs are not configured")
    os.environ.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
            "REDIS_URL": os.environ["TEST_REDIS_URL"],
            "EMAIL_BACKEND": "test",
            "SESSION_TOKEN_PEPPER": "integration-session-pepper-32-characters-minimum",
            "ONE_TIME_TOKEN_PEPPER": "integration-token-pepper-32-characters-minimum",
            "ARGON2_TIME_COST": "2",
            "ARGON2_MEMORY_COST_KIB": "19456",
            "ARGON2_PARALLELISM": "1",
        }
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(os.environ["TEST_REDIS_URL"], decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def integration_settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        app_env="test",
        database_url=os.environ["TEST_DATABASE_URL"],
        redis_url=os.environ["TEST_REDIS_URL"],
        email_backend="test",
        email_spool_directory=tmp_path,
        session_token_pepper="integration-session-pepper-32-characters-minimum",  # noqa: S106
        one_time_token_pepper="integration-token-pepper-32-characters-minimum",  # noqa: S106
        argon2_time_cost=2,
        argon2_memory_cost_kib=19_456,
        argon2_parallelism=1,
        _env_file=None,
    )


@pytest.fixture
def integration_client(integration_settings: Settings) -> Iterator[TestClient]:
    get_settings.cache_clear()
    get_settings.cache_info()
    with TestClient(create_app(integration_settings)) as client:
        yield client
    # The application lifespan owns global resources.
    get_settings.cache_clear()
