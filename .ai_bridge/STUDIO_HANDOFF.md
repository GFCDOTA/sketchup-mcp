# HANDOFF — INTERIOR STUDIO (continuar em sessão nova)

> Escrito 2026-06-20. A sessão anterior ficou GIGANTE (Claude começou a dropar coisa).
> Tudo committado/pushado. Reabrir limpo e continuar daqui.

## Onde está
- **Repo:** `E:\Claude\apps\sketchup-mcp` · **branch** `feat/living-room-golden-sample-propagation` · último commit `c1e997a`.
- **Container vivo:** `interior-studio-dashboard` em `:8782` (`docker compose up -d`; restart unless-stopped).
- **Ollama** no host `:11434` (deepseek-r1:14b, qwen2.5-coder:14b, llama3.1:8b, qwen2.5vl:7b, interior-designer:latest, coder-assistant:latest).
- **Memória:** `project_interior_studio` (MEMORY.md) tem o estado completo — LER primeiro.

## O que é
Painel multi-agente (`:8782`, Docker) que deixa os agentes "sábios" em design de interiores
(cozinha planta_74 = piloto). NÃO substitui o Claude pra gerar `.skp` — os LLMs locais dão
**TEXTO/diretriz**; o `.skp` continua sendo do Claude (precisa SketchUp).

## Arquitetura (arquivos-chave em `tools/`)
- `studio_dashboard.py` — servidor stdlib `:8782` (TODA a UI + endpoints). É o arquivo central.
- `studio_log.py` — barramento de atividade (feed): `post(agent,status,msg,to=,via=)`.
- `ollama_bridge.py` — cliente Ollama (host via `OLLAMA_HOST`, no container = `host.docker.internal`).
- `reference_db.py` — índice SQLite do `reference_lab` (5 testes verdes).
- `.claude/agents/interior-{orchestrator,pm,designer}.md` + `reference-scout.md` (dispatcháveis).

## O que JÁ funciona (provado)
- **3 guarda-chuvas:** PM 📋 (dono do Kanban) · Team Lead 🎯 · Arquiteto 🎨, cada um com sub-agentes + chat próprio.
- **Ciclo do orquestrador** (botão "▶ rodar 1 ciclo" no PM → `POST /api/cycle`): PM(llama) escolhe a
  próxima tarefa PELE + **move o card pra "execução"** → Team Lead(qwen) → Arquiteto(deepseek). Roda nos
  LOCAIS, sem Claude. Setas acendem, bolhas com logo do modelo (🐳🤖🦙) ou 🧠 consenso.
- **Alimentar o Arquiteto** (📚): cola texto (do GPT) → `.ai_bridge/knowledge/architect.md` → o Arquiteto
  USA isso nas respostas (provado: respondeu "mantendo o moody premium de Felipe").
- **Kanban** (Backlog/Refinamento/Execução/Teste/Executado, mover ◀▶), **curadoria** 3-ações + upload +
  🖼 og:image, **modal** de imagem/chat (⛶), gráficos, "marcar erro"→lição, refresh-só-quando-muda.
- **Consenso** (🧠 3 LLMs + síntese), chat ancora na última msg, identidade gold/gradiente.

## Endpoints (Claude é a "babá": lê e manda no :8782)
`GET /api/state` · `POST /api/ask {agent,prompt}` · `/api/cycle {goal}` · `/api/consensus {prompt}` ·
`/api/move {mt,direction}` · `/api/curate` · `/api/flag` · `/api/upload` · `/api/preview` · `/api/feed` · `/api/clear`.
Editou `studio_dashboard.py`? `docker compose restart studio-dashboard` (a UI é servida do arquivo).

## PENDÊNCIAS (ordem recomendada)
1. **Feed melhorado:** upload de **.txt** (não só colar) + **lista do que o Arquiteto já aprendeu**
   (Felipe vai colar VÁRIOS blocos de design do GPT — não pode encavalar/sair da tela).
2. **Timer auto do ciclo** (rodar sozinho a cada X min, com toggle).
3. **Banco de referências rico** (mood board + selos golden/exemplo) + mais identidade visual / luzes vivas.
4. **Fluxo dos agentes mais fundo:** PM↔Team Lead↔Arquiteto se consultando de verdade no ciclo (hierarquia
   PM→Lead→Arquiteto, mas atalho livre). Felipe é OK com qualquer cadeia que funcione melhor.

## A MISSÃO REAL (não esquecer)
O studio é meio pro fim: **fechar a COZINHA planta_74 a ~100%** (igual imagem que o GPT gera).
Fases: 0 infra ✅ → 1 designer bate paleta (caverna morta) → **2 GEO conteúdo (eletros/nicho geladeira/
Gola — espera OK do Felipe + bater D1-D9)** → 3 PELE fina. GEO é o gap maior. `.skp` = Claude.

## Regras/armadilhas (do CLAUDE.md + memória)
- `GOLDEN_SAMPLE_004` = geometria CONGELADA (não mexer). NÃO tocar o oráculo `:8765` (frágil).
- **OUTRA SESSÃO** pode estar na worktree `kitchen-ergo-gates` (MT-09/10) — checar `git worktree list` antes.
- `PT_TO_M=0.0259` pra furnish/render da planta_74. `gh pr create` FALHA (PAT sem escopo) → PR por URL.
- Felipe quer ritmo/economia: avisar quando não precisa de Opus/ultra; cortar cerimônia, não raciocínio.
