# Auditoria

## Estrutura

`audit_events` é append-only e possui trigger contra update/delete. Eventos de conta ficam também em `security_events`.

Campos principais:

- ator e usuário efetivo;
- tenant, empresa e filial;
- ação, categoria e resultado;
- recurso e identificador;
- correlation ID;
- IP minimizado e user agent tratado quando aplicável;
- campos alterados, justificativa e metadata sanitizada;
- timestamp UTC.

## Proibições

Nunca registrar senha, token bruto, cookie, hash de senha, credencial, DSN ou payload sensível completo.

## Retenção e exportação

A configuração padrão é 730 dias, sujeita à validação jurídica. Exportações futuras devem ser paginadas, autorizadas por `audit.read`, filtradas por tenant e registradas como novo evento.
