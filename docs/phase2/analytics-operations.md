# Operação da plataforma analítica — Etapa 2C

## Rotina

1. Verifique `/health`, `/readiness` e `GET /api/v1/analytics/freshness`.
2. Consulte `GET /api/v1/analytics/observability` com o mesmo usuário/escopo que será diagnosticado.
3. Correlacione `last_refresh_job_id` com os eventos estruturados `analytics_refresh_completed` ou `analytics_refresh_failed`.
4. Confirme watermark, `data_version`, qualidade, fatos/agregados e cache antes de intervir.
5. Use os endpoints de refresh, backfill ou recompute; não altere tabela analítica por SQL.

O dashboard versionado fica em `infra/observability/analytics-dashboard.json`; limiares e runbooks ficam em `infra/observability/analytics-alerts.yml`. A integração com o provedor de métricas deve consultar a API com uma identidade técnica de menor privilégio e transformar logs pelo template de rota, nunca por URL com IDs.

## Refresh failed

Localize a causa no log do worker, preserve o correlation ID em logs/traces e confira PostgreSQL/Redis. Falha transitória usa retry limitado. Falha de dados deve ser corrigida no canônico 2B e reprocessada. Não avance manualmente o watermark: a versão anterior continua válida até uma execução completar.

## Fila sem progresso

Se `refresh_queued > 0`, `refresh_running == 0` por dez minutos, valide workers e fila `analytics-refresh`. Reinicie somente o worker sem heartbeat, após confirmar que nenhum processo ainda detém o job. O advisory lock torna uma mensagem duplicada inócua, mas não substitui o diagnóstico do broker.

## Freshness e watermark

O alerta inicial é lag acima de 30 minutos por dez minutos. Compare o watermark analítico com o lote canônico mais recente. Se a origem chegou atrasada dentro do lookback, execute refresh incremental. Fora dele, use backfill com datas explícitas. O lag não é atraso da origem ERP; mede a publicação analítica.

## Qualidade baixa

Qualidade abaixo de 98% por quinze minutos exige verificar os fatos `data_quality` e os resultados da Etapa 2B. Não esconda a falha recalculando o KPI: corrija mapping/regra/origem e reprocesse. O dashboard continua exibindo o score junto ao resultado.

## Cache

Hit rate abaixo de 60% só alerta após cem requisições. Confirme estabilidade de filtros e `data_version`; refresh frequente invalida logicamente chaves antigas. Redis indisponível retorna erro explícito, pois servir resultado sem conhecer versão/grants não é seguro. Chaves expiram e não devem ser apagadas com glob em produção.

## Latência da API

Para p95 acima de dois segundos, separe tempo HTTP, consulta de agregado e cache. Use `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` com tenant/RLS e parâmetros representativos, sem copiar PII. Verifique se a consulta caiu no agregado correto e se uma combinação dimensional de alta cardinalidade foi recusada. Compare com [`analytics-benchmark.md`](analytics-benchmark.md), sem tratar números sintéticos como SLO real.

## Backfill e recompute

Backfill relê canônico em uma janela histórica; recompute refaz derivados. Ambos exigem `analytics.manage`, são auditados e serializados por tenant. Agende fora do pico, monitore duração/linhas/pico de memória e interrompa somente pelo endpoint de cancelamento. Mais de dez recomputes/hora indica loop operacional ou automação defeituosa.

## Crescimento de storage

Para aumento superior a 30% ao dia, compare fatos por tipo, agregados por grão e batches de origem. Confirme que `grain_key` continua única e que não houve nova granularidade inesperada. Antes de retenção/particionamento, valide obrigações fiscais, lineage e capacidade de reconstrução. Nunca apague fatos isolados sem o workflow de retenção aprovado.

## Recuperação

O warehouse pode ser reconstruído do canônico, mas metas e histórico de metas precisam de backup. Restaure PostgreSQL em ponto consistente, rode migrations, valide RLS, recalcule a janela necessária e compare contagens/lineage. RPO/RTO de produção só podem ser publicados após exercício de restauração.
