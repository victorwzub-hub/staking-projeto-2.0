from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from pharma_api.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Exception):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]

    try:
        encoded = jsonable_encoder(value)
    except (TypeError, ValueError):
        return repr(value)
    if encoded is value:
        return repr(value)
    return _json_safe(encoded)


def _payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": _json_safe(details)}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload("validation_error", "Request validation failed", exc.errors()),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        original = getattr(exc, "orig", None)
        diagnostic = getattr(original, "diag", None)
        logger.warning(
            "database_integrity_error",
            method=request.method,
            path=request.url.path,
            constraint=getattr(diagnostic, "constraint_name", None),
        )
        return JSONResponse(
            status_code=409,
            content=_payload(
                "resource_conflict", "The operation conflicts with an existing resource"
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unexpected_error",
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=_payload("internal_server_error", "An unexpected error occurred"),
        )
