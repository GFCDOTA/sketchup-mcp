# FP-060-A01 M1 — closed-loop minimo em laboratorio isolado

**Veredito: PASS** · modo `negative:codex-auth` · lab `run_20261110_neg_codex_auth_2` · HEAD final `a8697a9cc9668a2eb22b1bd7f0c513ee6ea1ef02`

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
| 1 | 1 | claude | 32044 | 0 | 8.7 | `claude.exe` |
| 2 | 3 | codex | 12628 | 1 | 15.0 | `codex.exe` |
| 3 | 3 | codex | 38180 | 1 | 13.8 | `codex.exe` |
| 4 | 3 | codex | 9404 | 1 | 13.5 | `codex.exe` |

| # | Evento | Estado | Tentativas | Pai |
|---|---|---|---|---|
| 1 | IMPLEMENT_REQUESTED | DONE | 1 |  |
| 2 | IMPLEMENT_COMPLETED | RECORDED | 0 | 1 |
| 3 | REVIEW_REQUESTED | DLQ | 3 | 1 |
| 4 | REVIEW_BLOCKED | RECORDED | 0 | 3 |
| 5 | REVIEW_BLOCKED | RECORDED | 0 | 3 |
| 6 | REVIEW_BLOCKED | RECORDED | 0 | 3 |
| 7 | JOB_FAILED | RECORDED | 0 | 3 |

Commits: `6e892ccfa6e3` lab: semente com defeito conhecido; `a8697a9cc966` lab: rodada 1 (IMPLEMENT_REQUESTED)
Coordenadores (processos distintos): lab-coordinator:29904, lab-coordinator:32836, lab-coordinator:34476, lab-coordinator:34548
Leases retomados: nenhum
Runs sem termino registrado (coordenador morreu com o CLI no ar): nenhum
Reviews bloqueados: auth/limite de uso: cted status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses; auth/limite de uso: cted status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses; auth/limite de uso: cted status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses
Motivos de falha gravados nos eventos: auth/limite de uso: cted status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses

Limites: testes sem sandbox de SO (env_allowlist_only; FP-060 P2); APPROVE tecnico de laboratorio != review independente no GitHub (M2); sem GitHub, sem --execute, sem outbox externo
