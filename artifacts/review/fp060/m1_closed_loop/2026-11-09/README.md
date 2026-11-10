# FP-060-A01 M1 — closed-loop mínimo Claude Code CLI ↔ Codex CLI (laboratório isolado)

Evidência datada (2026-11-09) de três execuções **reais** de `tools/orchestration/closed_loop_lab.py`. Refs #606.
Retrato imutável: nova prova vai numa pasta nova ao lado.

## O que é

Uma tarefa descartável (corrigir `lab_slug.py` num repositório git criado só para o teste) percorre o ciclo
`IMPLEMENT_REQUESTED → Claude → testes do coordenador → commit → REVIEW_REQUESTED → Codex → REVIEW_CHANGES_REQUESTED →
CORRECTION_REQUESTED → Claude → testes → commit → REVIEW_REQUESTED → Codex → REVIEW_APPROVED → WORKFLOW_COMPLETED`
sobre o `EventStore` de produção (`tools/orchestration/event_store.py`), reutilizando o contrato de parecer e a prova de
inspeção do `codex_reviewer` e o ambiente por allowlist do `event_executor`. Um único comando dispara tudo; cada `step`
roda num **processo novo** do coordenador.

## O que NÃO é

- Não é M2: não há GitHub, PR, CI nem revisão independente publicada. O `APPROVE` é técnico de laboratório.
- Não é sandbox de SO: os testes rodam com env por allowlist (`isolation: env_allowlist_only`). Job Object/AppContainer é FP-060 P2 (#610).
- Não prova encerramento da árvore de processos de um CLI órfão (ver limite 1).
- Não usa `--execute`, credencial de publicação, dado de produção nem backlog do SketchUp.

## Ambiente e commits sob prova

| Item | Valor |
|---|---|
| SO / Python | Windows 11 / CPython 3.12.13 (venv do repositório) |
| Claude Code CLI | 2.1.158 (login de assinatura; nenhuma chave de API no ambiente do filho) |
| Codex CLI | 0.164.0 (`codex login status`: "Logged in using ChatGPT") |
| run_01 | commit `710ec50`, árvore limpa |
| run_02 | commit `4d34b57`, árvore limpa |
| run_03 | commit `16d05a8`, árvore limpa |

Os `REPORT.md`/`REPORT.json` de run_01 e run_02 foram **regenerados** em `16d05a8` (só muda a renderização: run sem término
aparece como `INTERROMPIDO` e saem os caminhos de máquina); os eventos, runs e pareceres são os das execuções originais.

## Resultado por execução

| Execução | Veredito | Rodadas | Intervenções humanas | O que aconteceu |
|---|---|---|---|---|
| run_01 | **FAIL** | 2 | 0 | Rodada 1: `REQUEST_CHANGES` (regex ASCII viola R2). Rodada 2: código corrigido, mas o Codex respondeu `NEEDS_HUMAN` três vezes — nenhum teste provava o requisito Unicode e o laboratório proibia o executor de criar teste. Terminou em `JOB_FAILED` (DLQ). Defeito do laboratório, não do revisor. |
| run_02 | **PASS** | 2 | **1** | Mesmo fluxo, com o executor autorizado a criar `tests/test_lab_slug_review.py`. A sessão hospedeira caiu com o Codex no ar (run 2 sem término registrado); foi preciso **relançar o comando** — o lease expirado foi retomado e o workflow terminou sem refazer a entrega. |
| run_03 | **PASS** | 2 | **0** | Execução limpa, 99 s de parede, incluindo a morte forçada do coordenador (`exit 86`) logo após o claim da 1ª revisão e a retomada por outro processo. |

**Métrica principal (FP-060-A01 §7):** workflows E2E reais concluídos sem intervenção manual / tentados = **1 / 3**
(2 / 3 concluídos; run_02 precisou de um relançamento manual). Custo do Claude: ≈ US$ 0,10 por execução.

## Critérios de aceite do M1

| Critério (FP-060-A01 §4 M1) | Estado | Prova |
|---|---|---|
| Claude e Codex reais como processos observados (PID, exit code, versão) | PASS | tabela de runs em `run_0*/REPORT.md` (PIDs gravados no SQLite antes de esperar o processo) |
| SQLite registra a sequência causal e resiste a reinício do coordenador | PASS | um processo por `step` (`Coordenadores` no relatório); `exit 86` em `DRIVE_LOG.jsonl`; `Leases retomados` |
| REQUEST_CHANGES → correção → segunda revisão sem retransmissão humana | PASS | eventos 3→4→5→7→8→9 de run_02 e run_03 |
| Inspeção do Codex vinculada ao hash/HEAD real; sem inspeção ⇒ `REVIEW_BLOCKED` | PASS | `verdict_e007_a1.json` (sha256 e trecho conferidos byte a byte pelo `verify_inspection`); negativos em `tests/test_closed_loop_lab.py` |
| Testes por runner do coordenador, não declarados pelo modelo | PASS com ressalva | `evidence` no resultado do evento; **sem sandbox de SO** |
| Falha de auth e `is_error=true` nunca são sucesso | PASS só determinístico | `test_is_error_true_with_exit_zero_is_a_failure_not_a_delivery`, `test_reviewer_auth_failure_is_blocked_and_retried_never_success`; **não provocado com CLI real** |
| Duplicata, claims concorrentes, lease expirado e worker morto sem efeito duplicado | PASS | testes de duplicata, corrida, crash após claim e crash entre commit e ACK; `one_delivery_per_implement_event` nas execuções reais |
| Worker antigo não entrega após perder o lease; órfão sem capacidade de publicação | **PARCIAL** | fencing provado (`test_worker_that_lost_its_lease_cannot_deliver_a_late_result`); **matar a árvore do CLI órfão depende de P2** |
| Relatório PASS/FAIL com evidência verificável | PASS | este diretório; critérios derivados do SQLite e do git, nada digitado |

**Conclusão honesta: M1 não está DONE.** O núcleo do closed-loop está demonstrado com os dois CLIs reais; faltam o item
PARCIAL (P2) e a revisão independente do PR que traz o laboratório.

## Limites conhecidos

1. **Processo órfão.** Sem Job Object, um CLI cujo coordenador morreu pode continuar rodando. No laboratório ele não tem
   caminho de entrega (cópia de trabalho por tentativa, só o coordenador commita, lease conferido antes do commit), mas
   segue consumindo cota. Em run_02 o órfão morreu junto com a sessão — por acaso, não por garantia.
2. **Janela renovação → commit.** O lease é renovado imediatamente antes do commit; a janela restante é coberta pela
   reconciliação por trailer (`Lab-Idempotency-Key`), não eliminada.
3. **Relançamento.** Quem relança o `drive` depois que o processo hospedeiro morre ainda é um humano (run_02). O supervisor
   residente é M3.
4. **Cenário induzido.** A semente tem um defeito latente (regex ASCII) que os testes de aceitação não cobrem; o pedido
   da rodada 1 cita só os testes e o revisor mede contra a especificação completa. Os vereditos são dos CLIs reais, sem
   resultado forçado: se o Codex aprovar na rodada 1, o relatório reprova o critério de correção.
5. **Tentativas.** O crash proposital consome uma das 3 tentativas do evento de revisão; em run_02 a aprovação saiu na 3ª.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_closed_loop_lab.py -q                      # suíte determinística (sem LLM)
$PY -m tools.orchestration.closed_loop_lab drive \
    --lab <diretório novo FORA de qualquer repositório git> --crash-on REVIEW_REQUESTED
```

Relançar o mesmo comando num laboratório existente **retoma** do SQLite e do git. Saída bruta saneada dos CLIs, prompts,
banco SQLite e o repositório descartável ficam no diretório do laboratório (não versionados).

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `run_0N/REPORT.md`, `REPORT.json` | critérios, runs (PID/exit), eventos, commits, coordenadores, leases retomados |
| `run_0N/DRIVE_LOG.jsonl` | um registro por `step` (processo, exit code, ação) |
| `run_0N/verdict_e<evento>_a<tentativa>.json` | parecer bruto do Codex (`--output-last-message`) |
