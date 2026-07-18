from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from pharma_api.infrastructure.db.session import close_engine
from pharma_api.infrastructure.integrations import tasks
from pharma_api.infrastructure.object_storage import FilesystemObjectStorage

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_deterministic_erp_pipeline_is_complete_and_traceable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    admin_engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    app_engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    user_id = uuid4()
    tenant_id = uuid4()
    company_id = uuid4()
    branch_id = uuid4()
    instance_id = uuid4()
    source_id = uuid4()
    batch_id = uuid4()
    execution_id = uuid4()
    repeat_batch_id = uuid4()
    repeat_execution_id = uuid4()
    object_storage = FilesystemObjectStorage(tmp_path, "phase2b-test")
    monkeypatch.setattr(tasks, "get_object_storage", lambda: object_storage)
    for actor_name in (
        "parse_batch",
        "validate_batch",
        "map_batch",
        "normalize_batch",
        "load_batch",
        "finalize_batch",
        "publish_outbox",
    ):
        monkeypatch.setattr(getattr(tasks, actor_name), "send", lambda *args: None)
    try:
        async with admin_engine.begin() as connection:
            definition_id = (
                await connection.execute(
                    text(
                        "SELECT id FROM connector_definitions "
                        "WHERE connector_key='deterministic-erp' AND version='1.0.0'"
                    )
                )
            ).scalar_one()
            await connection.execute(
                text(
                    "INSERT INTO users (id,email,normalized_email,password_hash,status,"
                    "email_verified_at,is_platform_admin,created_at,updated_at,version) "
                    "VALUES (:id,:email,:email,'not-used','active',now(),false,now(),now(),1)"
                ),
                {"id": user_id, "email": f"pipeline-{user_id}@example.test"},
            )
            await connection.execute(
                text(
                    "INSERT INTO tenants "
                    "(id,name,slug,status,created_by_user_id,created_at,updated_at,version) "
                    "VALUES (:id,'Pipeline tenant',:slug,'active',:user,now(),now(),1)"
                ),
                {"id": tenant_id, "slug": f"pipeline-{tenant_id}", "user": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO companies "
                    "(id,tenant_id,legal_name,trade_name,slug,status,"
                    "created_at,updated_at,version) "
                    "VALUES (:id,:tenant,'Pipeline Ltda','Pipeline',:slug,'active',now(),now(),1)"
                ),
                {"id": company_id, "tenant": tenant_id, "slug": f"company-{company_id}"},
            )
            await connection.execute(
                text(
                    "INSERT INTO branches "
                    "(id,tenant_id,company_id,name,slug,status,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:company,'Main',:slug,'active',now(),now(),1)"
                ),
                {
                    "id": branch_id,
                    "tenant": tenant_id,
                    "company": company_id,
                    "slug": f"branch-{branch_id}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO connector_instances "
                    "(id,tenant_id,company_id,branch_id,connector_definition_id,name,status,"
                    "configuration,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:company,:branch,:definition,'Pipeline ERP','active',"
                    "CAST(:configuration AS jsonb),now(),now(),1)"
                ),
                {
                    "id": instance_id,
                    "tenant": tenant_id,
                    "company": company_id,
                    "branch": branch_id,
                    "definition": definition_id,
                    "configuration": '{"records":5,"seed":"integration-test"}',
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO data_sources "
                    "(id,tenant_id,company_id,branch_id,connector_instance_id,name,dataset_type,"
                    "status,sync_mode,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:company,:branch,:instance,'Pipeline source','all',"
                    "'active','incremental',now(),now(),1)"
                ),
                {
                    "id": source_id,
                    "tenant": tenant_id,
                    "company": company_id,
                    "branch": branch_id,
                    "instance": instance_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO import_batches "
                    "(id,tenant_id,company_id,branch_id,data_source_id,requested_by_user_id,"
                    "idempotency_key,dataset_type,state,progress_percent,received_records,"
                    "valid_records,rejected_records,duplicate_records,cancel_requested,queued_at,"
                    "correlation_id,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:company,:branch,:source,:user,'pipeline-test','all',"
                    "'queued',0,0,0,0,0,false,now(),'phase2b-test',now(),now(),2)"
                ),
                {
                    "id": batch_id,
                    "tenant": tenant_id,
                    "company": company_id,
                    "branch": branch_id,
                    "source": source_id,
                    "user": user_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO sync_executions "
                    "(id,tenant_id,data_source_id,batch_id,requested_by_user_id,idempotency_key,"
                    "mode,request_options,state,created_at,updated_at,version) "
                    "VALUES (:id,:tenant,:source,:batch,:user,'pipeline-test','incremental',"
                    "CAST(:options AS jsonb),'queued',now(),now(),2)"
                ),
                {
                    "id": execution_id,
                    "tenant": tenant_id,
                    "source": source_id,
                    "batch": batch_id,
                    "user": user_id,
                    "options": '{"entities":[]}',
                },
            )

        await close_engine()
        await tasks._acquire_batch(batch_id, tenant_id, "phase2b-test")
        await tasks._parse_batch(batch_id, tenant_id, "phase2b-test")
        await tasks._validate_batch(batch_id, tenant_id, "phase2b-test")
        await tasks._map_batch(batch_id, tenant_id, "phase2b-test")
        await tasks._normalize_batch(batch_id, tenant_id, "phase2b-test")
        await tasks._load_batch(batch_id, tenant_id, "phase2b-test")
        await tasks._finalize_batch(batch_id, tenant_id, "phase2b-test")

        async with admin_engine.connect() as connection:
            state, received, valid, rejected = (
                await connection.execute(
                    text(
                        "SELECT state,received_records,valid_records,rejected_records "
                        "FROM import_batches WHERE id=:id"
                    ),
                    {"id": batch_id},
                )
            ).one()
            assert state == "completed"
            assert (received, valid, rejected) == (30, 30, 0)
            counts = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT target_entity,count(*) FROM lineage_events "
                            "WHERE batch_id=:id GROUP BY target_entity"
                        ),
                        {"id": batch_id},
                    )
                ).all()
            )
            assert counts == {
                "price": 5,
                "product": 5,
                "purchase": 5,
                "sale": 5,
                "stock": 5,
                "supplier": 5,
            }
            product_count = (
                await connection.execute(
                    text("SELECT count(*) FROM canonical_products WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).scalar_one()
            assert product_count == 5
            quality_count, minimum_quality = (
                await connection.execute(
                    text(
                        "SELECT count(*),min(score) FROM quality_results "
                        "WHERE batch_id=:id AND rule_key='platform.overall'"
                    ),
                    {"id": batch_id},
                )
            ).one()
            assert quality_count == 6
            assert minimum_quality == 100
            load_duration, load_throughput = (
                await connection.execute(
                    text(
                        "SELECT max(duration_ms),min(records_per_second) "
                        "FROM processing_statistics WHERE batch_id=:id AND step_name='load'"
                    ),
                    {"id": batch_id},
                )
            ).one()
            assert load_duration > 0
            assert load_throughput > 0

        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO import_batches "
                    "(id,tenant_id,company_id,branch_id,data_source_id,requested_by_user_id,"
                    "idempotency_key,dataset_type,state,progress_percent,received_records,"
                    "valid_records,rejected_records,duplicate_records,cancel_requested,queued_at,"
                    "correlation_id,created_at,updated_at,version) "
                    "SELECT :repeat_id,tenant_id,company_id,branch_id,data_source_id,"
                    "requested_by_user_id,'pipeline-repeat',dataset_type,'queued',0,0,0,0,0,false,"
                    "now(),'phase2b-repeat',now(),now(),2 FROM import_batches WHERE id=:batch_id"
                ),
                {"repeat_id": repeat_batch_id, "batch_id": batch_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO sync_executions "
                    "(id,tenant_id,data_source_id,batch_id,requested_by_user_id,idempotency_key,"
                    "mode,request_options,state,created_at,updated_at,version) "
                    "SELECT :repeat_id,tenant_id,data_source_id,:repeat_batch,requested_by_user_id,"
                    "'pipeline-repeat',mode,request_options,'queued',now(),now(),2 "
                    "FROM sync_executions WHERE id=:execution_id"
                ),
                {
                    "repeat_id": repeat_execution_id,
                    "repeat_batch": repeat_batch_id,
                    "execution_id": execution_id,
                },
            )

        await tasks._acquire_batch(repeat_batch_id, tenant_id, "phase2b-repeat")
        async with admin_engine.connect() as connection:
            imported_file_count = (
                await connection.execute(
                    text("SELECT count(*) FROM imported_files WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).scalar_one()
            manifest_count = (
                await connection.execute(
                    text("SELECT count(*) FROM landing_manifests WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).scalar_one()
            assert imported_file_count == 1
            assert manifest_count == 2
            assert len(list((tmp_path / "phase2b-test").rglob("*.ndjson"))) == 1

        async with app_engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": str(user_id)},
            )
            await connection.execute(
                text("SELECT set_config('app.current_tenant_id', :value, true)"),
                {"value": str(tenant_id)},
            )
            await connection.execute(
                text("SELECT set_config('app.is_platform_admin', 'false', true)")
            )
            assert (
                await connection.execute(text("SELECT count(*) FROM canonical_products"))
            ).scalar_one() == 5
            assert (
                await connection.execute(text("SELECT count(*) FROM import_batches"))
            ).scalar_one() == 2

        cross_tenant_id = uuid4()
        async with app_engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": str(user_id)},
            )
            await connection.execute(
                text("SELECT set_config('app.current_tenant_id', :value, true)"),
                {"value": str(cross_tenant_id)},
            )
            await connection.execute(
                text("SELECT set_config('app.is_platform_admin', 'false', true)")
            )
            assert (
                await connection.execute(text("SELECT count(*) FROM canonical_products"))
            ).scalar_one() == 0
            assert (
                await connection.execute(text("SELECT count(*) FROM import_batches"))
            ).scalar_one() == 0
            assert (
                await connection.execute(text("SELECT count(*) FROM imported_files"))
            ).scalar_one() == 0
            update_result = await connection.execute(
                text(
                    "UPDATE canonical_products SET name='forbidden cross-tenant update' "
                    "WHERE tenant_id=:tenant"
                ),
                {"tenant": tenant_id},
            )
            assert update_result.rowcount == 0
    finally:
        await close_engine()
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE imported_files SET immutable=false,retention_until=current_date-1 "
                    "WHERE tenant_id=:tenant"
                ),
                {"tenant": tenant_id},
            )
            await connection.execute(
                text("DELETE FROM tenants WHERE id=:tenant"), {"tenant": tenant_id}
            )
            await connection.execute(text("DELETE FROM users WHERE id=:user"), {"user": user_id})
        await app_engine.dispose()
        await admin_engine.dispose()
