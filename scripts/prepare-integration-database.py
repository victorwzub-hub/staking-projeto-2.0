#!/usr/bin/env python3
"""Create the non-owner application role used by PostgreSQL/RLS integration tests."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import psycopg
from psycopg import sql


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def _psycopg_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    admin_url = _require("TEST_ADMIN_DATABASE_URL")
    app_url = _require("TEST_DATABASE_URL")
    parsed = urlsplit(_psycopg_url(app_url))
    if not parsed.username or parsed.password is None or not parsed.path.strip("/"):
        raise SystemExit("TEST_DATABASE_URL must contain database, user and password")

    role_name = parsed.username
    database_name = parsed.path.strip("/")
    with (
        psycopg.connect(_psycopg_url(admin_url), autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            sql.SQL(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {role}) THEN "
                "CREATE ROLE {identifier} LOGIN PASSWORD {password} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOINHERIT NOBYPASSRLS; "
                "ELSE ALTER ROLE {identifier} WITH LOGIN PASSWORD {password} NOSUPERUSER "
                "NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$;"
            ).format(
                role=sql.Literal(role_name),
                identifier=sql.Identifier(role_name),
                password=sql.Literal(parsed.password),
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database_name), sql.Identifier(role_name)
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role_name))
        )
        cursor.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(sql.Identifier(role_name))
        )
        cursor.execute(
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(sql.Identifier(role_name))
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}"
            ).format(sql.Identifier(role_name))
        )
        for protected_table in ("permissions", "terms_versions"):
            cursor.execute(
                sql.SQL("REVOKE INSERT, UPDATE, DELETE ON {} FROM {}").format(
                    sql.Identifier(protected_table), sql.Identifier(role_name)
                )
            )


if __name__ == "__main__":
    main()
