# FP-058 — Floating Agent Control Bar (Windows)

Vinculada a FP-057 / #589. Observabilidade e controle seguro dos agentes; **nao** e um segundo orquestrador.

## Objetivo
Barra flutuante (~550x65, sem borda, sempre no topo, arrastavel, semitransparente) com 4 indicadores reais — Claude, Codex, Listener,
GitHub — mais PR atual, painel expandido (agentes, atividade, backlog, saude) e controles operacionais seguros.

## Decisoes
- Python + PySide6-Essentials (extra opcional `agent-bar`; o CI nao instala; logica testavel sem Qt). Sem Electron/React/servidor HTTP.
- Pacote em `tools/orchestration/agent_bar/` (reusa o namespace de orquestracao; evita novo diretorio no guard de `tools/`).
- Fontes = o que o bridge/executor ja gravam (`event_bridge.json`, `event_bridge.log`, lock, kill switch, `executor/*.log`, CIM, Tarefa Agendada, `gh`).
  Nenhum codigo do executor foi alterado.
- Honestidade de estado: ausencia de dado = cinza/`Indisponivel`; Codex = `Nao integrado` ate existir revisor automatico; Claude so "Executando" se
  descendente do executor monitorado.

## Controles (limites)
Abrir repo/Project/PR/logs, copiar diagnostico, atualizar, parar e reiniciar o listener **em DRY_RUN** pela Tarefa Agendada, com confirmacao;
recusa com execucao ativa, processos indisponiveis ou `-Execute` na acao da tarefa. Proibido: executar, iniciar Claude, `taskkill`, git, gates.

## Fases
1. **Slice 1 (este PR):** modelos, coletores, controles, settings, barra + painel, launcher, testes, evidencia visual real.
2. Backlog real (contagens Ready/In Progress/GPT Review/Blocked) quando houver coletor confiavel do Project #1.
3. Estado do Codex quando a integracao existir (FP-057 fase B).

## Aceite
Barra abre no Windows; arrastavel e sobre outras janelas; dados reais do listener; Claude executando != instalado; Codex nao integrado;
heartbeat/erros confiaveis; links GitHub; ver logs; parar/reiniciar com seguranca; nao interfere no processamento do projeto.
**Veredito visual:** do Felipe (a evidencia de captura e auxiliar).
