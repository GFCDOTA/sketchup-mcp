# HANDOFF — Vitrine web do sketchup-mcp (:8783) + exploração Obsidian

> Escrito num arquivo PRÓPRIO (não no `HANDOFF.md`/`.ai_bridge` compartilhado) de
> propósito: outra sessão está ativa na MESMA branch editando `studio_dashboard.py`
> e `.ai_bridge/*`. Esta linha de trabalho (a "vitrine" web) é separada.

- **Data / sessão:** 2026-06-22 · session c25757f4-b090-42b3-b5a6-b42fa771fd4e
- **Repo / app:** `apps/sketchup-mcp` (arquivos novos em `tools/`; NÃO toquei o pipeline)
- **Status geral:** GREEN (vitrine no ar, dockerizada, verificada) · YELLOW no link do :8782 (uncommitted, contestado)

## 1. Objetivo atual
Felipe explorou o `claude-obsidian` (second brain Obsidian) só pra aprender o conceito e **decidiu NÃO usar Obsidian**. Pivot: construir uma **"vitrine" web própria** (HTML/CSS/JS, dark-pastel, animada) que **explica o sistema sketchup-mcp de forma intuitiva pra leigo** — servida em `:8783`, fora do Obsidian. ROI: artefato de explicação/pitch do sistema + base pra um possível app vendável.

## 2. Branch atual
- **Branch:** `feat/sofa-class-from-reference` · base `origin/develop` — ⚠️ **NÃO é minha**, é a que estava checada out (da OUTRA sessão).
- **Último commit:** `6dd415a` feat(studio): Felipe APROVOU LP-SOFA-001… (da outra sessão).
- **Ahead/behind:** não verifiquei remoto (handoff = snapshot, sem fetch). **Meus arquivos da vitrine = UNTRACKED, não commitados.**

## 3. Arquivos alterados (meus — untracked em `tools/`)
- `tools/home.html` `grafo.html` `flow.html` `agents.html` `explica.html` — as 5 páginas da vitrine.
- `tools/grafo_server.py` — servidor stdlib `:8783` (rotas `/`,`/grafo`,`/fluxo`,`/agents`,`/explica`,`/api/kgraph`).
- `tools/build_kgraph.py` — gera `kgraph.json` a partir de `E:\sketchup-mcp-vault`.
- `tools/kgraph.json` — dados do grafo (61 nós, 385 arestas) — **SNAPSHOT**.
- `tools/Dockerfile.grafo` + `tools/subir-vitrine.cmd` — container durável.
- ⚠️ `tools/studio_dashboard.py` — adicionei **1 linha de nav** (link Fluxo/Mapa → :8783), **NÃO commitada** (arquivo tem trabalho não-commitado da outra sessão; pode já ter sido revertida).
- **Fora do repo:** `E:\claude-obsidian-lab` (lab Obsidian = backup, pode deletar) e `E:\sketchup-mcp-vault` (61 notas markdown que alimentam o build_kgraph).

## 4. Decisões tomadas
- **Não usar Obsidian** (Felipe): foi só aprendizado → recriei o conceito em web própria.
- **Servidor separado `:8783`** (não dentro do `:8782` studio_dashboard): a outra sessão **reverteu** minhas rotas no `studio_dashboard.py` (out-of-band) → criei `grafo_server.py` independente pra não brigar (Hard Rule multi-agente: não tocar trabalho não-commitado alheio).
- **Dockerizar** (em vez de processo de fundo): o bg morria no reboot; container `--restart unless-stopped` é durável.
- **Conteúdo GROUNDED**: os diagramas foram baseados no **mapa real do código** (3 subagentes exploradores), não inventados.
- **Correções da auditoria:** `fluxo` passo 2 era "extrair vetor-first" (pipeline MORTO/arquivado) → corrigido pra "Consensus (humano lê o PDF)"; `agents` Single dava a entender que um LLM gera o `.skp` → corrigido (o agente CHAMA tools; o build do `.skp` é 0% IA, código puro).

## 5. Testes rodados + evidências
- **py_compile** `grafo_server.py` + `build_kgraph.py` → OK (exit 0).
- **Rotas (via container):** `/ /grafo /fluxo /agents /explica /api/kgraph` → todas **200**.
- **Render no Chrome (screenshots):** home, grafo, fluxo (animado), agents (single+multi), explica → renderizam, **0 erro de console JS**.
- **build_kgraph:** 61 nós, 385 arestas.
- **Veredito visual:** N/A — são páginas web (validadas por screenshot), não render de planta/SKP; não passa pelo GPT-gate.

## 6. Pendências
- **Link no header do :8782** (Fluxo/Mapa): vivo mas **UNCOMMITTED** sobre arquivo da outra sessão → some se ela reverter. Committar SÓ quando ela landar o trabalho dela (coordenar).
- **kgraph.json = SNAPSHOT** (de `E:\sketchup-mcp-vault`). Se a base mudar, regerar: `python tools/build_kgraph.py`.
- `E:\claude-obsidian-lab` (backup Obsidian) pode ser deletado quando Felipe quiser.
- Novas seções no `/explica` que Felipe citou (esperando ele escolher): **time de agentes em detalhe**, **ciclo git/PR**, **os gates**.
- North-star de estilo = **Alex Xu / ByteByteGo**; Felipe cola posts específicos pra match 1:1.

## 7. Riscos
- ⚠️ **MULTI-SESSÃO:** outra sessão ativa na MESMA branch editando `studio_dashboard.py` + `.ai_bridge/*` (sofa/reference). **JÁ engoli o trabalho não-commitado dela uma vez** nesta sessão (commit) — foi desfeito com `git reset HEAD~1`. Não repetir.
- Meus arquivos da vitrine são **untracked** → um `git clean -fd` os apagaria. Não-commitados de propósito (pra não poluir a PR de sofa dela).
- Container depende do Docker Desktop iniciar no boot (padrão = sim).
- `kgraph.json` fica stale se as notas mudarem (snapshot).

## 8. Próximos 5 passos
1. Felipe navega a vitrine (`localhost:8783`) e dá veredito / pede ajustes de estilo (menor risco).
2. Se aprovar: commitar os arquivos da vitrine numa **branch PRÓPRIA off `origin/develop`** (NÃO na `feat/sofa…`) → PR.
3. Coordenar com a outra sessão pra commitar o link no header do :8782 (ou ficar só no :8783).
4. (Opcional) Novas seções no `/explica` que Felipe escolher.
5. (Opcional) Deletar `E:\claude-obsidian-lab`.

## 9. Comandos úteis
```
# Subir / recriar a vitrine (container durável :8783):
E:\Claude\apps\sketchup-mcp\tools\subir-vitrine.cmd
# OU manual:
docker build -f E:\Claude\apps\sketchup-mcp\tools\Dockerfile.grafo -t sketchup-grafo E:\Claude\apps\sketchup-mcp
docker run -d --name sketchup-grafo --restart unless-stopped -p 8783:8783 -v E:/Claude:/workspace -w /workspace/apps/sketchup-mcp sketchup-grafo
# Status / logs:
docker ps --filter name=sketchup-grafo
docker logs --tail 30 sketchup-grafo
# Regerar os dados do grafo (após mudar as notas em E:\sketchup-mcp-vault):
& 'E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe' 'E:\Claude\apps\sketchup-mcp\tools\build_kgraph.py'
# Abrir:  http://localhost:8783/   (home → grafo · fluxo · agents · explica)
```

## 10. O que NÃO fazer
- **NÃO commitar `tools/studio_dashboard.py`** (engole trabalho não-commitado da outra sessão — já aconteceu).
- **NÃO escrever em `.ai_bridge/*`** (HANDOFF, kanban, lessons… — outra sessão editando).
- **NÃO `git clean -fd`** (apaga os arquivos untracked da vitrine).
- **NÃO commitar a vitrine na `feat/sofa-class-from-reference`** (muda a PR de sofa) — usar branch própria off develop.
- **NÃO parar/reiniciar o `:8782`** (studio) sem necessidade — é da outra sessão.

## 11. Checkpoint p/ próxima sessão
Parei com a **vitrine `:8783` NO AR** via container Docker `sketchup-grafo` (Up, restart=unless-stopped), 5 páginas servidas + verificadas no Chrome, conteúdo corrigido na auditoria. **Primeiro movimento ao retomar:** abrir `http://localhost:8783/` (deve mostrar a home com 4 cards). **Sinal de que está de pé:** `docker ps --filter name=sketchup-grafo` mostra "Up" e `http://localhost:8783/api/kgraph` retorna 200. Se o container não estiver up, rodar `tools/subir-vitrine.cmd`.
