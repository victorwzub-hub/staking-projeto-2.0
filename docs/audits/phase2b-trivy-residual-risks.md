# Riscos residuais do Trivy — Etapa 2B

Data da avaliação: 2026-07-18. Scanner: Trivy 0.72.0, banco atualizado em
2026-07-17. As imagens foram analisadas com os scanners `vuln,secret`, severidades
`HIGH,CRITICAL`, primeiro com e depois sem `--ignore-unfixed`.

## Resultado

| Imagem | Base observada | Tamanho | Usuário | High | Critical | Secrets |
|---|---|---:|---|---:|---:|---:|
| `pharma-intelligence-smoke-api:latest` | Debian 13.6 | 120,46 MiB | `appuser` | 19 | 3 | 0 |
| `pharma-intelligence-smoke-worker:latest` | Debian 13.6 | 120,44 MiB | `appuser` | 19 | 3 | 0 |
| `pharma-intelligence-smoke-web:latest` | Debian 12.15 | 94,30 MiB | `node` | 17 | 4 | 0 |

As contagens são ocorrências por pacote. Há 12 CVEs únicos, todos provenientes das
imagens Debian e sem `FixedVersion` no feed usado. Com `--ignore-unfixed`, as três
imagens retornaram zero High, zero Critical e zero secrets. O scan do repositório,
sem ignorar achados não corrigidos, retornou zero High/Critical, zero secrets e zero
misconfigurações High/Critical.

## Avaliação por vulnerabilidade

| CVE | Severidade/status | Pacotes e versões | Imagens | Explorabilidade no serviço | Mitigação e decisão |
|---|---|---|---|---|---|
| CVE-2023-45853 | Critical / `will_not_fix` | `zlib1g` 1:1.2.13.dfsg-1 | web | Exige uso da API minizip vulnerável para criar ZIP com entrada maliciosa; o servidor Next não cria ZIP. | Aceite temporário; runtime não expõe essa operação. |
| CVE-2025-69720 | High / `affected` | `libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin` 6.5+20250216-2; na web, 6.4-4 sem `libncursesw6` | todas | Exige processamento de terminal/terminfo malicioso; os containers não oferecem sessão terminal a usuários nem invocam ncurses no fluxo HTTP/worker. | Usuário não root e ausência de caminho de entrada; atualizar a base quando o Debian publicar correção. |
| CVE-2026-13221 | Critical / `affected` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | Exige compilação de expressão regular por Perl; a aplicação Python/Node não chama Perl. | Aceite temporário; monitorar pacote/base. |
| CVE-2026-41992 | High / `affected` ou `fix_deferred` | `gzip` 1.13-1; web 1.12-1 | todas | Exige descompressão LZH por gzip. Upload aceita somente CSV, JSON e NDJSON e não chama gzip. | Formatos comprimidos continuam fora da allowlist; atualizar quando houver pacote corrigido. |
| CVE-2026-42496 | Critical / `fix_deferred` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | Path traversal depende de extração de tar via Perl Archive::Tar; nenhum endpoint extrai arquivos tar. | Não habilitar upload/extração de arquivo compactado; atualizar a base assim que disponível. |
| CVE-2026-42497 | High / `fix_deferred` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | Modificação por hardlink também depende de Archive::Tar e arquivo controlado. | Mesma mitigação do CVE-2026-42496. |
| CVE-2026-48962 | High / `affected` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | Exige chamada Perl IO::Compress com glob de saída controlado; não faz parte do processo da aplicação. | Aceite temporário e atualização de base. |
| CVE-2026-53615 | High / `affected` | família `util-linux`/`libblkid` 2.41-5; web 2.38.1-5+deb12u3 | todas | Exige análise de imagem de partição DOS por libblkid. Containers não recebem dispositivos de bloco nem executam descoberta de partições. | Manter containers sem dispositivos/privileged; atualizar a base. |
| CVE-2026-54369 | High / `affected` ou `fix_deferred` | `libacl1` 2.3.2-2+b1; web 2.3.1-3 | todas | Exige operação libacl privilegiada sobre árvore com symlink controlado; processos rodam sem root e não oferecem operação ACL. | Não conceder root/privileged; atualizar a base. |
| CVE-2026-57432 | High / `affected` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | Exige entrada processada pelo compilador de regex Perl, que não é usado pelo serviço. | Aceite temporário e atualização de base. |
| CVE-2026-8376 | Critical / `affected` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | O alerta descreve builds de 32 bits; as imagens validadas são Linux `amd64` e a aplicação não chama Perl. | Não explorável na arquitetura validada; manter bloqueio a imagens 32-bit e atualizar a base. |
| CVE-2026-9538 | High / `fix_deferred` | `perl-base` 5.40.1-6; web 5.36.0-7+deb12u3 | todas | DoS exige tar malicioso processado por Perl Archive::Tar; não há extração tar em runtime. | Mesma mitigação dos demais achados Archive::Tar. |

## Decisão e plano

Os achados são aceitos de forma temporária para o fechamento da 2B porque não há
versão corrigida indicada, os caminhos vulneráveis não são invocados e os processos
rodam como usuários sem root. Isso não autoriza aceitar novos achados corrigíveis.

1. Reexecutar Trivy semanalmente e sempre que o digest das imagens base mudar.
2. Rebuildar e promover novas bases Debian assim que `FixedVersion` aparecer.
3. Manter a CI bloqueando vulnerabilidades corrigíveis High/Critical e secrets.
4. Avaliar runtime distroless para API/worker/web em um hardening isolado, com smoke,
   Playwright e rollback antes de produção.
5. Não adicionar suporte a arquivos compactados, terminal ou dispositivos sem nova
   modelagem de ameaça e testes de segurança.
