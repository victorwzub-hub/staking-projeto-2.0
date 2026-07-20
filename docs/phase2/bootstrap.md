# Bootstrap do primeiro platform admin

## Pré-condições

- migrations aplicadas;
- role de aplicação com acesso ao banco;
- `BOOTSTRAP_ENABLED=true` somente durante a execução;
- e-mail e senha fornecidos explicitamente por secret do ambiente.

## Comando

```bash
BOOTSTRAP_ENABLED=true \
BOOTSTRAP_ADMIN_EMAIL=admin@example.test \
BOOTSTRAP_ADMIN_PASSWORD='senha-forte-fornecida-no-ambiente' \
pharma-bootstrap-admin
```

O comando é idempotente, verifica usuário existente, nunca imprime senha, marca e-mail como verificado e registra `platform_admin.bootstrapped`.

Após o primeiro uso, remova as variáveis e mantenha `BOOTSTRAP_ENABLED=false`.
