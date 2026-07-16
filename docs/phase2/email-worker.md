# E-mail e worker

## Abstração

Casos de uso produzem `EmailCommand`. A API enfileira no Dramatiq e não espera resultado. Atores retornam `None`.

Templates atuais:

- verificação de e-mail;
- recuperação de senha;
- convite.

## Desenvolvimento/teste

O adapter grava JSON em `EMAIL_SPOOL_DIRECTORY`. Tokens completos ficam apenas no spool privado, nunca nos logs. O worker registra somente template e domínio do destinatário.

## Idempotência

Cada mensagem possui chave de idempotência em Redis. Em falha, o marcador é removido para permitir retry. Dramatiq aplica backoff e número máximo de tentativas.

## Provedor real

Antes de ativar: escolher fornecedor, configurar domínio/remetente, credenciais secretas, webhook de bounce/complaint, limites, observabilidade, DPA e política de retenção. Nenhuma credencial real foi incluída.
