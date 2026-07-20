# ruff: noqa: E501, S603
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from psycopg import errors
from sqlalchemy import create_engine

from pharma_api.cli.migrate import _grant_application_role

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).parents[1]
MIGRATION_PATH = API_ROOT / "alembic" / "versions" / "20260719_0005_diagnostics_rules_engine.py"
DIAGNOSTIC_TABLES = (
    "diagnostic_rule_definitions",
    "diagnostic_rule_versions",
    "diagnostic_action_catalog_snapshots",
    "diagnostic_action_catalog_entries",
    "diagnostic_rule_configurations",
    "diagnostic_evaluation_runs",
    "diagnostic_findings",
    "diagnostic_evidences",
    "diagnostic_hypotheses",
    "diagnostic_hypothesis_evidences",
    "diagnostic_action_recommendations",
    "diagnostic_suppressions",
    "diagnostic_incidents",
    "diagnostic_incident_memberships",
)


def _require_database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    app_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not app_url:
        pytest.skip("real PostgreSQL admin and non-bypass application URLs are required")
    return admin_url, app_url


def _psycopg_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _run_alembic(admin_url: str, command: str, revision: str) -> None:
    env = os.environ.copy()
    env.update({"APP_ENV": "test", "DATABASE_URL": admin_url})
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", command, revision],
        cwd=API_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("diagnostics_migration_0005_pg", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _grant_runtime(admin_url: str, app_url: str) -> None:
    role_name = urlsplit(_psycopg_url(app_url)).username
    assert role_name
    engine = create_engine(admin_url)
    try:
        with engine.begin() as connection:
            _grant_application_role(connection, role_name)
    finally:
        engine.dispose()


def _seed_idempotently(admin_url: str) -> None:
    migration = _load_migration()
    engine = create_engine(admin_url)
    try:
        with engine.begin() as connection:
            migration.__dict__["op"] = Operations(MigrationContext.configure(connection))
            seed_action_catalog = cast(
                Callable[[], None], migration.__dict__["_seed_action_catalog"]
            )
            seed_action_catalog()
    finally:
        engine.dispose()


def _insert_foundation(cursor: psycopg.Cursor[tuple[object, ...]]) -> dict[str, UUID]:
    ids = {
        name: uuid4()
        for name in (
            "user1",
            "user2",
            "tenant1",
            "tenant2",
            "company1",
            "company1b",
            "company2",
            "branch1",
            "branch1b",
            "branch2",
            "rule",
            "rule_version",
            "run1",
            "run2",
            "finding1",
            "finding2",
            "finding3",
            "evidence2",
            "hypothesis1",
            "incident1",
        )
    }
    token = uuid4().hex
    now = datetime.now(UTC)
    for number in (1, 2):
        cursor.execute(
            "INSERT INTO users (id,email,normalized_email,password_hash,status,is_platform_admin) "
            "VALUES (%s,%s,%s,'test-hash','active',false)",
            (
                ids[f"user{number}"],
                f"b4-{number}-{token}@example.test",
                f"b4-{number}-{token}@example.test",
            ),
        )
        cursor.execute(
            "INSERT INTO tenants (id,name,slug,status,created_by_user_id) VALUES (%s,%s,%s,'active',%s)",
            (
                ids[f"tenant{number}"],
                f"B4 Tenant {number}",
                f"b4-tenant-{number}-{token}",
                ids[f"user{number}"],
            ),
        )
    for company_key, tenant_key, suffix in (
        ("company1", "tenant1", "one"),
        ("company1b", "tenant1", "one-b"),
        ("company2", "tenant2", "two"),
    ):
        cursor.execute(
            "INSERT INTO companies (id,tenant_id,legal_name,trade_name,slug,status) "
            "VALUES (%s,%s,%s,%s,%s,'active')",
            (
                ids[company_key],
                ids[tenant_key],
                f"Legal {suffix}",
                f"Trade {suffix}",
                f"b4-{suffix}-{token}",
            ),
        )
    for branch_key, tenant_key, company_key, suffix in (
        ("branch1", "tenant1", "company1", "one"),
        ("branch1b", "tenant1", "company1b", "one-b"),
        ("branch2", "tenant2", "company2", "two"),
    ):
        cursor.execute(
            "INSERT INTO branches (id,tenant_id,company_id,name,slug,status) VALUES (%s,%s,%s,%s,%s,'active')",
            (
                ids[branch_key],
                ids[tenant_key],
                ids[company_key],
                f"Branch {suffix}",
                f"b4-branch-{suffix}-{token}",
            ),
        )
    cursor.execute(
        "INSERT INTO diagnostic_rule_definitions "
        "(id,tenant_id,code,domain,name,description,ownership_type,lifecycle_status,enabled_by_default) "
        "VALUES (%s,NULL,%s,'operations','B4 rule','B4 test rule','system','active',true)",
        (ids["rule"], f"operations.b4_{token}"),
    )
    cursor.execute(
        "INSERT INTO diagnostic_rule_versions "
        "(id,rule_definition_id,version_number,condition_document,condition_hash,definition_hash,"
        "kpi_codes,action_codes,controls,evidence_metadata,hypothesis_metadata,status,effective_from,"
        "publication_source,published_at,source_revision) "
        "VALUES (%s,%s,1,'{}',%s,%s,'[]','[]','{}','{}','{}','published',%s,'migration',%s,'b4-test')",
        (ids["rule_version"], ids["rule"], "a" * 64, "b" * 64, now, now),
    )
    for run_key, tenant_key, company_key, suffix in (
        ("run1", "tenant1", "company1", "one"),
        ("run2", "tenant2", "company2", "two"),
    ):
        cursor.execute(
            "INSERT INTO diagnostic_evaluation_runs "
            "(id,tenant_id,company_id,branch_id,scope_type,trigger_type,status,engine_version,"
            "analytics_data_version,window_start,window_end,correlation_id,idempotency_key,"
            "rules_evaluated,rules_skipped,rule_failures,diagnostics_generated) "
            "VALUES (%s,%s,%s,NULL,'company','manual','queued','b4-test',1,%s,%s,%s,%s,0,0,0,0)",
            (
                ids[run_key],
                ids[tenant_key],
                ids[company_key],
                now - timedelta(days=1),
                now,
                f"corr-{suffix}-{token}",
                f"idem-{suffix}-{token}",
            ),
        )
    finding_rows = (
        ("finding1", "tenant1", "company1", "run1", "a"),
        ("finding2", "tenant1", "company1", "run1", "b"),
        ("finding3", "tenant2", "company2", "run2", "c"),
    )
    for finding_key, tenant_key, company_key, run_key, hash_char in finding_rows:
        cursor.execute(
            "INSERT INTO diagnostic_findings "
            "(id,tenant_id,company_id,branch_id,scope_type,evaluation_run_id,rule_definition_id,"
            "rule_version_number,rule_ownership_type,rule_tenant_id,diagnostic_code,fingerprint,"
            "domain,title,summary,severity,priority,status,detected_at,affected_from,affected_to,"
            "first_observed_at,last_observed_at,occurrence_count,primary_kpi_code,analytics_data_version,"
            "formula_version,context_snapshot,opened_at) "
            "VALUES (%s,%s,%s,NULL,'company',%s,%s,1,'system',NULL,%s,%s,'operations','B4 finding',"
            "'B4 deterministic finding','medium',2,'open',%s,%s,%s,%s,%s,1,'operations.import_success_rate',1,1,'{}',%s)",
            (
                ids[finding_key],
                ids[tenant_key],
                ids[company_key],
                ids[run_key],
                ids["rule"],
                f"operations.b4_{hash_char}_{token}",
                hash_char * 64,
                now,
                now,
                now,
                now,
                now,
                now,
            ),
        )
    cursor.execute(
        "INSERT INTO diagnostic_evidences "
        "(id,tenant_id,diagnostic_id,evidence_type,kpi_code,period_start,period_end,direction,source_type,"
        "analytics_data_version,formula_version,detail_snapshot,evidence_hash,stable_order) "
        "VALUES (%s,%s,%s,'kpi_value','operations.import_success_rate',%s,%s,'below','analytics_kpi',1,1,'{}',%s,0)",
        (ids["evidence2"], ids["tenant1"], ids["finding2"], now, now, "d" * 64),
    )
    cursor.execute(
        "INSERT INTO diagnostic_hypotheses "
        "(id,tenant_id,diagnostic_id,hypothesis_code,definition_snapshot,evaluation_status,rank,"
        "supporting_evidence_count,contradicting_evidence_count,explanation,logic_version,evaluated_at) "
        "VALUES (%s,%s,%s,%s,'{}','supported',1,1,0,'deterministic','1',%s)",
        (
            ids["hypothesis1"],
            ids["tenant1"],
            ids["finding1"],
            f"operations.hypothesis_{token}",
            now,
        ),
    )
    cursor.execute(
        "INSERT INTO diagnostic_incidents "
        "(id,tenant_id,company_id,branch_id,scope_type,incident_code,fingerprint,domain,aggregate_severity,"
        "priority,status,first_event_at,last_event_at,diagnostic_count,primary_diagnostic_id,title,summary,opened_at) "
        "VALUES (%s,%s,%s,NULL,'company',%s,%s,'operations','medium',2,'open',%s,%s,1,%s,'B4 incident','B4 incident',%s)",
        (
            ids["incident1"],
            ids["tenant1"],
            ids["company1"],
            f"operations.incident_{token}",
            "e" * 64,
            now,
            now,
            ids["finding1"],
            now,
        ),
    )
    return ids


def test_diagnostics_migration_upgrade_rls_integrity_and_cycle() -> None:
    admin_url, app_url = _require_database_urls()
    _run_alembic(admin_url, "downgrade", "20260718_0004")
    _run_alembic(admin_url, "upgrade", "20260719_0005")
    _grant_runtime(admin_url, app_url)

    with (
        psycopg.connect(_psycopg_url(admin_url), autocommit=True) as admin,
        admin.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'diagnostic_%'"
        )
        assert {row[0] for row in cursor.fetchall()} == set(DIAGNOSTIC_TABLES)
        cursor.execute("SELECT count(*) FROM diagnostic_action_catalog_entries")
        assert cursor.fetchone() == (30,)
        cursor.execute("SELECT count(*) FROM diagnostic_action_catalog_snapshots WHERE is_current")
        assert cursor.fetchone() == (1,)
        cursor.execute(
            "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename LIKE 'diagnostic_%'"
        )
        policy_count = cursor.fetchone()
        assert policy_count is not None
        assert policy_count[0] >= 20
        cursor.execute("SELECT version_num FROM alembic_version")
        assert cursor.fetchone() == ("20260719_0005",)
        ids = _insert_foundation(cursor)

        with pytest.raises(errors.ForeignKeyViolation):
            cursor.execute(
                "INSERT INTO diagnostic_findings (id,tenant_id,company_id,scope_type,evaluation_run_id,"
                "rule_definition_id,rule_version_number,rule_ownership_type,diagnostic_code,fingerprint,domain,"
                "title,summary,severity,priority,status,detected_at,affected_from,affected_to,first_observed_at,"
                "last_observed_at,occurrence_count,primary_kpi_code,analytics_data_version,formula_version,"
                "context_snapshot,opened_at) VALUES (%s,%s,%s,'company',%s,%s,1,'system','operations.scope_mismatch',"
                "%s,'operations','Mismatch','Mismatch','medium',2,'open',now(),now(),now(),now(),now(),1,"
                "'operations.import_success_rate',1,1,'{}',now())",
                (uuid4(), ids["tenant1"], ids["company1b"], ids["run1"], ids["rule"], "f" * 64),
            )
        with pytest.raises(errors.ForeignKeyViolation):
            cursor.execute(
                "INSERT INTO diagnostic_hypothesis_evidences "
                "(tenant_id,diagnostic_id,hypothesis_id,evidence_id,relation,stable_order,created_at) "
                "VALUES (%s,%s,%s,%s,'supports',0,now())",
                (ids["tenant1"], ids["finding1"], ids["hypothesis1"], ids["evidence2"]),
            )
        with pytest.raises(errors.ForeignKeyViolation):
            cursor.execute(
                "INSERT INTO diagnostic_incident_memberships "
                "(tenant_id,incident_id,diagnostic_id,stable_order,linked_at) VALUES (%s,%s,%s,0,now())",
                (ids["tenant1"], ids["incident1"], ids["finding3"]),
            )

    _seed_idempotently(admin_url)
    with (
        psycopg.connect(_psycopg_url(admin_url), autocommit=True) as admin,
        admin.cursor() as cursor,
    ):
        cursor.execute("SELECT count(*) FROM diagnostic_action_catalog_entries")
        assert cursor.fetchone() == (30,)

    with psycopg.connect(_psycopg_url(app_url), autocommit=True) as app, app.cursor() as cursor:
        cursor.execute("SELECT set_config('app.is_platform_admin','false',false)")
        cursor.execute(
            "SELECT set_config('app.current_tenant_id',%s,false)", (str(ids["tenant1"]),)
        )
        cursor.execute("SELECT count(*) FROM diagnostic_action_catalog_entries")
        assert cursor.fetchone() == (30,)
        cursor.execute(
            "SELECT has_table_privilege(current_user,'diagnostic_action_catalog_entries','INSERT')"
        )
        assert cursor.fetchone() == (False,)
        with pytest.raises(errors.InsufficientPrivilege):
            cursor.execute("DELETE FROM diagnostic_action_catalog_entries")
        cursor.execute("SELECT count(*) FROM diagnostic_evaluation_runs")
        assert cursor.fetchone() == (1,)
        cursor.execute(
            "UPDATE diagnostic_evaluation_runs SET status='cancelled' WHERE id=%s", (ids["run2"],)
        )
        assert cursor.rowcount == 0
        cursor.execute("DELETE FROM diagnostic_evaluation_runs WHERE id=%s", (ids["run2"],))
        assert cursor.rowcount == 0
        with pytest.raises(errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO diagnostic_evaluation_runs "
                "(id,tenant_id,company_id,scope_type,trigger_type,status,engine_version,analytics_data_version,"
                "window_start,window_end,correlation_id,idempotency_key,rules_evaluated,rules_skipped,"
                "rule_failures,diagnostics_generated) VALUES (%s,%s,%s,'company','manual','queued','b4',1,"
                "now(),now(),'cross-tenant','cross-tenant',0,0,0,0)",
                (uuid4(), ids["tenant2"], ids["company2"]),
            )
        with pytest.raises(errors.ForeignKeyViolation):
            cursor.execute(
                "INSERT INTO diagnostic_evaluation_runs "
                "(id,tenant_id,company_id,scope_type,trigger_type,status,engine_version,analytics_data_version,"
                "window_start,window_end,correlation_id,idempotency_key,rules_evaluated,rules_skipped,"
                "rule_failures,diagnostics_generated) VALUES (%s,%s,%s,'company','manual','queued','b4',1,"
                "now(),now(),'cross-company','cross-company',0,0,0,0)",
                (uuid4(), ids["tenant1"], ids["company2"]),
            )

    _run_alembic(admin_url, "downgrade", "20260718_0004")
    _run_alembic(admin_url, "upgrade", "20260719_0005")
    with (
        psycopg.connect(_psycopg_url(admin_url), autocommit=True) as admin,
        admin.cursor() as cursor,
    ):
        cursor.execute("SELECT version_num FROM alembic_version")
        assert cursor.fetchone() == ("20260719_0005",)
        cursor.execute("SELECT count(*) FROM diagnostic_action_catalog_entries")
        assert cursor.fetchone() == (30,)
