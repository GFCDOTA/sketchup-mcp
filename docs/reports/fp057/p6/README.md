# FP-057 P6 — prova de recuperação (2026-10-24)

Issue de controle: #518. Código: `tools/validation/recovery_proof.py`, `tests/test_fp057_p6_recovery.py`.

## 1. Cenário sintético sobre o GitHub real
`python -m tools.validation.recovery_proof` criou a Issue #529 (`[RECOVERY-PROOF]`), descobriu-a como elegível, reivindicou-a,
simulou reinício (estado relido do disco por outra instância), consultou o plano de recuperação com fatos de PR e fechou a Issue
como NOT_PLANNED. Resultado em `recovery_proof_2026-10-24.json` (`ok: true`):

| Verificação | Resultado |
|---|---|
| claim sobrevive ao reinício e o scheduler manda `resume` | sim |
| PR com checks `fail` → `EDITING` (mesmo PR); `pending` → `CI_PENDING`; `pass` → `MERGING`; mergeado → `BOARD_SYNC` | sim |
| efeito externo (`once`) não se repete depois do reinício | sim |
| Issue NOT_PLANNED nunca vai a Done; cartão duplicado é reportado | sim |
| tarefa em GPT Review não impede escolher outra elegível | sim |

Nenhum artefato oficial foi tocado; o estado de execução usou diretório temporário.

## 2. Evento real equivalente (não simulado)
O PR #528 teve o check `pytest (py3.11)` reprovado (`test_two_executors_racing_for_the_same_task_only_one_wins`): corrida real na
trava de `execution_state.locked` (o dono apagava o arquivo entre `open` e `stat`). Recuperação seguida: logs lidos, causa-raiz
corrigida, **commit novo no MESMO PR** (nenhum PR duplicado), checks reexecutados, merge com `--match-head-commit` no head
verde (3e452f1). A correção está coberta pelo teste existente, repetido 5× localmente.

## 3. Limites declarados
- O CI **não** foi reprovado de propósito: a reprovação real do #528 serviu de prova, sem gastar um ciclo extra.
- Não há runner 24/7: a recuperação roda quando uma sessão executa o scheduler.
- `GPT Review` segue sem aprovação possível enquanto `review_policy.reviewers` estiver vazio (#524).
