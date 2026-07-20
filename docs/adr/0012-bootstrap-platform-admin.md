# ADR 0012 — Bootstrap do primeiro administrador

- Status: Aceito
- Data: 2026-07-16

## Decisão

O primeiro `platform_admin` é criado por CLI idempotente. O comando exige `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` e `BOOTSTRAP_ENABLED=true`; não possui credencial padrão. Se o usuário existir, somente confirma estado consistente, sem duplicar nem substituir senha silenciosamente.

Após o bootstrap, `BOOTSTRAP_ENABLED` deve ser removido/desativado. A operação gera auditoria de plataforma.
