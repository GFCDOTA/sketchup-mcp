# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: PASS** · modo `closed_loop` · lab `run_20261113_sandbox_01` · HEAD final `58413e65992de36eb393087a9764133c1dad38a2`

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

| Run | Evento | Agente | PID | Exit | s | Contencao | Binario |
|---|---|---|---|---|---|---|---|
| 1 | 1 | claude | 14924 | INTERROMPIDO | - | - | `claude.exe` |
| 2 | 1 | claude | 41648 | 0 | 10.3 | job_object | `claude.exe` |
| 3 | 3 | codex | 37732 | 0 | 26.7 | job_object | `codex.exe` |
| 4 | 5 | claude | 37996 | 0 | 16.6 | job_object | `claude.exe` |
| 5 | 7 | codex | 27384 | 0 | 22.7 | job_object | `codex.exe` |

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

Commits: `2b14021af865` lab: semente com defeito conhecido; `7022c4a0a9bf` lab: rodada 1 (IMPLEMENT_REQUESTED); `58413e65992d` lab: rodada 2 (CORRECTION_REQUESTED)
Coordenadores (processos distintos): lab-coordinator:37848, lab-coordinator:39352, lab-coordinator:41788, lab-coordinator:42540, lab-coordinator:42716, lab-coordinator:42764, lab-coordinator:8828
Leases retomados: reclaimed expired lease of lab-coordinator:39352; attempt 2; reclaimed expired lease of lab-coordinator:8828; attempt 2
Runs sem termino registrado (coordenador morreu com o CLI no ar): 1
Arvore dos CLIs interrompidos: run 1 (claude, pid 14924) apos 2.0s: nenhum processo vivo
Isolamento dos testes do coordenador (evidencia dos eventos concluidos): appcontainer_no_capabilities
Reviews bloqueados: nenhum
Motivos de falha gravados nos eventos: nenhum

Limites: testes em AppContainer sem capacidades: contem arquivo e rede, NAO a integridade do resultado (o codigo testado controla o exit code); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute, sem outbox externo; Job Object nao e sandbox: so prende a vida da arvore do CLI ao coordenador e ao lease
