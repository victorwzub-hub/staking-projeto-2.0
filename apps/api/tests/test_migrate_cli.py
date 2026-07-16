from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pharma_api.cli import migrate
from pharma_api.core.config import Settings


def test_migrate_commits_implicit_lock_transaction_before_grants(tmp_path: Path) -> None:
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\nscript_location = alembic\n")
    (tmp_path / "alembic").mkdir()

    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://admin:secret@database.test/pharma",
        database_application_role="pharma_app",
        _env_file=None,
    )
    connection = MagicMock()
    connection.scalar.return_value = True
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine = MagicMock()
    engine.connect.return_value = connection_context

    transaction = MagicMock()
    connection.begin.return_value = transaction

    with (
        patch.object(migrate, "get_settings", return_value=settings),
        patch.object(migrate, "_resolve_alembic_config", return_value=alembic_ini),
        patch.object(migrate, "create_engine", return_value=engine),
        patch.object(migrate.command, "upgrade") as upgrade,
        patch.object(migrate, "_grant_application_role") as grant_role,
    ):
        migrate.main()

    assert connection.commit.call_count == 2
    upgrade.assert_called_once()
    transaction.__enter__.assert_called_once()
    grant_role.assert_called_once_with(connection, "pharma_app")
    engine.dispose.assert_called_once()


def test_migrate_fails_when_deployment_lock_is_held(tmp_path: Path) -> None:
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\nscript_location = alembic\n")
    (tmp_path / "alembic").mkdir()

    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://admin:secret@database.test/pharma",
        _env_file=None,
    )
    connection = MagicMock()
    connection.scalar.return_value = False
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    engine = MagicMock()
    engine.connect.return_value = connection_context

    with (
        patch.object(migrate, "get_settings", return_value=settings),
        patch.object(migrate, "_resolve_alembic_config", return_value=alembic_ini),
        patch.object(migrate, "create_engine", return_value=engine),
        patch.object(migrate.command, "upgrade") as upgrade,
    ):
        try:
            migrate.main()
        except SystemExit as exc:
            assert str(exc) == "Another migration process holds the deployment lock."
        else:
            raise AssertionError("Expected migration lock failure")

    connection.rollback.assert_called_once()
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()
