"""Immutable governed catalog assembled from domain-specific rule slices."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pharma_api.domain.diagnostics.rules.definitions import GovernedRuleDefinition
from pharma_api.domain.diagnostics.rules.inventory import INVENTORY_RULES
from pharma_api.domain.diagnostics.rules.validation import (
    catalog_hash,
    catalog_manifest,
    read_only_rule_index,
    validate_catalog,
)

RULE_CATALOG: tuple[GovernedRuleDefinition, ...] = tuple(
    sorted(INVENTORY_RULES, key=lambda rule: rule.code)
)
validate_catalog(RULE_CATALOG)

RULE_BY_CODE: MappingProxyType[str, GovernedRuleDefinition] = read_only_rule_index(RULE_CATALOG)
RULE_CATALOG_MANIFEST: tuple[Mapping[str, object], ...] = catalog_manifest(RULE_CATALOG)
RULE_CATALOG_HASH: str = catalog_hash(RULE_CATALOG)
RULE_COUNT: int = len(RULE_CATALOG)
