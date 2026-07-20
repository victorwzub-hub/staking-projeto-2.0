from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Any


class QualitySeverity(StrEnum):
    INFORMATIONAL = "informational"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class QualityRuleType(StrEnum):
    REQUIRED_FIELD = "required_field"
    INVALID_TYPE = "invalid_type"
    INVALID_DATE = "invalid_date"
    UNEXPECTED_NEGATIVE = "unexpected_negative"
    INCOMPATIBLE_QUANTITY = "incompatible_quantity"
    MISSING_REFERENCE = "missing_reference"
    UNMAPPED_PRODUCT = "unmapped_product"
    MISSING_BRANCH = "missing_branch"
    MISSING_SUPPLIER = "missing_supplier"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"
    SALE_WITHOUT_ITEM = "sale_without_item"
    TOTAL_MISMATCH = "total_mismatch"
    PAYMENT_MISMATCH = "payment_mismatch"
    MISSING_COST = "missing_cost"
    IMPOSSIBLE_BALANCE = "impossible_balance"
    OUT_OF_ORDER_MOVEMENT = "out_of_order_movement"
    OVERLAPPING_PERIOD = "overlapping_period"
    STALE_DATA = "stale_data"
    VOLUME_ANOMALY = "volume_anomaly"
    PROBABLE_DUPLICATE = "probable_duplicate"


@dataclass(frozen=True, slots=True)
class QualityRuleDefinition:
    key: str
    rule_type: QualityRuleType
    severity: QualitySeverity
    entities: frozenset[str]
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QualityFinding:
    rule_key: str
    rule_type: QualityRuleType
    severity: QualitySeverity
    entity_type: str
    field_name: str | None
    message: str

    @property
    def blocks_loading(self) -> bool:
        return self.severity is QualitySeverity.BLOCKING


@dataclass(slots=True)
class QualityContext:
    seen_external_ids: set[tuple[str, str]] = field(default_factory=set)
    seen_content_hashes: set[str] = field(default_factory=set)
    latest_movement_at: dict[str, datetime] = field(default_factory=dict)
    known_products: set[str] = field(default_factory=set)
    known_suppliers: set[str] = field(default_factory=set)
    branch_exists: bool = True


@dataclass(frozen=True, slots=True)
class QualitySummary:
    total_records: int
    valid_records: int
    rejected_records: int
    findings_by_type: Mapping[str, int]
    score: Decimal


_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "product": ("sku", "name", "unit"),
    "supplier": ("supplier_code", "name"),
    "sale": ("sale_number", "occurred_at", "net_total", "items", "payments"),
    "purchase": ("purchase_number", "supplier_code", "occurred_at", "items"),
    "stock": ("product_code", "occurred_at", "on_hand"),
    "price": ("product_code", "price", "valid_from"),
}


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _finding(
    rule_type: QualityRuleType,
    entity_type: str,
    message: str,
    *,
    field_name: str | None = None,
    severity: QualitySeverity = QualitySeverity.ERROR,
) -> QualityFinding:
    return QualityFinding(
        rule_key=f"platform.{rule_type}",
        rule_type=rule_type,
        severity=severity,
        entity_type=entity_type,
        field_name=field_name,
        message=message,
    )


class QualityEngine:
    """Deterministic rules only; tenant configuration selects parameters, never executable code."""

    def evaluate_record(
        self,
        entity_type: str,
        external_id: str,
        payload: Mapping[str, Any],
        context: QualityContext,
        *,
        now: datetime | None = None,
    ) -> tuple[QualityFinding, ...]:
        findings: list[QualityFinding] = []
        current_time = now or datetime.now(UTC)

        for required in _REQUIRED_FIELDS.get(entity_type, ()):
            required_value = payload.get(required)
            if required_value is None or required_value == "":
                findings.append(
                    _finding(
                        QualityRuleType.REQUIRED_FIELD,
                        entity_type,
                        f"Required field is missing: {required}",
                        field_name=required,
                        severity=QualitySeverity.BLOCKING,
                    )
                )

        numeric_fields = {
            "gross_total",
            "discount_total",
            "net_total",
            "quantity",
            "unit_price",
            "unit_cost",
            "amount",
            "on_hand",
            "reserved",
            "in_transit",
            "movement_quantity",
            "price",
            "reference_price",
            "reference_cost",
        }
        for field_name in numeric_fields.intersection(payload):
            numeric = _decimal(payload[field_name])
            if numeric is None:
                findings.append(
                    _finding(
                        QualityRuleType.INVALID_TYPE,
                        entity_type,
                        f"Field {field_name} is not numeric",
                        field_name=field_name,
                        severity=QualitySeverity.BLOCKING,
                    )
                )
            elif numeric < 0 and field_name not in {"movement_quantity"}:
                findings.append(
                    _finding(
                        QualityRuleType.UNEXPECTED_NEGATIVE,
                        entity_type,
                        f"Field {field_name} cannot be negative",
                        field_name=field_name,
                        severity=QualitySeverity.BLOCKING,
                    )
                )

        for field_name in ("occurred_at", "valid_from", "valid_to", "expires_on"):
            if (
                field_name in payload
                and payload[field_name] is not None
                and _date(payload[field_name]) is None
            ):
                findings.append(
                    _finding(
                        QualityRuleType.INVALID_DATE,
                        entity_type,
                        f"Field {field_name} is not a valid ISO date",
                        field_name=field_name,
                        severity=QualitySeverity.BLOCKING,
                    )
                )

        identity = (entity_type, external_id)
        if identity in context.seen_external_ids:
            findings.append(
                _finding(
                    QualityRuleType.DUPLICATE_IDENTIFIER,
                    entity_type,
                    "External identifier was repeated in the same batch",
                    severity=QualitySeverity.WARNING,
                )
            )
        context.seen_external_ids.add(identity)

        content_hash = sha256(repr(sorted(payload.items())).encode()).hexdigest()
        if content_hash in context.seen_content_hashes:
            findings.append(
                _finding(
                    QualityRuleType.PROBABLE_DUPLICATE,
                    entity_type,
                    "A record with the same normalized content already exists in this batch",
                    severity=QualitySeverity.WARNING,
                )
            )
        context.seen_content_hashes.add(content_hash)

        if not context.branch_exists:
            findings.append(
                _finding(
                    QualityRuleType.MISSING_BRANCH,
                    entity_type,
                    "The selected branch does not exist in the source scope",
                    severity=QualitySeverity.BLOCKING,
                )
            )

        product_code = payload.get("product_code")
        if (
            product_code
            and context.known_products
            and str(product_code) not in context.known_products
        ):
            findings.append(
                _finding(
                    QualityRuleType.UNMAPPED_PRODUCT,
                    entity_type,
                    "Product identifier has no canonical mapping",
                    field_name="product_code",
                    severity=QualitySeverity.BLOCKING,
                )
            )

        if entity_type == "sale":
            items = payload.get("items")
            payments = payload.get("payments")
            if not isinstance(items, list) or not items:
                findings.append(
                    _finding(
                        QualityRuleType.SALE_WITHOUT_ITEM,
                        entity_type,
                        "Sale has no items",
                        field_name="items",
                        severity=QualitySeverity.BLOCKING,
                    )
                )
            else:
                item_total = sum((_decimal(item.get("net_total")) or Decimal()) for item in items)
                declared = _decimal(payload.get("net_total"))
                if declared is not None and abs(item_total - declared) > Decimal("0.01"):
                    findings.append(
                        _finding(
                            QualityRuleType.TOTAL_MISMATCH,
                            entity_type,
                            "Sale item total differs from the declared net total",
                            severity=QualitySeverity.BLOCKING,
                        )
                    )
                if any(_decimal(item.get("quantity")) in {None, Decimal()} for item in items):
                    findings.append(
                        _finding(
                            QualityRuleType.INCOMPATIBLE_QUANTITY,
                            entity_type,
                            "Sale item quantity must be a non-zero number",
                            field_name="items.quantity",
                            severity=QualitySeverity.BLOCKING,
                        )
                    )
                if any(item.get("unit_cost") in {None, ""} for item in items):
                    findings.append(
                        _finding(
                            QualityRuleType.MISSING_COST,
                            entity_type,
                            "Sale item has no cost-at-sale",
                            field_name="items.unit_cost",
                            severity=QualitySeverity.WARNING,
                        )
                    )
            if isinstance(payments, list):
                payment_total = sum(
                    (_decimal(payment.get("amount")) or Decimal()) for payment in payments
                )
                declared = _decimal(payload.get("net_total"))
                if declared is not None and abs(payment_total - declared) > Decimal("0.01"):
                    findings.append(
                        _finding(
                            QualityRuleType.PAYMENT_MISMATCH,
                            entity_type,
                            "Payment total differs from the declared net total",
                            severity=QualitySeverity.ERROR,
                        )
                    )

        if entity_type == "purchase":
            supplier = str(payload.get("supplier_code", ""))
            if not supplier or (
                context.known_suppliers and supplier not in context.known_suppliers
            ):
                findings.append(
                    _finding(
                        QualityRuleType.MISSING_SUPPLIER,
                        entity_type,
                        "Purchase supplier is not mapped",
                        field_name="supplier_code",
                        severity=QualitySeverity.BLOCKING,
                    )
                )

        if entity_type == "stock":
            on_hand = _decimal(payload.get("on_hand"))
            reserved = _decimal(payload.get("reserved")) or Decimal()
            if on_hand is not None and (on_hand < 0 or reserved > on_hand):
                findings.append(
                    _finding(
                        QualityRuleType.IMPOSSIBLE_BALANCE,
                        entity_type,
                        "Stock balance is negative or reserved quantity exceeds on-hand",
                        severity=QualitySeverity.BLOCKING,
                    )
                )
            movement_at = _date(payload.get("occurred_at"))
            movement_key = str(payload.get("product_code", external_id))
            previous_at = context.latest_movement_at.get(movement_key)
            if movement_at and previous_at and movement_at < previous_at:
                findings.append(
                    _finding(
                        QualityRuleType.OUT_OF_ORDER_MOVEMENT,
                        entity_type,
                        "Inventory movement precedes a movement already processed",
                        severity=QualitySeverity.WARNING,
                    )
                )
            if movement_at:
                context.latest_movement_at[movement_key] = max(
                    movement_at, previous_at or movement_at
                )

        valid_from = _date(payload.get("valid_from"))
        valid_to = _date(payload.get("valid_to"))
        if valid_from and valid_to and valid_to <= valid_from:
            findings.append(
                _finding(
                    QualityRuleType.OVERLAPPING_PERIOD,
                    entity_type,
                    "Validity period ends before it starts",
                    severity=QualitySeverity.BLOCKING,
                )
            )

        occurred_at = _date(payload.get("occurred_at"))
        if occurred_at and current_time - occurred_at > timedelta(days=30):
            findings.append(
                _finding(
                    QualityRuleType.STALE_DATA,
                    entity_type,
                    "Source record is more than 30 days late",
                    severity=QualitySeverity.WARNING,
                )
            )

        if product_code is None and entity_type in {"stock", "price"}:
            findings.append(
                _finding(
                    QualityRuleType.MISSING_REFERENCE,
                    entity_type,
                    "Product reference is required",
                    field_name="product_code",
                    severity=QualitySeverity.BLOCKING,
                )
            )
        return tuple(findings)

    def evaluate_volume(
        self, entity_counts: Mapping[str, int], expected_counts: Mapping[str, int]
    ) -> tuple[QualityFinding, ...]:
        findings: list[QualityFinding] = []
        for entity, expected in expected_counts.items():
            actual = entity_counts.get(entity, 0)
            if expected > 0 and (actual < expected * 0.25 or actual > expected * 4):
                findings.append(
                    _finding(
                        QualityRuleType.VOLUME_ANOMALY,
                        entity,
                        f"Volume {actual} is outside the expected range around {expected}",
                        severity=QualitySeverity.WARNING,
                    )
                )
        return tuple(findings)

    @staticmethod
    def summarize(records: Iterable[tuple[QualityFinding, ...]]) -> QualitySummary:
        record_findings = tuple(records)
        rejected = sum(
            1 for findings in record_findings if any(finding.blocks_loading for finding in findings)
        )
        total = len(record_findings)
        counts = Counter(
            finding.rule_type.value for findings in record_findings for finding in findings
        )
        valid = total - rejected
        score = (
            (Decimal(valid) / Decimal(total) * 100).quantize(Decimal("0.01"))
            if total
            else Decimal("100.00")
        )
        return QualitySummary(total, valid, rejected, dict(counts), score)
