"""First production slice of governed deterministic inventory rules."""

from __future__ import annotations

from decimal import Decimal

from pharma_api.domain.diagnostics.actions import ACTION_BY_CODE
from pharma_api.domain.diagnostics.conditions import (
    AllOf,
    CategoryAverage,
    Compare,
    Condition,
    Fixed,
    Kpi,
    NetworkAverage,
    PctChange,
    Persisted,
    Severity,
)
from pharma_api.domain.diagnostics.engine_contracts import (
    ActionReference,
    EvidenceDirection,
    EvidenceSpec,
    EvidenceType,
    HypothesisSpec,
)
from pharma_api.domain.diagnostics.rules.definitions import GovernedRuleDefinition

_OWNER = "inventory-operations"
_COMMON_LIMITATIONS = (
    "The rule reports an observed analytical signal and does not prove root cause.",
    "Any operational or financial intervention requires authorized human review.",
)


def _action(code: str, rationale: str) -> ActionReference:
    definition = ACTION_BY_CODE[code]
    return ActionReference(
        action_code=definition.code,
        action_version=definition.version,
        rationale=rationale,
        suggested_priority=definition.default_priority,
    )


def _evidence(
    *,
    code: str,
    kpi: str,
    evidence_type: EvidenceType,
    direction: EvidenceDirection,
    detail: str,
    reference_key: str | None = None,
) -> EvidenceSpec:
    return EvidenceSpec(
        evidence_code=code,
        evidence_type=evidence_type,
        kpi_code=kpi,
        observation_key=kpi,
        reference_key=reference_key,
        direction=direction,
        relation="supports",
        weight=Decimal("1"),
        detail=detail,
    )


def _hypothesis(code: str, evidence_code: str, explanation: str) -> HypothesisSpec:
    return HypothesisSpec(
        hypothesis_code=code,
        explanation=explanation,
        supporting_evidence_codes=(evidence_code,),
        logic_version="inventory-v1",
        minimum_support=Decimal("0.5000"),
    )


def _rule(
    *,
    code: str,
    title: str,
    objective: str,
    summary: str,
    severity: Severity,
    primary_kpi: str,
    condition: Condition,
    action_code: str,
    action_rationale: str,
    evidence_code: str,
    evidence_type: EvidenceType,
    evidence_direction: EvidenceDirection,
    evidence_detail: str,
    hypothesis_code: str,
    hypothesis: str,
    expected_impact: str,
    dimensions: tuple[str, ...] = ("branch", "product"),
    evaluation_window: str = "current analytical period",
    reference_key: str | None = None,
    limitations: tuple[str, ...] = _COMMON_LIMITATIONS,
) -> GovernedRuleDefinition:
    return GovernedRuleDefinition(
        code=code,
        version=1,
        title=title,
        objective=objective,
        summary=summary,
        domain="inventory",
        base_severity=severity,
        primary_kpi_code=primary_kpi,
        condition=condition,
        actions=(_action(action_code, action_rationale),),
        evidence=(
            _evidence(
                code=evidence_code,
                kpi=primary_kpi,
                evidence_type=evidence_type,
                direction=evidence_direction,
                detail=evidence_detail,
                reference_key=reference_key,
            ),
        ),
        hypotheses=(_hypothesis(hypothesis_code, evidence_code, hypothesis),),
        dimensions=dimensions,
        evaluation_window=evaluation_window,
        expected_impact=expected_impact,
        limitations=limitations,
        owner=_OWNER,
        change_note="Initial governed inventory production rule.",
    )


INVENTORY_RULES: tuple[GovernedRuleDefinition, ...] = tuple(
    sorted(
        (
            _rule(
                code="inventory.excess_products",
                title="Produtos com estoque excedente",
                objective="Detectar produtos já classificados pelo analytics como excesso.",
                summary="Existe ao menos um produto com estoque excedente no escopo avaliado.",
                severity="medium",
                primary_kpi="inventory.excess_count",
                condition=Compare(Kpi("inventory.excess_count"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.branch_transfer",
                action_rationale=(
                    "Revisar transferências internas antes de qualquer nova compra ou baixa."
                ),
                evidence_code="inventory.excess_products_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Quantidade observada de produtos classificados como excesso.",
                hypothesis_code="inventory.excess_allocation",
                hypothesis=(
                    "A distribuição entre filiais ou a demanda local pode explicar "
                    "parte do excesso."
                ),
                expected_impact="Reduzir capital imobilizado sem automatizar movimentações.",
            ),
            _rule(
                code="inventory.expired_lots",
                title="Lotes vencidos com saldo",
                objective="Detectar lotes vencidos que ainda possuem quantidade positiva.",
                summary="Há lote vencido com saldo no escopo avaliado.",
                severity="critical",
                primary_kpi="inventory.expired_lots",
                condition=Compare(Kpi("inventory.expired_lots"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.expiring_quarantine",
                action_rationale=(
                    "Submeter imediatamente os lotes vencidos à quarentena e destinação autorizada."
                ),
                evidence_code="inventory.expired_lots_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Contagem de lotes vencidos com quantidade positiva.",
                hypothesis_code="inventory.expiry_process_failure",
                hypothesis=(
                    "Falha de segregação, baixa ou sincronização pode ter mantido "
                    "lotes vencidos ativos."
                ),
                expected_impact=(
                    "Eliminar exposição sanitária observada com revisão humana obrigatória."
                ),
            ),
            _rule(
                code="inventory.expiring_lots",
                title="Lotes próximos do vencimento",
                objective="Detectar lotes com saldo dentro da janela analítica de 30 dias.",
                summary="Há lote com saldo próximo do vencimento no escopo avaliado.",
                severity="high",
                primary_kpi="inventory.expiring_lots",
                condition=Compare(Kpi("inventory.expiring_lots"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.expiring_quarantine",
                action_rationale=(
                    "Revisar segregação, remanejamento e destinação sem execução automática."
                ),
                evidence_code="inventory.expiring_lots_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail=(
                    "Contagem de lotes com saldo cuja validade está na janela analítica de 30 dias."
                ),
                hypothesis_code="inventory.expiry_exposure",
                hypothesis=(
                    "Baixo giro ou distribuição inadequada pode elevar a exposição ao vencimento."
                ),
                expected_impact="Reduzir perdas por validade com ação autorizada e rastreável.",
            ),
            _rule(
                code="inventory.high_coverage",
                title="Cobertura acima de 90 dias",
                objective=(
                    "Detectar cobertura superior ao limiar de excesso já usado pelo analytics."
                ),
                summary="A cobertura em dias está acima de 90 no escopo avaliado.",
                severity="medium",
                primary_kpi="inventory.coverage_days",
                condition=Compare(Kpi("inventory.coverage_days"), "gt", Fixed(Decimal("90"))),
                action_code="inventory.branch_transfer",
                action_rationale=(
                    "Avaliar transferência interna antes de nova compra, desconto ou baixa."
                ),
                evidence_code="inventory.high_coverage_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Cobertura observada acima do limiar analítico de 90 dias.",
                hypothesis_code="inventory.overstock_exposure",
                hypothesis=(
                    "Demanda local fraca ou parâmetro de reposição elevado pode "
                    "explicar a cobertura."
                ),
                expected_impact="Reduzir excesso e risco de vencimento sem automatizar decisões.",
            ),
            _rule(
                code="inventory.low_coverage",
                title="Cobertura abaixo de 7 dias",
                objective="Detectar cobertura inferior ao limiar de baixo estoque do analytics.",
                summary="A cobertura em dias está abaixo de 7 no escopo avaliado.",
                severity="high",
                primary_kpi="inventory.coverage_days",
                condition=Compare(Kpi("inventory.coverage_days"), "lt", Fixed(Decimal("7"))),
                action_code="inventory.coverage_review",
                action_rationale=(
                    "Revisar parâmetros e disponibilidade antes de propor reposição."
                ),
                evidence_code="inventory.low_coverage_signal",
                evidence_type="threshold",
                evidence_direction="below",
                evidence_detail="Cobertura observada abaixo do limiar analítico de 7 dias.",
                hypothesis_code="inventory.reorder_parameter_gap",
                hypothesis=(
                    "Parâmetro de reposição insuficiente ou demanda recente pode "
                    "explicar a cobertura."
                ),
                expected_impact="Antecipar risco de ruptura com recomendação consultiva.",
            ),
            _rule(
                code="inventory.negative_stock",
                title="Itens com estoque negativo",
                objective="Detectar qualquer item com saldo físico negativo.",
                summary="Existe ao menos um item com estoque negativo no escopo avaliado.",
                severity="high",
                primary_kpi="inventory.negative_stock_count",
                condition=Compare(Kpi("inventory.negative_stock_count"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.audit_count",
                action_rationale="Executar conferência física e rastrear a origem da divergência.",
                evidence_code="inventory.negative_stock_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Contagem observada de itens com estoque negativo.",
                hypothesis_code="inventory.inventory_record_gap",
                hypothesis=(
                    "Atraso de integração, lançamento incorreto ou divergência física "
                    "pode explicar o saldo."
                ),
                expected_impact="Restabelecer confiabilidade do saldo sem correção automática.",
            ),
            _rule(
                code="inventory.negative_stock_above_network",
                title="Estoque negativo acima da média da rede",
                objective="Comparar a taxa local de estoque negativo à média governada da rede.",
                summary="A taxa de estoque negativo supera a média da rede no mesmo contexto.",
                severity="high",
                primary_kpi="inventory.negative_stock_rate",
                condition=Compare(
                    Kpi("inventory.negative_stock_rate"),
                    "gt",
                    NetworkAverage("inventory.negative_stock_rate"),
                ),
                action_code="inventory.audit_count",
                action_rationale="Priorizar auditoria do escopo com desvio relativo à rede.",
                evidence_code="inventory.negative_stock_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local comparada à média autorizada da rede.",
                reference_key="network_average:inventory.negative_stock_rate",
                hypothesis_code="inventory.local_inventory_process_gap",
                hypothesis=(
                    "Processo local ou atraso de integração pode explicar o desvio frente à rede."
                ),
                expected_impact="Direcionar auditoria para o escopo com maior desvio relativo.",
            ),
            _rule(
                code="inventory.no_sale_stock",
                title="Estoque sem venda",
                objective="Detectar produtos com saldo disponível e nenhuma venda no período.",
                summary="Existe estoque disponível sem venda no escopo avaliado.",
                severity="medium",
                primary_kpi="inventory.no_sale_count",
                condition=Compare(Kpi("inventory.no_sale_count"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.coverage_review",
                action_rationale=(
                    "Revisar demanda, exposição e parâmetros antes de qualquer intervenção."
                ),
                evidence_code="inventory.no_sale_stock_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Contagem de produtos com estoque disponível e nenhuma venda.",
                hypothesis_code="inventory.assortment_demand_gap",
                hypothesis=(
                    "Baixa demanda, exposição inadequada ou cadastro do sortimento "
                    "pode explicar o sinal."
                ),
                expected_impact="Reduzir estoque inativo mediante decisão humana informada.",
            ),
            _rule(
                code="inventory.observed_stockout",
                title="Ruptura observada",
                objective="Detectar qualquer taxa positiva de produtos ativos sem estoque.",
                summary="A taxa de ruptura observada é maior que zero no escopo avaliado.",
                severity="high",
                primary_kpi="inventory.zero_stock_rate",
                condition=Compare(Kpi("inventory.zero_stock_rate"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.emergency_restock",
                action_rationale=(
                    "Confirmar a ruptura e preparar proposta de reposição sob revisão humana."
                ),
                evidence_code="inventory.observed_stockout_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail=(
                    "Taxa observada de produtos ativos com estoque físico igual a zero."
                ),
                hypothesis_code="inventory.replenishment_constraint",
                hypothesis=(
                    "Atraso de reposição, demanda recente ou divergência de saldo "
                    "pode explicar a ruptura."
                ),
                expected_impact="Reduzir indisponibilidade sem emitir compra automaticamente.",
            ),
            _rule(
                code="inventory.recurring_stockout",
                title="Ruptura recorrente",
                objective=(
                    "Detectar ruptura positiva no período atual e nos dois frames "
                    "analíticos anteriores."
                ),
                summary=(
                    "A ruptura permaneceu positiva no período atual e nos dois "
                    "períodos anteriores."
                ),
                severity="high",
                primary_kpi="inventory.zero_stock_rate",
                condition=AllOf(
                    nodes=(
                        Compare(
                            Kpi("inventory.zero_stock_rate"),
                            "gt",
                            Fixed(Decimal("0")),
                        ),
                        Persisted(
                            Compare(
                                Kpi("inventory.zero_stock_rate"),
                                "gt",
                                Fixed(Decimal("0")),
                            ),
                            periods=2,
                        ),
                    )
                ),
                action_code="inventory.emergency_restock",
                action_rationale=(
                    "Escalar revisão da ruptura persistente sem automatizar aquisição."
                ),
                evidence_code="inventory.recurring_stockout_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail=(
                    "Taxa atual de ruptura positiva; a persistência nos dois frames "
                    "anteriores é comprovada pelo trace."
                ),
                hypothesis_code="inventory.unresolved_replenishment_constraint",
                hypothesis=(
                    "Restrição de reposição ainda não resolvida pode explicar a persistência."
                ),
                expected_impact=(
                    "Priorizar ruptura persistente e evitar tratamento como evento isolado."
                ),
                evaluation_window="current analytical frame plus two previous frames",
            ),
            _rule(
                code="inventory.slow_moving_coverage",
                title="Cobertura acima de 60 dias",
                objective="Detectar cobertura superior ao limiar de baixo giro do analytics.",
                summary="A cobertura em dias está acima de 60 no escopo avaliado.",
                severity="medium",
                primary_kpi="inventory.coverage_days",
                condition=Compare(Kpi("inventory.coverage_days"), "gt", Fixed(Decimal("60"))),
                action_code="inventory.coverage_review",
                action_rationale="Revisar giro, exposição e parâmetros de cobertura.",
                evidence_code="inventory.slow_moving_coverage_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Cobertura observada acima do limiar analítico de 60 dias.",
                hypothesis_code="inventory.slow_demand",
                hypothesis=(
                    "Demanda desacelerada ou sortimento inadequado pode explicar a cobertura."
                ),
                expected_impact="Reduzir risco de imobilização e vencimento de estoque.",
            ),
            _rule(
                code="inventory.stock_adjustments",
                title="Ajustes de estoque observados",
                objective="Detectar quantidade positiva de ajustes de estoque no período.",
                summary="Foram observados ajustes de estoque no escopo avaliado.",
                severity="low",
                primary_kpi="inventory.adjustment_quantity",
                condition=Compare(Kpi("inventory.adjustment_quantity"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.audit_count",
                action_rationale="Revisar os ajustes e suas referências antes de nova correção.",
                evidence_code="inventory.stock_adjustment_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Quantidade absoluta de movimentos classificados como ajuste.",
                hypothesis_code="inventory.reconciliation_activity",
                hypothesis=(
                    "Correções operacionais ou divergências de registro podem explicar os ajustes."
                ),
                expected_impact="Aumentar rastreabilidade das correções de estoque.",
            ),
            _rule(
                code="inventory.stock_adjustments_worsening",
                title="Aumento de ajustes de estoque",
                objective="Detectar crescimento da quantidade ajustada frente ao período anterior.",
                summary="A quantidade ajustada cresceu em relação ao período anterior.",
                severity="medium",
                primary_kpi="inventory.adjustment_quantity",
                condition=Compare(
                    PctChange("inventory.adjustment_quantity", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="inventory.audit_count",
                action_rationale="Priorizar revisão do crescimento dos ajustes e suas origens.",
                evidence_code="inventory.stock_adjustment_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Quantidade ajustada comparada ao período anterior.",
                reference_key="previous:inventory.adjustment_quantity",
                hypothesis_code="inventory.reconciliation_issue_growth",
                hypothesis=(
                    "Aumento de divergências ou mudança operacional pode explicar o crescimento."
                ),
                expected_impact=(
                    "Conter recorrência de ajustes por meio de investigação rastreável."
                ),
            ),
            _rule(
                code="inventory.stock_damage",
                title="Avarias de estoque observadas",
                objective="Detectar quantidade positiva de movimentos de avaria.",
                summary="Foram observadas avarias de estoque no escopo avaliado.",
                severity="medium",
                primary_kpi="inventory.damage_quantity",
                condition=Compare(Kpi("inventory.damage_quantity"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.audit_count",
                action_rationale=(
                    "Revisar lotes, armazenamento e movimentações associadas às avarias."
                ),
                evidence_code="inventory.stock_damage_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Quantidade absoluta de movimentos classificados como avaria.",
                hypothesis_code="inventory.handling_storage_issue",
                hypothesis=(
                    "Condição de armazenamento ou manuseio pode explicar parte das avarias."
                ),
                expected_impact="Reduzir perdas por avaria com investigação operacional.",
            ),
            _rule(
                code="inventory.stock_loss",
                title="Perdas de estoque observadas",
                objective="Detectar quantidade positiva de movimentos de perda.",
                summary="Foram observadas perdas de estoque no escopo avaliado.",
                severity="high",
                primary_kpi="inventory.loss_quantity",
                condition=Compare(Kpi("inventory.loss_quantity"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.audit_count",
                action_rationale=(
                    "Auditar movimentos de perda e referências antes de qualquer baixa adicional."
                ),
                evidence_code="inventory.stock_loss_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Quantidade absoluta de movimentos classificados como perda.",
                hypothesis_code="inventory.loss_process_issue",
                hypothesis=(
                    "Falha operacional, quebra ou registro inadequado pode explicar parte da perda."
                ),
                expected_impact="Reduzir perdas e melhorar a rastreabilidade de estoque.",
            ),
            _rule(
                code="inventory.stockout_above_network",
                title="Ruptura acima da média da rede",
                objective="Comparar a ruptura local à média governada da rede.",
                summary="A taxa local de ruptura supera a média da rede.",
                severity="high",
                primary_kpi="inventory.zero_stock_rate",
                condition=Compare(
                    Kpi("inventory.zero_stock_rate"),
                    "gt",
                    NetworkAverage("inventory.zero_stock_rate"),
                ),
                action_code="inventory.emergency_restock",
                action_rationale=(
                    "Priorizar revisão do escopo com ruptura acima da referência da rede."
                ),
                evidence_code="inventory.stockout_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Taxa local de ruptura comparada à média autorizada da rede.",
                reference_key="network_average:inventory.zero_stock_rate",
                hypothesis_code="inventory.local_replenishment_gap",
                hypothesis=(
                    "Parâmetro local, sortimento ou disponibilidade pode explicar o "
                    "desvio frente à rede."
                ),
                expected_impact="Direcionar ação humana aos escopos com maior desvio relativo.",
            ),
            _rule(
                code="inventory.stockout_risk",
                title="Risco de ruptura observado",
                objective=(
                    "Detectar qualquer taxa positiva de produtos com cobertura abaixo de 7 dias."
                ),
                summary="Existe produto ativo classificado com risco de ruptura.",
                severity="medium",
                primary_kpi="inventory.stockout_risk_rate",
                condition=Compare(Kpi("inventory.stockout_risk_rate"), "gt", Fixed(Decimal("0"))),
                action_code="inventory.coverage_review",
                action_rationale="Revisar cobertura e disponibilidade antes de propor reposição.",
                evidence_code="inventory.stockout_risk_signal",
                evidence_type="threshold",
                evidence_direction="above",
                evidence_detail="Taxa de produtos ativos com cobertura inferior a 7 dias.",
                hypothesis_code="inventory.low_cover_assortment",
                hypothesis=(
                    "Demanda recente ou parâmetro de cobertura pode explicar os itens em risco."
                ),
                expected_impact="Antecipar ruptura sem gerar pedido automático.",
            ),
            _rule(
                code="inventory.stockout_risk_above_network",
                title="Risco de ruptura acima da média da rede",
                objective="Comparar o risco local de ruptura à média governada da rede.",
                summary="A taxa local de risco de ruptura supera a média da rede.",
                severity="medium",
                primary_kpi="inventory.stockout_risk_rate",
                condition=Compare(
                    Kpi("inventory.stockout_risk_rate"),
                    "gt",
                    NetworkAverage("inventory.stockout_risk_rate"),
                ),
                action_code="inventory.coverage_review",
                action_rationale="Revisar parâmetros locais com desvio frente à rede.",
                evidence_code="inventory.stockout_risk_network_gap",
                evidence_type="comparison",
                evidence_direction="above",
                evidence_detail="Risco local de ruptura comparado à média autorizada da rede.",
                reference_key="network_average:inventory.stockout_risk_rate",
                hypothesis_code="inventory.local_coverage_parameter_gap",
                hypothesis=(
                    "Parâmetros locais de cobertura podem explicar o desvio frente à rede."
                ),
                expected_impact="Priorizar revisão humana dos escopos com risco relativo elevado.",
            ),
            _rule(
                code="inventory.stockout_worsening",
                title="Aumento da ruptura observada",
                objective="Detectar crescimento da taxa de ruptura frente ao período anterior.",
                summary="A taxa de ruptura cresceu em relação ao período anterior.",
                severity="high",
                primary_kpi="inventory.zero_stock_rate",
                condition=Compare(
                    PctChange("inventory.zero_stock_rate", baseline="previous"),
                    "gt",
                    Fixed(Decimal("0")),
                ),
                action_code="inventory.emergency_restock",
                action_rationale="Revisar a aceleração da ruptura antes de propor reposição.",
                evidence_code="inventory.stockout_growth",
                evidence_type="comparison",
                evidence_direction="increasing",
                evidence_detail="Taxa de ruptura comparada ao período anterior.",
                reference_key="previous:inventory.zero_stock_rate",
                hypothesis_code="inventory.replenishment_demand_shift",
                hypothesis=("Mudança recente de demanda ou reposição pode explicar o crescimento."),
                expected_impact="Detectar deterioração antes que a ruptura se consolide.",
            ),
            _rule(
                code="inventory.weak_sell_through",
                title="Sell-through abaixo da categoria",
                objective="Comparar o sell-through do escopo à média governada da categoria.",
                summary="O sell-through está abaixo da média da categoria.",
                severity="medium",
                primary_kpi="inventory.sell_through",
                condition=Compare(
                    Kpi("inventory.sell_through"),
                    "lt",
                    CategoryAverage("inventory.sell_through"),
                ),
                action_code="inventory.coverage_review",
                action_rationale="Revisar demanda, exposição e cobertura antes de intervir.",
                evidence_code="inventory.sell_through_category_gap",
                evidence_type="comparison",
                evidence_direction="below",
                evidence_detail="Sell-through local comparado à média autorizada da categoria.",
                reference_key="category_average:inventory.sell_through",
                hypothesis_code="inventory.category_demand_gap",
                hypothesis=(
                    "Exposição, preço ou aderência local do sortimento pode explicar o desvio."
                ),
                expected_impact="Direcionar revisão de estoque sem automatizar preço ou promoção.",
                dimensions=("branch", "category", "product"),
            ),
        ),
        key=lambda rule: rule.code,
    )
)
