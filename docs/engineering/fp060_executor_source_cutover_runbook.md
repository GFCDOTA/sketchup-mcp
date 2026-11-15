# FP-060 MT-07 — fonte do executor: cutover e rollback (runbook)

Refs #626 · código: `tools/orchestration/sqlite_source.py` · testes: `tests/test_sqlite_source.py`

## Estado

| `EXECUTOR_SOURCE` | Quem escolhe o trabalho | A outra fila |
|---|---|---|
| `json` (**padrão**) | fila JSON do bridge (`event_bridge.json`) | SQLite é espelho (modo sombra) |
| `sqlite` | `EventStore.claim` (transacional, lease, fencing, DLQ) | a fila JSON vira espelho; nunca escolhe trabalho |

Valor desconhecido **recusa** (o executor sai com código 6 / devolve `BLOCKED_SOURCE`); nunca cai no outro caminho. SQLite indisponível em
modo `sqlite` devolve `BLOCKED_STORE`: o executor **não** volta para a fila JSON sozinho (duas fontes de verdade = trabalho duplicado).

Nada nesta mudança liga `sqlite` em produção, liga `--execute` ou liga o modo CONTINUOUS.

## Pré-requisitos do cutover (todos, nesta ordem)

1. E2E real da MT-06 concluído (issue #625), com a evidência datada em `artifacts/review/fp060/`.
2. `python -m tools.orchestration.sqlite_source status` com `divergences: []` e `live_leases: []`.
3. `DRY_RUN` validado com `EXECUTOR_SOURCE=sqlite` (o dry-run **não reivindica**; repetir não gasta tentativas).
4. `SUPERVISED` (um item, com o Felipe presente) validado antes de qualquer execução sem supervisão.
5. Revisão independente do PR que liga a fonte.

## Cutover

Parar o executor, definir `EXECUTOR_SOURCE=sqlite` no ambiente da tarefa agendada, reiniciar. Na partida o executor valida a variável.
Antes de cada claim, itens da fila JSON ainda `QUEUED` que o SQLite não tem são publicados (idempotente), então nada que o bridge aceitou
fica sem dono.

## Rollback (volta para a fila JSON)

```bash
# 1. parar o executor (ele segura leases vivos no SQLite)
python -m tools.orchestration.sqlite_source rollback-check   # lista o que mudaria; exit 1 se houver lease vivo
python -m tools.orchestration.sqlite_source rollback-apply   # marca na fila JSON o que o SQLite já concluiu
# 2. remover EXECUTOR_SOURCE (ou =json) e reiniciar o executor
```

`rollback-apply` mapeia `DONE → DONE_AWAITING_REREVIEW`, `SUPERSEDED → SUPERSEDED`, `DLQ → FAILED` (com as tentativas esgotadas) e deixa o que
ainda é `PENDING` como `QUEUED`. **Recusa** (exit 1, nada gravado) se algum evento tem lease vivo: o executor ainda está no meio de um trabalho.
O espelho reverso já grava cada resultado na fila JSON durante o modo `sqlite`; o `rollback-apply` cobre o que o espelho (melhor esforço) perdeu.

## O que NÃO está provado

- Nenhum teste aqui exercita o Claude/Codex reais nem o GitHub: handlers e `gh` são injetados; o SQLite é real.
- O teto diário conta reivindicações do SQLite (conservador: um claim que o preflight recusa também conta).
- Pré-requisito 1 (E2E da MT-06) ainda não existe.
