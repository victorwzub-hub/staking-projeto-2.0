# Observabilidade da Fase 2

## Implementado

- logs JSON estruturados via Structlog;
- correlation ID validado e propagado em todas as respostas;
- evento `http_request_completed` com método, template de rota, status e duração;
- evento `http_request_failed` sem registrar payload, query string ou identificadores da URL;
- eventos persistidos de autenticação, sessão e segurança;
- auditoria append-only para mutações e acessos negados;
- logs de worker, e-mail, Redis indisponível e falha de enfileiramento;
- health e readiness separados;
- diagnósticos de Compose impressos em falha.

- estatísticas persistidas por etapa de integração (bytes, duração, registros/s e qualidade);
- resumo RBAC-scoped em `GET /api/v1/integrations/observability`;
- eventos de lote/outbox, retries e dead letters correlacionáveis sem payload sensível.

O painel, alertas e SLOs da plataforma de dados estão em
[`data-platform.md`](data-platform.md#observabilidade-e-alertas).

## Métricas operacionais

No Railway, CPU, memória, reinícios e rede são providos pela plataforma. Contagens e latências de negócio são derivadas dos campos estruturados dos logs (`event`, `status_code`, `duration_ms`, `outcome`) sem PII em labels. Antes de produção, devem ser configurados painéis e alertas para:

- taxa de login aceito/negado e bloqueios;
- p50/p95/p99 por template de rota;
- HTTP 401, 403, 429 e 5xx;
- criação/revogação/expiração de sessão;
- falhas de Redis, PostgreSQL e filas;
- retries/falhas de e-mail;
- duração e falha de migrations;
- onboarding iniciado/concluído/falhado;
- acessos negados por permissão.

Não são usados e-mail, user ID, tenant ID, IP, token ou correlation ID como labels de cardinalidade não controlada.

## Alertas mínimos para staging

- readiness diferente de 200;
- migration ou deploy falhou;
- worker sem consumo de tarefas;
- repetição de erro 5xx;
- aumento de 429/403;
- Redis/PostgreSQL indisponível;
- fila de e-mails sem progresso.
