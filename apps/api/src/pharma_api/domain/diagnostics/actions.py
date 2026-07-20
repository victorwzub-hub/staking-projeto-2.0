"""Deterministic, advisory-only catalog for diagnostic recommendations.

The catalog follows the semantic KPI catalog convention: immutable dataclasses,
a stable tuple order and a read-only index by code.  Definitions never execute
an action.  Every recommendation requires an authorized human decision, and no
purchase, payment, credit, write-off or price change can be performed
automatically from this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pharma_api.domain.analytics.kpis import KPI_BY_CODE

ActionDomain = Literal["inventory", "sales", "margin", "purchases", "suppliers", "operations"]
ActionPriority = Literal[1, 2, 3, 4]
ActionStatus = Literal["active", "deprecated"]
SuggestedRole = Literal["tenant_admin", "company_admin", "branch_manager", "analyst"]
ExecutionMode = Literal["human_review_required"]

ACTION_DOMAINS: tuple[ActionDomain, ...] = (
    "inventory",
    "sales",
    "margin",
    "purchases",
    "suppliers",
    "operations",
)
ACTION_PRIORITIES: tuple[ActionPriority, ...] = (1, 2, 3, 4)
ACTION_STATUSES: tuple[ActionStatus, ...] = ("active", "deprecated")
SUGGESTED_ROLES: tuple[SuggestedRole, ...] = (
    "tenant_admin",
    "company_admin",
    "branch_manager",
    "analyst",
)
ACTION_CODE_MAX_LENGTH = 100
ACTION_TEXT_MAX_LENGTH = 500
ACTION_LIST_MAX_ITEMS = 16
MIN_DEADLINE_DAYS = 1
MAX_DEADLINE_DAYS = 90
MAX_ACTION_VERSION = 10_000
ACTION_SAFETY_CONSTRAINTS: tuple[str, ...] = (
    "A recomendação é consultiva e exige revisão e autorização humana antes da execução.",
    (
        "Nenhuma compra, pagamento, crédito, baixa, alteração de preço ou compromisso "
        "financeiro é executado automaticamente."
    ),
)
_ACTION_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Versioned recommendation definition with mandatory execution guardrails."""

    code: str
    title: str
    description: str
    justification: str
    domain: ActionDomain
    default_priority: ActionPriority
    suggested_role: SuggestedRole
    suggested_deadline_days: int
    preconditions: tuple[str, ...]
    steps: tuple[str, ...]
    risk: str
    expected_impact: str
    tracking_kpi: str | None
    success_criteria: str
    closure_criteria: str
    status: ActionStatus = "active"
    version: int = 1
    execution_mode: ExecutionMode = "human_review_required"
    allows_automatic_financial_execution: Literal[False] = False
    safety_constraints: tuple[str, ...] = ACTION_SAFETY_CONSTRAINTS

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation with stable field order."""

        return {
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "justification": self.justification,
            "domain": self.domain,
            "default_priority": self.default_priority,
            "suggested_role": self.suggested_role,
            "suggested_deadline_days": self.suggested_deadline_days,
            "preconditions": list(self.preconditions),
            "steps": list(self.steps),
            "risk": self.risk,
            "expected_impact": self.expected_impact,
            "tracking_kpi": self.tracking_kpi,
            "success_criteria": self.success_criteria,
            "closure_criteria": self.closure_criteria,
            "status": self.status,
            "version": self.version,
            "execution_mode": self.execution_mode,
            "allows_automatic_financial_execution": self.allows_automatic_financial_execution,
            "safety_constraints": list(self.safety_constraints),
        }


def _action(
    code: str,
    title: str,
    domain: ActionDomain,
    priority: ActionPriority,
    role: SuggestedRole,
    deadline_days: int,
    description: str,
    justification: str,
    steps: tuple[str, ...],
    risk: str,
    expected_impact: str,
    tracking_kpi: str | None,
    success_criteria: str,
    closure_criteria: str,
    preconditions: tuple[str, ...] = (),
) -> ActionDefinition:
    return ActionDefinition(
        code=code,
        title=title,
        description=description,
        justification=justification,
        domain=domain,
        default_priority=priority,
        suggested_role=role,
        suggested_deadline_days=deadline_days,
        preconditions=preconditions,
        steps=steps,
        risk=risk,
        expected_impact=expected_impact,
        tracking_kpi=tracking_kpi,
        success_criteria=success_criteria,
        closure_criteria=closure_criteria,
    )


ACTION_CATALOG: tuple[ActionDefinition, ...] = (
    # Inventory
    _action(
        "inventory.emergency_restock",
        "Reposição emergencial de ruptura",
        "inventory",
        1,
        "branch_manager",
        2,
        "Preparar uma recomendação de reposição emergencial para produtos em ruptura recorrente.",
        "Ruptura em produtos de giro compromete receita e fidelidade do cliente.",
        (
            "Confirmar ruptura física no estoque da filial.",
            "Selecionar fornecedor com menor lead time para os itens.",
            (
                "Gerar uma minuta de pedido com quantidade e custo estimados, sem "
                "transmissão automática."
            ),
            "Submeter a minuta ao fluxo humano de aprovação e registrar a decisão tomada.",
        ),
        "Custo de compra emergencial acima do negociado.",
        "Recuperação da disponibilidade e da receita perdida por ruptura.",
        "inventory.zero_stock_rate",
        "Taxa de ruptura dos itens tratados volta à média da rede em 7 dias.",
        (
            "Decisão registrada; quando aprovada fora do motor, recebimento acompanhado "
            "e estoque regularizado."
        ),
        ("Produto com histórico de venda no período.",),
    ),
    _action(
        "inventory.coverage_review",
        "Revisão de cobertura de estoque",
        "inventory",
        2,
        "analyst",
        5,
        "Recalcular parâmetros de cobertura dos produtos fora da faixa-alvo.",
        "Cobertura excessiva imobiliza capital; cobertura baixa gera ruptura.",
        (
            "Listar produtos fora da faixa de cobertura-alvo.",
            "Revisar demanda média e lead time parametrizados.",
            "Ajustar estoque mínimo e ponto de pedido.",
            "Monitorar a cobertura na semana seguinte.",
        ),
        "Ajuste incorreto de parâmetros pode gerar excesso ou ruptura.",
        "Cobertura em dias dentro da faixa-alvo da categoria.",
        "inventory.coverage_days",
        "Cobertura mediana da categoria dentro da faixa-alvo por 14 dias.",
        "Parâmetros revisados e cobertura estabilizada na faixa-alvo.",
    ),
    _action(
        "inventory.branch_transfer",
        "Transferência entre filiais",
        "inventory",
        2,
        "company_admin",
        3,
        "Transferir excedente de filiais com excesso para filiais em ruptura.",
        "Rebalancear estoque entre filiais evita compra desnecessária e perda.",
        (
            "Identificar filiais doadoras com excesso do produto.",
            "Confirmar necessidade e capacidade da filial receptora.",
            "Emitir ordem de transferência e agendar logística.",
            "Confirmar entrada do estoque na filial receptora.",
        ),
        "Custo logístico da transferência e risco de avaria no transporte.",
        "Redução simultânea de excesso e ruptura sem nova compra.",
        "inventory.excess_count",
        "Excesso e ruptura do produto reduzidos nas duas filiais em 7 dias.",
        "Transferência concluída e saldos regularizados nas duas filiais.",
    ),
    _action(
        "inventory.expiring_quarantine",
        "Quarentena de lotes próximos ao vencimento",
        "inventory",
        1,
        "branch_manager",
        1,
        "Isolar lotes próximos do vencimento e definir ação de escoamento.",
        "Venda de produto vencido gera risco sanitário, devolução e multa.",
        (
            "Bloquear os lotes no sistema e sinalizar fisicamente.",
            "Avaliar devolução ao fornecedor dentro do prazo contratual.",
            "Definir promoção de escoamento para lotes ainda vendáveis.",
            "Registrar o destino final de cada lote.",
        ),
        "Perda financeira dos lotes sem escoamento possível.",
        "Eliminação do risco de venda de produto vencido.",
        "inventory.expiring_lots",
        "Nenhum lote vencido disponível para venda após a quarentena.",
        "Todos os lotes com destino registrado e estoque vencido zerado.",
    ),
    _action(
        "inventory.audit_count",
        "Auditoria de inventário por contagem",
        "inventory",
        3,
        "branch_manager",
        7,
        "Executar contagem cíclica nos itens com divergência de estoque.",
        "Divergência entre estoque físico e sistêmico distorce KPIs e compras.",
        (
            "Bloquear movimentação dos itens selecionados.",
            "Executar contagem física com dupla conferência.",
            "Lançar ajustes com justificativa e aprovação.",
            "Investigar a causa raiz da divergência.",
        ),
        "Parada temporária da movimentação dos itens auditados.",
        "Acuracidade de estoque restaurada e ajustes rastreáveis.",
        "inventory.negative_stock_count",
        "Divergências ajustadas e sem reincidência em 30 dias.",
        "Contagem aprovada, ajustes lançados e causa documentada.",
    ),
    # Sales
    _action(
        "sales.revenue_drop_review",
        "Análise de queda de receita",
        "sales",
        1,
        "analyst",
        3,
        "Decompor a queda de receita por canal, categoria e horário.",
        "Queda persistente de receita exige ação antes de virar tendência.",
        (
            "Comparar receita por canal e categoria com o período-base.",
            "Identificar os produtos que mais contribuíram para a queda.",
            "Verificar ruptura e preço dos produtos identificados.",
            "Propor ação corretiva por causa identificada.",
        ),
        "Conclusões precipitadas sem decomposição completa do escopo.",
        "Causa da queda identificada e plano corretivo definido.",
        "sales.net_revenue",
        "Receita diária retorna à faixa do período-base em 14 dias.",
        "Causa documentada, ação executada e receita recuperada.",
    ),
    _action(
        "sales.ticket_mix_review",
        "Revisão de mix e ticket médio",
        "sales",
        3,
        "analyst",
        7,
        "Revisar mix de produtos e sugestões de venda para recuperar o ticket.",
        "Ticket médio em queda reduz receita mesmo com volume estável.",
        (
            "Analisar itens por venda e preço médio por categoria.",
            "Identificar categorias com queda de participação.",
            "Revisar exposição e sugestão de venda casada no PDV.",
            "Acompanhar o ticket médio semanalmente.",
        ),
        "Ações comerciais podem pressionar margem se mal calibradas.",
        "Recuperação do ticket médio sem perda de volume.",
        "sales.average_ticket",
        "Ticket médio recupera o nível do período-base em 30 dias.",
        "Ticket estabilizado e ações comerciais incorporadas à rotina.",
    ),
    _action(
        "sales.return_rate_investigation",
        "Investigação de devoluções",
        "sales",
        2,
        "branch_manager",
        5,
        "Investigar produtos e motivos por trás da alta de devoluções.",
        "Devoluções acima do padrão indicam problema de produto ou processo.",
        (
            "Agrupar devoluções por produto, motivo e operador.",
            "Verificar lotes e validade dos produtos devolvidos.",
            "Revisar orientação de venda dos produtos mais devolvidos.",
            "Encaminhar não conformidades ao fornecedor quando aplicável.",
        ),
        "Tratamento sintomático sem atacar a causa raiz.",
        "Taxa de devolução de volta ao padrão histórico.",
        "sales.return_rate",
        "Taxa de devolução abaixo do limite de alerta por 30 dias.",
        "Causa raiz tratada e taxa estabilizada no padrão.",
    ),
    _action(
        "sales.cancellation_process_review",
        "Revisão do processo de cancelamentos",
        "sales",
        3,
        "branch_manager",
        5,
        "Revisar cancelamentos de venda por motivo e por operador.",
        "Cancelamentos elevados indicam falha de processo, preço ou fraude.",
        (
            "Listar cancelamentos por motivo, operador e horário.",
            "Conferir autorização e senha de cancelamento.",
            "Reforçar treinamento do processo de venda.",
            "Reportar padrões suspeitos à auditoria interna.",
        ),
        "Exposição de dados de operadores exige tratamento confidencial.",
        "Redução de cancelamentos evitáveis e perdas associadas.",
        "sales.cancellation_rate",
        "Taxa de cancelamento dentro do limite por 30 dias.",
        "Processo revisado e taxa de cancelamento normalizada.",
    ),
    _action(
        "sales.hourly_staffing_review",
        "Revisão de escala por horário de pico",
        "sales",
        4,
        "branch_manager",
        10,
        "Ajustar escala de atendimento aos horários de maior venda por hora.",
        "Filas em horário de pico derrubam conversão e venda média por hora.",
        (
            "Mapear venda média por hora dos últimos 60 dias.",
            "Cruzar com a escala atual de atendentes.",
            "Remanejar horários para cobrir os picos.",
            "Medir venda por hora após o ajuste.",
        ),
        "Aumento de custo de pessoal se o remanejo não for líquido-zero.",
        "Aumento da venda por hora nos períodos de pico.",
        "sales.hourly_average",
        "Venda por hora nos picos cresce sem aumento de custo de escala.",
        "Escala ajustada e venda por hora estabilizada em patamar superior.",
    ),
    # Margin
    _action(
        "margin.price_review",
        "Revisão de preço de venda",
        "margin",
        2,
        "company_admin",
        5,
        "Revisar preços de produtos com margem abaixo do piso da categoria.",
        "Preço desalinhado de custo corrói margem de forma silenciosa.",
        (
            "Listar produtos com margem abaixo do piso.",
            "Conferir custo atual e tributação de cada item.",
            "Simular novo preço e impacto na margem.",
            (
                "Submeter o reajuste ao responsável autorizado e registrar a decisão "
                "antes de comunicar filiais."
            ),
        ),
        "Reajuste pode reduzir competitividade em itens sensíveis a preço.",
        "Margem bruta dos itens revisados de volta ao piso.",
        "margin.gross_percent",
        "Margem bruta da categoria acima do piso por 30 dias.",
        "Preços atualizados e margem estabilizada acima do piso.",
    ),
    _action(
        "margin.discount_policy_review",
        "Revisão da política de descontos",
        "margin",
        2,
        "company_admin",
        5,
        "Revisar limites e alçadas de desconto após alta da taxa de desconto.",
        "Desconto acima da política transfere margem sem ganho de volume.",
        (
            "Analisar descontos por operador, categoria e campanha.",
            "Comparar taxa praticada com o limite da política.",
            (
                "Propor ajustes de alçadas e bloqueios no PDV para aprovação do "
                "responsável autorizado."
            ),
            "Comunicar a nova política às equipes.",
        ),
        "Restrição excessiva pode derrubar conversão de vendas.",
        "Taxa de desconto de volta ao teto sem perda de receita.",
        "sales.discount_rate",
        "Taxa de desconto dentro do teto por 30 dias.",
        "Política ajustada, alçadas configuradas e taxa normalizada.",
    ),
    _action(
        "margin.negative_margin_cleanup",
        "Saneamento de margem negativa",
        "margin",
        1,
        "company_admin",
        3,
        "Corrigir produtos vendidos com margem negativa.",
        "Venda abaixo do custo gera prejuízo direto em cada unidade vendida.",
        (
            "Listar produtos com margem negativa no período.",
            "Verificar custo, tributo e preço cadastrados.",
            "Preparar correção cadastral ou proposta de reajuste e submetê-la à aprovação humana.",
            "Auditar vendas realizadas enquanto o erro vigorou.",
        ),
        "Correção de preço pode gerar atrito com clientes recorrentes.",
        "Eliminação das vendas com margem negativa.",
        "margin.negative_margin_rate",
        "Taxa de produtos com margem negativa zerada por 14 dias.",
        "Cadastros corrigidos e nenhuma venda abaixo do custo.",
    ),
    _action(
        "margin.gmroi_rebalance",
        "Rebalanceamento de capital por GMROI",
        "margin",
        3,
        "analyst",
        10,
        "Realocar capital de itens de baixo GMROI para itens de alto retorno.",
        "Capital em itens de baixo GMROI reduz o retorno total do estoque.",
        (
            "Classificar produtos por GMROI na categoria.",
            (
                "Propor redução de pedidos dos itens de baixo retorno para aprovação no "
                "processo de compras."
            ),
            "Ampliar cobertura dos itens de alto retorno.",
            "Acompanhar GMROI da categoria mensalmente.",
        ),
        "Redução de sortimento pode afetar a percepção de variedade.",
        "Aumento do retorno sobre o capital em estoque.",
        "margin.gmroi",
        "GMROI da categoria cresce em relação ao trimestre anterior.",
        "Carteira rebalanceada e GMROI em trajetória de alta.",
    ),
    _action(
        "margin.price_dispersion_review",
        "Revisão de dispersão de preços",
        "margin",
        4,
        "analyst",
        10,
        "Padronizar preços entre filiais com dispersão acima do tolerado.",
        "Dispersão de preço entre filiais confunde o cliente e corrói margem.",
        (
            "Comparar preço dos mesmos produtos entre filiais.",
            "Identificar origem da divergência (custo, campanha, cadastro).",
            "Definir preço de referência e alinhar exceções justificadas.",
            "Monitorar dispersão após o alinhamento.",
        ),
        "Alinhamento cego pode ignorar diferenças regionais de custo.",
        "Dispersão de preços dentro da banda tolerada.",
        "margin.price_dispersion",
        "Dispersão abaixo do limite definido por 30 dias.",
        "Preços alinhados ou exceções formalmente justificadas.",
    ),
    # Purchases
    _action(
        "purchases.order_parameter_review",
        "Revisão de parâmetros de compra",
        "purchases",
        2,
        "analyst",
        5,
        "Revisar múltiplos, lotes mínimos e sugestões automáticas de compra.",
        "Parâmetros desatualizados geram excesso, ruptura e compra emergencial.",
        (
            "Auditar múltiplos e lotes mínimos dos principais fornecedores.",
            "Confrontar sugestão automática com demanda real.",
            "Corrigir parâmetros divergentes.",
            "Acompanhar aderência ao múltiplo nas próximas compras.",
        ),
        "Correções podem exigir renegociação de condições comerciais.",
        "Compras aderentes aos parâmetros e sem emergenciais.",
        "purchases.multiple_adherence",
        "Aderência ao múltiplo acima da meta por 30 dias.",
        "Parâmetros corrigidos e aderência estabilizada na meta.",
    ),
    _action(
        "purchases.emergency_rate_reduction",
        "Redução de compras emergenciais",
        "purchases",
        2,
        "analyst",
        7,
        "Atacar as causas das compras emergenciais recorrentes.",
        "Compra emergencial tem custo maior e indica falha de planejamento.",
        (
            "Listar compras emergenciais por produto e motivo.",
            "Corrigir ponto de pedido dos itens recorrentes.",
            "Revisar lead time dos fornecedores envolvidos.",
            "Medir a taxa de emergenciais no ciclo seguinte.",
        ),
        "Aumento de estoque de segurança eleva capital imobilizado.",
        "Taxa de compras emergenciais de volta ao padrão.",
        "purchases.emergency_rate",
        "Taxa de emergenciais abaixo do limite por 30 dias.",
        "Causas tratadas e taxa de emergenciais normalizada.",
    ),
    _action(
        "purchases.receipt_followup",
        "Cobrança de recebimento de pedidos",
        "purchases",
        2,
        "branch_manager",
        3,
        "Cobrar fornecedores de pedidos vencidos ou com entrega parcial.",
        "Pedidos sem recebimento comprometem cobertura e geram ruptura.",
        (
            "Listar pedidos vencidos e entregas parciais.",
            "Acionar os fornecedores com prazo de regularização.",
            "Recomendar reprogramação ou cancelamento para decisão do responsável autorizado.",
            "Avaliar fornecedor reincidente para renegociação.",
        ),
        "Cancelamento pode deixar lacuna de cobertura temporária.",
        "Taxa de recebimento de pedidos de volta à meta.",
        "purchases.receipt_rate",
        "Pedidos vencidos zerados e taxa de recebimento na meta.",
        "Carteira de pedidos regularizada sem vencidos.",
    ),
    _action(
        "purchases.freight_review",
        "Revisão de condições de frete",
        "purchases",
        4,
        "company_admin",
        15,
        "Renegociar fretes com taxa acima da referência da rede.",
        "Frete acima da referência reduz a margem de compra.",
        (
            "Comparar taxa de frete por fornecedor e rota.",
            "Levantar referências de mercado para as rotas.",
            "Renegociar com os fornecedores acima da referência.",
            "Registrar novas condições no cadastro.",
        ),
        "Renegociação pode alongar prazos de entrega.",
        "Redução da taxa média de frete sobre compras.",
        "purchases.freight_rate",
        "Taxa de frete média dentro da referência em 60 dias.",
        "Condições renegociadas e taxa estabilizada na referência.",
    ),
    _action(
        "purchases.return_process_review",
        "Revisão de devoluções a fornecedores",
        "purchases",
        3,
        "analyst",
        7,
        "Formalizar devoluções de compra pendentes de coleta ou crédito.",
        "Devolução sem baixa financeira gera crédito não recebido.",
        (
            "Listar devoluções pendentes de coleta ou crédito.",
            "Acionar fornecedores para agendamento de coleta.",
            "Conferir créditos recebidos contra notas de devolução.",
            "Preparar a baixa sistêmica documentada e submetê-la ao responsável autorizado.",
        ),
        "Demora do fornecedor pode exigir compensação em pagamento.",
        "Créditos de devolução recebidos e baixados.",
        "purchases.return_rate",
        "Nenhuma devolução pendente há mais de 15 dias.",
        "Pendências zeradas e créditos conciliados.",
    ),
    # Suppliers
    _action(
        "suppliers.renegotiation",
        "Renegociação com fornecedor",
        "suppliers",
        2,
        "company_admin",
        15,
        "Renegociar custo e condições com fornecedor com variação acima do teto.",
        "Variação de custo acima do teto corrói margem de toda a categoria.",
        (
            "Levantar histórico de custo e volume do fornecedor.",
            "Preparar comparativo com fornecedores alternativos.",
            "Conduzir renegociação de tabela e prazos.",
            "Formalizar novas condições e atualizar cadastro.",
        ),
        "Risco de desabastecimento se a negociação travar.",
        "Variação de custo de volta ao teto acordado.",
        "suppliers.cost_variation",
        "Variação de custo dentro do teto no próximo ciclo.",
        "Acordo formalizado e custo estabilizado no teto.",
    ),
    _action(
        "suppliers.lead_time_review",
        "Revisão de lead time de fornecedor",
        "suppliers",
        3,
        "analyst",
        10,
        "Recalibrar lead time cadastrado com base nas entregas recentes.",
        "Lead time desatualizado distorce ponto de pedido e cobertura.",
        (
            "Calcular lead time realizado dos últimos recebimentos.",
            "Comparar com o lead time cadastrado.",
            "Atualizar cadastro e recalcular pontos de pedido.",
            "Cobrar plano de melhoria dos fornecedores fora do padrão.",
        ),
        "Lead time maior eleva estoque de segurança necessário.",
        "Parâmetros logísticos alinhados à realidade de entrega.",
        "suppliers.average_lead_time",
        "Lead time cadastrado com desvio menor que 20% do realizado.",
        "Cadastros atualizados e desvios dentro do tolerado.",
    ),
    _action(
        "suppliers.fill_rate_action",
        "Plano de atendimento de fornecedor",
        "suppliers",
        2,
        "company_admin",
        10,
        "Exigir plano de melhoria de fornecedor com atendimento abaixo da meta.",
        "Baixa taxa de atendimento transfere ruptura para a loja.",
        (
            "Quantificar faltas por produto e por pedido.",
            "Reunião de cobrança com plano de ação do fornecedor.",
            "Avaliar dual sourcing para itens críticos.",
            "Monitorar atendimento nos próximos ciclos.",
        ),
        "Dual sourcing pode reduzir poder de negociação por volume.",
        "Taxa de atendimento do fornecedor de volta à meta.",
        "suppliers.fill_rate",
        "Atendimento acima da meta por dois ciclos consecutivos.",
        "Plano cumprido e atendimento estabilizado na meta.",
    ),
    _action(
        "suppliers.dependency_reduction",
        "Redução de dependência de fornecedor",
        "suppliers",
        3,
        "company_admin",
        30,
        "Desenvolver alternativas para categorias dependentes de um fornecedor.",
        "Dependência concentrada amplifica impacto de qualquer falha.",
        (
            "Mapear categorias com concentração acima do limite.",
            "Homologar fornecedores alternativos.",
            "Distribuir volume gradualmente entre os homologados.",
            "Revisar concentração trimestralmente.",
        ),
        "Perda de escala pode elevar custo unitário.",
        "Concentração de abastecimento dentro do limite de risco.",
        "suppliers.dependency",
        "Dependência do principal fornecedor abaixo do limite.",
        "Alternativas homologadas e concentração dentro do limite.",
    ),
    _action(
        "suppliers.quality_claim",
        "Reclamação formal de qualidade",
        "suppliers",
        2,
        "company_admin",
        7,
        "Abrir reclamação formal por falhas de qualidade no recebimento.",
        "Falhas de qualidade geram perda, devolução e risco ao cliente.",
        (
            "Consolidar evidências das falhas por lote e nota.",
            "Abrir reclamação formal com prazo de resposta.",
            (
                "Solicitar proposta de crédito ou reposição, sem aceitar compromisso "
                "financeiro automaticamente."
            ),
            "Acompanhar score de qualidade do fornecedor.",
        ),
        "Escalada pode deteriorar relacionamento comercial.",
        "Qualidade do fornecimento de volta ao padrão acordado.",
        "suppliers.quality_score",
        "Score de qualidade acima da meta nos próximos recebimentos.",
        "Reclamação respondida, crédito recebido e score recuperado.",
    ),
    # Operations
    _action(
        "operations.integration_check",
        "Verificação de integração de dados",
        "operations",
        1,
        "tenant_admin",
        1,
        "Diagnosticar e restabelecer integrações com falha ou atraso.",
        "Sem integração atualizada, KPIs e diagnósticos perdem validade.",
        (
            "Identificar lotes com falha e origem do erro.",
            "Corrigir credencial, conexão ou layout conforme a causa.",
            "Reprocessar os lotes afetados.",
            "Confirmar freshness dentro do SLA.",
        ),
        "Reprocessamento incorreto pode duplicar registros.",
        "Disponibilidade da integração de volta ao SLA.",
        "operations.integration_availability",
        "Disponibilidade acima do SLA por 7 dias.",
        "Integrações estáveis e freshness dentro do SLA.",
    ),
    _action(
        "operations.rejection_triage",
        "Tratamento de rejeições de importação",
        "operations",
        2,
        "analyst",
        3,
        "Classificar e corrigir registros rejeitados na importação.",
        "Rejeições elevadas reduzem a completude dos dados analíticos.",
        (
            "Agrupar rejeições por motivo e arquivo de origem.",
            "Corrigir cadastros ou layouts causadores.",
            "Reenviar registros corrigidos.",
            "Acompanhar taxa de rejeição na próxima carga.",
        ),
        "Correções manuais em massa podem introduzir novos erros.",
        "Completude de volta à meta de qualidade.",
        "operations.rejection_rate",
        "Taxa de rejeição abaixo do limite na próxima carga.",
        "Causas corrigidas e rejeições dentro do limite.",
    ),
    _action(
        "operations.duplicate_cleanup",
        "Saneamento de duplicidades",
        "operations",
        2,
        "analyst",
        5,
        "Investigar e eliminar registros duplicados na ingestão.",
        "Duplicidades inflam medidas e corrompem KPIs e diagnósticos.",
        (
            "Identificar origem das duplicidades por chave natural.",
            "Corrigir o processo de ingestão causador.",
            "Deduplicar os registros afetados com rastreabilidade.",
            "Validar KPIs impactados após o saneamento.",
        ),
        "Deduplicação incorreta pode remover registros legítimos.",
        "Taxa de duplicidade de volta ao limite de qualidade.",
        "operations.duplicate_rate",
        "Taxa de duplicidade abaixo do limite por 7 dias.",
        "Causa corrigida, registros saneados e KPIs validados.",
    ),
    _action(
        "operations.freshness_recovery",
        "Recuperação de freshness analítica",
        "operations",
        2,
        "tenant_admin",
        2,
        "Restabelecer a atualização analítica dentro do SLA de freshness.",
        "Dados desatualizados invalidam sinais e diagnósticos recentes.",
        (
            "Verificar fila de atualização e jobs com falha.",
            "Reexecutar atualizações pendentes em ordem de prioridade.",
            "Investigar gargalos de processamento recorrentes.",
            "Confirmar watermark e freshness atualizados.",
        ),
        "Reprocessamento concorrente pode pressionar o banco.",
        "Freshness dentro do SLA e pipeline estável.",
        "operations.data_freshness",
        "Freshness dentro do SLA por 7 dias consecutivos.",
        "Pipeline estável e freshness sustentada no SLA.",
    ),
    _action(
        "operations.quality_incident_review",
        "Revisão de incidentes de qualidade",
        "operations",
        3,
        "analyst",
        7,
        "Analisar incidentes de qualidade recorrentes e corrigir a causa.",
        "Incidentes recorrentes indicam falha estrutural no pipeline.",
        (
            "Consolidar incidentes por tipo e origem.",
            "Priorizar a causa com maior impacto em completude.",
            "Corrigir regra de validação ou rotina de carga.",
            "Monitorar reincidência após a correção.",
        ),
        "Correção de regras pode rejeitar registros antes aceitos.",
        "Redução sustentada dos incidentes de qualidade.",
        "operations.quality_incidents",
        "Sem reincidência do incidente tratado por 30 dias.",
        "Causa corrigida e incidentes dentro do padrão.",
    ),
)


def _validate_text(value: str, field: str, code: str, errors: list[str]) -> None:
    if not value or value != value.strip():
        errors.append(f"{code}.{field}: must be a non-empty trimmed string")
    elif len(value) > ACTION_TEXT_MAX_LENGTH:
        errors.append(f"{code}.{field}: exceeds {ACTION_TEXT_MAX_LENGTH} characters")


def validate_action_catalog(
    catalog: tuple[ActionDefinition, ...],
) -> tuple[str, ...]:
    """Return deterministic integrity errors for an action catalog."""

    errors: list[str] = []
    seen_codes: set[str] = set()
    for index, action in enumerate(catalog):
        path = f"action[{index}]"
        if action.code in seen_codes:
            errors.append(f"{path}.code: duplicate code {action.code!r}")
        seen_codes.add(action.code)
        if len(action.code) > ACTION_CODE_MAX_LENGTH or not _ACTION_CODE_PATTERN.fullmatch(
            action.code
        ):
            errors.append(f"{path}.code: invalid stable code {action.code!r}")
        if not action.code.startswith(f"{action.domain}."):
            errors.append(f"{path}.code: prefix must match domain {action.domain!r}")
        if action.domain not in ACTION_DOMAINS:
            errors.append(f"{path}.domain: unsupported domain {action.domain!r}")
        if action.default_priority not in ACTION_PRIORITIES:
            errors.append(f"{path}.default_priority: unsupported priority")
        if action.suggested_role not in SUGGESTED_ROLES:
            errors.append(f"{path}.suggested_role: unsupported role {action.suggested_role!r}")
        if not MIN_DEADLINE_DAYS <= action.suggested_deadline_days <= MAX_DEADLINE_DAYS:
            errors.append(f"{path}.suggested_deadline_days: out of range")
        if action.status not in ACTION_STATUSES:
            errors.append(f"{path}.status: unsupported status {action.status!r}")
        if not 1 <= action.version <= MAX_ACTION_VERSION:
            errors.append(f"{path}.version: out of range")
        execution_mode = str(action.execution_mode)
        if execution_mode != "human_review_required":
            errors.append(f"{path}.execution_mode: actions must require human review")
        automatic_financial_execution = bool(action.allows_automatic_financial_execution)
        if automatic_financial_execution:
            errors.append(f"{path}: automatic financial execution is forbidden")
        if action.safety_constraints != ACTION_SAFETY_CONSTRAINTS:
            errors.append(f"{path}.safety_constraints: mandatory guardrails changed")
        if action.tracking_kpi is not None and action.tracking_kpi not in KPI_BY_CODE:
            errors.append(f"{path}.tracking_kpi: unknown KPI {action.tracking_kpi!r}")
        for field in (
            "title",
            "description",
            "justification",
            "risk",
            "expected_impact",
            "success_criteria",
            "closure_criteria",
        ):
            _validate_text(str(getattr(action, field)), field, action.code, errors)
        for field, values, minimum_items in (
            ("preconditions", action.preconditions, 0),
            ("steps", action.steps, 1),
        ):
            if not minimum_items <= len(values) <= ACTION_LIST_MAX_ITEMS:
                errors.append(
                    f"{path}.{field}: must contain between {minimum_items} and "
                    f"{ACTION_LIST_MAX_ITEMS} items"
                )
            if len(values) != len(set(values)):
                errors.append(f"{path}.{field}: duplicate entries are not allowed")
            for item_index, value in enumerate(values):
                _validate_text(value, f"{field}[{item_index}]", action.code, errors)
    if {action.domain for action in catalog} != set(ACTION_DOMAINS):
        errors.append("catalog: every diagnostic domain must be represented")
    return tuple(errors)


ACTION_BY_CODE = MappingProxyType({action.code: action for action in ACTION_CATALOG})
_ACTION_CATALOG_ERRORS = validate_action_catalog(ACTION_CATALOG)
if _ACTION_CATALOG_ERRORS:
    raise RuntimeError("Invalid action catalog: " + "; ".join(_ACTION_CATALOG_ERRORS))
