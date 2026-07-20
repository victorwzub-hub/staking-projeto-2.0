# Autenticação e sessões

## Estratégia

A aplicação web usa sessão opaca server-side. O token aleatório bruto existe apenas no cookie HttpOnly e no instante da emissão. PostgreSQL armazena HMAC do token, contexto ativo, IP minimizado, user agent sanitizado, expiração e revogação.

JWT foi rejeitado porque revogação, contexto mutável de tenant e perda imediata de permissões são requisitos centrais.

## Fluxos

- cadastro: resposta neutra e comando de verificação;
- verificação/reenvio: token de uso único e expiração;
- login: Argon2id, dummy hash contra enumeração, rate limit Redis e tentativa persistida;
- logout: revoga sessão atual e remove cookies;
- logout global: revoga todas as sessões;
- reset: revoga sessões e invalida token;
- troca autenticada: exige CSRF e revoga outras sessões;
- refresh: rotaciona sessão e CSRF;
- listagem/revogação por dispositivo.

## Cookies

- sessão: HttpOnly, path `/`, Secure em deploy;
- CSRF: mesmo escopo, não HttpOnly para duplo envio;
- SameSite `lax` por padrão; `none` exige Secure;
- CORS aceita credenciais apenas para origens explícitas.

## Enumeração

Cadastro duplicado, reenvio e recuperação retornam mensagens indistinguíveis. E-mail normalizado ou IP nunca aparece em chaves Redis ou logs sem HMAC.

## Operação

Revogue sessões pelo painel de segurança ou endpoints `/sessions`. Para incidentes amplos, suspenda o usuário e revogue todas as sessões em transação administrativa auditada.
