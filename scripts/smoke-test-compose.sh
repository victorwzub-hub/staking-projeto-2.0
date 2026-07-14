#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-pharma-intelligence-smoke}"
COMPOSE=(docker compose --project-name "$PROJECT_NAME")
CREATED_ENV=0

cleanup() {
  local exit_code=$?
  trap - EXIT

  if (( exit_code != 0 )); then
    echo "Smoke test failed. Container state follows:" >&2
    echo "+ docker compose ps" >&2
    "${COMPOSE[@]}" ps >&2 || true
    echo "+ docker compose logs" >&2
    "${COMPOSE[@]}" logs --no-color >&2 || true
  fi

  "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  if (( CREATED_ENV == 1 )); then
    rm -f .env
  fi
  exit "$exit_code"
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to execute the Compose smoke test." >&2
  exit 127
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  CREATED_ENV=1
fi

wait_for_health() {
  local service=$1
  local timeout_seconds=${2:-180}
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    local container_id
    container_id="$("${COMPOSE[@]}" ps -q "$service")"
    if [[ -n "$container_id" ]]; then
      local state
      state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
      if [[ "$state" == "healthy" || "$state" == "running" ]]; then
        return 0
      fi
      if [[ "$state" == "unhealthy" || "$state" == "exited" || "$state" == "dead" ]]; then
        echo "Service $service entered state $state." >&2
        return 1
      fi
    fi
    sleep 2
  done

  echo "Timed out waiting for service $service." >&2
  return 1
}

wait_for_http_200() {
  local url=$1
  local timeout_seconds=${2:-120}
  local deadline=$((SECONDS + timeout_seconds))

  while (( SECONDS < deadline )); do
    if curl --silent --show-error --fail --max-time 5 "$url" >/dev/null; then
      return 0
    fi
    sleep 2
  done

  echo "Timed out waiting for HTTP 200 from $url." >&2
  return 1
}

echo "+ docker compose up --build --detach"
"${COMPOSE[@]}" up --build --detach

wait_for_health postgres
wait_for_health redis
wait_for_health api
wait_for_health web
wait_for_health worker

wait_for_http_200 "http://127.0.0.1:${API_PORT:-8000}/api/v1/health"
wait_for_http_200 "http://127.0.0.1:${API_PORT:-8000}/api/v1/readiness"
wait_for_http_200 "http://127.0.0.1:${WEB_PORT:-3000}"

curl --silent --show-error --fail "http://127.0.0.1:${API_PORT:-8000}/api/v1/health" \
  | grep --quiet '"status":"ok"'
curl --silent --show-error --fail "http://127.0.0.1:${API_PORT:-8000}/api/v1/readiness" \
  | grep --quiet '"status":"ready"'
curl --silent --show-error --fail "http://127.0.0.1:${WEB_PORT:-3000}" \
  | grep --quiet "Verificando conexão com a API"

"${COMPOSE[@]}" exec -T web test -f /app/apps/web/server.js
"${COMPOSE[@]}" exec -T web node -e \
  "fetch('http://api:8000/api/v1/health').then(r => { if (!r.ok) process.exit(1); return r.json() }).then(b => { if (b.status !== 'ok') process.exit(1) }).catch(() => process.exit(1))"

expected_services=(postgres redis api worker web)
running_services="$("${COMPOSE[@]}" ps --status running --services)"
for service in "${expected_services[@]}"; do
  if ! grep --fixed-strings --line-regexp --quiet "$service" <<<"$running_services"; then
    echo "Expected service $service is not running." >&2
    exit 1
  fi
done

"${COMPOSE[@]}" ps
echo "Compose smoke test passed."
