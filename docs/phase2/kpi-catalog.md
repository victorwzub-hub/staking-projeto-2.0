# Catálogo semântico de KPIs — Etapa 2C

Este arquivo é gerado por `scripts/generate-kpi-catalog.py`. A fonte executável e versionada é `pharma_api.domain.analytics.kpis`; alterações de fórmula exigem nova versão e são registradas na auditoria durante a sincronização do catálogo.

KPIs operacionais: **120**. KPIs indisponíveis: **3**.

## KPIs operacionais

| Código | Nome | Categoria | Fórmula segura | Unidade | Direção | Versão |
|---|---|---|---|---|---|---:|
| `sales.gross_revenue` | Receita bruta | sales | `value(gross_revenue)` | BRL | increase | 1 |
| `sales.net_revenue` | Receita líquida | sales | `value(net_revenue)` | BRL | increase | 1 |
| `sales.completed_count` | Vendas concluídas | sales | `value(completed_sales)` | count | increase | 1 |
| `sales.units_sold` | Unidades vendidas | sales | `value(units_sold)` | unit | increase | 1 |
| `sales.average_ticket` | Ticket médio | sales | `ratio(net_revenue, completed_sales)` | BRL | increase | 1 |
| `sales.items_per_sale` | Itens por venda | sales | `ratio(item_count, completed_sales)` | ratio | increase | 1 |
| `sales.average_unit_price` | Preço médio por unidade | sales | `ratio(net_revenue, units_sold)` | BRL | target | 1 |
| `sales.average_discount` | Desconto médio | sales | `ratio(discount_amount, completed_sales)` | BRL | decrease | 1 |
| `sales.discount_rate` | Taxa de desconto | sales | `ratio(discount_amount, gross_revenue) x 100` | percent | decrease | 1 |
| `sales.cancellation_rate` | Taxa de cancelamento | sales | `ratio(cancelled_sales, sale_count) x 100` | percent | decrease | 1 |
| `sales.return_rate` | Taxa de devolução | sales | `ratio(return_amount, gross_revenue) x 100` | percent | decrease | 1 |
| `sales.return_count` | Quantidade de devoluções | sales | `value(return_count)` | count | decrease | 1 |
| `sales.discounted_sales_rate` | Vendas com desconto | sales | `ratio(discounted_sales, completed_sales) x 100` | percent | target | 1 |
| `sales.tax_value` | Tributos sobre vendas | sales | `value(sales_tax)` | BRL | informational | 1 |
| `sales.tax_rate` | Carga tributária sobre vendas | sales | `ratio(sales_tax, gross_revenue) x 100` | percent | informational | 1 |
| `sales.channel_share` | Participação por canal | sales | `ratio(scoped_net_revenue, network_net_revenue) x 100` | percent | target | 1 |
| `sales.category_share` | Participação por categoria | sales | `ratio(scoped_net_revenue, network_net_revenue) x 100` | percent | target | 1 |
| `sales.product_share` | Participação por produto | sales | `ratio(scoped_net_revenue, network_net_revenue) x 100` | percent | target | 1 |
| `sales.branch_share` | Participação por filial | sales | `ratio(scoped_net_revenue, network_net_revenue) x 100` | percent | target | 1 |
| `sales.top10_concentration` | Concentração das 10 maiores vendas | sales | `ratio(top10_revenue, net_revenue) x 100` | percent | decrease | 1 |
| `sales.active_product_count` | Produtos vendidos | sales | `value(sold_product_count)` | count | increase | 1 |
| `sales.revenue_per_product` | Receita por produto vendido | sales | `ratio(net_revenue, sold_product_count)` | BRL | increase | 1 |
| `sales.hourly_average` | Venda média por hora | sales | `ratio(net_revenue, active_hours)` | BRL | increase | 1 |
| `sales.daily_average` | Venda média diária | sales | `ratio(net_revenue, active_days)` | BRL | increase | 1 |
| `sales.payment_per_sale` | Pagamentos por venda | sales | `ratio(payment_count, completed_sales)` | ratio | target | 1 |
| `inventory.on_hand` | Estoque físico | inventory | `value(inventory_on_hand)` | unit | target | 1 |
| `inventory.available` | Estoque disponível | inventory | `value(inventory_available)` | unit | target | 1 |
| `inventory.reserved` | Estoque reservado | inventory | `value(inventory_reserved)` | unit | decrease | 1 |
| `inventory.in_transit` | Estoque em trânsito | inventory | `value(inventory_in_transit)` | unit | informational | 1 |
| `inventory.value_retail` | Valor do estoque a preço | inventory | `value(inventory_retail_value)` | BRL | target | 1 |
| `inventory.value_cost` | Capital em estoque | inventory | `value(inventory_cost_value)` | BRL | decrease | 1 |
| `inventory.coverage_days` | Cobertura em dias | inventory | `ratio(inventory_available, average_daily_units)` | day | target | 1 |
| `inventory.turnover` | Giro de estoque | inventory | `ratio(cogs, average_inventory_cost)` | ratio | increase | 1 |
| `inventory.sell_through` | Sell-through | inventory | `ratio(units_sold, units_available_for_sale) x 100` | percent | increase | 1 |
| `inventory.zero_stock_rate` | Ruptura observada | inventory | `ratio(zero_stock_products, active_products) x 100` | percent | decrease | 1 |
| `inventory.stockout_risk_rate` | Risco de ruptura | inventory | `ratio(low_cover_products, active_products) x 100` | percent | decrease | 1 |
| `inventory.negative_stock_count` | Itens com estoque negativo | inventory | `value(negative_stock_products)` | count | decrease | 1 |
| `inventory.negative_stock_rate` | Taxa de estoque negativo | inventory | `ratio(negative_stock_products, active_products) x 100` | percent | decrease | 1 |
| `inventory.excess_count` | Produtos em excesso | inventory | `value(excess_stock_products)` | count | decrease | 1 |
| `inventory.slow_moving_count` | Produtos parados | inventory | `value(slow_moving_products)` | count | decrease | 1 |
| `inventory.no_sale_count` | Estoque sem venda | inventory | `value(no_sale_products)` | count | decrease | 1 |
| `inventory.adjustment_quantity` | Ajustes de estoque | inventory | `value(stock_adjustment_quantity)` | unit | decrease | 1 |
| `inventory.loss_quantity` | Perdas de estoque | inventory | `value(stock_loss_quantity)` | unit | decrease | 1 |
| `inventory.damage_quantity` | Avarias | inventory | `value(stock_damage_quantity)` | unit | decrease | 1 |
| `inventory.expiring_lots` | Lotes próximos da validade | inventory | `value(expiring_lots)` | count | decrease | 1 |
| `inventory.expired_lots` | Lotes vencidos | inventory | `value(expired_lots)` | count | decrease | 1 |
| `inventory.movement_count` | Movimentações de estoque | inventory | `value(stock_movement_count)` | count | informational | 1 |
| `inventory.abc_capital_share` | Participação de capital na curva ABC | inventory | `ratio(scoped_inventory_value, inventory_cost_value) x 100` | percent | target | 1 |
| `inventory.xyz_variability` | Variabilidade da curva XYZ | inventory | `ratio(demand_stddev, average_daily_units) x 100` | percent | decrease | 1 |
| `purchases.net_value` | Valor comprado | purchases | `value(purchase_value)` | BRL | target | 1 |
| `purchases.quantity` | Quantidade comprada | purchases | `value(purchase_quantity)` | unit | target | 1 |
| `purchases.order_count` | Pedidos de compra | purchases | `value(purchase_count)` | count | informational | 1 |
| `purchases.average_order` | Compra média | purchases | `ratio(purchase_value, purchase_count)` | BRL | target | 1 |
| `purchases.average_unit_cost` | Custo médio comprado | purchases | `ratio(purchase_value, purchase_quantity)` | BRL | decrease | 1 |
| `purchases.discount_value` | Desconto em compras | purchases | `value(purchase_discount)` | BRL | increase | 1 |
| `purchases.discount_rate` | Taxa de desconto em compras | purchases | `ratio(purchase_discount, purchase_merchandise) x 100` | percent | increase | 1 |
| `purchases.bonus_value` | Bonificações | purchases | `value(purchase_bonus)` | BRL | increase | 1 |
| `purchases.freight_value` | Fretes | purchases | `value(purchase_freight)` | BRL | decrease | 1 |
| `purchases.freight_rate` | Frete sobre compras | purchases | `ratio(purchase_freight, purchase_value) x 100` | percent | decrease | 1 |
| `purchases.tax_value` | Tributos sobre compras | purchases | `value(purchase_tax)` | BRL | informational | 1 |
| `purchases.cancellation_rate` | Cancelamento de compras | purchases | `ratio(cancelled_purchases, purchase_count) x 100` | percent | decrease | 1 |
| `purchases.return_rate` | Devolução de compras | purchases | `ratio(returned_purchase_value, purchase_value) x 100` | percent | decrease | 1 |
| `purchases.receipt_rate` | Pedidos recebidos | purchases | `ratio(received_purchase_count, purchase_count) x 100` | percent | increase | 1 |
| `purchases.received_value` | Valor recebido | purchases | `value(received_purchase_value)` | BRL | increase | 1 |
| `purchases.receipt_fill_rate` | Atendimento de quantidade comprada | purchases | `ratio(received_purchase_quantity, purchase_quantity) x 100` | percent | increase | 1 |
| `purchases.frequency` | Frequência de compra | purchases | `ratio(purchase_count, active_days)` | order/day | target | 1 |
| `purchases.multiple_adherence` | Aderência ao múltiplo de compra | purchases | `ratio(multiple_adherent_lines, purchase_line_count) x 100` | percent | increase | 1 |
| `purchases.emergency_rate` | Compras emergenciais | purchases | `ratio(emergency_purchase_count, purchase_count) x 100` | percent | decrease | 1 |
| `purchases.post_purchase_coverage` | Cobertura após compra | purchases | `ratio(inventory_available, average_daily_units)` | day | target | 1 |
| `suppliers.active_count` | Fornecedores ativos | suppliers | `value(active_supplier_count)` | count | target | 1 |
| `suppliers.supply_share` | Participação no abastecimento | suppliers | `ratio(scoped_purchase_value, purchase_value) x 100` | percent | target | 1 |
| `suppliers.average_lead_time` | Lead time médio | suppliers | `ratio(lead_time_days_total, receipt_count)` | day | decrease | 1 |
| `suppliers.on_time_rate` | Pontualidade | suppliers | `ratio(on_time_receipts, receipt_count) x 100` | percent | increase | 1 |
| `suppliers.fill_rate` | Taxa de atendimento | suppliers | `ratio(received_purchase_quantity, purchase_quantity) x 100` | percent | increase | 1 |
| `suppliers.cost_variation` | Variação de custo do fornecedor | suppliers | `ratio(cost_change_value, previous_cost_value) x 100` | percent | decrease | 1 |
| `suppliers.purchase_frequency` | Frequência por fornecedor | suppliers | `ratio(scoped_purchase_count, active_days)` | order/day | target | 1 |
| `suppliers.return_rate` | Devoluções ao fornecedor | suppliers | `ratio(returned_purchase_value, purchase_value) x 100` | percent | decrease | 1 |
| `suppliers.quality_score` | Qualidade do fornecimento | suppliers | `ratio(supplier_passed_lines, purchase_line_count) x 100` | percent | increase | 1 |
| `suppliers.failure_rate` | Falhas de fornecimento | suppliers | `ratio(supplier_failed_lines, purchase_line_count) x 100` | percent | decrease | 1 |
| `suppliers.stockout_association` | Ruptura associada ao fornecedor | suppliers | `ratio(supplier_stockout_products, supplier_product_count) x 100` | percent | decrease | 1 |
| `suppliers.top5_concentration` | Concentração nos cinco fornecedores | suppliers | `ratio(top5_supplier_value, purchase_value) x 100` | percent | decrease | 1 |
| `suppliers.dependency` | Dependência do principal fornecedor | suppliers | `ratio(top_supplier_value, purchase_value) x 100` | percent | decrease | 1 |
| `suppliers.product_coverage` | Produtos cobertos por fornecedor | suppliers | `ratio(supplier_product_count, active_supplier_count)` | ratio | increase | 1 |
| `suppliers.average_minimum_order` | Pedido mínimo médio | suppliers | `ratio(minimum_order_total, supplier_product_count)` | unit | decrease | 1 |
| `margin.cogs` | CMV | margin | `value(cogs)` | BRL | decrease | 1 |
| `margin.gross_profit` | Lucro bruto | margin | `difference(net_revenue, cogs)` | BRL | increase | 1 |
| `margin.gross_percent` | Margem bruta percentual | margin | `ratio(gross_profit, net_revenue) x 100` | percent | increase | 1 |
| `margin.markup` | Markup | margin | `ratio(gross_profit, cogs) x 100` | percent | increase | 1 |
| `margin.markdown` | Markdown | margin | `ratio(discount_amount, gross_revenue) x 100` | percent | decrease | 1 |
| `margin.discount_on_price` | Desconto sobre preço | margin | `ratio(discount_amount, gross_revenue) x 100` | percent | decrease | 1 |
| `margin.profit_per_unit` | Lucro bruto por unidade | margin | `ratio(gross_profit, units_sold)` | BRL | increase | 1 |
| `margin.profit_per_sale` | Lucro bruto por venda | margin | `ratio(gross_profit, completed_sales)` | BRL | increase | 1 |
| `margin.gmroi` | GMROI | margin | `ratio(gross_profit, average_inventory_cost)` | ratio | increase | 1 |
| `margin.inventory_return` | Retorno sobre estoque | margin | `ratio(gross_profit, inventory_cost_value) x 100` | percent | increase | 1 |
| `margin.margin_loss` | Perda de margem por desconto | margin | `value(discount_amount)` | BRL | decrease | 1 |
| `margin.price_dispersion` | Dispersão de preços | margin | `ratio(price_stddev, average_price) x 100` | percent | decrease | 1 |
| `margin.price_variation` | Variação de preço | margin | `ratio(price_change_value, previous_price_value) x 100` | percent | target | 1 |
| `margin.weighted_price` | Preço médio ponderado | margin | `ratio(gross_revenue, units_sold)` | BRL | target | 1 |
| `margin.revenue_retention` | Retenção de receita após descontos | margin | `ratio(net_revenue, gross_revenue) x 100` | percent | increase | 1 |
| `margin.cost_to_revenue` | CMV sobre receita | margin | `ratio(cogs, net_revenue) x 100` | percent | decrease | 1 |
| `margin.product_contribution` | Contribuição por produto | margin | `value(scoped_gross_profit)` | BRL | increase | 1 |
| `margin.category_contribution` | Contribuição por categoria | margin | `value(scoped_gross_profit)` | BRL | increase | 1 |
| `margin.branch_contribution` | Contribuição por filial | margin | `value(scoped_gross_profit)` | BRL | increase | 1 |
| `margin.negative_margin_rate` | Produtos com margem negativa | margin | `ratio(negative_margin_products, sold_product_count) x 100` | percent | decrease | 1 |
| `operations.data_freshness` | Freshness analítica | operations | `value(freshness_seconds)` | second | decrease | 1 |
| `operations.source_lag` | Atraso da fonte | operations | `value(source_lag_seconds)` | second | decrease | 1 |
| `operations.completeness` | Completude | operations | `ratio(valid_records, received_records) x 100` | percent | increase | 1 |
| `operations.rejection_rate` | Taxa de rejeição | operations | `ratio(rejected_records, received_records) x 100` | percent | decrease | 1 |
| `operations.duplicate_rate` | Taxa de duplicidade | operations | `ratio(duplicate_records, received_records) x 100` | percent | decrease | 1 |
| `operations.consistency` | Consistência | operations | `ratio(quality_passed_records, quality_evaluated_records) x 100` | percent | increase | 1 |
| `operations.processed_volume` | Volume processado | operations | `value(received_records)` | record | increase | 1 |
| `operations.ingestion_duration` | Tempo de ingestão | operations | `value(processing_seconds)` | second | decrease | 1 |
| `operations.throughput` | Vazão da ingestão | operations | `ratio(received_records, processing_seconds)` | record/second | increase | 1 |
| `operations.integration_availability` | Disponibilidade da integração | operations | `ratio(successful_batches, batch_count) x 100` | percent | increase | 1 |
| `operations.failed_batches` | Importações com falha | operations | `value(failed_batches)` | count | decrease | 1 |
| `operations.quality_incidents` | Incidentes de qualidade | operations | `value(quality_incidents)` | count | decrease | 1 |
| `operations.analytics_duration` | Tempo de atualização analítica | operations | `value(analytics_processing_seconds)` | second | decrease | 1 |
| `operations.cache_hit_rate` | Cache hit rate | operations | `ratio(cache_hits, cache_requests) x 100` | percent | increase | 1 |
| `operations.backfill_count` | Backfills executados | operations | `value(backfill_count)` | count | informational | 1 |
| `operations.recomputation_count` | Recomputações executadas | operations | `value(recomputation_count)` | count | informational | 1 |

## Contrato comum

Todos os indicadores operacionais declaram descrição, objetivo, granularidade, dimensões e filtros permitidos, campos necessários, fonte, periodicidade, owner, tratamento de nulos, divisão por zero, arredondamento, comparação, dependências, limitações, interpretação, impacto e drill-down. A API `GET /api/v1/analytics/kpis` expõe o contrato integral e aplica a permissão financeira.

## KPIs indisponíveis

| Código | Nome | Dados necessários | Motivo |
|---|---|---|---|
| `margin.contribution_per_square_meter` | Contribuição por metro quadrado | store_area_square_meters | O cadastro canônico não possui área física da filial. |
| `purchases.realized_vs_planned` | Realizado versus planejado | approved_purchase_plan | Ainda não existe fonte canônica de planejamento de compras. |
| `inventory.forecast_accuracy` | Acurácia da previsão | forecast_series | Previsões por ML pertencem a uma etapa futura. |

## Regras de cálculo

- A AST aceita somente `value`, `sum`, `difference`, `ratio` e `product`; não há SQL ou código fornecido por usuário.
- Ausência de uma medida em um conjunto com dados equivale a zero; conjunto vazio é reportado como `no_data`.
- Divisão por zero retorna `null` e `reason=zero_denominator`.
- Resultados usam `ROUND_HALF_UP` com quatro casas; a UI aplica precisão da unidade.
- Resultados históricos carregam `formula_version` e `data_version`.
- Filtros e drill-down sempre passam por grant de tenant/empresa/filial e RLS.
