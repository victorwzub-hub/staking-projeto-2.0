# Contribuindo

## Runtimes oficiais

- Python 3.12;
- Node.js 22;
- npm 10.

Use `.python-version` e `.nvmrc` para manter o ambiente alinhado ao Docker e ao CI.

## Fluxo

1. Crie uma branch curta a partir da branch principal.
2. Faça alterações pequenas e coesas.
3. Inclua testes e documentação na mesma mudança.
4. Execute `make lint typecheck test build`.
5. Para mudanças de infraestrutura ou integração, execute também `make smoke`.
6. Atualize `CHANGELOG.md` quando houver comportamento relevante.
7. Crie ou atualize um ADR para decisões estruturais.

## Commits

Use mensagens objetivas, preferencialmente no padrão Conventional Commits, como `feat(api): add readiness probe`.

## Definition of Done da fundação

- Código executável e tipado.
- Entrada validada e erros tratados.
- Logs sem secrets.
- Recursos externos fechados no shutdown.
- Testes automatizados.
- Documentação atualizada.
- Lint, formatação, type checking e build sem erros.
- Smoke test Compose verde no CI quando a mudança afetar a stack.
- Nenhuma funcionalidade declarada como pronta sem execução verificável.
