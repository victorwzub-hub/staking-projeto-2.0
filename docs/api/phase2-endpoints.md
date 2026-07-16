# Contrato HTTP da Fase 2

Todos os endpoints usam `/api/v1`, schemas Pydantic, correlation ID e formato consistente de erro. Operações mutáveis autenticadas exigem CSRF.

## Públicos

| Método | Rota | Finalidade |
|---|---|---|
| POST | `/auth/register` | Cadastro com resposta neutra e verificação por e-mail. |
| POST | `/auth/verify-email` | Consome token de verificação. |
| POST | `/auth/resend-verification` | Reenvio neutro e rate limited. |
| POST | `/auth/login` | Cria sessão opaca e cookies. |
| POST | `/auth/forgot-password` | Inicia recuperação sem enumerar e-mail. |
| POST | `/auth/reset-password` | Consome token e redefine senha. |
| GET | `/health` | Liveness. |
| GET | `/readiness` | PostgreSQL e Redis. |

## Sessão e identidade

`/auth/logout`, `/auth/logout-all`, `/auth/change-password`, `/sessions`, `/sessions/refresh`, `/sessions/{id}`, `/me`, `/me/profile`, `/me/security-events` e `/me/context`.

## Onboarding e organizações

- `/onboarding`, `/onboarding/terms`, `/onboarding/complete`;
- `/tenants/current` — `tenant.read`/`tenant.update`;
- `/economic-groups` — permissões `company.*`;
- `/companies` — `company.create/read/update/delete`;
- `/branches` — `branch.create/read/update/delete`.

## Pessoas e autorização

- `/users` e `/memberships` — `user.read`/`membership.manage`;
- `/teams` — `team.create/read/update/delete`;
- `/invitations` — `user.invite`/`user.read`;
- `/permissions` — `role.read`;
- `/roles` — `role.create/read/update/delete`;
- `/roles/assignments` — `role.assign`;
- `/audit-events` — `audit.read`.

## Plataforma

`/platform/tenants`, `/platform/users` e `/platform/users/{id}/status` exigem `platform.admin` e auditoria. Suspensão revoga sessões ativas.

## Erros

Respostas não revelam a existência de recurso de outro tenant. Erros de autenticação, autorização, conflito, validação e rate limit usam código estável, mensagem segura e detalhes JSON serializáveis.
