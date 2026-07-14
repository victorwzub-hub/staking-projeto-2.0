from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from pharma_api import __version__
from pharma_api.application.health.service import probe_readiness
from pharma_api.core.config import get_settings
from pharma_api.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(service=get_settings().app_name, version=__version__)


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Dependency readiness probe",
)
async def readiness() -> JSONResponse:
    result = await probe_readiness()
    status_code = 200 if result.status == "ready" else 503
    return JSONResponse(status_code=status_code, content=result.model_dump())
