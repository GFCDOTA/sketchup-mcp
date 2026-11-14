# FP-060 M2 — publicação via outbox com reconciliação, provada no laboratório

Evidência datada (2026-11-14) de uma execução **real** de `tools/orchestration/closed_loop_lab.py` no commit `fa8e9cf`
(árvore limpa), com Claude Code CLI 2.1.158 e Codex CLI 0.164.0, Windows 11, Python 3.12.13. Refs #606.

## O que é

A exigência do M2 "publicação externa via outbox idempotente com reconciliação" (diretriz FP-060-A01 §4), ensaiada sem
GitHub: o "sistema externo" é um arquivo local (`LedgerTarget`). Cada parecer `APPROVE`/`REQUEST_CHANGES` do Codex deixa uma
entrada no outbox do `EventStore` na mesma transação que conclui a revisão; o `step` do laboratório a publica com
`outbox_publisher.publish_one`, que **pergunta ao alvo pela chave antes de enviar**.

O caos novo `--crash-after-publish` mata o coordenador (`os._exit(86)`) depois de o efeito ser gravado no ledger e antes de
o ACK ser gravado no SQLite: o resultado fica desconhecido para o banco, que é exatamente o caso que a reconciliação cobre.

## Resultado (`crash_after_publish/`)

Um comando (`drive --crash-on REVIEW_REQUESTED --kill-during claude --crash-after-publish`), nenhuma mensagem humana
intermediária, 2 min 28 s, três mortes do coordenador.

| Passo do driver | O que aconteceu |
|---|---|
| 1 | coordenador morto com o Claude no ar; árvore do CLI vazia 2 s depois |
| 14 | entrega da rodada 1 |
| 15 | coordenador morto logo após o claim da revisão |
| 25 | Codex devolveu `REQUEST_CHANGES`; o parecer foi gravado no ledger e o coordenador **morreu antes do ACK** |
| 26–34 | `IDLE` aguardando o outbox: nenhum evento novo reivindicado enquanto o lease do publicador morto valia |
| 35 | publicação **reconciliada** na 2ª tentativa (achada no ledger, não reenviada); só então a correção foi despachada |
| 36 | entrega da rodada 2 |
| 37 | Codex devolveu `APPROVE`; publicado na 1ª tentativa |
| 38 | `WORKFLOW_COMPLETED` |

Relatório: **PASS**, 14 de 14 critérios. Os dois novos:

| Critério | Como é derivado | Valor |
|---|---|---|
| `verdicts_published_once_via_outbox` | chaves esperadas (eventos de revisão concluídos) = linhas do ledger, uma a uma, e toda entrada do outbox em `DONE` | PASS |
| `interrupted_publication_was_reconciled` | o anterior + alguma entrada precisou de 2 ou mais tentativas | PASS |

O ledger (`crash_after_publish/LEDGER.jsonl`) tem 2 linhas e 2 chaves distintas. A entrada do `REQUEST_CHANGES` está em
`DONE` com 2 tentativas; a do `APPROVE`, com 1 (`REPORT.json`, campo `outbox`).

## O que NÃO é

- **Não é exactly-once.** A entrega é "pelo menos uma tentativa + reconciliação" e depende de o alvo achar o efeito pela
  chave. O ledger local acha sempre; um alvo real pode não achar (consistência eventual, paginação, efeito removido).
- **Não há GitHub aqui.** `codex_reviewer.publish` não foi alterado e continua fazendo o POST direto. O alvo GitHub e o E2E
  num PR descartável autorizado são o passo seguinte do M2 e dependem de decisão humana.
- **Não há controle com CLIs reais** (execução sem reconciliação mostrando a duplicata). O contraste está nos testes
  determinísticos: sem o `find`, `test_publisher_that_died_after_the_effect_is_reconciled_without_a_second_send` falha.
- Uma única morte entre efeito e ACK, na primeira publicação. A mesma morte na publicação do `APPROVE` está coberta só por
  teste determinístico (`test_workflow_is_not_terminal_while_the_approval_is_still_unpublished`).
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
| `REPORT.md`, `REPORT.json` | critérios, runs, eventos, commits, outbox (estado e tentativas) e chaves do ledger |
| `LEDGER.jsonl` | o que o "sistema externo" recebeu: uma linha por parecer publicado |
| `DRIVE_LOG.jsonl` | um registro por `step`; o passo 25 traz `interrupted_publication`, o 35 traz `RECONCILED` |
| `TEST_EVIDENCE.json`, `sandbox_logs/` | evidência dos testes do coordenador (AppContainer) de cada evento concluído |
| `ORPHAN_CHECKS.jsonl` | PIDs vivos na árvore do CLI interrompido |
| `verdict_e*.json` | pareceres brutos do Codex |
| `CLI_VERSIONS.json` | versões dos CLIs e do Python, sem caminho de binário |
