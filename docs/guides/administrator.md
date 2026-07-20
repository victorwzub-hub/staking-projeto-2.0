# Manual do administrador

## Operações iniciais

1. executar migrations;
2. bootstrap do primeiro platform admin;
3. entrar pela página `/login`;
4. criar tenant pelo onboarding ou administrar contas pela área de plataforma;
5. criar empresas e filiais;
6. convidar usuários com papel e escopo autorizados;
7. revisar sessões e auditoria.

## Usuários e convites

Convites são associados a e-mail normalizado, têm expiração, podem ser reenviados/revogados e são de uso único. Nunca envie token por canal de log. Uma membership suspensa ou revogada perde acesso imediatamente.

## Papéis

Prefira papéis de sistema. Crie papel customizado somente quando a combinação necessária não existir. O ator só pode delegar permissões dentro do próprio escopo.

## Sessões

A área de segurança lista sessões por dispositivo. O usuário pode revogar uma sessão específica ou todas. Suspender uma conta revoga sessões ativas.

## Auditoria

Use filtros e paginação para investigar alterações. Correlacione eventos pelo `correlation_id`. Não tente alterar registros de auditoria diretamente.
