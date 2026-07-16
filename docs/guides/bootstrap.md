# Bootstrap do primeiro platform administrator

## Pré-condições

- migration aplicada;
- conexão administrativa segura disponível ao comando;
- secrets fornecidos pelo ambiente;
- `BOOTSTRAP_ENABLED=true` somente durante a execução.

## Comando

```bash
BOOTSTRAP_ENABLED=true \
BOOTSTRAP_ADMIN_EMAIL='admin@example.com' \
BOOTSTRAP_ADMIN_PASSWORD='<secret-manager>' \
pharma-bootstrap-admin
```

O comando cria ou promove a identidade indicada, verifica e-mail, usa Argon2id, é idempotente e registra `platform_admin.bootstrapped`. Não existe senha padrão e a senha não é exibida.

## Pós-condição

Desative/remova `BOOTSTRAP_ENABLED`, `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD` do serviço. Revise o evento de auditoria e teste login com política de cookies do ambiente.
