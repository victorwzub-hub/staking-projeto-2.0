# ADR 0004 — Estratégia de autenticação

- Status: Aceito
- Data: 2026-07-16

## Contexto

A aplicação é um SaaS B2B servido por navegador, com API própria, requisitos de revogação imediata, auditoria e múltiplos contextos de tenant. Foram comparados JWT auto-contido, access/refresh token e sessão opaca server-side.

## Decisão

Usar credenciais por e-mail e senha com Argon2id e sessões opacas armazenadas no PostgreSQL. O navegador recebe somente um cookie de sessão HttpOnly. Tokens de verificação, recuperação, convite e sessão são aleatórios, de alta entropia, e persistidos apenas como HMAC-SHA-256.

## Alternativas

- JWT: reduz consulta ao banco, mas dificulta revogação imediata, troca segura de contexto, invalidação de permissões e auditoria de dispositivo.
- Access + refresh token: apropriado para APIs públicas/mobile, porém adiciona rotação e superfície de ataque sem benefício para o primeiro cliente web.
- Sessão somente em Redis: rápida, mas tornaria Redis fonte de verdade para identidade e prejudicaria auditoria e recuperação.

## Consequências

- Uma consulta de sessão é necessária por requisição autenticada.
- Revogação, expiração, troca de tenant e perda de papel têm efeito imediato.
- Redis continua sendo camada efêmera, não fonte de verdade de identidade.
