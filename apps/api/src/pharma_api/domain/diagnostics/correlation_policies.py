"""Governed immutable policies for correlating distinct diagnostic fingerprints."""

from __future__ import annotations

from types import MappingProxyType

from pharma_api.domain.diagnostics.correlation_contracts import (
    CORRELATION_ALGORITHM_VERSION,
    CORRELATION_CONTRACT_VERSION,
    MAX_CLUSTER_MEMBERS,
    MAX_CORRELATED_EVIDENCE,
    MAX_CORRELATED_HYPOTHESES,
    MAX_CORRELATED_RECOMMENDATIONS,
    MAX_CORRELATION_INPUTS,
    MAX_CORRELATION_POLICIES,
    MAX_OCCURRENCES_PER_FINGERPRINT,
    CorrelationManifest,
    CorrelationPolicyDefinition,
    CorrelationValidationError,
)
from pharma_api.domain.diagnostics.engine_contracts import canonical_sha256
from pharma_api.domain.diagnostics.rules.catalog import RULE_BY_CODE

_COMMON_LIMITATIONS = (
    "Correlation relates governed signals and does not prove a shared root cause.",
    "The policy only applies to the exact authorized scope and identical affected period.",
    "The resulting cluster is an immutable candidate, not an operational incident.",
)

# Every row is explicit and auditable. The catalog deliberately excludes inventory coverage
# because high and low coverage are opposite economic states even though they share one KPI.
_POLICY_ROWS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "correlation.inventory_adjustment_quantity",
        "inventory",
        "inventory.adjustment_quantity",
        (
            "inventory.stock_adjustments",
            "inventory.stock_adjustments_worsening",
        ),
    ),
    (
        "correlation.inventory_stockout_risk_rate",
        "inventory",
        "inventory.stockout_risk_rate",
        (
            "inventory.stockout_risk",
            "inventory.stockout_risk_above_network",
        ),
    ),
    (
        "correlation.inventory_zero_stock_rate",
        "inventory",
        "inventory.zero_stock_rate",
        (
            "inventory.observed_stockout",
            "inventory.recurring_stockout",
            "inventory.stockout_above_network",
            "inventory.stockout_worsening",
        ),
    ),
    (
        "correlation.margin_discount_on_price",
        "margin",
        "margin.discount_on_price",
        (
            "margin.discount_on_price_above_network",
            "margin.discount_on_price_increase",
        ),
    ),
    (
        "correlation.margin_gmroi",
        "margin",
        "margin.gmroi",
        (
            "margin.gmroi_below_category",
            "margin.gmroi_below_network",
            "margin.gmroi_decline",
        ),
    ),
    (
        "correlation.margin_gross_percent",
        "margin",
        "margin.gross_percent",
        (
            "margin.gross_percent_below_category",
            "margin.gross_percent_below_network",
            "margin.gross_percent_decline",
        ),
    ),
    (
        "correlation.margin_gross_profit",
        "margin",
        "margin.gross_profit",
        (
            "margin.gross_profit_decline",
            "margin.gross_profit_downward_trend",
            "margin.gross_profit_negative",
            "margin.gross_profit_persistent_negative",
        ),
    ),
    (
        "correlation.margin_markup",
        "margin",
        "margin.markup",
        (
            "margin.markup_below_category",
            "margin.markup_below_network",
        ),
    ),
    (
        "correlation.margin_negative_margin_rate",
        "margin",
        "margin.negative_margin_rate",
        (
            "margin.negative_margin_rate_above_network",
            "margin.negative_margin_rate_increase",
            "margin.negative_margin_rate_positive",
        ),
    ),
    (
        "correlation.operations_completeness",
        "operations",
        "operations.completeness",
        (
            "operations.completeness_below_network",
            "operations.completeness_decline",
        ),
    ),
    (
        "correlation.operations_consistency",
        "operations",
        "operations.consistency",
        (
            "operations.consistency_below_network",
            "operations.consistency_decline",
        ),
    ),
    (
        "correlation.operations_data_freshness",
        "operations",
        "operations.data_freshness",
        (
            "operations.data_freshness_above_network",
            "operations.data_freshness_increase",
        ),
    ),
    (
        "correlation.operations_duplicate_rate",
        "operations",
        "operations.duplicate_rate",
        (
            "operations.duplicate_rate_above_network",
            "operations.duplicate_rate_increase",
            "operations.duplicate_rate_positive",
        ),
    ),
    (
        "correlation.operations_failed_batches",
        "operations",
        "operations.failed_batches",
        (
            "operations.failed_batches_increase",
            "operations.failed_batches_persistent_positive",
            "operations.failed_batches_positive",
        ),
    ),
    (
        "correlation.operations_integration_availability",
        "operations",
        "operations.integration_availability",
        (
            "operations.integration_availability_decline",
            "operations.integration_availability_zero",
        ),
    ),
    (
        "correlation.operations_rejection_rate",
        "operations",
        "operations.rejection_rate",
        (
            "operations.rejection_rate_above_network",
            "operations.rejection_rate_increase",
            "operations.rejection_rate_positive",
        ),
    ),
    (
        "correlation.purchases_average_unit_cost",
        "purchases",
        "purchases.average_unit_cost",
        (
            "purchases.average_unit_cost_above_network",
            "purchases.average_unit_cost_increase",
        ),
    ),
    (
        "correlation.purchases_cancellation_rate",
        "purchases",
        "purchases.cancellation_rate",
        (
            "purchases.cancellation_rate_above_network",
            "purchases.cancellation_rate_increase",
        ),
    ),
    (
        "correlation.purchases_discount_rate",
        "purchases",
        "purchases.discount_rate",
        (
            "purchases.discount_rate_below_network",
            "purchases.discount_rate_decline",
        ),
    ),
    (
        "correlation.purchases_emergency_rate",
        "purchases",
        "purchases.emergency_rate",
        (
            "purchases.emergency_rate_increase",
            "purchases.emergency_rate_persistent_positive",
        ),
    ),
    (
        "correlation.purchases_freight_rate",
        "purchases",
        "purchases.freight_rate",
        (
            "purchases.freight_rate_above_network",
            "purchases.freight_rate_increase",
        ),
    ),
    (
        "correlation.purchases_multiple_adherence",
        "purchases",
        "purchases.multiple_adherence",
        (
            "purchases.multiple_adherence_below_network",
            "purchases.multiple_adherence_decline",
        ),
    ),
    (
        "correlation.purchases_receipt_fill_rate",
        "purchases",
        "purchases.receipt_fill_rate",
        (
            "purchases.receipt_fill_rate_below_category",
            "purchases.receipt_fill_rate_decline",
        ),
    ),
    (
        "correlation.purchases_receipt_rate",
        "purchases",
        "purchases.receipt_rate",
        (
            "purchases.receipt_rate_below_network",
            "purchases.receipt_rate_decline",
        ),
    ),
    (
        "correlation.purchases_return_rate",
        "purchases",
        "purchases.return_rate",
        (
            "purchases.return_rate_above_network",
            "purchases.return_rate_increase",
            "purchases.return_rate_positive",
        ),
    ),
    (
        "correlation.sales_average_ticket",
        "sales",
        "sales.average_ticket",
        (
            "sales.average_ticket_below_network",
            "sales.average_ticket_decline",
        ),
    ),
    (
        "correlation.sales_cancellation_rate",
        "sales",
        "sales.cancellation_rate",
        (
            "sales.cancellation_rate_above_network",
            "sales.cancellation_rate_increase",
        ),
    ),
    (
        "correlation.sales_discount_rate",
        "sales",
        "sales.discount_rate",
        (
            "sales.discount_rate_above_network",
            "sales.discount_rate_increase",
        ),
    ),
    (
        "correlation.sales_net_revenue",
        "sales",
        "sales.net_revenue",
        (
            "sales.net_revenue_below_network",
            "sales.net_revenue_decline",
            "sales.net_revenue_downward_trend",
            "sales.net_revenue_persistent_decline",
        ),
    ),
    (
        "correlation.sales_return_rate",
        "sales",
        "sales.return_rate",
        (
            "sales.return_rate_above_network",
            "sales.return_rate_increase",
        ),
    ),
    (
        "correlation.suppliers_average_lead_time",
        "suppliers",
        "suppliers.average_lead_time",
        (
            "suppliers.average_lead_time_above_network",
            "suppliers.average_lead_time_increase",
        ),
    ),
    (
        "correlation.suppliers_cost_variation",
        "suppliers",
        "suppliers.cost_variation",
        (
            "suppliers.cost_variation_above_network",
            "suppliers.cost_variation_positive",
        ),
    ),
    (
        "correlation.suppliers_failure_rate",
        "suppliers",
        "suppliers.failure_rate",
        (
            "suppliers.failure_rate_increase",
            "suppliers.failure_rate_persistent_positive",
            "suppliers.failure_rate_positive",
        ),
    ),
    (
        "correlation.suppliers_fill_rate",
        "suppliers",
        "suppliers.fill_rate",
        (
            "suppliers.fill_rate_below_network",
            "suppliers.fill_rate_decline",
        ),
    ),
    (
        "correlation.suppliers_on_time_rate",
        "suppliers",
        "suppliers.on_time_rate",
        (
            "suppliers.on_time_rate_below_network",
            "suppliers.on_time_rate_decline",
        ),
    ),
    (
        "correlation.suppliers_quality_score",
        "suppliers",
        "suppliers.quality_score",
        (
            "suppliers.quality_score_below_network",
            "suppliers.quality_score_decline",
        ),
    ),
    (
        "correlation.suppliers_return_rate",
        "suppliers",
        "suppliers.return_rate",
        (
            "suppliers.return_rate_above_network",
            "suppliers.return_rate_increase",
        ),
    ),
    (
        "correlation.suppliers_stockout_association",
        "suppliers",
        "suppliers.stockout_association",
        (
            "suppliers.stockout_association_above_network",
            "suppliers.stockout_association_positive",
        ),
    ),
)


def _build_policy(
    code: str,
    domain: str,
    kpi_code: str,
    members: tuple[str, ...],
) -> CorrelationPolicyDefinition:
    return CorrelationPolicyDefinition(
        code=code,
        version=1,
        domains=(domain,),
        member_diagnostic_codes=members,
        compatible_kpi_codes=(kpi_code,),
        scope_compatibility="exact",
        temporal_compatibility="same_affected_period",
        reason=(
            "Relate distinct governed diagnostics that evaluate the same KPI under "
            "complementary rule semantics."
        ),
        primary_selection_rule="severity_priority_confidence_recency_lexical",
        severity_aggregation_rule="maximum",
        priority_aggregation_rule="minimum",
        limitations=_COMMON_LIMITATIONS,
    )


CORRELATION_POLICY_CATALOG: tuple[CorrelationPolicyDefinition, ...] = tuple(
    sorted(
        (
            _build_policy(code, domain, kpi_code, members)
            for code, domain, kpi_code, members in _POLICY_ROWS
        ),
        key=lambda policy: policy.code,
    )
)


def validate_correlation_policy_catalog(
    policies: tuple[CorrelationPolicyDefinition, ...] = CORRELATION_POLICY_CATALOG,
) -> None:
    if len(policies) > MAX_CORRELATION_POLICIES:
        raise CorrelationValidationError("correlation policy catalog exceeds its bounded limit")
    if tuple(sorted(policies, key=lambda policy: policy.code)) != policies:
        raise CorrelationValidationError("correlation policies must be lexically ordered")
    codes = [policy.code for policy in policies]
    hashes = [policy.policy_hash for policy in policies]
    if len(set(codes)) != len(codes):
        raise CorrelationValidationError("correlation policy codes must be unique")
    if len(set(hashes)) != len(hashes):
        raise CorrelationValidationError("correlation policy hashes must be unique")
    member_owner: dict[str, str] = {}
    for policy in policies:
        for diagnostic_code in policy.member_diagnostic_codes:
            rule = RULE_BY_CODE.get(diagnostic_code)
            if rule is None:
                raise CorrelationValidationError(
                    f"policy {policy.code} references unknown diagnostic {diagnostic_code}"
                )
            if rule.domain not in policy.domains:
                raise CorrelationValidationError(
                    f"policy {policy.code} has incompatible domain for {diagnostic_code}"
                )
            if rule.primary_kpi_code not in policy.compatible_kpi_codes:
                raise CorrelationValidationError(
                    f"policy {policy.code} has incompatible KPI for {diagnostic_code}"
                )
            previous = member_owner.setdefault(diagnostic_code, policy.code)
            if previous != policy.code:
                raise CorrelationValidationError(
                    f"diagnostic {diagnostic_code} belongs to multiple correlation policies"
                )


validate_correlation_policy_catalog()

CORRELATION_POLICY_BY_CODE = MappingProxyType(
    {policy.code: policy for policy in CORRELATION_POLICY_CATALOG}
)
CORRELATION_POLICY_CATALOG_HASH = canonical_sha256(
    [policy.as_dict() for policy in CORRELATION_POLICY_CATALOG]
)
CORRELATION_MANIFEST = CorrelationManifest(
    contract_version=CORRELATION_CONTRACT_VERSION,
    algorithm_version=CORRELATION_ALGORITHM_VERSION,
    policy_count=len(CORRELATION_POLICY_CATALOG),
    policy_catalog_hash=CORRELATION_POLICY_CATALOG_HASH,
    limits=(
        ("batch_inputs", MAX_CORRELATION_INPUTS),
        ("occurrences_per_fingerprint", MAX_OCCURRENCES_PER_FINGERPRINT),
        ("policies", MAX_CORRELATION_POLICIES),
        ("cluster_members", MAX_CLUSTER_MEMBERS),
        ("evidence", MAX_CORRELATED_EVIDENCE),
        ("hypotheses", MAX_CORRELATED_HYPOTHESES),
        ("recommendations", MAX_CORRELATED_RECOMMENDATIONS),
    ),
)
CORRELATION_MANIFEST_HASH = CORRELATION_MANIFEST.manifest_hash
