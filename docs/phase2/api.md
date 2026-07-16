# API REST — Fase 2

Base: `/api/v1`. Erros seguem envelope consistente com `error.code`, `message`, `details` e correlation ID no header.

## Auth e sessões

| Método | Rota | Autorização |
|---|---|---|
| POST | `/auth/register` | pública + rate limit |
| POST | `/auth/verify-email` | pública + rate limit |
| POST | `/auth/resend-verification` | pública + rate limit |
| POST | `/auth/login` | pública + rate limit |
| POST | `/auth/logout` | sessão + CSRF |
| POST | `/auth/logout-all` | sessão + CSRF |
| POST | `/auth/forgot-password` | pública + rate limit |
| POST | `/auth/reset-password` | pública + rate limit |
| POST | `/auth/change-password` | sessão + CSRF |
| GET/DELETE | `/sessions` | própria conta; mutação com CSRF |
| POST | `/sessions/refresh` | sessão + CSRF |

## Contexto e onboarding

- `GET /me`, `GET/PATCH /me/profile`, `GET /me/security-events`;
- `POST /me/context` exige contexto autorizado e CSRF;
- `GET /onboarding`, `GET /onboarding/terms`, `POST /onboarding/complete`.

## Organizações

- `/tenants/current`;
- `/economic-groups`;
- `/companies`;
- `/branches`;
- `/memberships` e `/users`;
- `/teams` e membros;
- `/invitations` e aceite.

Cada operação usa permissão específica, tenant derivado da sessão, versionamento otimista quando há update e erro 404 neutro para recurso fora do tenant.

## RBAC e auditoria

- `/permissions`;
- `/roles`;
- `/roles/assignments`;
- `/audit-events`.

## Plataforma

- `/platform/tenants`;
- `/platform/users`;
- `/platform/users/{id}/status`.

Exige `platform.admin`; alterações administrativas exigem justificativa e auditoria.

A especificação OpenAPI executável está disponível em `/docs` fora de produção.
