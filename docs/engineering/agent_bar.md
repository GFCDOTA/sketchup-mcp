# Agent bar (FP-058)

Barra flutuante do Windows que **observa** Claude Code, Codex CLI, o listener/orquestrador (FP-057/#589) e o GitHub.
Painel de observabilidade e controle seguro, **nao** um segundo orquestrador.

## Uso

```powershell
uv sync --locked --extra dev --extra agent-bar      # PySide6-Essentials e opcional (o CI nao instala)
.\tools\orchestration\agent_bar\run_agent_bar.ps1   # inicia a barra
python -m tools.orchestration.agent_bar.app --once-json   # diagnostico em texto, sem GUI
```
Clique na barra = painel expandido; arraste = mover (posicao salva em `%APPDATA%\agent_bar\settings.json`); botao direito = menu.
Inicio no login: `run_agent_bar.ps1 -Autostart` (pede confirmacao; nunca automatico). Nao exige administrador.

## Fontes reais (nada novo e gravado)
`runs/governance/event_bridge.json` (heartbeat = `last_poll`, modo, fila, diagnosticos), `event_bridge.log`, `event_executor.instance.lock`,
`EXECUTOR_DISABLED`, `executor/*.log`, tabela de processos (CIM), Tarefa Agendada `sketchup-mcp event bridge`, `gh` (cache, 60 s).
O diretorio e o do checkout **principal** (`AGENT_BAR_GOV_DIR` sobrescreve).

## Cores
verde operacional · azul executando · amarelo aguardando/ocioso/ambiguo · vermelho erro · **cinza desligado, desconhecido, nao integrado**.
Ausencia de dado nunca e verde. Claude so e "Executando" se o `claude.exe` for **descendente** do executor monitorado; outros
`claude.exe` sao contados como "fora do orquestrador". Codex fica **Nao integrado** ate existir revisor automatico (instalado != integrado).

## Controles e limites
Abrir repo/Project #1/PR/logs, copiar diagnostico, atualizar, parar e reiniciar (em DRY_RUN) o listener pela Tarefa Agendada.
Parar/reiniciar pede confirmacao e **recusa** com execucao ativa, tabela de processos indisponivel ou acao da tarefa com `-Execute`.
Sem botao de execucao, sem iniciar Claude, sem `taskkill`, sem commit/push/branch, sem mexer em gates.

## Arquitetura
`models.py` (estado) · `collectors.py` (leitura, I/O injetavel) · `controls.py` (operacoes) · `settings.py` · `window.py` (Qt) · `app.py`.
Coleta em thread propria; a UI so recebe `Snapshot` por sinal. Backlog = Project #1 real via UMA consulta GraphQL enxuta (campo Status, paginada; cache 5 min). Falha mostra o erro tecnico (escopo `read:project`, rate limit...) e mantem a ultima leitura boa marcada como desatualizada.

## Estados (evolucao)
- **Modo:** `DRY_RUN — execucao automatica desligada` (ambar) / `EXECUTE` (vermelho); linha "apenas monitorando" x "TRABALHANDO" (fila RUNNING).
- **Claude:** executando = descendente do executor. Processos vivos fora dele: sessoes interativas (Claude Code) e auxiliares do app Desktop sao contados a parte; historico so em disco nunca entra.
- **Codex:** `Nao integrado` (instalado) / `Analise manual` (processo vivo fora do orquestrador) / `Vinculado`/`Revisando PR (vinculado)` (filho do executor) /
  `Falhou`/`Ocioso` (ultimo parecer) lendo `runs/governance/codex/last_review.json` (contrato para a futura integracao; ausente = nao integrado).
  O revisor automatico NAO e declarado operacional antes do E2E Claude<->Codex.
- **Lock:** PID do InstanceLock correlacionado com a cadeia real do executor (vivo/da cadeia, fora da cadeia, inexistente).
- **Historico:** eventos consecutivos identicos agrupados (`xN`, faixa de horario); erros em vermelho, novos em azul; duplo clique abre o log original.
- **Botoes:** cada um reporta o resultado REAL na linha de status (✓/✗); parar/reiniciar rodam fora da UI, recusam com kill switch, execucao ativa, `-Execute`
  ou executor que nao encerrou (nunca inicia 2a instancia).
