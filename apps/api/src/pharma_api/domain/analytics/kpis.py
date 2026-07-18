from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

KpiCategory = Literal["sales", "inventory", "purchases", "suppliers", "margin", "operations"]
Direction = Literal["increase", "decrease", "target", "informational"]
FormulaOperation = Literal["value", "sum", "difference", "ratio", "product"]

ALL_DIMENSIONS = (
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
)

FILTERS = (
    "from",
    "to",
    "economic_group_id",
    "company_id",
    "branch_id",
    "product_id",
    "category_id",
    "brand_id",
    "supplier_id",
    "channel",
)


@dataclass(frozen=True, slots=True)
class Formula:
    """Small, closed calculation AST. It cannot contain SQL or user code."""

    operation: FormulaOperation
    operands: tuple[str, ...]
    scale: Decimal = Decimal("1")

    def as_json(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "operands": list(self.operands),
            "scale": str(self.scale),
        }


@dataclass(frozen=True, slots=True)
class KpiDefinition:
    code: str
    name: str
    description: str
    category: KpiCategory
    objective: str
    formula: Formula
    unit: str
    desirable_direction: Direction
    grain: str
    dimensions: tuple[str, ...]
    filters: tuple[str, ...]
    required_fields: tuple[str, ...]
    data_source: str
    periodicity: str
    version: int
    owner: str
    status: Literal["operational"]
    null_rule: str
    zero_division_rule: str
    rounding_rule: str
    comparison_rule: str
    dependencies: tuple[str, ...]
    limitations: tuple[str, ...]
    interpretation: str
    impact: str
    drill_down: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["formula"] = self.formula.as_json()
        return payload


@dataclass(frozen=True, slots=True)
class UnavailableKpi:
    code: str
    name: str
    category: str
    required_data: tuple[str, ...]
    reason: str
    status: Literal["unavailable"] = "unavailable"


def value(measure: str) -> Formula:
    return Formula("value", (measure,))


def ratio(numerator: str, denominator: str, scale: str = "1") -> Formula:
    return Formula("ratio", (numerator, denominator), Decimal(scale))


def difference(left: str, right: str) -> Formula:
    return Formula("difference", (left, right))


def product(left: str, right: str) -> Formula:
    return Formula("product", (left, right))


def evaluate_formula(
    formula: Formula, measures: Mapping[str, Decimal | int | float | None]
) -> Decimal | None:
    def operand_value(key: str) -> Decimal:
        # Numeric literals are valid operands in this closed AST, but arbitrary
        # expressions remain impossible.
        try:
            return Decimal(key)
        except ArithmeticError:
            return Decimal(str(measures.get(key) or 0))

    values = [operand_value(key) for key in formula.operands]
    if formula.operation == "value":
        result = values[0]
    elif formula.operation == "sum":
        result = sum(values, Decimal(0))
    elif formula.operation == "difference":
        result = values[0] - values[1]
    elif formula.operation == "product":
        result = values[0] * values[1]
    else:
        if values[1] == 0:
            return None
        result = values[0] / values[1]
    return (result * formula.scale).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _definition(
    code: str,
    name: str,
    category: KpiCategory,
    unit: str,
    direction: Direction,
    formula: Formula,
    dimensions: tuple[str, ...] = ALL_DIMENSIONS,
    *,
    description: str | None = None,
    limitations: tuple[str, ...] = (),
) -> KpiDefinition:
    return KpiDefinition(
        code=code,
        name=name,
        description=description
        or f"Mede {name.casefold()} a partir dos fatos canônicos autorizados.",
        category=category,
        objective=f"Acompanhar {name.casefold()} com rastreabilidade até a origem.",
        formula=formula,
        unit=unit,
        desirable_direction=direction,
        grain="day",
        dimensions=dimensions,
        filters=FILTERS,
        required_fields=tuple(
            operand for operand in formula.operands if not operand.replace(".", "", 1).isdigit()
        ),
        data_source="canonical-platform-v2b",
        periodicity="incremental_after_import",
        version=1,
        owner="analytics-engineering",
        status="operational",
        null_rule=(
            "missing measures are treated as zero; an empty result set is identified separately"
        ),
        zero_division_rule="return null and reason=zero_denominator",
        rounding_rule=(
            "ROUND_HALF_UP to four decimal places; presentation applies the unit precision"
        ),
        comparison_rule=(
            "absolute and percentage variation against prior period, prior year, "
            "target or moving average"
        ),
        dependencies=formula.operands,
        limitations=limitations,
        interpretation=(
            f"Use a série e o drill-down para interpretar {name.casefold()} no escopo selecionado."
        ),
        impact=f"Orienta decisões relacionadas a {category} sem extrapolar os dados observados.",
        drill_down="canonical records and analytical lineage constrained by the caller grant",
    )


_ROWS: tuple[tuple[str, str, KpiCategory, str, Direction, Formula], ...] = (
    # Sales (25)
    ("sales.gross_revenue", "Receita bruta", "sales", "BRL", "increase", value("gross_revenue")),
    ("sales.net_revenue", "Receita líquida", "sales", "BRL", "increase", value("net_revenue")),
    (
        "sales.completed_count",
        "Vendas concluídas",
        "sales",
        "count",
        "increase",
        value("completed_sales"),
    ),
    ("sales.units_sold", "Unidades vendidas", "sales", "unit", "increase", value("units_sold")),
    (
        "sales.average_ticket",
        "Ticket médio",
        "sales",
        "BRL",
        "increase",
        ratio("net_revenue", "completed_sales"),
    ),
    (
        "sales.items_per_sale",
        "Itens por venda",
        "sales",
        "ratio",
        "increase",
        ratio("item_count", "completed_sales"),
    ),
    (
        "sales.average_unit_price",
        "Preço médio por unidade",
        "sales",
        "BRL",
        "target",
        ratio("net_revenue", "units_sold"),
    ),
    (
        "sales.average_discount",
        "Desconto médio",
        "sales",
        "BRL",
        "decrease",
        ratio("discount_amount", "completed_sales"),
    ),
    (
        "sales.discount_rate",
        "Taxa de desconto",
        "sales",
        "percent",
        "decrease",
        ratio("discount_amount", "gross_revenue", "100"),
    ),
    (
        "sales.cancellation_rate",
        "Taxa de cancelamento",
        "sales",
        "percent",
        "decrease",
        ratio("cancelled_sales", "sale_count", "100"),
    ),
    (
        "sales.return_rate",
        "Taxa de devolução",
        "sales",
        "percent",
        "decrease",
        ratio("return_amount", "gross_revenue", "100"),
    ),
    (
        "sales.return_count",
        "Quantidade de devoluções",
        "sales",
        "count",
        "decrease",
        value("return_count"),
    ),
    (
        "sales.discounted_sales_rate",
        "Vendas com desconto",
        "sales",
        "percent",
        "target",
        ratio("discounted_sales", "completed_sales", "100"),
    ),
    (
        "sales.tax_value",
        "Tributos sobre vendas",
        "sales",
        "BRL",
        "informational",
        value("sales_tax"),
    ),
    (
        "sales.tax_rate",
        "Carga tributária sobre vendas",
        "sales",
        "percent",
        "informational",
        ratio("sales_tax", "gross_revenue", "100"),
    ),
    (
        "sales.channel_share",
        "Participação por canal",
        "sales",
        "percent",
        "target",
        ratio("scoped_net_revenue", "network_net_revenue", "100"),
    ),
    (
        "sales.category_share",
        "Participação por categoria",
        "sales",
        "percent",
        "target",
        ratio("scoped_net_revenue", "network_net_revenue", "100"),
    ),
    (
        "sales.product_share",
        "Participação por produto",
        "sales",
        "percent",
        "target",
        ratio("scoped_net_revenue", "network_net_revenue", "100"),
    ),
    (
        "sales.branch_share",
        "Participação por filial",
        "sales",
        "percent",
        "target",
        ratio("scoped_net_revenue", "network_net_revenue", "100"),
    ),
    (
        "sales.top10_concentration",
        "Concentração das 10 maiores vendas",
        "sales",
        "percent",
        "decrease",
        ratio("top10_revenue", "net_revenue", "100"),
    ),
    (
        "sales.active_product_count",
        "Produtos vendidos",
        "sales",
        "count",
        "increase",
        value("sold_product_count"),
    ),
    (
        "sales.revenue_per_product",
        "Receita por produto vendido",
        "sales",
        "BRL",
        "increase",
        ratio("net_revenue", "sold_product_count"),
    ),
    (
        "sales.hourly_average",
        "Venda média por hora",
        "sales",
        "BRL",
        "increase",
        ratio("net_revenue", "active_hours"),
    ),
    (
        "sales.daily_average",
        "Venda média diária",
        "sales",
        "BRL",
        "increase",
        ratio("net_revenue", "active_days"),
    ),
    (
        "sales.payment_per_sale",
        "Pagamentos por venda",
        "sales",
        "ratio",
        "target",
        ratio("payment_count", "completed_sales"),
    ),
    # Inventory (24)
    (
        "inventory.on_hand",
        "Estoque físico",
        "inventory",
        "unit",
        "target",
        value("inventory_on_hand"),
    ),
    (
        "inventory.available",
        "Estoque disponível",
        "inventory",
        "unit",
        "target",
        value("inventory_available"),
    ),
    (
        "inventory.reserved",
        "Estoque reservado",
        "inventory",
        "unit",
        "decrease",
        value("inventory_reserved"),
    ),
    (
        "inventory.in_transit",
        "Estoque em trânsito",
        "inventory",
        "unit",
        "informational",
        value("inventory_in_transit"),
    ),
    (
        "inventory.value_retail",
        "Valor do estoque a preço",
        "inventory",
        "BRL",
        "target",
        value("inventory_retail_value"),
    ),
    (
        "inventory.value_cost",
        "Capital em estoque",
        "inventory",
        "BRL",
        "decrease",
        value("inventory_cost_value"),
    ),
    (
        "inventory.coverage_days",
        "Cobertura em dias",
        "inventory",
        "day",
        "target",
        ratio("inventory_available", "average_daily_units"),
    ),
    (
        "inventory.turnover",
        "Giro de estoque",
        "inventory",
        "ratio",
        "increase",
        ratio("cogs", "average_inventory_cost"),
    ),
    (
        "inventory.sell_through",
        "Sell-through",
        "inventory",
        "percent",
        "increase",
        ratio("units_sold", "units_available_for_sale", "100"),
    ),
    (
        "inventory.zero_stock_rate",
        "Ruptura observada",
        "inventory",
        "percent",
        "decrease",
        ratio("zero_stock_products", "active_products", "100"),
    ),
    (
        "inventory.stockout_risk_rate",
        "Risco de ruptura",
        "inventory",
        "percent",
        "decrease",
        ratio("low_cover_products", "active_products", "100"),
    ),
    (
        "inventory.negative_stock_count",
        "Itens com estoque negativo",
        "inventory",
        "count",
        "decrease",
        value("negative_stock_products"),
    ),
    (
        "inventory.negative_stock_rate",
        "Taxa de estoque negativo",
        "inventory",
        "percent",
        "decrease",
        ratio("negative_stock_products", "active_products", "100"),
    ),
    (
        "inventory.excess_count",
        "Produtos em excesso",
        "inventory",
        "count",
        "decrease",
        value("excess_stock_products"),
    ),
    (
        "inventory.slow_moving_count",
        "Produtos parados",
        "inventory",
        "count",
        "decrease",
        value("slow_moving_products"),
    ),
    (
        "inventory.no_sale_count",
        "Estoque sem venda",
        "inventory",
        "count",
        "decrease",
        value("no_sale_products"),
    ),
    (
        "inventory.adjustment_quantity",
        "Ajustes de estoque",
        "inventory",
        "unit",
        "decrease",
        value("stock_adjustment_quantity"),
    ),
    (
        "inventory.loss_quantity",
        "Perdas de estoque",
        "inventory",
        "unit",
        "decrease",
        value("stock_loss_quantity"),
    ),
    (
        "inventory.damage_quantity",
        "Avarias",
        "inventory",
        "unit",
        "decrease",
        value("stock_damage_quantity"),
    ),
    (
        "inventory.expiring_lots",
        "Lotes próximos da validade",
        "inventory",
        "count",
        "decrease",
        value("expiring_lots"),
    ),
    (
        "inventory.expired_lots",
        "Lotes vencidos",
        "inventory",
        "count",
        "decrease",
        value("expired_lots"),
    ),
    (
        "inventory.movement_count",
        "Movimentações de estoque",
        "inventory",
        "count",
        "informational",
        value("stock_movement_count"),
    ),
    (
        "inventory.abc_capital_share",
        "Participação de capital na curva ABC",
        "inventory",
        "percent",
        "target",
        ratio("scoped_inventory_value", "inventory_cost_value", "100"),
    ),
    (
        "inventory.xyz_variability",
        "Variabilidade da curva XYZ",
        "inventory",
        "percent",
        "decrease",
        ratio("demand_stddev", "average_daily_units", "100"),
    ),
    # Purchases (20)
    (
        "purchases.net_value",
        "Valor comprado",
        "purchases",
        "BRL",
        "target",
        value("purchase_value"),
    ),
    (
        "purchases.quantity",
        "Quantidade comprada",
        "purchases",
        "unit",
        "target",
        value("purchase_quantity"),
    ),
    (
        "purchases.order_count",
        "Pedidos de compra",
        "purchases",
        "count",
        "informational",
        value("purchase_count"),
    ),
    (
        "purchases.average_order",
        "Compra média",
        "purchases",
        "BRL",
        "target",
        ratio("purchase_value", "purchase_count"),
    ),
    (
        "purchases.average_unit_cost",
        "Custo médio comprado",
        "purchases",
        "BRL",
        "decrease",
        ratio("purchase_value", "purchase_quantity"),
    ),
    (
        "purchases.discount_value",
        "Desconto em compras",
        "purchases",
        "BRL",
        "increase",
        value("purchase_discount"),
    ),
    (
        "purchases.discount_rate",
        "Taxa de desconto em compras",
        "purchases",
        "percent",
        "increase",
        ratio("purchase_discount", "purchase_merchandise", "100"),
    ),
    (
        "purchases.bonus_value",
        "Bonificações",
        "purchases",
        "BRL",
        "increase",
        value("purchase_bonus"),
    ),
    (
        "purchases.freight_value",
        "Fretes",
        "purchases",
        "BRL",
        "decrease",
        value("purchase_freight"),
    ),
    (
        "purchases.freight_rate",
        "Frete sobre compras",
        "purchases",
        "percent",
        "decrease",
        ratio("purchase_freight", "purchase_value", "100"),
    ),
    (
        "purchases.tax_value",
        "Tributos sobre compras",
        "purchases",
        "BRL",
        "informational",
        value("purchase_tax"),
    ),
    (
        "purchases.cancellation_rate",
        "Cancelamento de compras",
        "purchases",
        "percent",
        "decrease",
        ratio("cancelled_purchases", "purchase_count", "100"),
    ),
    (
        "purchases.return_rate",
        "Devolução de compras",
        "purchases",
        "percent",
        "decrease",
        ratio("returned_purchase_value", "purchase_value", "100"),
    ),
    (
        "purchases.receipt_rate",
        "Pedidos recebidos",
        "purchases",
        "percent",
        "increase",
        ratio("received_purchase_count", "purchase_count", "100"),
    ),
    (
        "purchases.received_value",
        "Valor recebido",
        "purchases",
        "BRL",
        "increase",
        value("received_purchase_value"),
    ),
    (
        "purchases.receipt_fill_rate",
        "Atendimento de quantidade comprada",
        "purchases",
        "percent",
        "increase",
        ratio("received_purchase_quantity", "purchase_quantity", "100"),
    ),
    (
        "purchases.frequency",
        "Frequência de compra",
        "purchases",
        "order/day",
        "target",
        ratio("purchase_count", "active_days"),
    ),
    (
        "purchases.multiple_adherence",
        "Aderência ao múltiplo de compra",
        "purchases",
        "percent",
        "increase",
        ratio("multiple_adherent_lines", "purchase_line_count", "100"),
    ),
    (
        "purchases.emergency_rate",
        "Compras emergenciais",
        "purchases",
        "percent",
        "decrease",
        ratio("emergency_purchase_count", "purchase_count", "100"),
    ),
    (
        "purchases.post_purchase_coverage",
        "Cobertura após compra",
        "purchases",
        "day",
        "target",
        ratio("inventory_available", "average_daily_units"),
    ),
    # Suppliers (15)
    (
        "suppliers.active_count",
        "Fornecedores ativos",
        "suppliers",
        "count",
        "target",
        value("active_supplier_count"),
    ),
    (
        "suppliers.supply_share",
        "Participação no abastecimento",
        "suppliers",
        "percent",
        "target",
        ratio("scoped_purchase_value", "purchase_value", "100"),
    ),
    (
        "suppliers.average_lead_time",
        "Lead time médio",
        "suppliers",
        "day",
        "decrease",
        ratio("lead_time_days_total", "receipt_count"),
    ),
    (
        "suppliers.on_time_rate",
        "Pontualidade",
        "suppliers",
        "percent",
        "increase",
        ratio("on_time_receipts", "receipt_count", "100"),
    ),
    (
        "suppliers.fill_rate",
        "Taxa de atendimento",
        "suppliers",
        "percent",
        "increase",
        ratio("received_purchase_quantity", "purchase_quantity", "100"),
    ),
    (
        "suppliers.cost_variation",
        "Variação de custo do fornecedor",
        "suppliers",
        "percent",
        "decrease",
        ratio("cost_change_value", "previous_cost_value", "100"),
    ),
    (
        "suppliers.purchase_frequency",
        "Frequência por fornecedor",
        "suppliers",
        "order/day",
        "target",
        ratio("scoped_purchase_count", "active_days"),
    ),
    (
        "suppliers.return_rate",
        "Devoluções ao fornecedor",
        "suppliers",
        "percent",
        "decrease",
        ratio("returned_purchase_value", "purchase_value", "100"),
    ),
    (
        "suppliers.quality_score",
        "Qualidade do fornecimento",
        "suppliers",
        "percent",
        "increase",
        ratio("supplier_passed_lines", "purchase_line_count", "100"),
    ),
    (
        "suppliers.failure_rate",
        "Falhas de fornecimento",
        "suppliers",
        "percent",
        "decrease",
        ratio("supplier_failed_lines", "purchase_line_count", "100"),
    ),
    (
        "suppliers.stockout_association",
        "Ruptura associada ao fornecedor",
        "suppliers",
        "percent",
        "decrease",
        ratio("supplier_stockout_products", "supplier_product_count", "100"),
    ),
    (
        "suppliers.top5_concentration",
        "Concentração nos cinco fornecedores",
        "suppliers",
        "percent",
        "decrease",
        ratio("top5_supplier_value", "purchase_value", "100"),
    ),
    (
        "suppliers.dependency",
        "Dependência do principal fornecedor",
        "suppliers",
        "percent",
        "decrease",
        ratio("top_supplier_value", "purchase_value", "100"),
    ),
    (
        "suppliers.product_coverage",
        "Produtos cobertos por fornecedor",
        "suppliers",
        "ratio",
        "increase",
        ratio("supplier_product_count", "active_supplier_count"),
    ),
    (
        "suppliers.average_minimum_order",
        "Pedido mínimo médio",
        "suppliers",
        "unit",
        "decrease",
        ratio("minimum_order_total", "supplier_product_count"),
    ),
    # Margin and pricing (20)
    ("margin.cogs", "CMV", "margin", "BRL", "decrease", value("cogs")),
    (
        "margin.gross_profit",
        "Lucro bruto",
        "margin",
        "BRL",
        "increase",
        difference("net_revenue", "cogs"),
    ),
    (
        "margin.gross_percent",
        "Margem bruta percentual",
        "margin",
        "percent",
        "increase",
        ratio("gross_profit", "net_revenue", "100"),
    ),
    (
        "margin.markup",
        "Markup",
        "margin",
        "percent",
        "increase",
        ratio("gross_profit", "cogs", "100"),
    ),
    (
        "margin.markdown",
        "Markdown",
        "margin",
        "percent",
        "decrease",
        ratio("discount_amount", "gross_revenue", "100"),
    ),
    (
        "margin.discount_on_price",
        "Desconto sobre preço",
        "margin",
        "percent",
        "decrease",
        ratio("discount_amount", "gross_revenue", "100"),
    ),
    (
        "margin.profit_per_unit",
        "Lucro bruto por unidade",
        "margin",
        "BRL",
        "increase",
        ratio("gross_profit", "units_sold"),
    ),
    (
        "margin.profit_per_sale",
        "Lucro bruto por venda",
        "margin",
        "BRL",
        "increase",
        ratio("gross_profit", "completed_sales"),
    ),
    (
        "margin.gmroi",
        "GMROI",
        "margin",
        "ratio",
        "increase",
        ratio("gross_profit", "average_inventory_cost"),
    ),
    (
        "margin.inventory_return",
        "Retorno sobre estoque",
        "margin",
        "percent",
        "increase",
        ratio("gross_profit", "inventory_cost_value", "100"),
    ),
    (
        "margin.margin_loss",
        "Perda de margem por desconto",
        "margin",
        "BRL",
        "decrease",
        value("discount_amount"),
    ),
    (
        "margin.price_dispersion",
        "Dispersão de preços",
        "margin",
        "percent",
        "decrease",
        ratio("price_stddev", "average_price", "100"),
    ),
    (
        "margin.price_variation",
        "Variação de preço",
        "margin",
        "percent",
        "target",
        ratio("price_change_value", "previous_price_value", "100"),
    ),
    (
        "margin.weighted_price",
        "Preço médio ponderado",
        "margin",
        "BRL",
        "target",
        ratio("gross_revenue", "units_sold"),
    ),
    (
        "margin.revenue_retention",
        "Retenção de receita após descontos",
        "margin",
        "percent",
        "increase",
        ratio("net_revenue", "gross_revenue", "100"),
    ),
    (
        "margin.cost_to_revenue",
        "CMV sobre receita",
        "margin",
        "percent",
        "decrease",
        ratio("cogs", "net_revenue", "100"),
    ),
    (
        "margin.product_contribution",
        "Contribuição por produto",
        "margin",
        "BRL",
        "increase",
        value("scoped_gross_profit"),
    ),
    (
        "margin.category_contribution",
        "Contribuição por categoria",
        "margin",
        "BRL",
        "increase",
        value("scoped_gross_profit"),
    ),
    (
        "margin.branch_contribution",
        "Contribuição por filial",
        "margin",
        "BRL",
        "increase",
        value("scoped_gross_profit"),
    ),
    (
        "margin.negative_margin_rate",
        "Produtos com margem negativa",
        "margin",
        "percent",
        "decrease",
        ratio("negative_margin_products", "sold_product_count", "100"),
    ),
    # Operations and quality (16)
    (
        "operations.data_freshness",
        "Freshness analítica",
        "operations",
        "second",
        "decrease",
        value("freshness_seconds"),
    ),
    (
        "operations.source_lag",
        "Atraso da fonte",
        "operations",
        "second",
        "decrease",
        value("source_lag_seconds"),
    ),
    (
        "operations.completeness",
        "Completude",
        "operations",
        "percent",
        "increase",
        ratio("valid_records", "received_records", "100"),
    ),
    (
        "operations.rejection_rate",
        "Taxa de rejeição",
        "operations",
        "percent",
        "decrease",
        ratio("rejected_records", "received_records", "100"),
    ),
    (
        "operations.duplicate_rate",
        "Taxa de duplicidade",
        "operations",
        "percent",
        "decrease",
        ratio("duplicate_records", "received_records", "100"),
    ),
    (
        "operations.consistency",
        "Consistência",
        "operations",
        "percent",
        "increase",
        ratio("quality_passed_records", "quality_evaluated_records", "100"),
    ),
    (
        "operations.processed_volume",
        "Volume processado",
        "operations",
        "record",
        "increase",
        value("received_records"),
    ),
    (
        "operations.ingestion_duration",
        "Tempo de ingestão",
        "operations",
        "second",
        "decrease",
        value("processing_seconds"),
    ),
    (
        "operations.throughput",
        "Vazão da ingestão",
        "operations",
        "record/second",
        "increase",
        ratio("received_records", "processing_seconds"),
    ),
    (
        "operations.integration_availability",
        "Disponibilidade da integração",
        "operations",
        "percent",
        "increase",
        ratio("successful_batches", "batch_count", "100"),
    ),
    (
        "operations.failed_batches",
        "Importações com falha",
        "operations",
        "count",
        "decrease",
        value("failed_batches"),
    ),
    (
        "operations.quality_incidents",
        "Incidentes de qualidade",
        "operations",
        "count",
        "decrease",
        value("quality_incidents"),
    ),
    (
        "operations.analytics_duration",
        "Tempo de atualização analítica",
        "operations",
        "second",
        "decrease",
        value("analytics_processing_seconds"),
    ),
    (
        "operations.cache_hit_rate",
        "Cache hit rate",
        "operations",
        "percent",
        "increase",
        ratio("cache_hits", "cache_requests", "100"),
    ),
    (
        "operations.backfill_count",
        "Backfills executados",
        "operations",
        "count",
        "informational",
        value("backfill_count"),
    ),
    (
        "operations.recomputation_count",
        "Recomputações executadas",
        "operations",
        "count",
        "informational",
        value("recomputation_count"),
    ),
)

KPI_CATALOG: tuple[KpiDefinition, ...] = tuple(_definition(*row) for row in _ROWS)
KPI_BY_CODE = {definition.code: definition for definition in KPI_CATALOG}

if len(KPI_BY_CODE) != len(KPI_CATALOG):
    raise RuntimeError("KPI codes must be unique")
if len(KPI_CATALOG) < 100:
    raise RuntimeError("The operational KPI catalog must contain at least 100 entries")

UNAVAILABLE_KPIS: tuple[UnavailableKpi, ...] = (
    UnavailableKpi(
        "margin.contribution_per_square_meter",
        "Contribuição por metro quadrado",
        "margin",
        ("store_area_square_meters",),
        "O cadastro canônico não possui área física da filial.",
    ),
    UnavailableKpi(
        "purchases.realized_vs_planned",
        "Realizado versus planejado",
        "purchases",
        ("approved_purchase_plan",),
        "Ainda não existe fonte canônica de planejamento de compras.",
    ),
    UnavailableKpi(
        "inventory.forecast_accuracy",
        "Acurácia da previsão",
        "inventory",
        ("forecast_series",),
        "Previsões por ML pertencem a uma etapa futura.",
    ),
)
