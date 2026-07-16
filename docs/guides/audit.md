# Auditoria

## Modelo

`audit_events` registra eventos funcionais e administrativos de forma append-only. `security_events` registra eventos da conta e autenticação.

Campos relevantes incluem ator, usuário efetivo, tenant, empresa, filial, ação, categoria, recurso, resultado, correlation ID, timestamp, IP tratado, user-agent e metadata segura.

## Eventos cobertos

Cadastro, verificação, login e falha, logout, senha, criação/revogação de sessão, onboarding, tenant, empresa, filial, convite, membership, papel, permissão, contexto, acesso negado e administração de plataforma.

## Dados proibidos

Nunca registrar senha, token bruto, cookie, segredo, hash de senha, DSN completo ou payload sensível integral.

## Integridade

Trigger PostgreSQL rejeita `UPDATE` e `DELETE` comuns. A aplicação oferece leitura paginada com `audit.read`; não existe endpoint de alteração.

## Retenção

`AUDIT_RETENTION_DAYS` define a política operacional, atualmente 730 dias por padrão. Exclusão/anonymização deve ocorrer por processo administrativo controlado e validado juridicamente, não por CRUD comum.
