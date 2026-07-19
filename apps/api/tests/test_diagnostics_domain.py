from __future__ import annotations

import ast
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pharma_api.domain.diagnostics.conditions as conditions_module
import pytest
from pharma_api.domain.analytics.kpis import KPI_BY_CODE
from pharma_api.domain.diagnostics.actions import (
    ACTION_BY_CODE,
    ACTION_CATALOG,
    ACTION_DOMAINS,
    ACTION_PRIORITIES,
    ACTION_SAFETY_CONSTRAINTS,
    ACTION_STATUSES,
    MAX_DEADLINE_DAYS,
    MIN_DEADLINE_DAYS,
    SUGGESTED_ROLES,
    ActionDefinition,
    validate_action_catalog,
)
from pharma_api.domain.diagnostics.conditions import (
    MAX_ABS_NUMBER,
    MAX_BOOLEAN_CHILDREN,
    MAX_CODE_LENGTH,
    MAX_CONTROL_ITEMS,
    MAX_DECIMAL_PLACES,
    MAX_DEPTH,
    MAX_NODES,
    MAX_PERIODS,
    ConditionValidationError,
    condition_kpi_dependencies,
    evaluate_predicate,
    parse_condition,
    parse_rule_controls,
    serialize_condition,
    serialize_rule_controls,
    validate_condition,
)


def _compare_document(kpi_code: str = "sales.net_revenue") -> dict[str, object]:
    return {
        "type": "compare",
        "left": {"type": "kpi", "kpi_code": kpi_code},
        "op": "gt",
        "right": {"type": "fixed", "value": "100"},
    }


def test_parses_valid_closed_ast_and_extracts_stable_dependencies() -> None:
    document: dict[str, object] = {
        "type": "all_of",
        "nodes": [
            {
                "type": "compare",
                "left": {
                    "type": "pct_change",
                    "kpi_code": "sales.net_revenue",
                    "baseline": "previous",
                },
                "op": "lt",
                "right": {"type": "fixed", "value": "-10"},
            },
            {
                "type": "data_available",
                "kpi_code": "sales.net_revenue",
                "min_coverage": "0.95",
            },
            {
                "type": "negate",
                "node": {"type": "missing_data", "kpi_code": "inventory.coverage_days"},
            },
        ],
    }

    condition = parse_condition(document)

    assert condition_kpi_dependencies(condition) == (
        "inventory.coverage_days",
        "sales.net_revenue",
    )
    assert validate_condition(document) == ()


def test_serialization_is_json_compatible_and_round_trips_canonically() -> None:
    condition = parse_condition(
        {
            "type": "between",
            "value": {"type": "moving_average", "kpi_code": "sales.average_ticket", "periods": 7},
            "minimum": {"type": "fixed", "value": 10},
            "maximum": {"type": "fixed", "value": "250.50"},
        }
    )

    serialized = serialize_condition(condition)
    reparsed = parse_condition(json.loads(json.dumps(serialized)))

    assert serialize_condition(reparsed) == serialized
    assert serialized["minimum"] == {"type": "fixed", "value": "10"}


@pytest.mark.parametrize(
    "document, expected_fragment",
    [
        ({"type": "python", "code": "raise SystemExit"}, "unknown condition type"),
        ({"type": "kpi", "kpi_code": "sales.net_revenue"}, "is not a condition"),
        (_compare_document("sales.not_real"), "unknown KPI code"),
        ({**_compare_document(), "sql": "DROP TABLE users"}, "unknown fields"),
        ({"type": "all_of", "nodes": []}, "must contain at least one"),
    ],
)
def test_rejects_unknown_nodes_kpis_extra_fields_and_empty_boolean_nodes(
    document: dict[str, object], expected_fragment: str
) -> None:
    with pytest.raises(ConditionValidationError, match=expected_fragment):
        parse_condition(document)


def test_rejects_non_json_container_shapes() -> None:
    with pytest.raises(ConditionValidationError, match="expected a condition object"):
        parse_condition([_compare_document()])
    with pytest.raises(ConditionValidationError, match="expected a non-empty JSON array"):
        parse_condition({"type": "all_of", "nodes": (_compare_document(),)})


@pytest.mark.parametrize(
    "document",
    [
        {"type": []},
        {"type": {}},
        {"type": None},
        {"type": True},
        {"type": 1},
        {},
        {"type": "not_a_real_condition"},
        {
            "type": "compare",
            "left": {"type": []},
            "op": "gt",
            "right": {"type": "fixed", "value": "1"},
        },
        {
            "type": "compare",
            "left": {"type": {}},
            "op": "gt",
            "right": {"type": "fixed", "value": "1"},
        },
    ],
)
def test_invalid_node_types_raise_validation_error_without_leaking_type_error(
    document: dict[str, object],
) -> None:
    with pytest.raises(ConditionValidationError):
        parse_condition(document)


def test_depth_limit_is_enforced_during_descent() -> None:
    document: dict[str, object] = _compare_document()
    for _ in range(MAX_DEPTH):
        document = {"type": "negate", "node": document}

    errors = validate_condition(document)

    assert errors
    assert any("depth exceeds" in error for error in errors)


def test_node_limit_is_enforced_during_descent() -> None:
    compare_count = MAX_NODES // 3 + 1
    document = {"type": "all_of", "nodes": [_compare_document() for _ in range(compare_count)]}

    with pytest.raises(ConditionValidationError, match="node count exceeds"):
        parse_condition(document)


def test_direct_boolean_child_limit_rejects_wide_documents_before_iteration() -> None:
    document = {
        "type": "any_of",
        "nodes": [
            {"type": "missing_data", "kpi_code": "sales.net_revenue"}
            for _ in range(MAX_BOOLEAN_CHILDREN + 1)
        ],
    }

    with pytest.raises(ConditionValidationError, match="direct children"):
        parse_condition(document)


@pytest.mark.parametrize(
    "value",
    [
        str(MAX_ABS_NUMBER + 1),
        "NaN",
        "Infinity",
        "0." + ("1" * (MAX_DECIMAL_PLACES + 1)),
        "9" * 65,
    ],
)
def test_fixed_numbers_are_bounded_and_finite(value: str) -> None:
    document = _compare_document()
    cast(dict[str, object], document["right"])["value"] = value

    with pytest.raises(ConditionValidationError, match="bounded finite number"):
        parse_condition(document)


@pytest.mark.parametrize("periods", [1, MAX_PERIODS + 1, True, "7"])
def test_period_operands_reject_out_of_range_or_non_integer_values(periods: object) -> None:
    document = {
        "type": "compare",
        "left": {
            "type": "moving_average",
            "kpi_code": "sales.average_ticket",
            "periods": periods,
        },
        "op": "gt",
        "right": {"type": "fixed", "value": "0"},
    }

    with pytest.raises(ConditionValidationError):
        parse_condition(document)


def test_between_rejects_incoherent_fixed_range() -> None:
    with pytest.raises(ConditionValidationError, match="minimum must not exceed"):
        parse_condition(
            {
                "type": "between",
                "value": {"type": "kpi", "kpi_code": "sales.average_ticket"},
                "minimum": {"type": "fixed", "value": "20"},
                "maximum": {"type": "fixed", "value": "10"},
            }
        )


def test_evaluation_is_deterministic_and_does_not_mutate_measurements() -> None:
    condition = parse_condition(
        {
            "type": "all_of",
            "nodes": [
                _compare_document(),
                {
                    "type": "compare",
                    "left": {
                        "type": "pct_change",
                        "kpi_code": "sales.net_revenue",
                        "baseline": "previous",
                    },
                    "op": "gte",
                    "right": {"type": "fixed", "value": "20"},
                },
                {
                    "type": "compare",
                    "left": {
                        "type": "share",
                        "numerator_kpi": "sales.net_revenue",
                        "denominator_kpi": "sales.gross_revenue",
                    },
                    "op": "gte",
                    "right": {"type": "fixed", "value": "80"},
                },
            ],
        }
    )
    measurements: dict[str, object] = {
        "sales.net_revenue": "120",
        "previous:sales.net_revenue": "100",
        "sales.gross_revenue": "140",
    }
    original = deepcopy(measurements)

    results = [evaluate_predicate(condition, measurements) for _ in range(10)]

    assert results == [True] * 10
    assert measurements == original


def test_missing_measurements_produce_explicit_three_valued_logic() -> None:
    comparison = parse_condition(_compare_document())
    missing = parse_condition({"type": "missing_data", "kpi_code": "sales.net_revenue"})
    all_of = parse_condition(
        {
            "type": "all_of",
            "nodes": [
                _compare_document(),
                {"type": "missing_data", "kpi_code": "inventory.coverage_days"},
            ],
        }
    )
    any_of = parse_condition(
        {
            "type": "any_of",
            "nodes": [
                _compare_document(),
                {"type": "missing_data", "kpi_code": "inventory.coverage_days"},
            ],
        }
    )

    assert evaluate_predicate(comparison, {}) is None
    assert evaluate_predicate(missing, {}) is True
    assert evaluate_predicate(all_of, {}) is None
    assert evaluate_predicate(any_of, {}) is True


def test_persisted_evaluation_requires_complete_ordered_history() -> None:
    condition = parse_condition(
        {"type": "persisted", "predicate": _compare_document(), "periods": 3}
    )

    assert (
        evaluate_predicate(
            condition,
            {
                "history": [
                    {"sales.net_revenue": "110"},
                    {"sales.net_revenue": "120"},
                    {"sales.net_revenue": "130"},
                ]
            },
        )
        is True
    )
    assert (
        evaluate_predicate(
            condition,
            {
                "history": [
                    {"sales.net_revenue": "110"},
                    {},
                    {"sales.net_revenue": "130"},
                ]
            },
        )
        is None
    )
    assert evaluate_predicate(condition, {"history": [{"sales.net_revenue": "110"}]}) is None


def test_injection_strings_are_rejected_or_remain_inert(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    payload = f"__import__('pathlib').Path({str(marker)!r}).write_text('owned')"
    document = _compare_document()
    cast(dict[str, object], document["right"])["value"] = payload

    with pytest.raises(ConditionValidationError):
        parse_condition(document)
    controls = parse_rule_controls({"exceptions": [payload]})

    assert controls.exceptions == (payload,)
    assert not marker.exists()


def test_source_contains_no_dynamic_execution_or_import_primitives() -> None:
    source_path = Path(conditions_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_calls = {"eval", "exec", "compile", "__import__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "import_module"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported_module = (
                node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
            )
            assert imported_module != "importlib"


def test_rule_controls_are_bounded_serializable_and_round_trip() -> None:
    document: dict[str, object] = {
        "cooldown_hours": 24,
        "suppression": ["branch.closed", "data.backfill"],
        "exceptions": ["Ignorar apenas durante inventário físico autorizado."],
        "severity_ladder": [
            {"threshold_pct": "5", "severity": "low"},
            {"threshold_pct": "15", "severity": "medium"},
            {"threshold_pct": "30", "severity": "high"},
        ],
    }

    controls = parse_rule_controls(document)
    serialized = serialize_rule_controls(controls)

    assert serialize_rule_controls(parse_rule_controls(serialized)) == serialized


@pytest.mark.parametrize(
    "document, fragment",
    [
        ({"cooldown_hours": 0}, "between"),
        ({"unknown": True}, "unknown fields"),
        ({"suppression": ["x"] * 2}, "duplicate value"),
        ({"suppression": ["x" * (MAX_CODE_LENGTH + 1)]}, "exceeds"),
        ({"exceptions": ["x"] * (MAX_CONTROL_ITEMS + 1)}, "maximum"),
        (
            {
                "severity_ladder": [
                    {"threshold_pct": "10", "severity": "high"},
                    {"threshold_pct": "5", "severity": "critical"},
                ]
            },
            "strictly ascending",
        ),
        (
            {
                "severity_ladder": [
                    {"threshold_pct": "5", "severity": "high"},
                    {"threshold_pct": "10", "severity": "medium"},
                ]
            },
            "severity must strictly increase",
        ),
    ],
)
def test_rule_controls_reject_invalid_fields_lists_ranges_and_ladders(
    document: dict[str, object], fragment: str
) -> None:
    with pytest.raises(ConditionValidationError, match=fragment):
        parse_rule_controls(document)


def test_action_catalog_codes_domains_priorities_deadlines_and_kpis_are_integral() -> None:
    assert validate_action_catalog(ACTION_CATALOG) == ()
    assert len(ACTION_BY_CODE) == len(ACTION_CATALOG)
    assert {action.domain for action in ACTION_CATALOG} == set(ACTION_DOMAINS)

    for action in ACTION_CATALOG:
        assert ACTION_BY_CODE[action.code] is action
        assert action.default_priority in ACTION_PRIORITIES
        assert action.status in ACTION_STATUSES
        assert action.suggested_role in SUGGESTED_ROLES
        assert MIN_DEADLINE_DAYS <= action.suggested_deadline_days <= MAX_DEADLINE_DAYS
        assert action.tracking_kpi is None or action.tracking_kpi in KPI_BY_CODE
        assert action.success_criteria
        assert action.closure_criteria
        assert action.steps


def test_action_catalog_is_advisory_only_and_financially_non_automatic() -> None:
    for action in ACTION_CATALOG:
        assert action.execution_mode == "human_review_required"
        assert action.allows_automatic_financial_execution is False
        assert action.safety_constraints == ACTION_SAFETY_CONSTRAINTS


def test_action_serialization_is_stable_and_json_compatible() -> None:
    first = [action.as_dict() for action in ACTION_CATALOG]
    second = [action.as_dict() for action in ACTION_CATALOG]

    assert first == second
    assert json.dumps(first, ensure_ascii=False, separators=(",", ":")) == json.dumps(
        second, ensure_ascii=False, separators=(",", ":")
    )


def test_action_definitions_and_index_are_immutable() -> None:
    action = ACTION_CATALOG[0]
    with pytest.raises(FrozenInstanceError):
        action.title = "mutated"  # type: ignore[misc]

    mutable_view = cast(dict[str, ActionDefinition], ACTION_BY_CODE)
    with pytest.raises(TypeError):
        mutable_view["inventory.injected"] = action


def test_action_catalog_validator_detects_duplicate_and_unknown_kpi() -> None:
    original = ACTION_CATALOG[0]
    duplicate = replace(ACTION_CATALOG[1], code=original.code, domain=original.domain)
    unknown_kpi = replace(ACTION_CATALOG[2], tracking_kpi="inventory.not_real")

    errors = validate_action_catalog((original, duplicate, unknown_kpi))

    assert any("duplicate code" in error for error in errors)
    assert any("unknown KPI" in error for error in errors)
    assert any("every diagnostic domain" in error for error in errors)
