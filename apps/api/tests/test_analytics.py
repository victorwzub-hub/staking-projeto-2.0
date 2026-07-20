from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pharma_api.api.v1.analytics import _safe_csv
from pharma_api.application.analytics.processing import AGGREGATE_GRAINS, FACT_LOADERS
from pharma_api.application.analytics.queries import DERIVED_MEASURES
from pharma_api.domain.analytics.kpis import (
    KPI_BY_CODE,
    KPI_CATALOG,
    UNAVAILABLE_KPIS,
    evaluate_formula,
)
from pharma_api.infrastructure.db.models.analytics import DIMENSION_TYPES, FACT_TYPES
from pharma_api.schemas.analytics import AnalyticsFilters, AnalyticsGoalCreateRequest


def test_operational_catalog_contains_120_unique_safe_definitions() -> None:
    assert len(KPI_CATALOG) == 120
    assert len(KPI_BY_CODE) == 120
    assert {item.category for item in KPI_CATALOG} == {
        "sales",
        "inventory",
        "purchases",
        "suppliers",
        "margin",
        "operations",
    }
    for definition in KPI_CATALOG:
        assert definition.version >= 1
        assert definition.formula.operation in {"value", "sum", "difference", "ratio", "product"}
        assert definition.formula.operands
        assert "sql" not in definition.formula.as_json()
        assert definition.drill_down
        assert definition.interpretation
        assert definition.impact


def test_unavailable_kpis_are_explicit_and_not_counted_as_operational() -> None:
    assert len(UNAVAILABLE_KPIS) == 3
    assert not ({item.code for item in UNAVAILABLE_KPIS} & set(KPI_BY_CODE))
    assert all(item.required_data and item.reason for item in UNAVAILABLE_KPIS)


def test_every_operational_kpi_uses_a_real_base_or_derived_measure() -> None:
    warehouse_sql = "".join(statement for _, statement in FACT_LOADERS)
    base_measures = set(re.findall(r"'([a-z][a-z0-9_]*)'\s*,", warehouse_sql))
    required = {field for item in KPI_CATALOG for field in item.required_fields}
    assert required <= base_measures | DERIVED_MEASURES


def test_known_formulas_round_and_protect_zero_division() -> None:
    ticket = KPI_BY_CODE["sales.average_ticket"]
    assert evaluate_formula(
        ticket.formula,
        {"net_revenue": Decimal("123.45"), "completed_sales": 3},
    ) == Decimal("41.1500")
    assert evaluate_formula(ticket.formula, {"net_revenue": 100, "completed_sales": 0}) is None
    profit = KPI_BY_CODE["margin.gross_profit"]
    assert evaluate_formula(
        profit.formula, {"net_revenue": Decimal("250"), "cogs": Decimal("175.25")}
    ) == Decimal("74.7500")


@pytest.mark.parametrize(
    ("code", "measures", "expected"),
    [
        ("sales.cancellation_rate", {"cancelled_sales": 2, "sale_count": 20}, "10.0000"),
        ("sales.return_rate", {"return_amount": 25, "gross_revenue": 500}, "5.0000"),
        ("sales.discount_rate", {"discount_amount": 30, "gross_revenue": 600}, "5.0000"),
        (
            "suppliers.cost_variation",
            {"cost_change_value": -4, "previous_cost_value": 80},
            "-5.0000",
        ),
        (
            "suppliers.quality_score",
            {"supplier_passed_lines": 18, "purchase_line_count": 20},
            "90.0000",
        ),
    ],
)
def test_operational_edge_formulas(code: str, measures: dict[str, int], expected: str) -> None:
    assert evaluate_formula(KPI_BY_CODE[code].formula, measures) == Decimal(expected)


def test_dimensional_and_fact_contracts_cover_required_domains() -> None:
    assert {
        "date",
        "hour",
        "tenant",
        "economic_group",
        "company",
        "branch",
        "product",
        "product_identifier",
        "category",
        "category_hierarchy",
        "brand",
        "manufacturer",
        "supplier",
        "channel",
        "payment_method",
        "sale_origin",
        "movement_type",
        "promotion",
        "price_band",
        "commercial_classification",
    } <= set(DIMENSION_TYPES)
    assert {
        "sale",
        "sale_item",
        "payment",
        "return",
        "purchase",
        "purchase_item",
        "receipt",
        "inventory_movement",
        "stock_snapshot",
        "price",
        "promotion",
        "cost",
        "data_quality",
        "import_execution",
    } == set(FACT_TYPES)
    assert {fact_type for fact_type, _ in FACT_LOADERS} == set(FACT_TYPES)
    assert len(FACT_LOADERS) >= len(FACT_TYPES)
    assert {item[0] for item in AGGREGATE_GRAINS} == {
        "scope",
        "product",
        "category",
        "supplier",
        "channel",
        "payment_method",
        "movement_type",
    }


def test_filters_and_goals_reject_unsafe_ranges() -> None:
    with pytest.raises(ValidationError):
        AnalyticsFilters(from_date=date(2026, 7, 2), to_date=date(2026, 7, 1))
    with pytest.raises(ValidationError):
        AnalyticsFilters(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 2),
            branch_id="00000000-0000-0000-0000-000000000001",
        )
    with pytest.raises(ValidationError):
        AnalyticsGoalCreateRequest(
            kpi_code="sales.net_revenue",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
            direction="increase",
            owner_user_id="00000000-0000-0000-0000-000000000001",
        )


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2", "@formula", "\tcell", "\rline"])
def test_csv_export_neutralizes_formula_injection(value: str) -> None:
    assert _safe_csv(value) == f"'{value}"
