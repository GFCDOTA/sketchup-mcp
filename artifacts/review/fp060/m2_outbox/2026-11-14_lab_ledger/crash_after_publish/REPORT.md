# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: PASS** · modo `closed_loop` · lab `run_20261114_outbox_01` · HEAD final `94c05aa5eda4538f2aef699d67fbe7a3acac9d0b`

| Criterio (derivado do SQLite/git) | Resultado |
|---|---|
| claude_cli_observed | PASS |
| codex_cli_observed | PASS |
| request_changes_then_correction | PASS |
| approved_after_correction | PASS |
| approval_bound_to_final_head | PASS |
| workflow_completed | PASS |
| no_pending_or_running_event | PASS |
| one_delivery_per_implement_event | PASS |
| survived_coordinator_restart | PASS |
| finished_cli_runs_job_contained | PASS |
| orphan_cli_tree_dead_after_coordinator_kill | PASS |
| coordinator_tests_ran_in_os_sandbox | PASS |
| verdicts_published_once_via_outbox | PASS |
| interrupted_publication_was_reconciled | PASS |

| Run | Evento | Agente | PID | Exit | s | Contencao | Binario |
|---|---|---|---|---|---|---|---|
| 1 | 1 | claude | 42192 | INTERROMPIDO | - | - | `claude.exe` |
| 2 | 1 | claude | 41312 | 0 | 10.1 | job_object | `claude.exe` |
| 3 | 3 | codex | 10784 | 0 | 19.2 | job_object | `codex.exe` |
| 4 | 5 | claude | 23512 | 0 | 19.1 | job_object | `claude.exe` |
| 5 | 7 | codex | 13072 | 0 | 18.3 | job_object | `codex.exe` |

| # | Evento | Estado | Tentativas | Pai |
|---|---|---|---|---|
| 1 | IMPLEMENT_REQUESTED | DONE | 2 |  |
| 2 | IMPLEMENT_COMPLETED | RECORDED | 0 | 1 |
| 3 | REVIEW_REQUESTED | DONE | 2 | 1 |
| 4 | REVIEW_CHANGES_REQUESTED | DONE | 1 | 3 |
| 5 | CORRECTION_REQUESTED | DONE | 1 | 4 |
| 6 | IMPLEMENT_COMPLETED | RECORDED | 0 | 5 |
| 7 | REVIEW_REQUESTED | DONE | 1 | 5 |
| 8 | REVIEW_APPROVED | RECORDED | 0 | 7 |
| 9 | WORKFLOW_COMPLETED | RECORDED | 0 | 7 |

Commits: `101286d3cc10` lab: semente com defeito conhecido; `d329e4264562` lab: rodada 1 (IMPLEMENT_REQUESTED); `94c05aa5eda4` lab: rodada 2 (CORRECTION_REQUESTED)
Coordenadores (processos distintos): lab-coordinator:2184, lab-coordinator:23448, lab-coordinator:36632, lab-coordinator:39300, lab-coordinator:41332, lab-coordinator:41680, lab-coordinator:41828
Leases retomados: reclaimed expired lease of lab-coordinator:36632; attempt 2; reclaimed expired lease of lab-coordinator:2184; attempt 2
Runs sem termino registrado (coordenador morreu com o CLI no ar): 1
Arvore dos CLIs interrompidos: run 1 (claude, pid 42192) apos 2.0s: nenhum processo vivo
Isolamento dos testes do coordenador (evidencia dos eventos concluidos): appcontainer_no_capabilities
Outbox: #1 `lab:slug:review:d329e42645629f31969c1e541f7e8bfea01751cc:REQUEST_CHANGES` DONE em 2 tentativa(s); #2 `lab:slug:review:94c05aa5eda4538f2aef699d67fbe7a3acac9d0b:APPROVE` DONE em 1 tentativa(s)
Ledger (o que o sistema externo recebeu): 2 linha(s), 2 chave(s) distinta(s)
Reviews bloqueados: nenhum
Motivos de falha gravados nos eventos: nenhum

Limites: testes em AppContainer sem capacidades: contem arquivo e rede, NAO a integridade do resultado (o codigo testado controla o exit code); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute; o alvo do outbox e um arquivo local que faz o papel de sistema externo; Job Object nao e sandbox: so prende a vida da arvore do CLI ao coordenador e ao lease
