FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY apps/api /build/apps/api
RUN python -m pip wheel --wheel-dir /wheels /build/apps/api

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install /wheels/* && rm -rf /wheels

USER appuser
EXPOSE 8000
CMD ["uvicorn", "pharma_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
