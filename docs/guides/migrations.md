# Migrations

## Estratégia

A primeira migration real é `20260716_0001`, uma base consolidada de identidade, tenancy, RBAC, onboarding e auditoria. Ela possui `upgrade` e `downgrade`, cria constraints, índices, seeds versionados, RLS e triggers.

## Comandos

```bash
cd apps/api
alembic heads
alembic current
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Gate automatizado com PostgreSQL real:

```bash
TEST_ADMIN_DATABASE_URL='postgresql+psycopg://...' ./scripts/test-migrations.sh
```

## Railway/produção

Execute migrations em uma etapa exclusiva antes de liberar tráfego. Apenas um processo usa a role administrativa. API e worker iniciam somente após sucesso. Falha bloqueia o deploy.

Mudanças destrutivas futuras exigem expansão e contração. Não execute seed perigoso automaticamente e não use a role de migration na aplicação.

## Rollback

Rollback de código não implica automaticamente downgrade. Avalie compatibilidade e perda de dados antes de `alembic downgrade`. A migration inicial é reversível para ambientes descartáveis e testes.
