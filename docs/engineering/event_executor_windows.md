# Executor local do Claude Code (Issue #589) — Windows, Agendador de Tarefas e teste controlado

Estado: fase 1 (`event_bridge`, #590) mergeada; fase 2 (`event_executor`, #591) **em revisão**. Nada aqui ativa `-Execute`
sem aprovação independente de `fmmodesto` no #591.

## O que roda e com que identidade

`tools/orchestration/run_event_bridge.ps1` → `python -m tools.orchestration.event_executor run` com o `gh auth` do **executor**
(`fmodesto30`). O launcher e o Python recusam (exit 3) qualquer outra conta, em especial o revisor `fmmodesto`.
Sem `-Execute` é **dry-run**: ingere a fila e mostra o que rodaria. Com `-Execute` consome um item por vez e chama o `claude` local.

## Medido no Windows real (2026-11-04, claude 2.1.158, sonda em repo de brinquedo)

| Achado | Consequência no código |
|---|---|
| `claude` instalado pelo npm é um shim `claude.cmd`; `CreateProcess("claude")` falha (WinError 2) e `.cmd` passaria pelo `cmd.exe` | `resolve_claude()` usa o `claude.exe` ao lado do shim (ou `CLAUDE_BIN`); nunca roda `.cmd` |
| O hook `rtk` do usuário reescreve `git status` → `rtk git status` **antes** da checagem de permissão; **todo** padrão `Bash(git …)` passava a negar (inclusive `git status`) | `--setting-sources ""` (fonte vazia) `--strict-mcp-config` |
| **Correção do 2º review:** `--setting-sources local` NÃO isola — `local` é uma fonte a carregar (`.claude/settings.local.json` do cwd). Sonda negativa com settings hostis (`allow Bash(rm:*)` + hook que grava marcador) em claude 2.1.158: `local` → **INVADIDO** (hook executou); `""` → **ISOLADO** (nenhum hook, nenhuma permissão extra). `--bare` não serve (exige `ANTHROPIC_API_KEY`, nunca lê o login OAuth) | `build_command` usa fonte vazia; `tools/orchestration/isolation_probe.py` reproduz a medição. Com as settings hostis presentes, a sonda 8/8 da allowlist continua igual |
| Com isso, 8/8 casos deram o resultado esperado | ver tabela abaixo |

Sonda (`tools/orchestration/allowlist_probe.py`, remoto bare local, nada tocou o GitHub; custo ≈ US$ 0,08):

| Comando | Resultado |
|---|---|
| `git status` · `<venv>/python.exe -m pytest --version` · `git push origin HEAD:feat/x` | permitido |
| `git push origin HEAD:other` · `… HEAD:feat/x --force` · `rm a.txt` · `gh api user` · `<venv>/python.exe -c …` | **negado** |

Limite do isolamento: *managed settings* da máquina (política corporativa) não são desligáveis por flag; esta máquina não tem.

Limites que continuam: `Edit`/`Write` não têm restrição de caminho além do cwd/`--add-dir` da worktree; o venv (`BRIDGE_PYTHON`
ou `.venv` do checkout principal) é compartilhado com a worktree do PR; não há merge automático nem tratamento de `APPROVED`.

## Mutex da execução (como não rodar o mesmo item duas vezes)

O `lockfile` do `execution_state` é quebrado após 60 s — não serve para proteger 45 min. Por isso: **claim** (`RUNNING` + `owner`
+ `lease_expires`) gravado sob trava curta; o Claude roda **sem** a trava; um *heartbeat* renova o lease a cada 60 s (lease 5 min);
toda gravação final exige `owner` igual (perdeu o lease → resultado descartado e diagnosticado). Lease vencido = dono morto →
reenfileira; se o HEAD já mudou (o Claude chegou a empurrar) vira `SUPERSEDED`, nunca reexecuta.

**Perda de lease com o filho vivo (2º review):** o heartbeat, ao perder o dono ou não conseguir renovar antes do lease acabar, aciona `cancel` e `default_runner` derruba a árvore do filho (`taskkill /T` no PID dele) — fail-closed; o resultado é descartado. Backstop adicional: o push do prompt é `git push origin HEAD:<branch>` **sem force**; um 2º filho a partir do mesmo SHA seria rejeitado como não-fast-forward. Janela residual: pausa do SO (suspensão) em que nem o heartbeat roda — ao voltar, o 1º tick cancela, mas o filho pode ter publicado nesse intervalo.

## Iniciar automaticamente pelo Agendador de Tarefas

Pré-requisitos (uma vez): `uv sync --locked --extra dev`, `gh auth login` como `fmodesto30`, `claude auth login` na conta do proprietário.

```powershell
cd E:\Claude\apps\sketchup-mcp
powershell -File tools\orchestration\install_event_bridge_task.ps1            # registra em DRY-RUN
Start-ScheduledTask -TaskName "sketchup-mcp event bridge"                      # inicia agora (ou faca logoff/logon)
Get-Content runs\governance\event_bridge.log -Tail 20 -Wait                    # acompanhar
.venv\Scripts\python.exe -m tools.orchestration.event_executor status          # fila / bloqueios / diagnosticos
```

Depois da aprovação do #591: `install_event_bridge_task.ps1 -Execute` (re-registra com `-Execute`). Parar: `Stop-ScheduledTask`
ou criar `runs\governance\EXECUTOR_DISABLED` (interruptor: o executor para de consumir a fila no próximo ciclo). Remover:
`install_event_bridge_task.ps1 -Remove`. A tarefa roda como o próprio usuário, só com a sessão dele ativa, 1 instância, e reinicia
até 3× a cada 5 min. Sem admin e sem segredo gravado: usa o keyring do `gh` e o login do `claude`.

## Teste real controlado (E2E) — protocolo

Só depois do #591 mergeado (ou com o checkout do #591) e **sem** declarar sucesso antes das evidências:

1. PR descartável `chore/e2e-executor-probe` contra `develop` com `Refs #589` no corpo e uma mudança trivial **em docs**.
2. `fmmodesto` publica `CHANGES_REQUESTED` pedindo uma correção objetiva e pequena (ex.: "acrescente a linha X em docs/..."),
   no HEAD atual.
3. `python -m tools.orchestration.event_executor run --once` (dry-run) → confirmar `DRY_RUN` com o review certo.
4. `… run --once --execute` → esperado: `DONE`, **novo commit na mesma branch**, comentário do executor no PR com SHA/testes,
   estado `DONE_AWAITING_REREVIEW`, log em `runs\governance\executor\`.
5. `fmmodesto` reavalia o novo HEAD. Fechar o PR sem merge (sonda). Registrar na #589: PR, SHA antes/depois, log, veredito.

Critérios de falha a registrar como tal: qualquer push para outra branch, merge, alteração fora do escopo do review, ou item
reexecutado.

## Estabilização do listener (2026-11-04, medido no Windows real)

- **Log UTF-8:** `Tee-Object` do PS 5.1 gravava UTF-16 misturado com UTF-8. O launcher agora usa `event_bridge_log.ps1`
  (`Initialize-BridgeLog`/`Write-BridgeLog`): UTF-8 sem BOM, LF; log legado (byte NUL) é **preservado** como
  `event_bridge.log.legacy-utf16-<data>`; acima de 5 MB roda para `event_bridge.log.1`. Testes rodam o PowerShell 5.1 real.
- **Achado — órfãos e duas instâncias:** `Stop-ScheduledTask` matou só o `powershell.exe` do launcher; o `python.exe` (shim do venv +
  python real) **continuou vivo** e o `Start-ScheduledTask` seguinte criou uma 2ª cadeia → 2 executores consumindo a mesma fila.
  (A cadeia normal tem 3 processos: `powershell` → `python` do venv (shim) → `python` real; os dois `python.exe` são pai/filho, não 2 executores.)
- **Correção:** (1) `InstanceLock`: lock exclusivo do SO (`msvcrt`/`fcntl`) mantido pela vida do processo — a 2ª instância sai com código **4**
  sem consumir a fila; o SO solta o lock se o processo morrer (sem pidfile velho). (2) `--watch-pid`: o launcher passa o próprio `$PID`; se ele
  morrer o executor sai (código 5) e, se houver filho Claude rodando, o heartbeat o derruba. Medido: com o launcher morto à força a cadeia some
  em < 8 s; um 2º launcher com o 1º vivo sai com 4; reinício normal sobe 1 cadeia.
- **Limite:** as 3 provas acima usaram o launcher desta branch num checkout de teste; o listener do Agendador só passa a ter o comportamento
  depois do merge e do reinício da tarefa.


## Entrega pelo executor e autorizacao por label (review #598)
O PR so e processado com a label `executor-ok` (autorizacao explicita, revalidada no preflight). A entrega (`executor_delivery.deliver`) revalida a
autorizacao no GitHub ANTES de stagear e de novo IMEDIATAMENTE antes do push (HEAD == SHA revisado, review valido, label, identidade) e confere o HEAD remoto
(`ls-remote`). Staging explicito da allowlist validada (nunca `git add` em massa): arquivo regular, tipo permitido, nao critico, sem symlink/gitlink; depois
`execution_guards` (teto, binario, paths). Testes so rodam por selecao segura (testes alterados + `tests/test_<modulo>*.py`); sem selecao => bloqueia.
