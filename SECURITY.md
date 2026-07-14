# Política de Segurança

## Relato responsável

Não abra issues públicas para vulnerabilidades. Envie o relato ao canal privado de segurança definido pela organização antes do ambiente comercial. Enquanto esse canal não existir, o repositório não deve ser publicado como produto em produção.

Inclua impacto, passos mínimos de reprodução, versões afetadas e evidências sem dados pessoais reais.

## Princípios aplicados na fundação

- Ausência de secrets no código e `.env` ignorado pelo Git.
- Variáveis públicas do frontend limitadas ao prefixo `NEXT_PUBLIC_`.
- Logs estruturados sem impressão intencional de credenciais.
- Erros internos não expõem stack trace ao cliente.
- Detalhes de validação são convertidos para estruturas JSON seguras.
- Correlation ID limitado a 128 caracteres e ao conjunto `A-Z`, `a-z`, `0-9`, ponto, hífen e underscore.
- UUID substitui correlation IDs ausentes ou inválidos.
- Readiness separado de liveness.
- Engine SQLAlchemy e cliente Redis são fechados no shutdown.
- Imagens Docker executam com usuário sem privilégios.
- Imagens Docker não executam migrations implicitamente.
- Dependências fixadas por versão e verificadas no CI.

## Guardas de configuração em produção

Quando `APP_ENV=production`, a API recusa debug ativo, senha local padrão, hosts de loopback para PostgreSQL/Redis e CORS com wildcard, HTTP ou loopback. Esses guardas evitam acidentes comuns, mas não substituem secret manager, TLS, firewall, políticas IAM ou revisão de deploy.

## Antes de produção

São obrigatórios: autenticação, RBAC, isolamento por tenant, gestão de secrets, TLS, headers de segurança, rate limiting, auditoria, análise de dependências, SAST, backup/restore testado, plano de incidentes e validação jurídica/LGPD.

## Dados sensíveis

Não use dados reais de pacientes, clientes ou funcionários em desenvolvimento. A plataforma ainda não está autorizada para processamento de dados pessoais em produção.
