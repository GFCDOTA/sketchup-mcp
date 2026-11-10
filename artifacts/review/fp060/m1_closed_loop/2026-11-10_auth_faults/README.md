# FP-060-A01 M1 — prova negativa: falha de autenticação com os CLIs reais

Evidência datada (2026-11-10 UTC) de duas execuções **reais** de `tools/orchestration/closed_loop_lab.py drive --fault …`.
Refs #606. Complementa `../2026-11-09/` (closed-loop positivo), onde este critério estava provado só com runners falsos.

## O que é

O critério do M1 "falhas de auth e `is_error=true` não são tratadas como sucesso" exercitado com os binários reais. Os
processos `step` de **um** dos CLIs recebem um diretório de configuração do próprio laboratório, sem login
(`CLAUDE_CONFIG_DIR` para o Claude, `CODEX_HOME` para o Codex). Nenhuma credencial real é lida, copiada ou alterada: só a
variável de ambiente do processo filho muda. Depois das execuções, `codex login status` e `claude auth status`
continuaram reportando as sessões reais como logadas.

Neste modo o relatório mede a prova **negativa**: `PASS` significa que a falha continuou sendo falha até o DLQ.

## Resultado

| Execução | Commit | Falha injetada | O que o CLI real fez | Desfecho | Veredito |
|---|---|---|---|---|---|
| `claude_auth/` | `28aab9b` | Claude sem login | 3 processos, `exit 1`, resultado com `subtype: success` **e** `is_error: true`, "Not logged in · Please run /login" | `IMPLEMENT_REQUESTED` em DLQ após 3 tentativas, `JOB_FAILED`, **nenhum commit** além da semente, nenhuma revisão pedida | PASS |
| `codex_auth/` | `2ea7653` | Codex sem login | Claude real entregou a rodada 1; 3 processos do Codex, `exit 1`, `401 Unauthorized`, nenhum parecer gerado | 3 × `REVIEW_BLOCKED`, `REVIEW_REQUESTED` em DLQ, `JOB_FAILED`, **nenhuma aprovação**, 1 commit por evento entregue | PASS |

O relatório de `claude_auth/` foi regenerado em `2ea7653` (por isso a última linha do `DRIVE_LOG.jsonl` é um `TERMINAL`
posterior); eventos e runs são os da execução em `28aab9b`.

A assinatura do Claude sem login é exatamente a do defeito D-060-04 da SPEC: `subtype: success` com `is_error: true`.

## Defeitos do próprio laboratório que estas execuções reais encontraram

1. **Classificação errada.** O Claude sem login sai com `exit 1` *e* devolve um resultado válido com `is_error: true`; o
   laboratório olhava o exit code primeiro e registraria "sem resultado válido". Agora `is_error` é avaliado antes e o motivo
   gravado é `credencial/login`.
2. **Driver derrubado por um caractere.** Na primeira tentativa de `claude-auth` o `drive` morreu com `UnicodeEncodeError`
   ao imprimir o "·" da mensagem (pipe em cp1252 no Windows). O estado do laboratório ficou íntegro — relançar o comando
   terminou o workflow — mas o driver não podia cair. A saída de máquina passou a ser JSON só com ASCII.
3. **Identificadores de rede no motivo.** O `401` do Codex traz `cf-ray` e `request id`; eles saem do motivo antes de
   chegar ao evento, ao log e ao relatório (a primeira execução de `codex-auth`, em `cee42ba`, os continha e por isso não
   foi versionada).

## O que NÃO é

- Não prova expiração de token no meio de uma execução, limite de uso nem credencial revogada: só "sem login".
- Não muda os limites de `../2026-11-09/README.md`: sem sandbox de SO, sem encerramento da árvore de processos órfãos
  (P2), sem supervisor residente (M3), sem GitHub (M2).

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_closed_loop_lab.py -q -k "fault or negative or not_logged_in or network or ascii"
$PY -m tools.orchestration.closed_loop_lab drive --lab <dir novo fora de qualquer repositório git> --fault claude-auth
$PY -m tools.orchestration.closed_loop_lab drive --lab <outro dir novo> --fault codex-auth
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `<falha>/REPORT.md`, `REPORT.json` | critérios negativos, runs (PID/exit), eventos, commits, motivos de falha |
| `<falha>/DRIVE_LOG.jsonl` | um registro por `step` (exit code do processo, ação, motivo) |
