# Migrations

## Base atual

Head atual: `20260718_0004`.

As quatro revisões criam identidade/escopo, endurecimento 2A.2, plataforma canônica 2B e warehouse/camada semântica 2C. A revisão `20260718_0004` adiciona dez tabelas analíticas, índices, constraints, oito permissões e políticas RLS forçadas. Todas implementam `upgrade` e `downgrade`.

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
