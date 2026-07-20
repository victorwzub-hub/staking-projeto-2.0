# Arquitetura da Fase 2

## Decisão central

A identidade e a autorização permanecem dentro do monólito modular. A API FastAPI concentra casos de uso, autorização e transações; o worker reutiliza os mesmos contratos e recebe contexto de tenant explícito. PostgreSQL é a fonte de verdade. Redis não é a fonte primária de sessão.

## Identidade e sessão

`users` é uma identidade global. O mesmo usuário pode participar de vários tenants por `memberships`. A aplicação web usa um token opaco aleatório em cookie HttpOnly; apenas o hash HMAC do token é persistido em `sessions`. A sessão contém contexto ativo de tenant, empresa e filial, atualizado somente após autorização no backend.

Redis é usado para rate limiting e broker, não para tornar a sessão válida. A remoção de membership ou papel afeta a próxima requisição, pois permissões são recalculadas no banco.

## Fronteira multi-tenant

`tenant_id` é a principal fronteira. A defesa é composta por:

1. sessão válida;
2. membership ativa;
3. contexto autorizado;
4. permissão específica deny-by-default;
5. consultas tenant-scoped;
6. PostgreSQL RLS com `SET LOCAL` dentro da transação;
7. constraints compostas que impedem relações entre tenants;
8. auditoria de negações.

O navegador não define o tenant por header confiável. Trocas de contexto usam `POST /api/v1/me/context` e persistem na sessão após validação.

## RBAC

Permissões são capacidades atômicas versionadas. Papéis apenas agregam permissões; endpoints nunca autorizam somente pelo nome do papel. Papéis de sistema são imutáveis por operações comuns. Papéis customizados pertencem a um tenant e não podem receber capacidades que o ator não pode delegar.

Atribuições podem ser limitadas a tenant, empresa ou filial. Constraints verificam a coerência dos escopos.

## Auditoria

`audit_events` é append-only. Trigger de banco bloqueia `UPDATE` e `DELETE` comuns. Eventos registram ator, usuário efetivo, contexto, ação, resultado, correlation ID, recurso e metadata sanitizada. Senhas, tokens, cookies e hashes de senha não são registrados.

Eventos que precisam sobreviver a uma resposta 401/403 são confirmados antes da exceção HTTP.

## E-mail e worker

O serviço de aplicação produz comandos de e-mail sem acoplamento ao provedor. O adapter de desenvolvimento grava mensagens em spool local com token mascarado nos logs. Dramatiq executa o envio com retries e retorna `None`.

## Deploy

Serviços separados: `api`, `web`, `worker`, PostgreSQL e Redis. Um serviço/etapa exclusiva executa migrations antes de liberar tráfego. API e worker usam a role de aplicação sem `BYPASSRLS`; a role administrativa de migration não é usada em runtime.

## Evolução

A Etapa 2B consome `AuthContext`, tenant, escopo e permissões para integrar ERPs e publicar o modelo canônico. A Etapa 2C deriva desse canônico um warehouse no PostgreSQL, camada semântica segura, cache versionado e dashboard. Os detalhes de grãos, SCD2, refresh, segurança e critérios de evolução para um warehouse dedicado estão em [`analytics-platform.md`](analytics-platform.md) e no [ADR 0016](../adr/0016-postgresql-analytics-semantic-layer.md).
