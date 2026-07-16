# ADR 0006 — Modelo multi-tenant

- Status: Aceito
- Data: 2026-07-16

## Decisão

`tenant_id` é a fronteira primária de isolamento. Usuários são identidades globais e participam de tenants por `memberships`. Empresas pertencem a um tenant; filiais pertencem a uma empresa do mesmo tenant. O contexto ativo fica na sessão e somente pode ser trocado após validação de membership e escopo.

A aplicação aplica defesa em profundidade:

1. sessão autenticada;
2. membership ativa;
3. autorização por permissão e escopo;
4. filtros explícitos nos repositórios;
5. PostgreSQL RLS;
6. auditoria de negações.

Cabeçalhos fornecidos pelo navegador não são fonte de confiança para tenant.
