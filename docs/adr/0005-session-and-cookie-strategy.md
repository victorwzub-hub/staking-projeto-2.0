# ADR 0005 — Sessões, cookies e CSRF

- Status: Aceito
- Data: 2026-07-16

## Decisão

A sessão opaca é enviada em cookie HttpOnly, Secure em staging/produção, SameSite configurável e Path `/`. Um segundo cookie não HttpOnly contém um token CSRF aleatório. Requisições autenticadas que alteram estado devem enviar o mesmo valor em `X-CSRF-Token`; o backend compara seu HMAC com o hash vinculado à sessão.

A sessão possui expiração absoluta, `last_seen_at`, dispositivo, user agent sanitizado, IP minimizado e contexto ativo de tenant/empresa/filial. Refresh explícito rotaciona token de sessão e CSRF, revogando o segredo anterior.

## Consequências

- CORS usa lista explícita e `allow_credentials=true`.
- Credenciais permanentes não são armazenadas em `localStorage`.
- A API e o frontend podem operar em domínios diferentes desde que cookies, domínio e CORS sejam configurados de forma compatível.
