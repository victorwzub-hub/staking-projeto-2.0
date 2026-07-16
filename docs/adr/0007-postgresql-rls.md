# ADR 0007 — PostgreSQL Row-Level Security

- Status: Aceito
- Data: 2026-07-16

## Decisão

Tabelas com dados organizacionais recebem `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY`. Cada transação autenticada configura, por `set_config(..., true)`, `app.current_user_id`, `app.current_tenant_id`, `app.is_platform_admin` e, somente para aceite de convite, `app.invitation_token_hash`.

As políticas usam `current_setting(..., true)` e nunca valores de cabeçalhos enviados pelo navegador. O contexto é local à transação, evitando permanência quando a conexão retorna ao pool. Jobs precisam declarar explicitamente o tenant antes de consultar dados tenant-scoped.

Migrations usam uma credencial administrativa separada. API e worker usam uma role PostgreSQL comum sem `SUPERUSER`, `CREATEROLE` ou `BYPASSRLS`. O Compose cria essa role de forma idempotente; o smoke test verifica seus atributos antes de aprovar a stack.

## Alternativas rejeitadas

- filtros manuais como única barreira: sujeitos a omissão em novos repositórios;
- schema por tenant: custo operacional e de migrations inadequado neste estágio;
- banco por tenant: isolamento forte, porém custo e administração excessivos para milhares de organizações;
- role proprietária das tabelas na aplicação: aumenta o risco de bypass acidental.

## Riscos e controles

- RLS precisa de PostgreSQL real; SQLite e mocks não comprovam isolamento;
- queries administrativas precisam declarar explicitamente `app.is_platform_admin`;
- `SET LOCAL` depende de transação ativa e deve ser reaplicado em cada unidade de trabalho;
- o usuário comum do banco não pode ser proprietário das tabelas nem receber `BYPASSRLS`;
- testes negativos cobrem troca de UUID, membership suspensa/revogada, escopos, reutilização de pool e jobs sem tenant.
