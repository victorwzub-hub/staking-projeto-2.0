#!/usr/bin/env python3
"""Reproducible analytical benchmark with generator and processing timings separated."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tracemalloc
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from pharma_api.domain.analytics.kpis import KPI_BY_CODE, evaluate_formula  # noqa: E402

PROFILES = {"smoke": 2_000, "local": 50_000, "staging": 1_000_000}
BENCHMARK_KPIS = (
    "sales.net_revenue",
    "sales.average_ticket",
    "inventory.coverage_days",
    "purchases.average_unit_cost",
    "margin.gross_percent",
    "operations.completeness",
)


def _fact(index: int) -> dict[str, Any]:
    day = date(2026, 1, 1) + timedelta(days=index % 365)
    product = index % 10_000
    gross = Decimal(10 + index % 91)
    discount = Decimal(index % 7)
    net = gross - discount
    units = Decimal(index % 5 + 1)
    return {
        "date": day,
        "company": index % 20,
        "branch": index % 200,
        "product": product,
        "measures": {
            "gross_revenue": gross,
            "net_revenue": net,
            "completed_sales": Decimal(1),
            "sale_count": Decimal(1),
            "units_sold": units,
            "item_count": units,
            "discount_amount": discount,
            "cogs": net * Decimal("0.68"),
            "inventory_available": Decimal(10 + product % 80),
            "inventory_cost_value": Decimal(50 + product % 500),
            "purchase_value": Decimal(20 + index % 100),
            "purchase_quantity": Decimal(2 + index % 9),
            "received_records": Decimal(1),
            "valid_records": Decimal(1),
        },
    }


def _timed(stage: str, operation: Any) -> tuple[Any, dict[str, Any]]:
    cpu_before = process_time()
    started = perf_counter()
    result = operation()
    elapsed = perf_counter() - started
    return result, {
        "stage": stage,
        "duration_seconds": round(elapsed, 6),
        "cpu_seconds": round(process_time() - cpu_before, 6),
    }


def _aggregate(facts: list[dict[str, Any]]) -> dict[tuple[date, int, int], dict[str, Decimal]]:
    rows: dict[tuple[date, int, int], dict[str, Decimal]] = {}
    for fact in facts:
        key = (fact["date"], fact["company"], fact["branch"])
        target = rows.setdefault(key, defaultdict(Decimal))
        for measure, value in fact["measures"].items():
            target[measure] += value
    return rows


def _semantic_snapshot(
    aggregates: dict[tuple[date, int, int], dict[str, Decimal]],
) -> dict[str, Decimal]:
    snapshot: dict[str, Decimal] = defaultdict(Decimal)
    active_dates: set[date] = set()
    for (day, _, _), measures in aggregates.items():
        active_dates.add(day)
        for key, value in measures.items():
            snapshot[key] += value
    days = Decimal(max(len(active_dates), 1))
    snapshot["active_days"] = days
    snapshot["active_hours"] = days * 24
    snapshot["average_daily_units"] = snapshot["units_sold"] / days
    snapshot["average_inventory_cost"] = snapshot["inventory_cost_value"] / days
    snapshot["gross_profit"] = snapshot["net_revenue"] - snapshot["cogs"]
    return snapshot


def _database_benchmark(database_url: str, tenant_id: UUID) -> dict[str, Any]:
    import psycopg

    url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    query = """
        SELECT measures FROM analytics_daily_aggregates
        WHERE tenant_id=%s AND grain='scope'
        ORDER BY date_value DESC LIMIT 732
    """
    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_tenant_id', %s, false)", (str(tenant_id),))
        cursor.execute("SELECT set_config('app.is_platform_admin', 'false', false)")
        timings: list[float] = []
        row_count = 0
        for _ in range(2):
            started = perf_counter()
            cursor.execute(query, (tenant_id,))
            row_count = len(cursor.fetchall())
            timings.append(perf_counter() - started)
        cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, (tenant_id,))
        plan = cursor.fetchone()[0][0]
        cursor.execute(
            "SELECT count(*),pg_total_relation_size('analytics_facts'),"
            "pg_total_relation_size('analytics_daily_aggregates') "
            "FROM analytics_facts WHERE tenant_id=%s",
            (tenant_id,),
        )
        facts, fact_bytes, aggregate_bytes = cursor.fetchone()
    return {
        "scope_rows": row_count,
        "uncached_query_seconds": round(timings[0], 6),
        "warm_query_seconds": round(timings[1], 6),
        "execution_plan_seconds": round(float(plan["Execution Time"]) / 1_000, 6),
        "shared_hit_blocks": plan["Plan"].get("Shared Hit Blocks", 0),
        "tenant_facts": facts,
        "facts_table_bytes": fact_bytes,
        "aggregates_table_bytes": aggregate_bytes,
    }


def run(
    profile: str, records: int, database_url: str | None, tenant_id: UUID | None
) -> dict[str, Any]:
    tracemalloc.start()
    facts, generator = _timed("deterministic_generator", lambda: [_fact(i) for i in range(records)])
    generator["records"] = records
    generator["records_per_second"] = round(records / generator["duration_seconds"], 2)
    aggregates, aggregation = _timed("daily_aggregation", lambda: _aggregate(facts))
    aggregation["input_facts"] = records
    aggregation["output_rows"] = len(aggregates)
    snapshot, transformation = _timed(
        "semantic_transformation", lambda: _semantic_snapshot(aggregates)
    )

    def calculate() -> dict[str, str | None]:
        return {
            code: str(evaluate_formula(KPI_BY_CODE[code].formula, snapshot))
            for code in BENCHMARK_KPIS
        }

    values, calculation = _timed("kpi_calculation", calculate)
    second_aggregates, recomputation = _timed("idempotent_recomputation", lambda: _aggregate(facts))
    recomputation["identical"] = second_aggregates == aggregates
    encoded = json.dumps(values, sort_keys=True).encode()
    cache: dict[str, bytes] = {}
    _, cache_write = _timed("cache_write", lambda: cache.setdefault("result", encoded))
    cached, cache_read = _timed("cache_read", lambda: cache["result"])
    assert cached == encoded
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report: dict[str, Any] = {
        "benchmark_version": "2c.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": profile,
        "seed": "fixed-formula-2026-01-01",
        "dataset_sha256": sha256(f"{records}:fixed-formula-2026-01-01".encode()).hexdigest(),
        "peak_memory_mib": round(peak / 1_048_576, 3),
        "stages": [
            generator,
            aggregation,
            transformation,
            calculation,
            recomputation,
            cache_write,
            cache_read,
        ],
        "kpi_results": values,
        "database": None,
        "worker": "measured by analytics_refresh_jobs.metrics in real-stack tests",
    }
    if database_url and tenant_id:
        report["database"] = _database_benchmark(database_url, tenant_id)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=tuple(PROFILES), default="smoke")
    parser.add_argument("--records", type=int)
    parser.add_argument("--database-url", default=os.getenv("BENCHMARK_DATABASE_URL"))
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--output", type=Path, default=Path(".local/bench/phase2c.json"))
    args = parser.parse_args()
    records = args.records or PROFILES[args.profile]
    if records < 1:
        parser.error("--records must be positive")
    if bool(args.database_url) != bool(args.tenant_id):
        parser.error("--database-url and --tenant-id must be provided together")
    report = run(args.profile, records, args.database_url, args.tenant_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
