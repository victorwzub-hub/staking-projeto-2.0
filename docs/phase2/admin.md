# Manual do administrador

## Platform admin

O painel `/app/platform` permite listar tenants e usuários e alterar status com motivo obrigatório. Não é possível suspender a própria conta nem o último platform admin ativo.

## Tenant owner/admin

- edite o tenant em `/app/tenant`;
- gerencie grupos, empresas e filiais;
- convide usuários e acompanhe convites;
- suspenda ou revogue memberships;
- crie equipes;
- crie papéis customizados e atribuições;
- consulte auditoria;
- revogue sessões da própria conta.

## Procedimentos sensíveis

Confirme identidade e escopo antes de suspender usuários, remover papéis ou arquivar estruturas. Nunca altere o banco manualmente para contornar RBAC/RLS.
