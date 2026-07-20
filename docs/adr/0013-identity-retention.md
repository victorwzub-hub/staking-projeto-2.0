# ADR 0013 — Retenção e exclusão de identidade

- Status: Aceito
- Data: 2026-07-16

## Decisão

Identidades não são apagadas em cascata durante operação normal. Revogação e suspensão preservam evidência. Solicitações de exclusão usam processo administrativo: revogar sessões, remover memberships, anonimizar perfil e e-mail com marcador irreversível, mantendo identificadores técnicos mínimos de auditoria.

Tokens expirados e tentativas de autenticação têm limpeza periódica. Sessões revogadas são retidas por 180 dias; eventos de segurança e auditoria por 24 meses, pendente de validação jurídica/LGPD.
