# FP-060-A01 M1 — CLI órfão: árvore de processos presa ao coordenador e ao lease

Evidência datada (2026-11-11) de duas execuções **reais** de `tools/orchestration/closed_loop_lab.py` no commit `1814f43`
(árvore limpa). Refs #606. Complementa `../2026-11-09/` e `../2026-11-10_auth_faults/`, onde este critério estava PARCIAL.

## O que é

O critério do M1 "nenhum worker antigo publica após perder o lease; processo órfão não mantém capacidade de publicação"
exercitado com o Process Supervisor da FP-060 P2 (`process_supervisor.run_claimed`): no Windows, cada CLI do laboratório
passa a rodar dentro de um Job Object que renova o lease enquanto o CLI roda e mata a **árvore inteira** quando o lease se
perde, no timeout ou quando o coordenador morre (o sistema fecha o handle do job).

O caos `--kill-during claude` mata o coordenador (`os._exit(86)`) 4 s depois de o Claude subir. O driver espera 2 s e
lista, a partir de um snapshot do sistema, os PIDs ainda vivos na árvore do CLI interrompido.

## Resultado

| Execução | Runner | Depois de matar o coordenador com o Claude no ar | Workflow | Veredito |
|---|---|---|---|---|
| `control_observed/` | sem Job Object (`--runner observed`) | **2 processos vivos** (o Claude e um descendente) | interrompido de propósito após a verificação | FAIL (esperado: é o controle) |
| `supervised/` | Job Object | **nenhum processo vivo** | retomou sozinho e terminou: REQUEST_CHANGES → correção → APPROVE → `WORKFLOW_COMPLETED` | **PASS** |

A execução `supervised/` é o cenário completo num único comando, sem mensagem humana intermediária, com **duas** mortes
do coordenador: uma com o Claude no ar (`--kill-during claude`) e outra logo após o claim da revisão
(`--crash-on REVIEW_REQUESTED`). Os quatro CLIs que terminaram rodaram com `containment=job_object`; o evento cujo
CLI foi morto ficou retomável em menos de 30 s (lease curto, renovado a cada 2 s pelo supervisor).

O controle existe para mostrar que a verificação discrimina: com o mesmo caos e sem o supervisor, o órfão sobrevive.

## Critérios do M1 depois desta evidência

| Critério (FP-060-A01 §4 M1) | Estado | Prova |
|---|---|---|
| Worker antigo não entrega após perder o lease; órfão sem capacidade de publicação | **PASS** | `supervised/ORPHAN_CHECKS.jsonl` (árvore vazia) × `control_observed/ORPHAN_CHECKS.jsonl` (2 vivos); `test_supervised_runner_kills_the_cli_tree_and_raises_when_the_lease_is_lost`; `test_worker_that_lost_its_lease_cannot_deliver_a_late_result` |
| Demais critérios do closed-loop | PASS | `supervised/REPORT.md` (11 critérios derivados do SQLite, do git e da verificação de órfãos) |
| Testes por runner do coordenador | PASS **sem sandbox de SO** | inalterado: `env_allowlist_only` |

## O que NÃO é

- **Job Object não é sandbox.** Ele prende a vida da árvore ao coordenador e ao lease; não restringe rede, disco nem
  credenciais. Os testes do coordenador continuam sem isolamento de SO (o AppContainer do P2 ainda é protótipo e não foi
  ligado ao laboratório).
- A verificação de órfãos é uma observação 2 s depois da morte, por snapshot; não prova ausência de processo que tenha
  escapado do job por outro meio (nenhum foi observado).
- A saída bruta de um CLI morto no meio fica no diretório do laboratório **sem** passar pela redação de segredos (o
  coordenador que faria isso morreu). Esse diretório não é versionado.
- Não elimina o relançamento manual do `drive` quando o processo hospedeiro morre (M3) nem cobre GitHub (M2).
- Uma execução por cenário: é demonstração, não medida de taxa de sucesso.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_process_supervisor.py tests/test_closed_loop_lab.py -q
$PY -m tools.orchestration.closed_loop_lab drive --lab <dir novo fora de qualquer repositório git> \
    --crash-on REVIEW_REQUESTED --kill-during claude
$PY -m tools.orchestration.closed_loop_lab drive --lab <outro dir novo> --runner observed --kill-during claude \
    --max-steps 3 --idle-limit 3                                   # controle: o órfão sobrevive
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `<execução>/REPORT.md`, `REPORT.json` | critérios, runs (PID, exit, contenção), eventos, commits, verificação de órfãos |
| `<execução>/DRIVE_LOG.jsonl` | um registro por `step` (exit code do processo, ação, órfãos encontrados) |
| `<execução>/ORPHAN_CHECKS.jsonl` | PIDs vivos na árvore de cada CLI interrompido |
| `supervised/verdict_e*.json` | pareceres brutos do Codex (rodada 1: REQUEST_CHANGES; rodada 2: APPROVE) |
