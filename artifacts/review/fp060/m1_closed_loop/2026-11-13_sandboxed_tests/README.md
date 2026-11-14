# FP-060-A01 M1 — testes do coordenador dentro de um AppContainer sem capacidades

Evidência datada (2026-11-13) de uma execução **real** de `tools/orchestration/closed_loop_lab.py` no commit `1dde548`
(árvore limpa), com Claude Code CLI 2.1.158 e Codex CLI 0.164.0, Windows 11, Python 3.12.13. Refs #606. Complementa
`../2026-11-11_supervised/`, onde este item estava declarado como "PASS **sem sandbox de SO**".

## O que é

O laboratório roda os testes do código escrito pelo agente antes de entregar e antes de revisar. Até aqui eles rodavam no
contexto do usuário, só com uma allowlist de variáveis de ambiente. Nesta execução cada rodada de testes aconteceu sobre uma
cópia da árvore dentro de um AppContainer do Windows **sem capacidades**, num Job Object kill-on-close
(`tools/orchestration/sandboxed_tests.py`).

Cada rodada de testes carrega duas provas feitas nela mesma, antes de o pytest começar:

1. o token do processo criado, lido do kernel: é AppContainer e tem zero capacidades;
2. uma sonda no mesmo perfil e workspace não lê nem escreve um canário fora do workspace, e escreve dentro dele.

O critério novo do relatório, `coordinator_tests_ran_in_os_sandbox`, é derivado da evidência gravada nos eventos concluídos
do SQLite: só passa se **toda** entrega e **todo** parecer tiverem o rótulo do AppContainer **e** as duas provas.

## Resultado

Um comando, nenhuma mensagem humana intermediária, 2 min 22 s do primeiro ao último passo:

| Passo relevante | O que aconteceu |
|---|---|
| semente | testes de aceitação reprovados como esperado (3 falhas, exit 1), já dentro do AppContainer |
| Claude, 1ª tentativa | coordenador morto com o CLI no ar (`--kill-during claude`); 2 s depois, nenhum processo vivo na árvore |
| Claude, 2ª tentativa | entrega da rodada 1; testes verdes no AppContainer |
| revisão, 1ª tentativa | coordenador morto logo após o claim (`--crash-on REVIEW_REQUESTED`); lease retomado |
| Codex | `REQUEST_CHANGES` |
| Claude | correção da rodada 2, com teste de regressão; 10 testes verdes no AppContainer |
| Codex | `APPROVE` → `WORKFLOW_COMPLETED` |

Veredito do relatório: **PASS**, 12 de 12 critérios (`sandboxed/REPORT.md`).

As quatro rodadas de testes que sustentam entregas e pareceres estão em `sandboxed/TEST_EVIDENCE.json`: todas com
`isolation = appcontainer_no_capabilities`, `is_appcontainer = true`, `capabilities = 0`, canário negado para leitura e
escrita e `workspace_removed = true`. Depois da execução não sobrou workspace, canário nem perfil AppContainer.

## Critérios do M1 depois desta evidência

| Critério (FP-060-A01 §4 M1) | Estado | Prova |
|---|---|---|
| Testes por runner do coordenador | **PASS com isolamento de SO** | `sandboxed/TEST_EVIDENCE.json`, `sandboxed/sandbox_logs/*_probe.txt`; `tests/test_sandboxed_tests.py` |
| Worker antigo não entrega após perder o lease; órfão sem capacidade de publicação | PASS | `sandboxed/ORPHAN_CHECKS.jsonl` (árvore vazia) |
| Demais critérios do closed-loop | PASS | `sandboxed/REPORT.md` |

## O que NÃO é

- **Não garante a integridade do resultado.** O código testado roda no mesmo processo do pytest e controla exit code e
  saída. O sandbox contém o que esse código alcança (arquivos, rede); não o impede de declarar sucesso.
- **Não há controle com CLIs reais nesta pasta.** O contraste "com e sem sandbox" está nos testes determinísticos: a mesma
  árvore que tenta ler fora, escrever fora e conectar em `127.0.0.1` falha nas três tentativas dentro do AppContainer e
  consegue as três fora dele; e um laboratório com `--test-isolation env` reprova o critério do relatório.
- **Não cobre a morte do coordenador no meio dos testes.** O Job Object mata o processo, mas o perfil AppContainer e a pasta
  `sandbox-*` ficariam órfãos. Os dois caos desta execução matam o coordenador fora da janela dos testes.
- **Não impõe limite de CPU, memória ou disco** dentro do workspace.
- **Não muda produção.** `codex_reviewer.run_coordinator_tests` continua fail-closed e a publicação automática de APPROVE
  continua bloqueada; o rótulo usado aqui é do laboratório.
- Não elimina o relançamento manual do `drive` quando o processo hospedeiro morre (M3) nem cobre GitHub (M2).
- Uma execução: é demonstração, não medida de taxa de sucesso.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_sandboxed_tests.py tests/test_appcontainer_isolation.py tests/test_closed_loop_lab.py -q
$PY -m tools.orchestration.closed_loop_lab drive --lab <dir novo fora de qualquer repositório git> \
    --crash-on REVIEW_REQUESTED --kill-during claude
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `sandboxed/REPORT.md`, `REPORT.json` | critérios, runs (PID, exit, contenção), eventos, commits, isolamento dos testes |
| `sandboxed/TEST_EVIDENCE.json` | evidência de testes de cada evento concluído, extraída do SQLite do laboratório |
| `sandboxed/sandbox_logs/*_probe.txt` | saída bruta da sonda de isolamento de cada rodada de testes |
| `sandboxed/sandbox_logs/*_tests.txt` | saída bruta do pytest dentro do AppContainer |
| `sandboxed/DRIVE_LOG.jsonl` | um registro por `step` (exit code do processo, ação, órfãos encontrados) |
| `sandboxed/ORPHAN_CHECKS.jsonl` | PIDs vivos na árvore do CLI interrompido |
| `sandboxed/verdict_e*.json` | pareceres brutos do Codex (rodada 1: REQUEST_CHANGES; rodada 2: APPROVE) |
