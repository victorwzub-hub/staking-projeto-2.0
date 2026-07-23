"""Public governed diagnostic rule catalog."""

from pharma_api.domain.diagnostics.rules.catalog import (
    RULE_BY_CODE,
    RULE_CATALOG,
    RULE_CATALOG_HASH,
    RULE_CATALOG_MANIFEST,
    RULE_COUNT,
)
from pharma_api.domain.diagnostics.rules.definitions import (
    GovernedRuleDefinition,
    deterministic_rule_id,
)
from pharma_api.domain.diagnostics.rules.inventory import INVENTORY_RULES
from pharma_api.domain.diagnostics.rules.margin import MARGIN_RULES
from pharma_api.domain.diagnostics.rules.operations import OPERATIONS_RULES
from pharma_api.domain.diagnostics.rules.purchases import PURCHASES_RULES
from pharma_api.domain.diagnostics.rules.sales import SALES_RULES
from pharma_api.domain.diagnostics.rules.suppliers import SUPPLIERS_RULES
from pharma_api.domain.diagnostics.rules.validation import (
    RuleCatalogValidationError,
    catalog_hash,
    catalog_manifest,
    rule_validation_errors,
    validate_catalog,
    validate_rule,
)

__all__ = [
    "INVENTORY_RULES",
    "MARGIN_RULES",
    "OPERATIONS_RULES",
    "PURCHASES_RULES",
    "RULE_BY_CODE",
    "RULE_CATALOG",
    "RULE_CATALOG_HASH",
    "RULE_CATALOG_MANIFEST",
    "RULE_COUNT",
    "SALES_RULES",
    "SUPPLIERS_RULES",
    "GovernedRuleDefinition",
    "RuleCatalogValidationError",
    "catalog_hash",
    "catalog_manifest",
    "deterministic_rule_id",
    "rule_validation_errors",
    "validate_catalog",
    "validate_rule",
]
