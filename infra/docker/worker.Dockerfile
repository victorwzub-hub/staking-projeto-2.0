FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY apps/api /build/apps/api
COPY apps/worker /build/apps/worker
RUN python -m pip wheel --wheel-dir /wheels /build/apps/api \
    && python -m pip wheel --wheel-dir /wheels --find-links /wheels /build/apps/worker

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/.local/emails \
    && chown -R appuser:appuser /app
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install /wheels/* && rm -rf /wheels

USER appuser
CMD ["sh", "-c", "dramatiq pharma_worker.tasks --processes ${DRAMATIQ_PROCESSES:-1} --threads ${DRAMATIQ_THREADS:-4}"]
