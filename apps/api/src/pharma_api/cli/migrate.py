from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from pharma_api.core.config import get_settings

_LOCK_ID = 7_240_216_202_607_16
_PROTECTED_RUNTIME_TABLES = (
    "permissions",
    "terms_versions",
    "diagnostic_action_catalog_snapshots",
    "diagnostic_action_catalog_entries",
)


def _resolve_alembic_config() -> Path:
    explicit = os.getenv("ALEMBIC_CONFIG")
    candidates = [
        Path(explicit) if explicit else None,
        Path.cwd() / "alembic.ini",
        Path("/app/alembic.ini"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    locations = ", ".join(str(value) for value in candidates if value is not None)
    raise SystemExit(f"Alembic configuration not found. Checked: {locations}")


def _grant_application_role(connection: Connection, role_name: str | None) -> None:
    """Grant least-privilege DML access after migrations create or alter objects."""
    if role_name is None:
        return

    quoted_role = '"' + role_name.replace('"', '""') + '"'
    statements = (
        f"GRANT USAGE ON SCHEMA public TO {quoted_role}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted_role}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted_role}",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted_role}",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {quoted_role}",
    )
    for statement in statements:
        connection.execute(text(statement))
    for table in _PROTECTED_RUNTIME_TABLES:
        connection.execute(text(f"REVOKE INSERT, UPDATE, DELETE ON {table} FROM {quoted_role}"))


def main() -> None:
    settings = get_settings()
    alembic_ini = _resolve_alembic_config()
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _LOCK_ID}
            )
            if not acquired:
                connection.rollback()
                raise SystemExit("Another migration process holds the deployment lock.")

            # The lock is session-scoped. Commit the implicit transaction opened by
            # pg_try_advisory_lock before starting the grants transaction below.
            connection.commit()
            try:
                command.upgrade(config, "head")
                with connection.begin():
                    _grant_application_role(connection, settings.database_application_role)
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _LOCK_ID}
                )
                connection.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
