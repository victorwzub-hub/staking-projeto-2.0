# ADR 0008 — RBAC, permissões e escopos

- Status: Aceito
- Data: 2026-07-16

## Decisão

Autorização é deny-by-default e baseada em permissões estáveis, não no nome do papel. Papéis de sistema são templates globais e imutáveis; papéis customizados pertencem a um tenant. Atribuições ligam membership, papel e escopo opcional de empresa/filial.

Escopos suportados: plataforma, tenant, empresa e filial. `platform_admin` é um atributo global de usuário criado somente por comando de bootstrap. A aplicação impede delegação acima do escopo do ator e remoção do último `tenant_owner`.
