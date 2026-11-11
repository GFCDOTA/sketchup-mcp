# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: PASS** · modo `closed_loop` · lab `run_20261111_supervised_01` · HEAD final `f5582eaee7f0cfa201ecb682f105d5920dd02bbe`

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

| Run | Evento | Agente | PID | Exit | s | Contencao | Binario |
|---|---|---|---|---|---|---|---|
| 1 | 1 | claude | 13300 | INTERROMPIDO | - | - | `claude.exe` |
| 2 | 1 | claude | 26256 | 0 | 9.7 | job_object | `claude.exe` |
| 3 | 3 | codex | 32500 | 0 | 24.4 | job_object | `codex.exe` |
| 4 | 5 | claude | 10832 | 0 | 26.4 | job_object | `claude.exe` |
| 5 | 7 | codex | 34320 | 0 | 25.3 | job_object | `codex.exe` |

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

Commits: `4a8b0e551bc5` lab: semente com defeito conhecido; `0f8c6b1d56f6` lab: rodada 1 (IMPLEMENT_REQUESTED); `f5582eaee7f0` lab: rodada 2 (CORRECTION_REQUESTED)
Coordenadores (processos distintos): lab-coordinator:10892, lab-coordinator:1340, lab-coordinator:24468, lab-coordinator:26552, lab-coordinator:30936, lab-coordinator:35256, lab-coordinator:9048
Leases retomados: reclaimed expired lease of lab-coordinator:26552; attempt 2; reclaimed expired lease of lab-coordinator:35256; attempt 2
Runs sem termino registrado (coordenador morreu com o CLI no ar): 1
Arvore dos CLIs interrompidos: run 1 (claude, pid 13300) apos 2.0s: nenhum processo vivo
Reviews bloqueados: nenhum
Motivos de falha gravados nos eventos: nenhum

Limites: testes sem sandbox de SO (env_allowlist_only; FP-060 P2); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute, sem outbox externo; Job Object nao e sandbox: so prende a vida da arvore do CLI ao coordenador e ao lease
