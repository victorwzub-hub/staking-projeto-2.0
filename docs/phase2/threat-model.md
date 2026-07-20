# Modelo de ameaças — identidade e multi-tenancy

## Fronteiras de confiança

1. Navegador ↔ web: conteúdo público e aplicação Next.js; nenhuma credencial permanente é mantida em `localStorage`.
2. Navegador ↔ API: HTTPS em deploy, cookie de sessão opaco HttpOnly, cookie CSRF legível e cabeçalho correspondente.
3. API/worker ↔ PostgreSQL: role de aplicação sem privilégios administrativos e RLS forçado.
4. API/worker ↔ Redis: dados efêmeros de rate limiting, broker e idempotência; Redis não é a fonte autoritativa da sessão.
5. Migration/bootstrap ↔ PostgreSQL: credencial administrativa separada e comandos explicitamente habilitados.
6. Worker ↔ provedor de e-mail: adapter de desenvolvimento/teste nesta fase; provedor externo ainda não ativado.

## Ativos críticos

- hashes Argon2id de senha;
- hashes HMAC de sessão e tokens de uso único;
- contexto ativo de tenant, empresa e filial;
- memberships, atribuições de papel e catálogo de permissões;
- eventos de segurança e auditoria append-only;
- peppers, credenciais de banco/Redis e configuração de cookies.

## Principais ameaças e controles

| Ameaça | Controle implementado | Evidência esperada |
|---|---|---|
| enumeração de conta | respostas neutras em cadastro, reenvio e recuperação | testes de API e integração |
| credential stuffing/força bruta | rate limiting Redis fail-closed e backoff progressivo limitado | testes Redis e HTTP 429 |
| roubo/reutilização de token | tokens aleatórios, hash HMAC, expiração, uso único e revogação | testes de token e integração |
| CSRF | SameSite, cookie de duplo envio e vínculo do token CSRF à sessão | testes de cookies/CSRF |
| fixação de sessão | nova sessão opaca no login e revogação explícita | teste de login/sessões |
| acesso cruzado entre tenants | contexto server-side, repositórios filtrados, constraints e RLS | matriz negativa PostgreSQL |
| vazamento pelo pool | `set_config(..., true)` transacional | teste de reutilização de conexão |
| elevação de privilégio | deny-by-default, permissões específicas e validação de delegação/escopo | testes RBAC negativos |
| alteração da auditoria | trigger que rejeita update/delete e role comum sem privilégio administrativo | migration e teste PostgreSQL |
| exposição em logs | sanitização de metadata, IP hasheado, user agent limitado e proibição de tokens | testes de sanitização |
| migration concorrente | advisory lock de sessão e falha segura | teste do CLI e smoke Compose |
| bootstrap inseguro | opt-in, variáveis explícitas, sem senha padrão e idempotência | teste/comando de bootstrap |

## Ameaças não encerradas nesta execução

- validação da topologia real, TLS, cookies e domínios no Railway;
- fornecedor real de e-mail, bounce/complaint e reputação do remetente;
- backup, restauração e resposta a incidente em staging;
- execução da matriz PostgreSQL/Redis, Playwright real e smoke Docker neste ambiente;
- impersonation, deliberadamente não implementada pelo ADR 0014.

Nenhum desses itens pode ser tratado como aprovado sem evidência operacional.
