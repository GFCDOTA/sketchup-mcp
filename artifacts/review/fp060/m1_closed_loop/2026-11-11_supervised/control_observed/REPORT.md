# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: FAIL** · modo `closed_loop` · lab `run_20261111_control_observed` · HEAD final `90fa6ead750a3d1be01bfd0944e11d8be429c56e`

| Criterio (derivado do SQLite/git) | Resultado |
|---|---|
| claude_cli_observed | FAIL |
| codex_cli_observed | FAIL |
| request_changes_then_correction | FAIL |
| approved_after_correction | FAIL |
| approval_bound_to_final_head | FAIL |
| workflow_completed | FAIL |
| no_pending_or_running_event | FAIL |
| one_delivery_per_implement_event | PASS |
| survived_coordinator_restart | FAIL |
| finished_cli_runs_job_contained | FAIL |
| orphan_cli_tree_dead_after_coordinator_kill | FAIL |

| Run | Evento | Agente | PID | Exit | s | Contencao | Binario |
|---|---|---|---|---|---|---|---|
| 1 | 1 | claude | 32688 | INTERROMPIDO | - | - | `claude.exe` |

| # | Evento | Estado | Tentativas | Pai |
|---|---|---|---|---|
| 1 | IMPLEMENT_REQUESTED | RUNNING | 1 |  |

Commits: `90fa6ead750a` lab: semente com defeito conhecido
Coordenadores (processos distintos): lab-coordinator:9724
Leases retomados: nenhum
Runs sem termino registrado (coordenador morreu com o CLI no ar): 1
Arvore dos CLIs interrompidos: run 1 (claude, pid 32688) apos 2.0s: VIVOS [30848, 32688]
Reviews bloqueados: nenhum
Motivos de falha gravados nos eventos: nenhum

Limites: testes sem sandbox de SO (env_allowlist_only; FP-060 P2); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute, sem outbox externo; Job Object nao e sandbox: so prende a vida da arvore do CLI ao coordenador e ao lease
