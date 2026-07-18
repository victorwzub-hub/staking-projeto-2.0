# Plataforma de dados canônica e integração ERP — Etapa 2B

## Arquitetura executável

O fluxo é `origem → landing S3 → staging → qualidade → mapeamento → normalização → modelo canônico → outbox`. Dramatiq transporta somente IDs e metadados; arquivos nunca passam pelo Redis. As filas `integration-acquire`, `integration-process`, `integration-notifications` e `integration-maintenance` separam I/O externo, transformação, eventos e retenção.

O Compose sobe MinIO com bucket privado `pharma-landing`. Em produção, `OBJECT_STORAGE_BACKEND=s3` é obrigatório. O backend `filesystem` existe apenas para desenvolvimento/teste isolado. Todo objeto recebe chave segura, hash, tamanho, MIME, origem, escopo, correlação e data de retenção. O trigger `protect_immutable_landing()` impede alteração dos metadados imutáveis e exclusão antecipada.

## Catálogo e granularidade

| Tabela/grupo | Uma linha representa | Identidade/idempotência |
|---|---|---|
| `canonical_products` | um produto de uma fonte no escopo empresa/filial | tenant + fonte + external ID |
| identificadores/apresentações | um EAN/SKU ou apresentação/unidade do produto | identificador global no tenant; produto + nome |
| marcas/fabricantes/categorias | uma dimensão normalizada do tenant | nome normalizado; categoria permite pai |
| `canonical_suppliers` | um fornecedor de uma fonte e empresa | tenant + fonte + external ID |
| supplier products/costs | vínculo comercial e um período de custo | fornecedor + produto; evento de custo |
| `canonical_sales` | uma venda na data operacional | tenant + fonte + external ID + data; particionada |
| sale items/payments/adjustments | uma linha, pagamento, devolução/cancelamento/desconto | venda + linha/ocorrência |
| purchase orders/items/receipts | um pedido, item ou documento de recebimento | fonte + external ID; pedido + linha/documento |
| stock balances/snapshots | saldo corrente ou fotografia temporal por filial/produto | filial + produto; snapshot do evento |
| inventory lots/movements | lote físico ou movimento operacional | filial + produto + lote; fonte + external ID |
| product prices | vigência de preço por filial/produto | fonte + external ID + início |
| promotions/products | promoção vigente e produto participante | fonte + external ID; promoção + produto |

Todo fato consultável mantém `data_source_id`, `batch_id`, `staging_record_id`, `external_id` e `source_version` quando aplicável. `lineage_events` liga o envelope à entidade e ao ID canônico.

## SDK de conectores

`application/integrations/connectors.py` define descriptor, capacidades, autenticação, descoberta, teste, extração completa/incremental, paginação, checkpoint, timeout, cancelamento e erros classificados. Um conector não recebe sessão de banco e não pode gravar no canônico.

Para adicionar um conector:

1. Implemente o `Connector` Protocol e descriptor com chave/versão imutáveis.
2. Converta respostas externas em `ConnectorEnvelope`; nunca exponha segredo no envelope ou log.
3. Classifique falhas como autenticação, autorização, rate limit, timeout, transitória, resposta inválida, configuração, cancelamento ou permanente.
4. Respeite `page_size`, `timeout_seconds`, `checkpoint` e cancelamento cooperativo.
5. Registre a implementação no `ConnectorRegistry`, publique `connector_definitions` por migração e adicione testes determinísticos de contrato.
6. Uma quebra de schema exige nova versão e validação/publicação de novo mapping; não altere uma versão publicada.

O `deterministic-erp` é o conector de referência real da SDK. `file-upload` usa o mesmo landing/staging a partir de CSV, JSON ou NDJSON.

## Idempotência, checkpoint e concorrência

- `Idempotency-Key` é único por tenant/fonte para lote e execução.
- Arquivos repetidos são detectados por SHA-256 antes de criar novo processamento.
- Staging é único por lote/entidade/external ID/source version; páginas repetidas viram duplicados.
- Cada chunk confirma staging e atualiza `sync_checkpoints`; retry relê o objeto e continua por `ON CONFLICT DO NOTHING`.
- Cursores por fonte registram página, valor e versão.
- IDs canônicos são UUIDv5 determinísticos; fatos usam constraints naturais e `upsert` controlado.
- O `SELECT … FOR UPDATE` cobre apenas transições curtas. Extração e transformação não mantêm lock de longa duração.
- Transições de estado no domínio e trigger do banco tornam mensagens duplicadas inócuas.
- Outbox possui chave idempotente; inbox e webhooks possuem identidade externa única.
- Dead letters são criadas após retries limitados e podem originar replay explícito.

## Máquina de estados

Fluxo feliz: `created → queued → connecting → extracting → received → validating → mapping → normalizing → loading → completed|completed_with_warnings`.

Qualquer etapa ativa pode ir a `retry_scheduled`, `failed` ou `cancelled` conforme a matriz do domínio. Validação/mapping/normalização/loading podem ir a `quarantined`. Replay cria outro lote com `parent_batch_id`; estados terminais não são reabertos. Cada mudança gera `processing_state_transitions` com ator, motivo e correlation ID.

## Qualidade e quarentena

O motor implementa vinte tipos: obrigatório, tipo/data inválidos, negativo, quantidade, referência/produto/filial/fornecedor ausentes, identificador duplicado, venda sem item, total/pagamento, custo, saldo, ordem de movimento, período, atraso, volume e duplicidade provável. Severidades são informativa, aviso, erro e bloqueante.

Regras são estruturas declarativas; nenhum código configurável é executado. Bloqueantes mantêm o registro fora do canônico e criam `rejected_records`. O lote finaliza em quarentena quando há bloqueante. Resultados guardam entidade, regra, avaliados, falhas, score e detalhes. Correções são versionadas e voltam ao staging antes de um replay.

## Segurança, LGPD e credenciais

- `CredentialReference` aceita apenas URI de AWS Secrets Manager, Vault, Azure Key Vault ou variável externa. O valor secreto não entra no banco.
- RLS é habilitada e forçada em todas as tabelas de cliente; o role da aplicação não tem `BYPASSRLS`.
- FKs compostas bloqueiam relações cross-tenant, mesmo com UUID conhecido.
- Escopo de filial não enxerga/aciona integração de outra filial; escopo de empresa não atravessa empresa.
- Raw exige `integration.raw` e todo acesso gera auditoria. Downloads pelo API preservam autorização.
- Cliente de venda é pseudonimizado. Não há payload, token, segredo, e-mail ou identificador pessoal em logs.
- Upload é streaming, limitado, com extensão/MIME allowlist, nome sanitizado, path traversal bloqueado e parser incremental.
- CSV exportado prefixa células iniciadas por `=`, `+`, `-`, `@`, tab ou CR para impedir formula injection.

## Retenção, restauração e exclusão

`INTEGRATION_RETENTION_DAYS` define o mínimo do landing. O ator `cleanup_expired_landing` remove somente objetos vencidos e previamente marcados não imutáveis por um processo autorizado. Backups devem manter PostgreSQL e bucket no mesmo recovery point lógico; manifests e hashes permitem validar o pareamento restaurado. Antes de restaurar, pause workers; restaure banco/bucket; valide hashes amostrais; suba migrations; retome outbox e filas.

Solicitações LGPD devem preferir pseudonimização. Exclusão de objeto ainda sob obrigação fiscal/auditoria deve ser negada e registrada; após expiração, um workflow autorizado muda a imutabilidade e agenda limpeza.

## Operação, falhas, replay e dead letters

1. Consulte lote, etapas, estatísticas, erros e correlation ID em `/integrations`.
2. Para erro transitório, confirme disponibilidade da fonte/Redis/S3 e aguarde backoff limitado.
3. Para erro de autenticação, rotacione no secret manager e atualize somente a referência.
4. Para mapping/qualidade, publique nova versão, corrija rejeitados e use `reprocess` com nova chave idempotente.
5. Replay reutiliza o manifest imutável; nunca altere o arquivo original.
6. Para dead letter, corrija a causa, confira que não existe worker ainda processando o lote e crie replay. Não edite o estado via SQL.
7. Em backlog, reduza `INTEGRATION_CHUNK_RECORDS` se houver pressão de memória ou aumente processos das filas pesadas; preserve workers de notificações.
8. Em corrupção/hash divergente, isole o bucket/lote, mantenha evidência e restaure; não processe payload não comprovado.

## Observabilidade e alertas

`GET /api/v1/integrations/observability` expõe syncs, falhas, backlog, dead letters, registros, duplicados, bytes, throughput e qualidade sob o mesmo escopo RBAC. `processing_statistics` registra bytes, duração e registros/s. Logs estruturados de worker incluem tenant, lote, etapa, aggregate/event e classificação, sem payload.

Painel mínimo: taxa de conclusão, p50/p95 por etapa, registros/s, bytes/dia, backlog por fila, source lag, retries, dead letters, rejeição/duplicidade, score por tenant, disponibilidade/latência do conector e armazenamento. Alertas de staging:

- backlog sem redução por 15 min; dead letter > 0;
- falhas > 5% em 15 min; retry > 10% em 15 min;
- p95 do pipeline acima do SLO; fonte atrasada acima de 30 min;
- qualidade < 98% ou rejeição > 2%; duplicidade > 5%;
- worker sem heartbeat/consumo por 5 min; S3/Redis/PostgreSQL indisponível;
- bucket acima de 80% da cota ou crescimento diário anômalo.

Evite IDs de tenant, usuário, lote e correlation ID como labels Prometheus de cardinalidade aberta; mantenha-os apenas nos logs/traces.

## SLOs da Etapa 2B

- disponibilidade mensal das APIs de integração: 99,9%;
- 99% das solicitações aceitas retornam lote em até 2 s (o processamento permanece assíncrono);
- p95 de arquivo de 100 mil registros até canônico: 10 min em staging de referência;
- p95 de arquivo de 1 milhão: 60 min, sem exceder 1 GiB por worker;
- perda de payload aceito: 0; RPO do landing: 0 após resposta 2xx; RTO operacional: 60 min;
- replay idempotente: 100% sem duplicar venda, compra ou movimento;
- qualidade calculada em 100% dos registros antes da carga.

## Desenvolvimento local e benchmark

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
python scripts/benchmark-integration-data.py --records 100000 --output .local/bench/100k.ndjson
python scripts/benchmark-integration-data.py --records 1000000 --output .local/bench/1m.ndjson
```

Crie uma fonte `file-upload` na UI, envie o NDJSON como domínio `all` e registre: tamanho, tempo total, pico de RSS do worker, registros/s, p95 por etapa e contagens finais. Perfis recomendados: 10k no CI opt-in, 100k em PR de performance, 1M/5M em staging. O gerador é streaming, determinístico e reporta hash, throughput e pico de memória.

O resultado anteriormente observado para 10.000 registros (3.672,81 registros/s e
0,03 MiB de pico) mede **somente o gerador**: serialização JSON, hash SHA-256 e
escrita sequencial do arquivo. O pico vem de `tracemalloc` e representa alocações
Python rastreadas no processo gerador; não é RSS, memória do worker nem memória
total da stack. Essa medição não inclui upload, fila, parsing, staging, qualidade,
mapeamento, normalização ou carga PostgreSQL. O throughput integral deve ser medido
separadamente, do aceite do lote ao estado terminal, usando as estatísticas
persistidas por etapa e a telemetria dos containers.

## Gates de CI

CI executa Ruff, MyPy, Pytest unitário, ciclo Alembic upgrade/downgrade/upgrade, RLS negativo, pipeline determinístico real no PostgreSQL, OpenAPI drift, TypeScript, ESLint, Vitest, build, Playwright e Compose com PostgreSQL/Redis/MinIO/API/worker/web. O E2E real-stack executa o simulador duas vezes e verifica cardinalidade canônica estável.

Os achados não corrigíveis das imagens base e suas mitigações estão registrados em
[`phase2b-trivy-residual-risks.md`](../audits/phase2b-trivy-residual-risks.md).
