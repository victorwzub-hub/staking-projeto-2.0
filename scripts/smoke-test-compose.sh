#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-pharma-intelligence-smoke}"
COMPOSE=(docker compose --project-name "$PROJECT_NAME")
CREATED_ENV=0
KEEP_STACK="${KEEP_STACK:-0}"

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
  if (( exit_code != 0 )) || [[ "$KEEP_STACK" != "1" ]]; then
    "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
    if (( CREATED_ENV == 1 )); then rm -f .env; fi
  else
    echo "KEEP_STACK=1: Compose services remain running for the next gate."
  fi
  exit "$exit_code"
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || { echo "Docker is required." >&2; exit 127; }
command -v curl >/dev/null 2>&1 || { echo "curl is required." >&2; exit 127; }
if [[ ! -f .env ]]; then cp .env.example .env; CREATED_ENV=1; fi

wait_for_container() {
  local service=$1
  local expected=$2
  local timeout_seconds=${3:-240}
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    local id state exit_code
    id="$("${COMPOSE[@]}" ps --all --quiet "$service")"
    if [[ -n "$id" ]]; then
      state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id")"
      exit_code="$(docker inspect --format '{{.State.ExitCode}}' "$id")"
      if [[ "$expected" == "completed" && "$state" == "exited" && "$exit_code" == "0" ]]; then return 0; fi
      if [[ "$expected" == "healthy" && ( "$state" == "healthy" || "$state" == "running" ) ]]; then return 0; fi
      if [[ "$state" == "unhealthy" || "$state" == "dead" || ( "$state" == "exited" && "$expected" != "completed" ) ]]; then
        echo "Service $service entered state $state (exit $exit_code)." >&2; return 1
      fi
    fi
    sleep 2
  done
  echo "Timed out waiting for $service ($expected)." >&2; return 1
}

wait_for_http_200() {
  local url=$1
  local timeout_seconds=${2:-180}
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    if curl --silent --show-error --fail --max-time 5 "$url" >/dev/null; then return 0; fi
    sleep 2
  done
  echo "Timed out waiting for HTTP 200 from $url." >&2; return 1
}

wait_for_redis_key() {
  local key=$1
  local timeout_seconds=${2:-60}
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    if [[ "$("${COMPOSE[@]}" exec -T redis redis-cli GET "$key" | tr -d '\r')" == "ok" ]]; then return 0; fi
    sleep 1
  done
  echo "Worker probe key $key was not produced." >&2; return 1
}

echo "+ docker compose config"
"${COMPOSE[@]}" config >/dev/null

echo "+ docker compose build"
"${COMPOSE[@]}" build

echo "+ docker compose up --detach"
"${COMPOSE[@]}" up --detach

wait_for_container postgres healthy
wait_for_container redis healthy
wait_for_container migrate completed
wait_for_container api healthy
wait_for_container worker healthy
wait_for_container web healthy

# The application role must never own the database or bypass PostgreSQL RLS.
role_flags="$(${COMPOSE[@]} exec -T postgres psql \
  --username "${POSTGRES_ADMIN_USER:-pharma_admin}" \
  --dbname "${POSTGRES_DB:-pharma}" \
  --tuples-only --no-align \
  --command "SELECT rolsuper::text || ':' || rolbypassrls::text || ':' || rolcreaterole::text FROM pg_roles WHERE rolname='${POSTGRES_APP_USER:-pharma_app}'" | tr -d '\r')"
[[ "$role_flags" == "false:false:false" ]] || {
  echo "Application PostgreSQL role has unsafe privileges: $role_flags" >&2
  exit 1
}

wait_for_http_200 "http://127.0.0.1:${API_PORT:-8000}/api/v1/health"
wait_for_http_200 "http://127.0.0.1:${API_PORT:-8000}/api/v1/readiness"
wait_for_http_200 "http://127.0.0.1:${WEB_PORT:-3000}"

curl --silent --show-error --fail "http://127.0.0.1:${API_PORT:-8000}/api/v1/health" | grep --quiet '"status":"ok"'
curl --silent --show-error --fail "http://127.0.0.1:${API_PORT:-8000}/api/v1/readiness" | grep --quiet '"status":"ready"'
"${COMPOSE[@]}" exec -T web test -f /app/apps/web/server.js
"${COMPOSE[@]}" exec -T web node -e \
  "fetch('http://api:8000/api/v1/health').then(r => r.json()).then(b => { if (b.status !== 'ok') process.exit(1) })"

# Verify migrations can be executed repeatedly under the advisory lock.
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" exec -T api alembic -c /app/alembic.ini current | grep --quiet '20260716_0001'

# Prove the worker consumes a real Redis-backed Dramatiq task.
probe="compose-$(date +%s)"
"${COMPOSE[@]}" exec -T api python -c \
  "from pharma_api.infrastructure.email.tasks import system_ping; system_ping.send('$probe')"
wait_for_redis_key "worker:probe:$probe"

expected_running=(postgres redis api worker web)
running_services="$("${COMPOSE[@]}" ps --status running --services)"
for service in "${expected_running[@]}"; do
  grep --fixed-strings --line-regexp --quiet "$service" <<<"$running_services" || {
    echo "Expected service $service is not running." >&2; exit 1;
  }
done

# Restartability gate.
"${COMPOSE[@]}" restart api worker web
wait_for_container api healthy
wait_for_container worker healthy
wait_for_container web healthy
wait_for_http_200 "http://127.0.0.1:${API_PORT:-8000}/api/v1/readiness"

"${COMPOSE[@]}" ps
echo "Compose smoke test passed."
