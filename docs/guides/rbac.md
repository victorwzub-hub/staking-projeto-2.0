# RBAC e escopos

## Princípios

- deny-by-default;
- autorização por permissão, não por nome de papel;
- menor privilégio;
- papéis do sistema imutáveis;
- papéis customizados pertencem ao tenant;
- invalidação imediata: permissões são recalculadas por requisição.

## Papéis iniciais

`platform_admin`, `tenant_owner`, `tenant_admin`, `company_admin`, `branch_manager`, `analyst`, `consultant`, `accountant` e `viewer`.

## Escopos

Atribuições podem possuir escopo de plataforma, tenant, empresa ou filial. O backend verifica que o ator pode delegar todas as permissões pedidas e que o escopo está dentro do seu próprio alcance.

## Operações protegidas

- catálogo: `role.read`;
- criar/alterar/excluir papel: `role.create`, `role.update`, `role.delete`;
- atribuir/remover papel: `role.assign`;
- memberships: `membership.manage`;
- organizações: permissões `company.*`, `branch.*` e `tenant.*`;
- auditoria: `audit.read`;
- plataforma: `platform.admin`.

## Guardas

- não editar/excluir papel de sistema por API comum;
- não excluir o último `tenant_owner`;
- não atribuir permissão não delegável pelo ator;
- não elevar escopo por payload;
- remover atribuição afeta a próxima requisição.
