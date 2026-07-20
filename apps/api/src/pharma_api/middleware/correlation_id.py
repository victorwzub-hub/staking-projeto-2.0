from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.requests import Request
from starlette.responses import Response

from pharma_api.core.logging import get_logger

CORRELATION_ID_HEADER = "X-Correlation-ID"
CORRELATION_ID_MAX_LENGTH = 128
_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
logger = get_logger(__name__)


def _safe_correlation_id(candidate: str | None) -> str:
    if (
        candidate
        and len(candidate) <= CORRELATION_ID_MAX_LENGTH
        and _CORRELATION_ID_PATTERN.fullmatch(candidate)
    ):
        return candidate
    return str(uuid4())


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    candidate = getattr(route, "path", None)
    return candidate if isinstance(candidate, str) else "unmatched"


async def correlation_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    correlation_id = _safe_correlation_id(request.headers.get(CORRELATION_ID_HEADER))
    request.state.correlation_id = correlation_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    started = perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1_000, 2)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        logger.info(
            "http_request_completed",
            method=request.method,
            route=_route_template(request),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
    except Exception:
        logger.exception(
            "http_request_failed",
            method=request.method,
            route=_route_template(request),
            duration_ms=round((perf_counter() - started) * 1_000, 2),
        )
        raise
    finally:
        structlog.contextvars.clear_contextvars()
