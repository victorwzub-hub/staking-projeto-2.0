from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from pharma_api.core.config import Settings
from pharma_api.core.errors import AppError
from pharma_api.main import create_app


class ControlledValidationPayload(BaseModel):
    quantity: int

    @field_validator("quantity")
    @classmethod
    def reject_negative_quantity(cls, value: int) -> int:
        if value < 0:
            raise ValueError("quantity must be non-negative")
        return value


def test_openapi_is_versioned() -> None:
    app = create_app()
    schema = app.openapi()

    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/readiness" in schema["paths"]


def test_root_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "Pharma Intelligence SaaS",
        "version": "0.2.0",
        "status": "ok",
        "documentation_url": "/docs",
        "health_url": "/api/v1/health",
    }


def test_root_omits_documentation_url_in_production() -> None:
    settings = Settings(
        app_env="production",
        database_url=("postgresql+psycopg://pharma:strong-example@db.internal:5432/pharma"),
        redis_url="redis://cache.internal:6379/0",
        api_cors_origins="https://app.example.com",
        frontend_base_url="https://app.example.com",
        session_cookie_secure=True,
        session_token_pepper="0123456789abcdef0123456789abcdef",  # noqa: S106
        one_time_token_pepper="abcdef0123456789abcdef0123456789",  # noqa: S106
        _env_file=None,
    )

    with TestClient(create_app(settings)) as production_client:
        response = production_client.get("/")

    assert response.status_code == 200
    assert response.json()["documentation_url"] is None


def test_global_app_error_handler() -> None:
    app: FastAPI = create_app()

    @app.get("/test-error")
    async def test_error() -> None:
        raise AppError(code="test_error", message="Expected failure", status_code=409)

    with TestClient(app) as client:
        response = client.get("/test-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "test_error", "message": "Expected failure", "details": {}}
    }


def test_request_validation_details_are_json_serializable() -> None:
    app: FastAPI = create_app()

    @app.post("/test-validation")
    async def test_validation(payload: ControlledValidationPayload) -> ControlledValidationPayload:
        return payload

    with TestClient(app) as client:
        response = client.post("/test-validation", json={"quantity": -1})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["ctx"]["error"] == "quantity must be non-negative"


def test_lifespan_closes_database_and_redis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    close_redis = AsyncMock()
    close_database = AsyncMock()
    monkeypatch.setattr("pharma_api.main.close_redis_client", close_redis)
    monkeypatch.setattr("pharma_api.main.close_engine", close_database)

    with TestClient(create_app()):
        pass

    close_redis.assert_awaited_once_with()
    close_database.assert_awaited_once_with()
