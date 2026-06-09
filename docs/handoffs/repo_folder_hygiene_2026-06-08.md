# Repo / Folder Hygiene — 2026-06-08

Branch `chore/repo-folder-hygiene` (off `origin/develop`). **Zero produto novo** nesta slice.
Regras seguidas: inventário antes de qualquer delete; nada destrutivo em pasta bloqueada;
dúvida → manter/quarantine; worktrees fora do repo; runs/ = scratch gitignored.

## FASE 1 — Inventário (read-only)
- **Worktrees (git):** eram 5, agora **3 registrados**: `sketchup-mcp` [feat/brain-muscle-plan, ATIVO — dashboard.html modificado], `sketchup-mcp-mobiliar` [feat/mobiliar-bedroom-layout, SESSÃO PARALELA ATIVA], `worktrees/repo-hygiene` [esta branch].
- **Órfã no disco:** `E:\Claude\wt-port` (deregistrada do git; PASTA presa por handle — ver FASE 4).
- **`D:\` NÃO existe** → regra 3 ("worktrees em D:\Claude\worktrees") inviável como escrita.
- **Repo root limpo:** só `CLAUDE.md`, `README.md`, `CLAUDE_COGNITIVE_ARCHITECTURE.md` (.md), `planta_74.pdf`, `pyproject.toml`, `uv.lock`, `.gitignore`. (Os "espalhados" do find eram quase tudo `.venv/` = lib gitignored, não scatter real.)
- **`.gitignore`** já ignora `/runs/`, `scratch/`, temp/backup ✓.
- **`docs/`** tinha `interiors/`, `specs/` — faltava `adr/`, `handoffs/`.
- **`artifacts/`** tinha `review/` — faltava `canonical/`.
- **Sem gate executável** de higiene (só o skill `repo-governance`).
- **Tamanhos:** `sketchup-mcp/runs` 23M (scratch), `artifacts` 22M, backups 67K+181K, `_ULTIMO_SKP` 140K, `wt-port` 248K.

## FASE 2 — Classificação
- **A) canonical/review importante:** `artifacts/review/planta_74/**` (entregáveis); `artifacts/canonical/` (novo, baseline aprovado). O trabalho de escala/Suíte 01 vive em `chore/suite01-scale-gate` (no origin), não em develop.
- **B) scratch reproduzível:** `runs/**` (gitignored, 23M), `.claude/scratch/*.skp`. Regeneráveis — **mantidos** (não toquei scratch de sessão ativa).
- **C) worktree ATIVO (não tocar):** `sketchup-mcp` (brain-muscle, dashboard.html WIP), `sketchup-mcp-mobiliar` (sessão paralela).
- **D) worktree órfão já no origin:** `wt-sofa-bevel` + `wt-fidelity` → **REMOVIDOS** (turno anterior; branches pushadas). `wt-port` → deregistrado, branch `chore/suite01-scale-gate` no origin; **pasta presa** (FASE 4).
- **E) arquivo solto a mover:** nenhum real. `CLAUDE_COGNITIVE_ARCHITECTURE.md` é **referenciado** por `tools/claude_bridge/server.py` → **mantido no root** (allowlistado no gate).
- **F) candidato seguro a delete:** `E:\Claude\runs` (top-level) — pensei vazio, mas tem `planta_74/` → **mantido**. `wt-port` folder → bloqueada (não deletável agora).
- **G) precisa DECISÃO HUMANA:**
  1. `D:\` não existe — onde ficam os worktrees? (usei `E:\Claude\worktrees\`).
  2. `_repo_wip_backups` (67K) + `_synthetic_untracked_backup` (181K) — backups de segurança; manter, arquivar ou consolidar em `_backups/`?
  3. `E:\Claude\runs\planta_74` (top-level fora dos repos) — scratch órfão de qual sessão?
  4. `wt-port` folder — deletar `rmdir /S /Q E:\Claude\wt-port` quando o handle soltar.

## FASE 3 — Estrutura alvo (criada nesta branch)
✅ `artifacts/canonical/planta_74/` · `docs/adr/` · `docs/handoffs/` (com `.gitkeep`).
✅ `artifacts/review/`, `docs/specs/`, `.ai_bridge/` já existiam. `runs/` gitignored ✓.
✅ Worktrees movidos pra fora do repo, organizados em **`E:\Claude\worktrees\`** (já que D: não existe).

## FASE 4 — Limpeza segura
- **Removidos** (turno anterior, com branch preservada no origin): worktrees `wt-sofa-bevel`, `wt-fidelity`.
- **Backfill de report** (compliance do gate, regra 5) em 3 review artifacts legacy sem report: `bedroom-window-ratio`, `glass-railing-3dw`, `janelas-esquadria` (README.md descrevendo os PNGs).
- **BLOQUEADO (regra 4f):** `E:\Claude\wt-port` — handle aberto (processo `SketchUp.exe` Id 21392/22788 visto antes; pode ter trocado). NÃO forcei. **Path registrado**; deletar manualmente após fechar o SketchUp: `rmdir /S /Q E:\Claude\wt-port`.
- **NÃO mexido:** scratch/runs das 2 sessões ativas; backups; `_ULTIMO_SKP` (convenção, 1 .skp).

## FASE 5 — Gate (`tools/repo_health_gate.py`)
Determinístico, exit 1 em violação, roda como pytest (`test_repo_health`). Checa:
1. `.md` solto no root só na allowlist (CLAUDE/README/COGNITIVE).
2. nenhum `.skp` TRACKED em `runs/` (evidência vai p/ artifacts — regra 7).
3. nenhum worktree DENTRO do repo (`.git` aninhado).
4. cada artifact `artifacts/review/**` com `.skp`/`.png` precisa de report (`.json`/`.md`).
**Estado: PASS (0 violações)** após o backfill.

## Antes / Depois
| | Antes | Depois |
|---|---|---|
| Worktrees registrados | 5 | 3 (2 ativos + esta hygiene) |
| Worktrees órfãos no disco | 3 (wt-port/sofa/fidelity) | 1 (wt-port, presa) |
| `_ULTIMO_SKP` | subpasta com 5 .skp | 1 único .skp |
| `docs/` | interiors, specs | + adr, handoffs |
| `artifacts/` | review | + canonical |
| Gate de higiene | nenhum | `repo_health_gate.py` (PASS) |

## Movido / Deletado (explícito)
- **Deletado:** worktrees `wt-sofa-bevel`, `wt-fidelity` (folders; branches no origin); subpasta residual em `_ULTIMO_SKP` (turno anterior).
- **Criado:** `artifacts/canonical/planta_74/.gitkeep`, `docs/adr/.gitkeep`, `docs/handoffs/.gitkeep`, 3× `README.md` (review legacy), `tools/repo_health_gate.py`, este report.
- **Movido:** worktrees novos → `E:\Claude\worktrees\` (convenção). Nenhum arquivo do repo movido (root já limpo).
- **NÃO deletado (proposital):** backups, scratch de sessão ativa, `wt-port` (bloqueada), `planta_74.pdf` + `CLAUDE_COGNITIVE_ARCHITECTURE.md` (referenciados).
