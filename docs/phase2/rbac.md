# RBAC e escopos

## Catálogo

Permissões são chaves estáveis e versionadas, por exemplo `company.create`, `branch.update`, `membership.manage` e `audit.read`.

Papéis iniciais:

- `platform_admin`;
- `tenant_owner`;
- `tenant_admin`;
- `company_admin`;
- `branch_manager`;
- `analyst`;
- `consultant`;
- `accountant`;
- `viewer`.

Autorização nunca depende apenas do nome do papel.

## Regras

- deny-by-default;
- papel de sistema global e imutável;
- papel customizado pertence a um tenant;
- platform roles não são atribuíveis pela API comum;
- ator só delega permissões que possui;
- company/branch assignment deve respeitar hierarquia;
- o último `tenant_owner` não pode ser removido;
- remoção de assignment afeta a próxima resolução de sessão, sem cache autoritativo.

## Administração

Crie papéis em `/app/roles`, selecione permissões delegáveis e atribua a memberships. Alterações usam versionamento otimista e são auditadas.
