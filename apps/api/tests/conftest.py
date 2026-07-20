import asyncio
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pharma_api.main import create_app

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client
