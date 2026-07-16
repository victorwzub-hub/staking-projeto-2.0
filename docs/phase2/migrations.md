# Migrations

## Base atual

Revision: `20260716_0001`.

A migration cria 24 tabelas, índices, constraints, triggers, catálogo de permissões, papéis de sistema, termos de staging e 14 políticas RLS. `upgrade` e `downgrade` são implementados.

## Comandos

```bash
cd apps/api
alembic heads
alembic current
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

O script `scripts/test-migrations.sh` exige PostgreSQL real e executa upgrade, downgrade, novo upgrade e upgrade idempotente.

## Deploy

`pharma-migrate` usa advisory lock para garantir um executor. Depois da migration, concede DML mínimo à role da aplicação e revoga escrita em catálogos estruturais.

Migrations destrutivas futuras exigem expansão/contração, compatibilidade entre versões e plano explícito de rollback.
