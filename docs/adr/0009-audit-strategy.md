# ADR 0009 — Auditoria append-only

- Status: Aceito
- Data: 2026-07-16

## Decisão

Eventos de auditoria são persistidos em `audit_events`, com ator real, usuário efetivo, contexto, ação, resultado, correlation ID e metadados sanitizados. Triggers do PostgreSQL rejeitam `UPDATE` e `DELETE` comuns.

Senhas, tokens, cookies, hashes de senha, credenciais e payloads sensíveis completos nunca são gravados. IP é armazenado como HMAC truncado; user agent é limitado.

Retenção inicial: 24 meses, sujeita a validação jurídica e contratual. Exportação será somente leitura e autorizada por `audit.read`.
