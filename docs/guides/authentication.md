# Autenticação e sessões

## Estratégia

A web usa sessões opacas controladas pelo servidor. O cookie de sessão é `HttpOnly`; o token bruto nunca é persistido. O banco armazena apenas HMAC do token usando `SESSION_TOKEN_PEPPER`.

Cookies mutáveis usam proteção CSRF de duplo envio: cookie legível `pharma_csrf` e header `X-CSRF-Token` idêntico. CORS deve habilitar credentials apenas para origens explícitas.

## Fluxos

- cadastro: cria usuário pendente e token de verificação;
- verificação: consome token uma única vez e ativa a conta;
- login: valida Argon2id, rate limit e cria sessão por dispositivo;
- logout: revoga a sessão atual;
- logout-all: revoga todas as sessões do usuário;
- recuperação: resposta neutra, token de uso único e expiração;
- redefinição/troca de senha: rehash quando necessário e revogação de sessões;
- sessões: listar, renovar e revogar sessão específica.

## Cookies em deploy

- `HttpOnly=true` para sessão;
- `Secure=true` em staging/produção;
- `SameSite=lax` por padrão;
- `SameSite=none` somente com `Secure=true`;
- `Path=/`;
- domínio configurável por `SESSION_COOKIE_DOMAIN`;
- nenhuma credencial permanente em `localStorage`.

## Proteções

- Argon2id configurável;
- tokens criptograficamente aleatórios;
- hashes HMAC com peppers separados;
- comparação em tempo constante;
- mensagens neutras contra enumeração;
- backoff exponencial limitado para falhas de login;
- rate limiting fail-closed quando Redis está indisponível;
- IP minimizado/hasheado e user-agent truncado;
- auditoria de sucesso e falha.

## Revogação

A sessão é inválida quando expirada, revogada, ociosa, associada a usuário indisponível ou a contexto sem membership ativa. Alterações de papel são avaliadas novamente na requisição seguinte.
