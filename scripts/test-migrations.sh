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

python - <<'PY'
from __future__ import annotations

import os

import sqlalchemy as sa

EXPECTED_PHASE2_TABLES = {
    "audit_events",
    "authentication_attempts",
    "branches",
    "companies",
    "consent_records",
    "economic_groups",
    "email_verification_tokens",
    "invitations",
    "memberships",
    "onboarding_progress",
    "password_reset_tokens",
    "permissions",
    "role_assignments",
    "role_permissions",
    "roles",
    "security_events",
    "sessions",
    "team_memberships",
    "teams",
    "tenants",
    "terms_versions",
    "user_profiles",
    "users",
    "canonical_products",
    "canonical_sales",
    "data_sources",
    "import_batches",
    "staging_records",
}

engine = sa.create_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
try:
    with engine.connect() as connection:
        remaining = EXPECTED_PHASE2_TABLES.intersection(
            sa.inspect(connection).get_table_names(schema="public")
        )
finally:
    engine.dispose()

if remaining:
    raise SystemExit(
        "Phase 2 migration tables remain after downgrade: " + ", ".join(sorted(remaining))
    )
PY

alembic upgrade head
alembic upgrade head
current_revision="$(alembic current)"
printf '%s\n' "$current_revision"
grep -q "20260719_0005" <<<"$current_revision"
