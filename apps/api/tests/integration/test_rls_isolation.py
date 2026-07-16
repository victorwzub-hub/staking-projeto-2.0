from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import exc, text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_read_update_and_pool_context_leakage() -> None:
    admin_engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    app_engine = create_async_engine(os.environ["TEST_DATABASE_URL"], pool_size=1, max_overflow=0)
    user_id = uuid4()
    tenant_a = uuid4()
    tenant_b = uuid4()
    company_a = uuid4()
    company_b = uuid4()
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (id,email,normalized_email,password_hash,status,"
                    "email_verified_at,is_platform_admin,created_at,updated_at,version) "
                    "VALUES (:user_id,:email,:email,'not-used','active',now(),false,now(),now(),1)"
                ),
                {"user_id": user_id, "email": f"rls-{user_id}@example.test"},
            )
            for tenant_id, name, slug, company_id in (
                (tenant_a, "Tenant A", f"tenant-a-{tenant_a}", company_a),
                (tenant_b, "Tenant B", f"tenant-b-{tenant_b}", company_b),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO tenants "
                        "(id,name,slug,status,created_by_user_id,created_at,updated_at,version) "
                        "VALUES (:id,:name,:slug,'active',:user_id,now(),now(),1)"
                    ),
                    {"id": tenant_id, "name": name, "slug": slug, "user_id": user_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO companies "
                        "(id,tenant_id,legal_name,trade_name,slug,status,"
                        "created_at,updated_at,version) "
                        "VALUES (:id,:tenant_id,:name,:name,:slug,'active',now(),now(),1)"
                    ),
                    {
                        "id": company_id,
                        "tenant_id": tenant_id,
                        "name": f"Company {name}",
                        "slug": f"company-{company_id}",
                    },
                )

        async with app_engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": str(user_id)},
            )
            await connection.execute(
                text("SELECT set_config('app.current_tenant_id', :value, true)"),
                {"value": str(tenant_a)},
            )
            rows = (await connection.execute(text("SELECT id, tenant_id FROM companies"))).all()
            assert rows == [(company_a, tenant_a)]
            changed = await connection.execute(
                text("UPDATE companies SET trade_name='forbidden' WHERE id=:id"),
                {"id": company_b},
            )
            assert changed.rowcount == 0

        # RLS must reject cross-tenant inserts, not merely hide them afterwards.
        async with app_engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(
                    text("SELECT set_config('app.current_tenant_id', :value, true)"),
                    {"value": str(tenant_a)},
                )
                with pytest.raises(exc.DBAPIError):
                    await connection.execute(
                        text(
                            "INSERT INTO companies "
                            "(id,tenant_id,legal_name,trade_name,slug,status,"
                            "created_at,updated_at,version) "
                            "VALUES (:id,:tenant_id,'Forbidden','Forbidden',:slug,'active',"
                            "now(),now(),1)"
                        ),
                        {
                            "id": uuid4(),
                            "tenant_id": tenant_b,
                            "slug": f"forbidden-{uuid4()}",
                        },
                    )
            finally:
                await transaction.rollback()

        # A rolled-back transaction must clear transaction-local tenant context too.
        async with app_engine.connect() as connection, connection.begin():
            visible_after_rollback = (
                await connection.execute(text("SELECT count(*) FROM companies"))
            ).scalar_one()
            assert visible_after_rollback == 0

        # Reusing the single pooled connection must not retain SET LOCAL values after commit.
        async with app_engine.connect() as connection, connection.begin():
            visible_without_context = (
                await connection.execute(text("SELECT count(*) FROM companies"))
            ).scalar_one()
            assert visible_without_context == 0
            await connection.execute(
                text("SELECT set_config('app.current_tenant_id', :value, true)"),
                {"value": str(tenant_b)},
            )
            rows = (await connection.execute(text("SELECT id FROM companies"))).scalars().all()
            assert rows == [company_b]
    finally:
        await app_engine.dispose()
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_rls_allows_only_user_scoped_global_audit_events() -> None:
    admin_engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    app_engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    current_user_id = uuid4()
    other_user_id = uuid4()
    own_event_id = uuid4()
    other_event_id = uuid4()
    try:
        async with admin_engine.begin() as connection:
            for user_id in (current_user_id, other_user_id):
                await connection.execute(
                    text(
                        "INSERT INTO users (id,email,normalized_email,password_hash,status,"
                        "email_verified_at,is_platform_admin,created_at,updated_at,version) "
                        "VALUES (:user_id,:email,:email,'not-used','active',now(),false,"
                        "now(),now(),1)"
                    ),
                    {"user_id": user_id, "email": f"audit-rls-{user_id}@example.test"},
                )
            await connection.execute(
                text(
                    "INSERT INTO audit_events "
                    "(id,actor_user_id,effective_user_id,action,category,outcome) "
                    "VALUES (:id,:user_id,:user_id,'other.global','authorization','denied')"
                ),
                {"id": other_event_id, "user_id": other_user_id},
            )

        async with app_engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": str(current_user_id)},
            )
            await connection.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
            await connection.execute(
                text("SELECT set_config('app.is_platform_admin', 'false', true)")
            )
            await connection.execute(
                text(
                    "INSERT INTO audit_events "
                    "(id,actor_user_id,effective_user_id,action,category,outcome) "
                    "VALUES (:id,:user_id,:user_id,'csrf.denied','authorization','denied')"
                ),
                {"id": own_event_id, "user_id": current_user_id},
            )
            visible_ids = (
                (await connection.execute(text("SELECT id FROM audit_events ORDER BY id")))
                .scalars()
                .all()
            )
            assert visible_ids == [own_event_id]

        async with app_engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(
                    text("SELECT set_config('app.current_user_id', :value, true)"),
                    {"value": str(current_user_id)},
                )
                await connection.execute(
                    text("SELECT set_config('app.current_tenant_id', '', true)")
                )
                await connection.execute(
                    text("SELECT set_config('app.is_platform_admin', 'false', true)")
                )
                with pytest.raises(exc.DBAPIError):
                    await connection.execute(
                        text(
                            "INSERT INTO audit_events "
                            "(id,actor_user_id,effective_user_id,action,category,outcome) "
                            "VALUES (:id,:user_id,:user_id,'forbidden.global',"
                            "'authorization','denied')"
                        ),
                        {"id": uuid4(), "user_id": other_user_id},
                    )
            finally:
                await transaction.rollback()
    finally:
        await app_engine.dispose()
        await admin_engine.dispose()
