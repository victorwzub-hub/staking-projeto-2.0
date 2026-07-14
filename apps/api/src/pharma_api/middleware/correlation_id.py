from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"
CORRELATION_ID_MAX_LENGTH = 128
_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_correlation_id(candidate: str | None) -> str:
    if (
        candidate
        and len(candidate) <= CORRELATION_ID_MAX_LENGTH
        and _CORRELATION_ID_PATTERN.fullmatch(candidate)
    ):
        return candidate
    return str(uuid4())


async def correlation_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    correlation_id = _safe_correlation_id(request.headers.get(CORRELATION_ID_HEADER))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    try:
        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
    finally:
        structlog.contextvars.clear_contextvars()
