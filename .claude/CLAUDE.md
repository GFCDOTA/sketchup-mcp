# sketchup-mcp — instruções do agente

<!-- Mantenedor: alvo < 200 linhas (doc oficial de memória do Claude Code). Estado que decai rápido NÃO entra aqui:
     vai para .ai_bridge/HANDOFF.md. Regra de uma parte do código vai para .claude/rules/ com `paths:`; procedimento de
     vários passos vai para uma skill. Imports são relativos a ESTE arquivo (.claude/). Travado por tests/test_claude_assets.py. -->

@constitution.md

## Missão

Gerar um `.skp` SketchUp **fiel** à planta em PDF e mobiliá-lo com componentes paramétricos de verdade, cômodo a cômodo.
O `.skp` é o artefato humano; teste verde, render e report são evidência auxiliar, não substitutos.
Estado vivo (PRs, fases, pendências): `.ai_bridge/HANDOFF.md` — ler ao retomar trabalho.

## Regras duras (quebrar = RED, parar e perguntar)

1. **Nunca inventar parede, cômodo ou abertura.** O `consensus` é a verdade da arquitetura; PDF vence inferência.
2. **Nunca escavar janela em altura total** (peitoril e verga preservam massa; porta/passagem vão pelo caminho 2D).
3. **Nunca alterar** `fixtures/quadrado/`, `fixtures/planta_74/`, os `.skp` canônicos em `artifacts/<plant>/` nem o PDF sem aprovação explícita do Felipe.
4. **Nunca push em `main`.** Branch `feat/|fix/|chore/|refactor/|docs/<x>` a partir de `origin/develop`; PR contra `develop`.
5. **Nunca autodeclarar aparência.** `visual` fica `NOT_REVIEWED`/`PENDING_HUMAN` até o Felipe decidir `APPROVED`/`CHANGES_REQUESTED` no chat.
6. **Medida que o pedido não trouxe não vira geometria.** Toda grandeza chega como `{value, unit, origin}`; sem default inventado.
7. **SketchUp real só em cópia sob `runs/`.** Fechar só os PIDs que você abriu; nunca `taskkill /IM`; `--mode headless` só no CI.

## Mapa do código (detalhe: `docs/architecture/repository_map.md`)

| Onde | O que é |
|---|---|
| `core/` | domínio sem framework: escala (`scale.py`), semântica espacial, schemas (`core/schemas/`), observabilidade |
| `tools/rooms/<cômodo>/` | um módulo por cômodo: `specialist.v1.json` (perfil + allowlist), `knowledge/`, `capabilities/`, `validation/`, layout |
| `tools/rooms/shared/` | peças reutilizáveis entre cômodos (gabinete paramétrico, Shaker, sofá, cama, materiais, geometria) |
| `tools/rooms/capability_catalog.v1.json` | catálogo de capacidades: símbolos, estados `implementation/validation/visual`, evidência L2 com digests |
| `tools/rooms/specialists.py` | `plan()` fail-closed: pedido → binding → capability → `PLAN_READY_NOT_EXECUTED` ou `BLOCKED_*` |
| `tools/sketchup/` | executor SketchUp (jobs Ruby, `su_*` do MCP, shell da planta) |
| `tools/validation/` | gates transversais (arquitetura, sobreposição, circulação, regressão por cômodo FP-047) |
| `references/sketchup/knowledge/` | recipes de aulas com fonte, trecho e `human_review` (conhecimento ≠ execução) |
| `docs/specs/FP-NNN_*.md` | specs SDD por frente; `docs/specs/fp042_*.v1.json` = inventário e hashes de todo arquivo versionado |
| `runs/` | scratch ignorado pelo git; evidência que vale vai para `artifacts/review/` |

## Comandos

```bash
PY=E:/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe          # venv canônico (nunca o Python global)
$PY -m pytest tests -q -m "not planta74_scale"                    # suíte padrão
PT_TO_M=0.0259 $PY -m pytest tests -q -m planta74_scale           # testes que exigem a escala da planta_74
$PY -m ruff check <arquivos tocados>                               # nunca `ruff --fix` num diretório inteiro
$PY -m tools.rooms.capability_catalog                              # integridade do catálogo (errors = {})
$PY -m tools.rooms.capability_catalog --digest python:<mod.simbolo> ruby:<caminho.rb>
```
Rodar sempre de dentro do repo (rodar da raiz do workspace cria caches lá).

## Níveis de prova (não confundir)

- **L1** — contrato/cálculo puro testado (sem SketchUp). **L2** — SketchUp real (26.0.429) em cópia: salvar, fechar o próprio PID,
  reabrir em outro processo, inspecionar e verificar. **L3** — veredito visual humano.
- **R-18:** mudou um símbolo provado → o digest não casa → `BLOCKED_EVIDENCE_STALE`. Prova velha nunca é reaproveitada:
  revogar no catálogo, rodar o L2 de novo num **commit limpo** (`dirty: false`) e restaurar com os digests novos. Skill `capability-l2-proof`.
- `human_review` de uma fonte vale para **uma recipe e um trecho**; outra recipe do mesmo vídeo não herda.
- Capacidade que não existe **recusa com o motivo** (`BLOCKED_*`); não contornar por outra tool.

## Todo arquivo novo versionado

Registrar no mesmo PR em `docs/specs/fp042_inventory.v1.json`; evidência em `artifacts/review/**` também em
`fp042_references.v1.json` (blob sha do índice — refazer se o arquivo mudar depois do `git add`); binário (PNG) também em
`fp042_asset_blobs.v1.json`. Os gates `-k "inventory or fp042"` acusam o que faltar. Raiz e `tools/` têm guard de entrada nova.

## Git e PR

- `git fetch --all --prune` antes de decisão remota; worktree isolada em `E:/Claude/worktrees/` quando houver paralelismo.
- Um commit = uma intenção; mensagem no imperativo com prefixo de tipo. PR pequena; nunca deixar PR aberta no fim da sessão.
- Merge só com os **4 checks verdes no head exato** (pytest 3.11, pytest 3.12, deterministic fidelity gates, mcp server smoke+stdio):
  `gh pr merge <n> --merge --match-head-commit <sha>`. `gh`: `"/c/Program Files/GitHub CLI/gh.exe"`, `unset GH_TOKEN`, sempre `--repo GFCDOTA/sketchup-mcp`.
- Relatório/evidência histórica não se reescreve: nova evidência datada ao lado.

## Armadilhas reais deste ambiente

- Heredoc do Bash come `\` e aspas: regex/strings com barra invertida só via Write/Edit ou script em arquivo.
- O hook `rtk` esconde merge commits em `git log` (usar `rtk proxy git log --graph`) e `git diff > x.patch` não gera patch.
- Script L2 grava `dirty` pelo `git status --porcelain`: commitar antes de rodar. Saída e logs em `runs/`.
- SketchUp sem `.skp` base trava na tela inicial: abrir a partir de uma cópia de template.
- `.ps1` com acento precisa de BOM no PowerShell 5.1.

## Ler sob demanda (não carregado por padrão)

| Quando | Arquivo |
|---|---|
| retomar trabalho / saber o que está aberto | `.ai_bridge/HANDOFF.md`, `.claude/plans/next_actions.md` |
| autonomia GREEN/YELLOW/RED, quando parar | `.claude/memory/operational_rules.md` |
| promover `.skp`, `runs/` × `artifacts/` | `.claude/memory/artifact_policy.md`, `.claude/specs/skp_artifact_layout.md` |
| PR que muda geração do `.skp` | `.claude/specs/skp_proof_of_progress_gate.md`, `.claude/specs/fidelity_gate.md` |
| coordenação com outro agente | `.claude/memory/multi_agent_coordination.md` |
| histórico e lições | `.claude/memory/lessons_learned.md`, `.claude/memory/deprecated_context.md` |
| frente ativa (gabinete, Shaker, regressão, aprendizado) | `docs/specs/FP-045*` … `FP-052*` (índice no `.ai_bridge/HANDOFF.md`) |

## Oráculos externos

GPT-Docker `:8899` está **dormente** e o NOC `:8765` foi removido (2026-07-24). Decisão técnica: evidência determinística + LLM local
(Ollama `:11434`) se precisar de segunda opinião. Veredito visual: só o Felipe, no chat. Não reviver bridge sem ele pedir.
