"""Closed, declarative and bounded condition DSL for diagnostic rules.

Documents are parsed into an immutable AST. The parser accepts only known node
shapes, validates KPI references against the semantic catalog, rejects extra
fields and enforces limits while descending the input. No user-provided code,
SQL or import target is ever evaluated or executed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Literal, cast

from pharma_api.domain.analytics.kpis import KPI_BY_CODE

CompareOp = Literal["lt", "lte", "gt", "gte", "eq", "ne"]
Baseline = Literal["previous", "year_ago"]
Severity = Literal["info", "low", "medium", "high", "critical"]

COMPARE_OPS: tuple[CompareOp, ...] = ("lt", "lte", "gt", "gte", "eq", "ne")
BASELINES: tuple[Baseline, ...] = ("previous", "year_ago")
SEVERITIES: tuple[Severity, ...] = ("info", "low", "medium", "high", "critical")

MAX_DEPTH = 8
MAX_NODES = 64
MAX_BOOLEAN_CHILDREN = 32
MAX_CODE_LENGTH = 140
MAX_STRING_LENGTH = 500
MAX_NUMBER_CHARACTERS = 64
MAX_DECIMAL_PLACES = 8
MAX_ABS_NUMBER = Decimal("1000000000000000")
MIN_PERIODS = 2
MAX_PERIODS = 60
MIN_TOP_N = 1
MAX_TOP_N = 50
MIN_COOLDOWN_HOURS = 1
MAX_COOLDOWN_HOURS = 24 * 30
MAX_CONTROL_ITEMS = 32
MAX_SEVERITY_STEPS = len(SEVERITIES)
MAX_SEVERITY_THRESHOLD_PCT = Decimal("100000")

type Measurements = Mapping[str, object]
_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]*$")
_SEVERITY_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}


class ConditionValidationError(ValueError):
    """Raised when a condition or controls document fails validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


class Operand:
    """Base class for numeric operand nodes. Evaluation may be indeterminate."""

    node_type: ClassVar[str]

    def as_json(self) -> dict[str, object]:
        raise NotImplementedError


class Condition:
    """Base class for predicate and boolean nodes."""

    node_type: ClassVar[str]

    def as_json(self) -> dict[str, object]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Fixed(Operand):
    node_type: ClassVar[str] = "fixed"
    value: Decimal

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "value": str(self.value)}


@dataclass(frozen=True, slots=True)
class KpiRef(Operand):
    node_type: ClassVar[str] = "kpi"
    kpi_code: str

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "kpi_code": self.kpi_code}


@dataclass(frozen=True, slots=True)
class Kpi(KpiRef):
    node_type: ClassVar[str] = "kpi"


@dataclass(frozen=True, slots=True)
class Goal(KpiRef):
    node_type: ClassVar[str] = "goal"


@dataclass(frozen=True, slots=True)
class Previous(KpiRef):
    node_type: ClassVar[str] = "previous"


@dataclass(frozen=True, slots=True)
class YearAgo(KpiRef):
    node_type: ClassVar[str] = "year_ago"


@dataclass(frozen=True, slots=True)
class NetworkAverage(KpiRef):
    node_type: ClassVar[str] = "network_average"


@dataclass(frozen=True, slots=True)
class CategoryAverage(KpiRef):
    node_type: ClassVar[str] = "category_average"


@dataclass(frozen=True, slots=True)
class PeriodsOperand(KpiRef):
    periods: int = MIN_PERIODS

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "kpi_code": self.kpi_code, "periods": self.periods}


@dataclass(frozen=True, slots=True)
class MovingAverage(PeriodsOperand):
    node_type: ClassVar[str] = "moving_average"


@dataclass(frozen=True, slots=True)
class Trend(PeriodsOperand):
    node_type: ClassVar[str] = "trend"


@dataclass(frozen=True, slots=True)
class Frequency(PeriodsOperand):
    node_type: ClassVar[str] = "frequency"


@dataclass(frozen=True, slots=True)
class ChangeOperand(KpiRef):
    baseline: Baseline = "previous"

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "kpi_code": self.kpi_code, "baseline": self.baseline}


@dataclass(frozen=True, slots=True)
class AbsChange(ChangeOperand):
    node_type: ClassVar[str] = "abs_change"


@dataclass(frozen=True, slots=True)
class PctChange(ChangeOperand):
    node_type: ClassVar[str] = "pct_change"


@dataclass(frozen=True, slots=True)
class Share(Operand):
    node_type: ClassVar[str] = "share"
    numerator_kpi: str
    denominator_kpi: str

    def as_json(self) -> dict[str, object]:
        return {
            "type": self.node_type,
            "numerator_kpi": self.numerator_kpi,
            "denominator_kpi": self.denominator_kpi,
        }


@dataclass(frozen=True, slots=True)
class Concentration(KpiRef):
    node_type: ClassVar[str] = "concentration"
    top_n: int = 1

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "kpi_code": self.kpi_code, "top_n": self.top_n}


@dataclass(frozen=True, slots=True)
class Percentile(KpiRef):
    node_type: ClassVar[str] = "percentile"
    p: Decimal = Decimal("50")

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "kpi_code": self.kpi_code, "p": str(self.p)}


@dataclass(frozen=True, slots=True)
class Compare(Condition):
    node_type: ClassVar[str] = "compare"
    left: Operand
    op: CompareOp
    right: Operand

    def as_json(self) -> dict[str, object]:
        return {
            "type": self.node_type,
            "left": self.left.as_json(),
            "op": self.op,
            "right": self.right.as_json(),
        }


@dataclass(frozen=True, slots=True)
class Between(Condition):
    node_type: ClassVar[str] = "between"
    value: Operand
    minimum: Operand
    maximum: Operand

    def as_json(self) -> dict[str, object]:
        return {
            "type": self.node_type,
            "value": self.value.as_json(),
            "minimum": self.minimum.as_json(),
            "maximum": self.maximum.as_json(),
        }


@dataclass(frozen=True, slots=True)
class Persisted(Condition):
    node_type: ClassVar[str] = "persisted"
    predicate: Condition
    periods: int = MIN_PERIODS

    def as_json(self) -> dict[str, object]:
        return {
            "type": self.node_type,
            "predicate": self.predicate.as_json(),
            "periods": self.periods,
        }


@dataclass(frozen=True, slots=True)
class DataAvailable(Condition):
    node_type: ClassVar[str] = "data_available"
    kpi_code: str
    min_coverage: Decimal = Decimal("1")

    def as_json(self) -> dict[str, object]:
        return {
            "type": self.node_type,
            "kpi_code": self.kpi_code,
            "min_coverage": str(self.min_coverage),
        }


@dataclass(frozen=True, slots=True)
class MinQuality(Condition):
    node_type: ClassVar[str] = "min_quality"
    score: Decimal

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "score": str(self.score)}


@dataclass(frozen=True, slots=True)
class MissingData(Condition):
    node_type: ClassVar[str] = "missing_data"
    kpi_code: str

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "kpi_code": self.kpi_code}


@dataclass(frozen=True, slots=True)
class AllOf(Condition):
    node_type: ClassVar[str] = "all_of"
    nodes: tuple[Condition, ...]

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "nodes": [node.as_json() for node in self.nodes]}


@dataclass(frozen=True, slots=True)
class AnyOf(Condition):
    node_type: ClassVar[str] = "any_of"
    nodes: tuple[Condition, ...]

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "nodes": [node.as_json() for node in self.nodes]}


@dataclass(frozen=True, slots=True)
class Negate(Condition):
    node_type: ClassVar[str] = "negate"
    node: Condition

    def as_json(self) -> dict[str, object]:
        return {"type": self.node_type, "node": self.node.as_json()}


@dataclass(frozen=True, slots=True)
class SeverityStep:
    threshold_pct: Decimal
    severity: Severity

    def as_json(self) -> dict[str, object]:
        return {"threshold_pct": str(self.threshold_pct), "severity": self.severity}


@dataclass(frozen=True, slots=True)
class RuleControls:
    cooldown_hours: int | None = None
    suppression: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    severity_ladder: tuple[SeverityStep, ...] = ()

    def as_json(self) -> dict[str, object]:
        return {
            "cooldown_hours": self.cooldown_hours,
            "suppression": list(self.suppression),
            "exceptions": list(self.exceptions),
            "severity_ladder": [step.as_json() for step in self.severity_ladder],
        }


DEFAULT_RULE_CONTROLS = RuleControls()

_OPERAND_TYPES = frozenset(
    {
        "fixed",
        "kpi",
        "goal",
        "previous",
        "year_ago",
        "network_average",
        "category_average",
        "moving_average",
        "abs_change",
        "pct_change",
        "trend",
        "share",
        "concentration",
        "percentile",
        "frequency",
    }
)
_PREDICATE_TYPES = frozenset(
    {"compare", "between", "persisted", "data_available", "min_quality", "missing_data"}
)
_BOOLEAN_TYPES = frozenset({"all_of", "any_of", "negate"})


@dataclass(slots=True)
class _ParseBudget:
    nodes: int = 0

    def enter(self, path: str, depth: int, errors: list[str]) -> bool:
        if depth > MAX_DEPTH:
            errors.append(f"{path}: depth exceeds the maximum of {MAX_DEPTH}")
            return False
        self.nodes += 1
        if self.nodes > MAX_NODES:
            errors.append(f"{path}: node count exceeds the maximum of {MAX_NODES}")
            return False
        return True


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, int):
        if abs(value) > int(MAX_ABS_NUMBER):
            return None
        candidate = Decimal(value)
    elif isinstance(value, float):
        candidate = Decimal(str(value))
    elif isinstance(value, str):
        if not value or len(value) > MAX_NUMBER_CHARACTERS:
            return None
        try:
            candidate = Decimal(value)
        except InvalidOperation:
            return None
    else:
        return None
    if not candidate.is_finite() or abs(candidate) > MAX_ABS_NUMBER:
        return None
    exponent = candidate.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -MAX_DECIMAL_PLACES:
        return None
    return candidate


def _field_decimal(
    data: Mapping[object, object],
    key: str,
    errors: list[str],
    path: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal | None:
    raw = data.get(key)
    result = _to_decimal(raw)
    if result is None:
        errors.append(f"{path}.{key}: expected a bounded finite number, got {raw!r}")
        return None
    if minimum is not None and result < minimum:
        errors.append(f"{path}.{key}: must be >= {minimum}, got {result}")
        return None
    if maximum is not None and result > maximum:
        errors.append(f"{path}.{key}: must be <= {maximum}, got {result}")
        return None
    return result


def _field_string(
    data: Mapping[object, object],
    key: str,
    errors: list[str],
    path: str,
    *,
    max_length: int = MAX_STRING_LENGTH,
    pattern: re.Pattern[str] | None = None,
) -> str | None:
    raw = data.get(key)
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        errors.append(f"{path}.{key}: expected a non-empty trimmed string, got {raw!r}")
        return None
    if len(raw) > max_length:
        errors.append(f"{path}.{key}: exceeds {max_length} characters")
        return None
    if pattern is not None and pattern.fullmatch(raw) is None:
        errors.append(f"{path}.{key}: has an invalid format")
        return None
    return raw


def _field_kpi(data: Mapping[object, object], key: str, errors: list[str], path: str) -> str | None:
    code = _field_string(
        data,
        key,
        errors,
        path,
        max_length=MAX_CODE_LENGTH,
        pattern=_CODE_PATTERN,
    )
    if code is None:
        return None
    if code not in KPI_BY_CODE:
        errors.append(f"{path}.{key}: unknown KPI code {code!r}")
        return None
    return code


def _field_int(
    data: Mapping[object, object],
    key: str,
    errors: list[str],
    path: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    raw = data.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        errors.append(f"{path}.{key}: expected an integer, got {raw!r}")
        return None
    if raw < minimum or raw > maximum:
        errors.append(f"{path}.{key}: must be between {minimum} and {maximum}, got {raw}")
        return None
    return raw


def _check_keys(
    data: Mapping[object, object], allowed: frozenset[str], errors: list[str], path: str
) -> None:
    extras = sorted(repr(key) for key in data if not isinstance(key, str) or key not in allowed)
    if extras:
        errors.append(f"{path}: unknown fields {extras}")


def _parse_kpi_ref[KpiRefT: KpiRef](
    data: Mapping[object, object],
    errors: list[str],
    path: str,
    cls: type[KpiRefT],
) -> KpiRefT | None:
    initial_errors = len(errors)
    _check_keys(data, frozenset({"type", "kpi_code"}), errors, path)
    code = _field_kpi(data, "kpi_code", errors, path)
    if len(errors) != initial_errors or code is None:
        return None
    return cls(kpi_code=code)


def _parse_periods_operand[PeriodsOperandT: PeriodsOperand](
    data: Mapping[object, object],
    errors: list[str],
    path: str,
    cls: type[PeriodsOperandT],
) -> PeriodsOperandT | None:
    initial_errors = len(errors)
    _check_keys(data, frozenset({"type", "kpi_code", "periods"}), errors, path)
    code = _field_kpi(data, "kpi_code", errors, path)
    periods = _field_int(
        data,
        "periods",
        errors,
        path,
        minimum=MIN_PERIODS,
        maximum=MAX_PERIODS,
    )
    if len(errors) != initial_errors or code is None or periods is None:
        return None
    return cls(kpi_code=code, periods=periods)


def _parse_change_operand[ChangeOperandT: ChangeOperand](
    data: Mapping[object, object],
    errors: list[str],
    path: str,
    cls: type[ChangeOperandT],
) -> ChangeOperandT | None:
    initial_errors = len(errors)
    _check_keys(data, frozenset({"type", "kpi_code", "baseline"}), errors, path)
    code = _field_kpi(data, "kpi_code", errors, path)
    baseline = data.get("baseline")
    if baseline not in BASELINES:
        errors.append(f"{path}.baseline: expected one of {BASELINES}, got {baseline!r}")
    if len(errors) != initial_errors or code is None:
        return None
    return cls(kpi_code=code, baseline=cast(Baseline, baseline))


def _parse_operand(
    data: object,
    errors: list[str],
    path: str,
    budget: _ParseBudget,
    depth: int,
) -> Operand | None:
    if not budget.enter(path, depth, errors):
        return None
    if not isinstance(data, Mapping):
        errors.append(f"{path}: expected an operand object, got {data!r}")
        return None
    node_type = data.get("type")
    if not isinstance(node_type, str):
        errors.append(f"{path}.type: expected a string, got {node_type!r}")
        return None
    if node_type not in _OPERAND_TYPES:
        errors.append(f"{path}.type: unknown operand type {node_type!r}")
        return None
    if node_type == "fixed":
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "value"}), errors, path)
        value = _field_decimal(data, "value", errors, path)
        if len(errors) != initial_errors or value is None:
            return None
        return Fixed(value=value)
    if node_type == "kpi":
        return _parse_kpi_ref(data, errors, path, Kpi)
    if node_type == "goal":
        return _parse_kpi_ref(data, errors, path, Goal)
    if node_type == "previous":
        return _parse_kpi_ref(data, errors, path, Previous)
    if node_type == "year_ago":
        return _parse_kpi_ref(data, errors, path, YearAgo)
    if node_type == "network_average":
        return _parse_kpi_ref(data, errors, path, NetworkAverage)
    if node_type == "category_average":
        return _parse_kpi_ref(data, errors, path, CategoryAverage)
    if node_type == "moving_average":
        return _parse_periods_operand(data, errors, path, MovingAverage)
    if node_type == "trend":
        return _parse_periods_operand(data, errors, path, Trend)
    if node_type == "frequency":
        return _parse_periods_operand(data, errors, path, Frequency)
    if node_type == "abs_change":
        return _parse_change_operand(data, errors, path, AbsChange)
    if node_type == "pct_change":
        return _parse_change_operand(data, errors, path, PctChange)
    if node_type == "share":
        initial_errors = len(errors)
        _check_keys(
            data,
            frozenset({"type", "numerator_kpi", "denominator_kpi"}),
            errors,
            path,
        )
        numerator = _field_kpi(data, "numerator_kpi", errors, path)
        denominator = _field_kpi(data, "denominator_kpi", errors, path)
        if len(errors) != initial_errors or numerator is None or denominator is None:
            return None
        return Share(numerator_kpi=numerator, denominator_kpi=denominator)
    if node_type == "concentration":
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "kpi_code", "top_n"}), errors, path)
        code = _field_kpi(data, "kpi_code", errors, path)
        top_n = _field_int(
            data,
            "top_n",
            errors,
            path,
            minimum=MIN_TOP_N,
            maximum=MAX_TOP_N,
        )
        if len(errors) != initial_errors or code is None or top_n is None:
            return None
        return Concentration(kpi_code=code, top_n=top_n)
    initial_errors = len(errors)
    _check_keys(data, frozenset({"type", "kpi_code", "p"}), errors, path)
    code = _field_kpi(data, "kpi_code", errors, path)
    percentile = _field_decimal(
        data,
        "p",
        errors,
        path,
        minimum=Decimal("0"),
        maximum=Decimal("100"),
    )
    if len(errors) != initial_errors or code is None or percentile is None:
        return None
    return Percentile(kpi_code=code, p=percentile)


def _parse_condition(
    data: object,
    errors: list[str],
    path: str,
    budget: _ParseBudget,
    depth: int,
) -> Condition | None:
    if not budget.enter(path, depth, errors):
        return None
    if not isinstance(data, Mapping):
        errors.append(f"{path}: expected a condition object, got {data!r}")
        return None
    node_type = data.get("type")
    if not isinstance(node_type, str):
        errors.append(f"{path}.type: expected a string, got {node_type!r}")
        return None
    if node_type in _OPERAND_TYPES:
        errors.append(f"{path}.type: operand {node_type!r} is not a condition")
        return None
    if node_type not in _PREDICATE_TYPES | _BOOLEAN_TYPES:
        errors.append(f"{path}.type: unknown condition type {node_type!r}")
        return None
    if node_type == "compare":
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "left", "op", "right"}), errors, path)
        left = _parse_operand(data.get("left"), errors, f"{path}.left", budget, depth + 1)
        right = _parse_operand(data.get("right"), errors, f"{path}.right", budget, depth + 1)
        operator = data.get("op")
        if operator not in COMPARE_OPS:
            errors.append(f"{path}.op: expected one of {COMPARE_OPS}, got {operator!r}")
        if len(errors) != initial_errors or left is None or right is None:
            return None
        return Compare(left=left, op=cast(CompareOp, operator), right=right)
    if node_type == "between":
        initial_errors = len(errors)
        _check_keys(
            data,
            frozenset({"type", "value", "minimum", "maximum"}),
            errors,
            path,
        )
        value = _parse_operand(data.get("value"), errors, f"{path}.value", budget, depth + 1)
        minimum = _parse_operand(data.get("minimum"), errors, f"{path}.minimum", budget, depth + 1)
        maximum = _parse_operand(data.get("maximum"), errors, f"{path}.maximum", budget, depth + 1)
        if (
            isinstance(minimum, Fixed)
            and isinstance(maximum, Fixed)
            and minimum.value > maximum.value
        ):
            errors.append(f"{path}: fixed minimum must not exceed fixed maximum")
        if len(errors) != initial_errors or value is None or minimum is None or maximum is None:
            return None
        return Between(value=value, minimum=minimum, maximum=maximum)
    if node_type == "persisted":
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "predicate", "periods"}), errors, path)
        predicate = _parse_condition(
            data.get("predicate"), errors, f"{path}.predicate", budget, depth + 1
        )
        periods = _field_int(
            data,
            "periods",
            errors,
            path,
            minimum=MIN_PERIODS,
            maximum=MAX_PERIODS,
        )
        if len(errors) != initial_errors or predicate is None or periods is None:
            return None
        return Persisted(predicate=predicate, periods=periods)
    if node_type == "data_available":
        initial_errors = len(errors)
        _check_keys(
            data,
            frozenset({"type", "kpi_code", "min_coverage"}),
            errors,
            path,
        )
        code = _field_kpi(data, "kpi_code", errors, path)
        coverage = _field_decimal(
            data,
            "min_coverage",
            errors,
            path,
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        if len(errors) != initial_errors or code is None or coverage is None:
            return None
        return DataAvailable(kpi_code=code, min_coverage=coverage)
    if node_type == "min_quality":
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "score"}), errors, path)
        score = _field_decimal(
            data,
            "score",
            errors,
            path,
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        if len(errors) != initial_errors or score is None:
            return None
        return MinQuality(score=score)
    if node_type == "missing_data":
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "kpi_code"}), errors, path)
        code = _field_kpi(data, "kpi_code", errors, path)
        if len(errors) != initial_errors or code is None:
            return None
        return MissingData(kpi_code=code)
    if node_type in {"all_of", "any_of"}:
        initial_errors = len(errors)
        _check_keys(data, frozenset({"type", "nodes"}), errors, path)
        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, list):
            errors.append(f"{path}.nodes: expected a non-empty JSON array, got {raw_nodes!r}")
            return None
        if not raw_nodes:
            errors.append(f"{path}.nodes: must contain at least one condition")
            return None
        if len(raw_nodes) > MAX_BOOLEAN_CHILDREN:
            errors.append(
                f"{path}.nodes: exceeds the maximum of {MAX_BOOLEAN_CHILDREN} direct children"
            )
            return None
        nodes: list[Condition] = []
        for index, item in enumerate(raw_nodes):
            child = _parse_condition(
                item,
                errors,
                f"{path}.nodes[{index}]",
                budget,
                depth + 1,
            )
            if child is not None:
                nodes.append(child)
        if len(errors) != initial_errors:
            return None
        if node_type == "all_of":
            return AllOf(nodes=tuple(nodes))
        return AnyOf(nodes=tuple(nodes))
    initial_errors = len(errors)
    _check_keys(data, frozenset({"type", "node"}), errors, path)
    node = _parse_condition(data.get("node"), errors, f"{path}.node", budget, depth + 1)
    if len(errors) != initial_errors or node is None:
        return None
    return Negate(node=node)


def parse_condition(data: object) -> Condition:
    """Parse and validate a JSON-like condition document."""

    errors: list[str] = []
    node = _parse_condition(data, errors, "$", _ParseBudget(), 1)
    if errors or node is None:
        raise ConditionValidationError(errors or ("$: invalid condition document",))
    return node


def validate_condition(data: object) -> tuple[str, ...]:
    """Return deterministic validation errors without raising."""

    try:
        parse_condition(data)
    except ConditionValidationError as exc:
        return exc.errors
    return ()


def _parse_string_list(
    data: Mapping[object, object],
    key: str,
    errors: list[str],
    path: str,
    *,
    max_length: int,
    pattern: re.Pattern[str] | None = None,
) -> tuple[str, ...]:
    raw = data.get(key, [])
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errors.append(f"{path}.{key}: expected a JSON array of strings, got {raw!r}")
        return ()
    if len(raw) > MAX_CONTROL_ITEMS:
        errors.append(f"{path}.{key}: exceeds the maximum of {MAX_CONTROL_ITEMS} items")
        return ()
    values: list[str] = []
    for index, item in enumerate(raw):
        item_path = f"{path}.{key}[{index}]"
        if not isinstance(item, str) or not item or item != item.strip():
            errors.append(f"{item_path}: expected a non-empty trimmed string")
            continue
        if len(item) > max_length:
            errors.append(f"{item_path}: exceeds {max_length} characters")
            continue
        if pattern is not None and pattern.fullmatch(item) is None:
            errors.append(f"{item_path}: has an invalid format")
            continue
        if item in values:
            errors.append(f"{item_path}: duplicate value {item!r}")
            continue
        values.append(item)
    return tuple(values)


def parse_rule_controls(data: object) -> RuleControls:
    """Parse bounded non-predicate controls associated with a rule version."""

    if not isinstance(data, Mapping):
        raise ConditionValidationError((f"$: expected an object, got {data!r}",))
    errors: list[str] = []
    _check_keys(
        data,
        frozenset({"cooldown_hours", "suppression", "exceptions", "severity_ladder"}),
        errors,
        "$",
    )
    cooldown: int | None = None
    if "cooldown_hours" in data and data.get("cooldown_hours") is not None:
        cooldown = _field_int(
            data,
            "cooldown_hours",
            errors,
            "$",
            minimum=MIN_COOLDOWN_HOURS,
            maximum=MAX_COOLDOWN_HOURS,
        )
    suppression = _parse_string_list(
        data,
        "suppression",
        errors,
        "$",
        max_length=MAX_CODE_LENGTH,
        pattern=_CODE_PATTERN,
    )
    exceptions = _parse_string_list(
        data,
        "exceptions",
        errors,
        "$",
        max_length=MAX_STRING_LENGTH,
    )
    ladder: list[SeverityStep] = []
    raw_ladder = data.get("severity_ladder", [])
    if raw_ladder is None:
        raw_ladder = []
    if not isinstance(raw_ladder, list):
        errors.append(f"$.severity_ladder: expected a JSON array, got {raw_ladder!r}")
    elif len(raw_ladder) > MAX_SEVERITY_STEPS:
        errors.append(f"$.severity_ladder: exceeds the maximum of {MAX_SEVERITY_STEPS} steps")
    else:
        previous_threshold: Decimal | None = None
        previous_rank = -1
        for index, item in enumerate(raw_ladder):
            step_path = f"$.severity_ladder[{index}]"
            if not isinstance(item, Mapping):
                errors.append(f"{step_path}: expected an object, got {item!r}")
                continue
            initial_errors = len(errors)
            _check_keys(item, frozenset({"threshold_pct", "severity"}), errors, step_path)
            threshold = _field_decimal(
                item,
                "threshold_pct",
                errors,
                step_path,
                minimum=Decimal("0"),
                maximum=MAX_SEVERITY_THRESHOLD_PCT,
            )
            severity_value = item.get("severity")
            if severity_value not in SEVERITIES:
                errors.append(
                    f"{step_path}.severity: expected one of {SEVERITIES}, got {severity_value!r}"
                )
            if len(errors) != initial_errors or threshold is None:
                continue
            severity = cast(Severity, severity_value)
            rank = _SEVERITY_RANK[severity]
            if previous_threshold is not None and threshold <= previous_threshold:
                errors.append(f"{step_path}.threshold_pct: ladder must be strictly ascending")
                continue
            if rank <= previous_rank:
                errors.append(f"{step_path}.severity: ladder severity must strictly increase")
                continue
            previous_threshold = threshold
            previous_rank = rank
            ladder.append(SeverityStep(threshold_pct=threshold, severity=severity))
    if errors:
        raise ConditionValidationError(errors)
    return RuleControls(
        cooldown_hours=cooldown,
        suppression=suppression,
        exceptions=exceptions,
        severity_ladder=tuple(ladder),
    )


def serialize_condition(condition: Condition) -> dict[str, object]:
    """Serialize an AST into its canonical JSON-compatible form."""

    return condition.as_json()


def serialize_rule_controls(controls: RuleControls) -> dict[str, object]:
    """Serialize bounded controls into their canonical JSON-compatible form."""

    return controls.as_json()


def condition_kpi_dependencies(condition: Condition) -> tuple[str, ...]:
    """Return referenced KPI codes in stable lexical order."""

    codes: set[str] = set()

    def visit_operand(operand: Operand) -> None:
        if isinstance(operand, KpiRef):
            codes.add(operand.kpi_code)
        elif isinstance(operand, Share):
            codes.add(operand.numerator_kpi)
            codes.add(operand.denominator_kpi)

    def visit(node: Condition) -> None:
        if isinstance(node, Compare):
            visit_operand(node.left)
            visit_operand(node.right)
        elif isinstance(node, Between):
            visit_operand(node.value)
            visit_operand(node.minimum)
            visit_operand(node.maximum)
        elif isinstance(node, Persisted):
            visit(node.predicate)
        elif isinstance(node, (DataAvailable, MissingData)):
            codes.add(node.kpi_code)
        elif isinstance(node, (AllOf, AnyOf)):
            for child in node.nodes:
                visit(child)
        elif isinstance(node, Negate):
            visit(node.node)

    visit(condition)
    return tuple(sorted(codes))


def evaluate_operand(operand: Operand, measurements: Measurements) -> Decimal | None:
    """Evaluate an operand only against already-resolved measurements."""

    if isinstance(operand, Fixed):
        return operand.value
    if isinstance(operand, Kpi):
        return _to_decimal(measurements.get(operand.kpi_code))
    if isinstance(operand, (MovingAverage, Trend, Frequency)):
        key = f"{operand.node_type}:{operand.kpi_code}:{operand.periods}"
        return _to_decimal(measurements.get(key))
    if isinstance(operand, Concentration):
        return _to_decimal(measurements.get(f"concentration:{operand.kpi_code}:{operand.top_n}"))
    if isinstance(operand, Percentile):
        return _to_decimal(measurements.get(f"percentile:{operand.kpi_code}:{operand.p}"))
    if isinstance(operand, ChangeOperand):
        current = _to_decimal(measurements.get(operand.kpi_code))
        baseline = _to_decimal(measurements.get(f"{operand.baseline}:{operand.kpi_code}"))
        if current is None or baseline is None:
            return None
        if isinstance(operand, AbsChange):
            return current - baseline
        if baseline == 0:
            return None
        return (current - baseline) / baseline * Decimal("100")
    if isinstance(operand, Share):
        numerator = _to_decimal(measurements.get(operand.numerator_kpi))
        denominator = _to_decimal(measurements.get(operand.denominator_kpi))
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator * Decimal("100")
    if isinstance(operand, KpiRef):
        return _to_decimal(measurements.get(f"{operand.node_type}:{operand.kpi_code}"))
    raise TypeError(f"unsupported operand {type(operand).__name__}")


def _compare(operator: CompareOp, left: Decimal, right: Decimal) -> bool:
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "eq":
        return left == right
    return left != right


def evaluate_predicate(condition: Condition, measurements: Measurements) -> bool | None:
    """Evaluate a condition deterministically; ``None`` means indeterminate."""

    if isinstance(condition, Compare):
        left = evaluate_operand(condition.left, measurements)
        right = evaluate_operand(condition.right, measurements)
        if left is None or right is None:
            return None
        return _compare(condition.op, left, right)
    if isinstance(condition, Between):
        value = evaluate_operand(condition.value, measurements)
        minimum = evaluate_operand(condition.minimum, measurements)
        maximum = evaluate_operand(condition.maximum, measurements)
        if value is None or minimum is None or maximum is None:
            return None
        return minimum <= value <= maximum
    if isinstance(condition, DataAvailable):
        coverage = _to_decimal(measurements.get(f"coverage:{condition.kpi_code}"))
        if coverage is None or not Decimal("0") <= coverage <= Decimal("1"):
            return None
        return coverage >= condition.min_coverage
    if isinstance(condition, MinQuality):
        score = _to_decimal(measurements.get("quality_score"))
        if score is None or not Decimal("0") <= score <= Decimal("1"):
            return None
        return score >= condition.score
    if isinstance(condition, MissingData):
        return _to_decimal(measurements.get(condition.kpi_code)) is None
    if isinstance(condition, Persisted):
        history = measurements.get("history")
        if not isinstance(history, list):
            return None
        entries = history[-condition.periods :]
        if len(entries) < condition.periods:
            return None
        results: list[bool | None] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                return None
            results.append(
                evaluate_predicate(condition.predicate, cast(Mapping[str, object], entry))
            )
        if any(result is False for result in results):
            return False
        if any(result is None for result in results):
            return None
        return True
    if isinstance(condition, AllOf):
        results = [evaluate_predicate(node, measurements) for node in condition.nodes]
        if any(result is False for result in results):
            return False
        if any(result is None for result in results):
            return None
        return True
    if isinstance(condition, AnyOf):
        results = [evaluate_predicate(node, measurements) for node in condition.nodes]
        if any(result is True for result in results):
            return True
        if any(result is None for result in results):
            return None
        return False
    if isinstance(condition, Negate):
        result = evaluate_predicate(condition.node, measurements)
        return None if result is None else not result
    raise TypeError(f"unsupported condition {type(condition).__name__}")
