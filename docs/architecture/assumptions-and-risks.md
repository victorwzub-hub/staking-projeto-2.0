# Suposições e riscos

## Suposições registradas

1. Nenhum repositório foi fornecido na Fase 1; o projeto foi iniciado do zero.
2. O idioma inicial da interface e da documentação é português brasileiro.
3. Python 3.12 e Node.js 22 são as versões oficiais do projeto.
4. PostgreSQL e Redis serão serviços gerenciados em produção, mas containers locais nesta fase.
5. A API não falha no startup quando banco ou Redis estão indisponíveis; readiness comunica indisponibilidade.
6. Não há entidades de negócio ou migrations de tabelas na fundação.
7. O CI usa GitHub Actions por determinação da especificação.
8. Credenciais, domínio, cloud e provedor de observabilidade ainda não foram definidos.

## Riscos atuais

- **Docker indisponível no ambiente de execução:** o smoke test foi implementado e validado sintaticamente, mas precisa passar no GitHub Actions para fechar o gate ambiental.
- **Python local 3.13.5:** o ambiente atual não oferece Python 3.12; Docker e CI foram alinhados a 3.12 e são a validação autoritativa dessa versão.
- **Playwright local bloqueado:** o Chromium do sistema impede acesso ao loopback por política administrativa. O teste foi descoberto, mas não foi declarado como aprovado localmente.
- **Escopo regulatório:** requisitos LGPD e farmacêuticos exigem validação jurídica e de especialistas antes de produção.
- **Dependências recentes:** upgrades devem passar por CI, testes e revisão de changelog.
- **Readiness simples:** suficiente para a fundação, mas ainda sem métricas, tracing ou circuit breakers.
- **Worker mínimo:** não processa dados de negócio nesta fase.
