# FP-060-A01 M1 — matriz de aceite e repetição do E2E no HEAD corrigido

Evidência datada (2026-11-14). Refs #606. Duas coisas:

1. uma segunda execução **real** do laboratório closed-loop, no commit `fa03d72` (árvore limpa), depois da correção de
   captura do pytest (`48f8bac`) que o CI exigiu — a execução de `../2026-11-13_sandboxed_tests/` é anterior a ela;
2. a matriz dos nove critérios de aceite do M1 (diretriz FP-060-A01 §4), cada um com a prova que o sustenta.

**Este documento não declara o M1 concluído.** Ele mostra onde está a prova de cada critério. O PR que traz o isolamento de
SO dos testes (#617) ainda não passou por revisão independente, e a decisão de aceite é humana.

## Repetição do E2E (`rerun_fa03d72/`)

Claude Code CLI 2.1.158, Codex CLI 0.164.0, Windows 11, Python 3.12.13. Um comando
(`drive --crash-on REVIEW_REQUESTED --kill-during claude`), nenhuma mensagem humana intermediária, 2 min 14 s.

| Passo | O que aconteceu |
|---|---|
| Claude, 1ª tentativa | coordenador morto com o CLI no ar; 2 s depois, nenhum processo vivo na árvore |
| Claude, 2ª tentativa | entrega da rodada 1; testes verdes no AppContainer |
| revisão, 1ª tentativa | coordenador morto logo após o claim; lease retomado por outro processo |
| Codex | `REQUEST_CHANGES` |
| Claude | correção da rodada 2 com teste de regressão; testes verdes no AppContainer |
| Codex | `APPROVE` → `WORKFLOW_COMPLETED` |

Relatório: **PASS**, 12 de 12 critérios. As quatro rodadas de testes que sustentam entregas e pareceres têm token
AppContainer sem capacidades e canário negado (`rerun_fa03d72/TEST_EVIDENCE.json`). Não sobrou workspace, canário nem
perfil AppContainer.

E2E reais positivos concluídos sem intervenção, desde 2026-11-09: **4 de 6** (`../2026-11-09/run_01` FAIL,
`run_02` com um relançamento manual; `run_03`, `../2026-11-11_supervised/`, `../2026-11-13_sandboxed_tests/` e esta sem
intervenção).

## Matriz de aceite do M1

"Teste" = suíte determinística (CLIs falsos; git, SQLite e runner de testes reais). "E2E" = execução com os dois CLIs reais.

| # | Critério (FP-060-A01 §4 M1) | Prova | Onde |
|---|---|---|---|
| 1 | CLIs reais como processos observados: PID, exit code, resultado bruto, versão, autenticação sem expor segredo | E2E | `rerun_fa03d72/REPORT.md` (tabela de runs: PID, exit, contenção, binário); `CLI_VERSIONS.json`; `verdict_e*.json` (pareceres brutos); falha de autenticação em `../2026-11-10_auth_faults/` |
| 2 | SQLite registra a sequência causal e resiste a encerramento/reinício do coordenador | E2E + teste | `REPORT.md` (eventos com pai, 7 coordenadores distintos, 2 leases retomados); `test_coordinator_crash_after_claim_is_recovered_by_a_new_owner_after_lease_expiry` |
| 3 | REQUEST_CHANGES seguido de correção e segunda revisão; nenhum humano retransmite | E2E | `DRIVE_LOG.jsonl` (um comando); critérios `request_changes_then_correction` e `approved_after_correction` |
| 4 | Inspeção do Codex vinculada ao hash/HEAD real; sem inspeção vira `REVIEW_BLOCKED` | E2E + teste | `verdict_e*.json` (`head_sha`, `sha256` e trecho literal por arquivo); critério `approval_bound_to_final_head`; `test_review_without_literal_inspection_proof_is_blocked_never_approved`, `test_reviewer_that_alters_the_workspace_invalidates_its_own_verdict` |
| 5 | Testes rodados por runner confiável, não declarados pelo modelo | E2E + teste | `TEST_EVIDENCE.json`, `sandbox_logs/`; critério `coordinator_tests_ran_in_os_sandbox`; `tests/test_sandboxed_tests.py`; `test_failing_trusted_tests_block_delivery_and_feed_the_retry` |
| 6 | Falha de auth e `is_error=true` não são tratadas como sucesso | E2E negativo + teste | `../2026-11-10_auth_faults/` (dois CLIs reais sem login → DLQ, nada aprovado); `test_is_error_true_with_exit_zero_is_a_failure_not_a_delivery`, `test_real_claude_not_logged_in_signature_is_classified_as_credential_failure`, `test_reviewer_auth_failure_is_blocked_and_retried_never_success` |
| 7 | Evento duplicado, dois eventos do mesmo agregado, claims concorrentes, lease expirado e worker morto não duplicam efeito | teste + E2E | `test_duplicate_seed_event_does_not_create_a_second_job`, `test_two_coordinators_racing_launch_a_single_cli`, `test_crash_between_delivery_and_ack_is_reconciled_without_a_second_commit`; em `tests/test_event_store.py`: `test_same_event_has_only_one_concurrent_owner`, `test_same_aggregate_different_events_have_only_one_owner`; critério `one_delivery_per_implement_event` |
| 8 | Worker antigo não publica após perder lease/fencing; órfão sem capacidade de publicação | E2E + teste | `ORPHAN_CHECKS.jsonl` (árvore vazia) contra o controle de `../2026-11-11_supervised/control_observed/` (2 vivos); `test_worker_that_lost_its_lease_cannot_deliver_a_late_result`, `test_supervised_runner_kills_the_cli_tree_and_raises_when_the_lease_is_lost`, `test_expired_aggregate_owner_cannot_complete_after_successor` |
| 9 | Relatório PASS/FAIL por passo, com evidência verificável | E2E | `REPORT.md` / `REPORT.json`, derivados do SQLite e do git; `test_report_passes_only_when_every_m1_criterion_is_derived_from_the_store` |

## Lacunas que continuam abertas

- **Revisão independente do #617.** A prova do critério 5 com isolamento de SO está num PR ainda não revisado. Sem ele em
  `develop`, o critério 5 vale só na forma anterior (runner do coordenador com allowlist de ambiente).
- **"Efeito externo" no M1 é o commit no repositório do laboratório.** Não há efeito no GitHub; isso é M2.
- **Integridade do resultado dos testes.** O código testado controla o exit code do pytest; o sandbox contém arquivo e
  rede, não o que o código declara.
- **Coordenador morto no meio dos testes** deixaria perfil AppContainer e pasta `sandbox-*` órfãos; os caos exercitados
  matam o coordenador fora dessa janela.
- **Saída bruta do Claude** fica no diretório do laboratório, não versionado; quando o coordenador morre com o CLI no ar ela
  não passa pela redação de segredos.
- **O relançamento do `drive` é manual** quando o processo hospedeiro morre (M3).
- Seis execuções reais ao todo: é demonstração, não medida de taxa de sucesso.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_sandboxed_tests.py tests/test_appcontainer_isolation.py tests/test_closed_loop_lab.py \
    tests/test_event_store.py -q
$PY -m tools.orchestration.closed_loop_lab drive --lab <dir novo fora de qualquer repositório git> \
    --crash-on REVIEW_REQUESTED --kill-during claude
```

## Arquivos (`rerun_fa03d72/`)

| Arquivo | Conteúdo |
|---|---|
| `REPORT.md`, `REPORT.json` | critérios, runs, eventos, commits, isolamento dos testes |
| `TEST_EVIDENCE.json` | evidência de testes de cada evento concluído, extraída do SQLite do laboratório |
| `sandbox_logs/` | saída bruta da sonda de isolamento e do pytest de cada rodada |
| `DRIVE_LOG.jsonl`, `ORPHAN_CHECKS.jsonl` | um registro por `step`; PIDs vivos na árvore do CLI interrompido |
| `verdict_e*.json` | pareceres brutos do Codex (rodada 1: REQUEST_CHANGES; rodada 2: APPROVE) |
| `CLI_VERSIONS.json` | versões dos CLIs e do Python, sem caminho de binário |
