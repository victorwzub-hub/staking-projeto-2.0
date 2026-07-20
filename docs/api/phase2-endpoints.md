# Contrato HTTP da Fase 2

Todos os endpoints usam `/api/v1`, schemas Pydantic, correlation ID e formato consistente de erro. Operações mutáveis autenticadas exigem CSRF.

## Públicos

| Método | Rota | Finalidade |
|---|---|---|
| POST | `/auth/register` | Cadastro com resposta neutra e verificação por e-mail. |
| POST | `/auth/verify-email` | Consome token de verificação. |
| POST | `/auth/resend-verification` | Reenvio neutro e rate limited. |
| POST | `/auth/login` | Cria sessão opaca e cookies. |
| POST | `/auth/forgot-password` | Inicia recuperação sem enumerar e-mail. |
| POST | `/auth/reset-password` | Consome token e redefine senha. |
| GET | `/health` | Liveness. |
| GET | `/readiness` | PostgreSQL e Redis. |

## Sessão e identidade

`/auth/logout`, `/auth/logout-all`, `/auth/change-password`, `/sessions`, `/sessions/refresh`, `/sessions/{id}`, `/me`, `/me/profile`, `/me/security-events` e `/me/context`.

## Onboarding e organizações

- `/onboarding`, `/onboarding/terms`, `/onboarding/complete`;
- `/tenants/current` — `tenant.read`/`tenant.update`;
- `/economic-groups` — permissões `company.*`;
- `/companies` — `company.create/read/update/delete`;
- `/branches` — `branch.create/read/update/delete`.

## Pessoas e autorização

- `/users` e `/memberships` — `user.read`/`membership.manage`;
- `/teams` — `team.create/read/update/delete`;
- `/invitations` — `user.invite`/`user.read`;
- `/permissions` — `role.read`;
- `/roles` — `role.create/read/update/delete`;
- `/roles/assignments` — `role.assign`;
- `/audit-events` — `audit.read`.

## Plataforma

`/platform/tenants`, `/platform/users` e `/platform/users/{id}/status` exigem `platform.admin` e auditoria. Suspensão revoga sessões ativas.

## Integrações e dados canônicos (Etapa 2B)

Todas as rotas abaixo usam o prefixo `/integrations`, respeitam o contexto de tenant/empresa/filial e exigem as permissões granulares `integration.*`, `data.*`, `quality.*` ou `lineage.*` indicadas no OpenAPI.

- Catálogo e configuração: `/connectors`, `/credential-references`, `/sources`, `/sources/{id}/test`, `/mappings` e `/mappings/validate`;
- ingestão: `/sources/{id}/sync` aceita `Idempotency-Key`, enquanto `/sources/{id}/upload` recebe `multipart/form-data` por streaming;
- operação: `/batches`, `/batches/{id}`, `/cancel`, `/reprocess`, `/errors`, `/rejections`, `/quality`, `/lineage` e `/report.csv`;
- dados brutos: `/batches/{id}/raw` e `/raw/download` exigem permissão especial e geram evento de auditoria;
- observabilidade: `/observability` agrega execução, backlog, dead letter, volume, throughput e qualidade;
- consumo canônico: `/canonical/products`, `/suppliers`, `/sales`, `/purchases`, `/inventory` e `/prices`, todos com paginação por cursor opaco.

## Analytics e camada semântica (Etapa 2C)

Rotas sob `/analytics` exigem `analytics.view` e mantêm tenant/grants/filtros no servidor. Métricas financeiras exigem `analytics.financial`; detalhe, exportação, metas e operação exigem permissões dedicadas.

- catálogo/consulta: `/kpis`, `/kpis/{code}`, `/results`, `/kpis/{code}/result` e `/comparisons`;
- análise: `/timeseries`, `/ranking`, `/composition` e `/drilldown`;
- contexto: `/filters`, `/dimensions/{type}`, `/freshness`, `/quality` e `/observability`;
- metas: `/goals`, `/goals/{id}` e `/goals/{id}/history`;
- operação: `/refresh`, `/refresh/{id}` e `/refresh/{id}/cancel`, com modo `backfill` ou `recompute` no payload;
- exportação: `/export.csv` aplica rate limit, auditoria, escopo, limite de linhas e proteção contra formula injection.

Resultados trazem versão de fórmula/dados, freshness, qualidade e cache. Comparações incluem período anterior, ano anterior, média móvel, rede autorizada e categoria quando aplicável. O catálogo não expõe valores financeiros sem a permissão correspondente.

O artefato versionado `docs/openapi/phase2-openapi.json` é gerado diretamente da aplicação e contém os schemas completos das rotas publicadas.

## Erros

Respostas não revelam a existência de recurso de outro tenant. Erros de autenticação, autorização, conflito, validação e rate limit usam código estável, mensagem segura e detalhes JSON serializáveis.
