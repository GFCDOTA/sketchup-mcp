# FP-060 M2 — publicação via outbox com reconciliação, provada pelo diário (2026-11-16)

Evidência datada (2026-11-16) de uma execução **real** de `tools/orchestration/closed_loop_lab.py` no commit `7a8afa1c`
(árvore limpa), com Claude Code CLI 2.1.158 e Codex CLI 0.164.0, Windows 11, Python 3.12.13. Refs #606.

Substitui, como prova do critério **atual**, a evidência de `2026-11-14_lab_ledger/` (commit `fa8e9cf`). Aquela foi produzida
antes de existir o diário `PUBLICATIONS.jsonl` e não comprova o critério que o código exige hoje. Ela fica preservada como retrato
datado.

## O critério, como o código o deriva hoje

`interrupted_publication_was_reconciled` exige:

1. `verdicts_published_once_via_outbox`: as chaves esperadas (eventos de revisão concluídos) são exatamente as linhas do ledger,
   e toda entrada do outbox está em `DONE`;
2. no diário `PUBLICATIONS.jsonl`, para uma mesma chave, uma tentativa com `EFFECT_APPLIED` **sem desfecho**, porque o
   coordenador morreu entre o efeito e o ACK, **seguida** de `RECONCILED` numa tentativa posterior.

Duas tentativas por outro motivo (por exemplo, falha antes do envio) não contam. Diário ausente, vazio ou com linha truncada ou
malformada **reprova** o critério, e o motivo vai para `publications_journal_error` no relatório; o relatório nunca quebra por
causa do diário. As gravações do diário são duráveis (`flush` + `fsync`), e um fragmento de gravação interrompida fica isolado
na própria linha.

## Resultado (`crash_after_publish/`)

Um comando (`drive --crash-on REVIEW_REQUESTED --kill-during claude --crash-after-publish`), nenhuma mensagem humana
intermediária, 2 min 52 s, três mortes do coordenador.

| Passo do driver | O que aconteceu |
|---|---|
| 1 | coordenador morto (`86`) com o Claude no ar |
| 14 | entrega da rodada 1 |
| 15 | coordenador morto logo após o claim da revisão |
| 25 | Codex devolveu `REQUEST_CHANGES`; o efeito foi gravado no ledger e o coordenador **morreu antes do ACK** (`interrupted_publication`) |
| 26–35 | `IDLE` enquanto o lease do publicador morto valia |
| 36 | publicação **reconciliada** na 2ª tentativa (achada no ledger, não reenviada); só então a correção foi despachada |
| 37 | entrega da rodada 2 |
| 38 | Codex devolveu `APPROVE`; publicado na 1ª tentativa |
| 39 | `WORKFLOW_COMPLETED` |

Relatório: **PASS**, 14 de 14 critérios; `publications_journal_error: null`.

`PUBLICATIONS.jsonl` (4 linhas):

| Chave | Tentativa | Evento |
|---|---|---|
| `…:618fc164…:REQUEST_CHANGES` | 1 | `EFFECT_APPLIED` (sem desfecho: morte antes do ACK) |
| `…:618fc164…:REQUEST_CHANGES` | 2 | `RECONCILED` |
| `…:56bb00b1…:APPROVE` | 1 | `EFFECT_APPLIED` |
| `…:56bb00b1…:APPROVE` | 1 | `SENT` |

O ledger (`LEDGER.jsonl`) tem 2 linhas e 2 chaves distintas; o outbox termina com as duas entradas em `DONE` (2 tentativas e 1).

## Testes do coordenador no AppContainer (o que a revisão viu)

A execução confiável dos testes do coordenador pelo revisor, neste ramo, registra falhas e erros que **não** vêm do código do
PR: os testes do laboratório executam `git` (ausente no AppContainer) e os `TestRealProcesses` do `event_store` usam
`multiprocessing.Pipe` (`CreateNamedPipe` negado no AppContainer). Os que já existem na `develop` são delegados ao CI, um node id
exato por vez, pelo #672. Os testes de `git` que este PR **acrescenta** só podem ser delegados depois de existirem na `develop`
(limite declarado no #672). Fora do AppContainer, a suíte inteira passa (`tests/test_closed_loop_lab.py`,
`tests/test_outbox_publisher.py`, `tests/test_event_store.py`).

## O que NÃO é

- **Não é exactly-once.** A entrega é "pelo menos uma tentativa + reconciliação" e depende de o alvo achar o efeito pela chave.
- **Não há GitHub aqui.** O alvo é um arquivo local (`LedgerTarget`). O alvo GitHub é o #619.
- Uma única morte entre efeito e ACK, na primeira publicação. A mesma morte na publicação do `APPROVE` está coberta só por teste
  determinístico.
- Uma execução: é demonstração, não medida de taxa de sucesso.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_outbox_publisher.py tests/test_closed_loop_lab.py tests/test_event_store.py -q
$PY -m tools.orchestration.closed_loop_lab drive --lab <dir novo fora de qualquer repositório git> \
    --crash-on REVIEW_REQUESTED --kill-during claude --crash-after-publish
```

## Arquivos (`crash_after_publish/`)

| Arquivo | Conteúdo |
|---|---|
| `REPORT.md`, `REPORT.json` | critérios, runs, eventos, commits, outbox (estado e tentativas), chaves do ledger, erro do diário |
| `PUBLICATIONS.jsonl` | o diário de que o critério é derivado: efeito aplicado e desfecho de cada tentativa |
| `LEDGER.jsonl` | o que o "sistema externo" recebeu: uma linha por parecer publicado |
| `DRIVE_LOG.jsonl` | um registro por `step`; o passo 25 traz `interrupted_publication`, o 36 traz `RECONCILED` |
| `sandbox_logs/` | sonda e testes do coordenador (AppContainer) de cada evento concluído |
| `ORPHAN_CHECKS.jsonl` | PIDs vivos na árvore do CLI interrompido |
| `CLI_VERSIONS.json` | versões dos CLIs e do Python, sem caminho de binário |
