#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${TEST_ADMIN_DATABASE_URL:?TEST_ADMIN_DATABASE_URL is required}"

export DATABASE_URL="$TEST_ADMIN_DATABASE_URL"
cd "$ROOT_DIR/apps/api"

alembic heads
alembic upgrade head
alembic current
alembic downgrade base
alembic upgrade head
alembic upgrade head
alembic current
