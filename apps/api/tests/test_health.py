from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from pharma_api.application.health import service
from pharma_api.middleware.correlation_id import (
    CORRELATION_ID_MAX_LENGTH,
    _safe_correlation_id,
)


async def _ok() -> None:
    return None


async def _fail() -> None:
    raise ConnectionError("dependency unavailable")


def test_liveness_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.1"
    assert response.headers["X-Correlation-ID"]


def test_valid_correlation_id_is_propagated(client: TestClient) -> None:
    correlation_id = "Request_2026-07.14"
    response = client.get("/api/v1/health", headers={"X-Correlation-ID": correlation_id})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == correlation_id


def test_too_long_correlation_id_is_replaced_with_uuid(client: TestClient) -> None:
    invalid_id = "a" * (CORRELATION_ID_MAX_LENGTH + 1)
    response = client.get("/api/v1/health", headers={"X-Correlation-ID": invalid_id})

    generated_id = response.headers["X-Correlation-ID"]
    assert generated_id != invalid_id
    assert str(UUID(generated_id)) == generated_id


@pytest.mark.parametrize("invalid_id", ["has spaces", "value/with/slashes", "line\nbreak"])
def test_invalid_correlation_id_characters_are_replaced(invalid_id: str) -> None:
    generated_id = _safe_correlation_id(invalid_id)

    assert generated_id != invalid_id
    assert str(UUID(generated_id)) == generated_id


def test_readiness_returns_200_when_dependencies_are_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "check_database", _ok)
    monkeypatch.setattr(service, "check_redis", _ok)

    response = client.get("/api/v1/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "ok", "detail": None},
            "redis": {"status": "ok", "detail": None},
        },
    }


def test_readiness_returns_503_when_a_dependency_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "check_database", _fail)
    monkeypatch.setattr(service, "check_redis", _ok)

    response = client.get("/api/v1/readiness")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == {
        "status": "error",
        "detail": "ConnectionError",
    }
