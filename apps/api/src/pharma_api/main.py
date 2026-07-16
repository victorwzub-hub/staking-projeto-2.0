from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pharma_api import __version__
from pharma_api.api.v1.router import api_router
from pharma_api.core.config import Settings, get_settings
from pharma_api.core.errors import register_exception_handlers
from pharma_api.core.logging import configure_logging, get_logger
from pharma_api.infrastructure.cache.redis import close_redis_client
from pharma_api.infrastructure.db.session import close_engine
from pharma_api.middleware.correlation_id import correlation_id_middleware
from pharma_api.schemas.service import ServiceResponse

logger = get_logger(__name__)


def _build_lifespan(
    app_settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_started",
            environment=app_settings.app_env,
            version=__version__,
        )
        try:
            yield
        finally:
            await close_redis_client()
            await close_engine()
            logger.info("application_stopped")

    return lifespan


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or get_settings()
    configure_logging(settings.app_log_level)
    docs_url = "/docs" if settings.app_env != "production" else None
    redoc_url = "/redoc" if settings.app_env != "production" else None

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.app_debug,
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=_build_lifespan(settings),
    )
    app.state.settings = settings
    app.middleware("http")(correlation_id_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-ID",
            "X-CSRF-Token",
            "Idempotency-Key",
        ],
    )
    register_exception_handlers(app)

    @app.get("/", response_model=ServiceResponse, include_in_schema=False)
    async def service_root() -> ServiceResponse:
        return ServiceResponse(
            service=settings.app_name,
            version=__version__,
            documentation_url=docs_url,
            health_url=f"{settings.api_v1_prefix}/health",
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
