# Multi-tenancy e PostgreSQL RLS

## Modelo

`users` é identidade global. `memberships` conecta usuários a tenants. Empresas pertencem a tenant; filiais pertencem a uma empresa do mesmo tenant. Constraints compostas garantem a coerência.

## Contexto confiável

O contexto ativo é persistido na sessão. A troca segue:

1. recebe tenant/empresa/filial solicitados;
2. valida membership ativa;
3. valida hierarquia e escopo;
4. atualiza a sessão;
5. registra auditoria;
6. aplica novo contexto nas requisições seguintes.

Headers de tenant enviados pelo navegador não são fonte de confiança.

## RLS

Cada transação executa `set_config` local para usuário, tenant, platform admin e token de convite. Como o terceiro argumento é `true`, valores somem ao commit/rollback e não vazam pelo pool.

Tabelas tenant-aware usam `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY`. A role da aplicação é `NOBYPASSRLS`. O smoke test valida as flags.

## Matriz negativa

Testes de integração cobrem leitura/alteração cruzada, contexto ausente, reutilização de conexão, membership suspensa/revogada, empresa/filial divergente e ausência de membership. Devem rodar somente contra PostgreSQL real.

## Workers

Jobs tenant-aware futuros devem receber tenant explícito no comando, validar o contexto e aplicar RLS antes de consultar. Nenhum job deve inferir tenant de estado global ou de conexão reutilizada.
