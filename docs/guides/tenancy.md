# Multi-tenancy e PostgreSQL RLS

## Modelo

- `users`: identidade global;
- `tenants`: unidade principal de isolamento;
- `economic_groups`: agrupamento opcional dentro do tenant;
- `companies`: pertencem a um tenant;
- `branches`: pertencem a empresa do mesmo tenant;
- `memberships`: vinculam usuário global a tenant;
- `teams`: agrupam memberships do mesmo tenant.

Memberships possuem estados `pending`, `active`, `suspended` e `revoked`.

## Contexto seguro

O contexto é derivado da sessão e de membership válida. Não confie em `X-Tenant-ID`. Para trocar contexto:

1. cliente solicita tenant/empresa/filial;
2. backend valida membership e relações;
3. backend atualiza a sessão;
4. backend registra auditoria;
5. nova transação recebe o contexto RLS.

## RLS

A role de aplicação deve ter `NOBYPASSRLS`. A cada transação tenant-scoped, a aplicação usa `SET LOCAL` para variáveis de contexto. `SET LOCAL` desaparece no commit/rollback, evitando vazamento no pool.

O script `scripts/prepare-integration-database.py` cria/configura a role de teste. Os testes de integração verificam leitura/escrita cruzada, reuso de conexão e rollback.

## Regras operacionais

- jobs assíncronos exigem tenant explícito;
- platform admin usa contexto explicitamente marcado e auditado;
- IDs de outro tenant retornam resposta indistinguível de recurso inexistente;
- relações empresa/filial/equipe possuem FKs compostas de mesmo tenant;
- nunca desabilite RLS para corrigir uma consulta.
