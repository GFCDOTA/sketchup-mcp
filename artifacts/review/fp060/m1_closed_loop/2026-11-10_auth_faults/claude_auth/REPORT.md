# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: PASS** · modo `negative:claude-auth` · lab `run_20261110_neg_claude_auth_2` · HEAD final `3908cfa64b7f8c78b81b480da6fa7daa68f4bc36`

| Criterio (derivado do SQLite/git) | Resultado |
|---|---|
| faulted_cli_really_started | PASS |
| faulted_cli_never_exited_zero | PASS |
| faulted_cli_never_completed_an_event | PASS |
| no_approval_or_completion | PASS |
| dead_lettered_with_job_failed | PASS |
| one_delivery_per_implement_event | PASS |
| no_pending_or_running_event | PASS |

| Run | Evento | Agente | PID | Exit | s | Binario |
|---|---|---|---|---|---|---|
| 1 | 1 | claude | 5692 | 1 | 0.8 | `claude.exe` |
| 2 | 1 | claude | 21012 | 1 | 0.6 | `claude.exe` |
| 3 | 1 | claude | 23888 | 1 | 0.7 | `claude.exe` |

| # | Evento | Estado | Tentativas | Pai |
|---|---|---|---|---|
| 1 | IMPLEMENT_REQUESTED | DLQ | 3 |  |
| 2 | JOB_FAILED | RECORDED | 0 | 1 |

Commits: `3908cfa64b7f` lab: semente com defeito conhecido
Coordenadores (processos distintos): lab-coordinator:33644, lab-coordinator:35480, lab-coordinator:8888
Leases retomados: nenhum
Runs sem termino registrado (coordenador morreu com o CLI no ar): nenhum
Reviews bloqueados: nenhum
Motivos de falha gravados nos eventos: claude devolveu erro (credencial/login, exit 1): Not logged in · Please run /login

Limites: testes sem sandbox de SO (env_allowlist_only; FP-060 P2); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute, sem outbox externo
