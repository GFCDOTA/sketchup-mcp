# Current state — sketchup-mcp

> **Snapshot:** 2026-06-06. Verificar com `git`/`gh` antes de agir em
> decisões remotas — este arquivo decai rápido.

## Branch base & worktrees ativos

`develop` é a integration branch. `main` só recebe `develop` via merge
(Hard Rule #4 — nunca commitar/push direto em `main`).

- **`main` == `develop`** ambas em `73eb9da` (reconciliadas em 2026-06-06:
  `develop` estava 292 commits atrás de `main` — fast-forward limpo, sem
  rewrite. `develop` era ancestral de `main`, então zero perda).
- **PRs em voo (draft → `develop`, 2026-06-06):** #222 `feat/noc-dispatcher`
  (atuador NOC), #223 `chore/noc-t1` (doc; depois do #222), #224
  `chore/refresh-nba-seed`, #225 `fix(deps)` matplotlib+numpy (destrava o
  `pytest`), #226 `fix(cockpit)` consult paths em call-time.
- **Worktrees ativos (`git worktree list`) — ambiente MULTI-AGENT vivo
  (último snapshot conhecido; confirmar live):**
  - `E:/Claude/sketchup-mcp` `[main]` — tree principal (serve o cockpit :8765).
  - `E:/Claude/sketchup-mcp-mobiliar` `[feat/mobiliar-bedroom-layout]` —
    **sessão de mobiliado ATIVA** (dirty: `tools/furniture_anatomy_spec.py`,
    `.skb`, place-logs). Hands-off: é WIP de peer vivo.
  - `E:/Claude/wt-fidelity` `[feat/planta74-peitoril]`.

## Trabalho recente mergeado (origin/develop)

- **NOC/Cockpit:** aba "Cérebro" virou **estado vivo** (mapa mental +
  estado operacional + próxima ação) + endpoint `/api/brain-state`
  (d31951a). Cockpit+gate = `:8765` (Opus 4.8 modo B); restart seguro =
  matar o PID e deixar o `gate-watchdog-loop.ps1` relançar.
- **Interiores/mobiliado:** `bedroom_designer` minimalista por default
  (review GPT); cama por tamanho do quarto + guarda-roupa (suíte + quarto
  em L r000); apê inteiro mobiliado; cozinha planejada (torre + aéreos
  flutuantes). Variantes em `sketchup-mcp-mobiliar/artifacts/planta_74/furnished/`.
- **planta_74:** ground-truth humano restaurado (apagado por hygiene #134, aa2b8e6).

## Baselines estáveis (não retrabalhar)

- **planta_74 canonical:** `artifacts/planta_74/planta_74.skp` (veredito
  **IMPROVED**) + renders + report. É o deliverable atual.
- **quadrado canonical**, **runs/ vs artifacts/ convention**,
  **`--mode headless` proibido em dev local**, **junction-aware endpoint
  extension** (FP-026), **opening routing invariants** pinados (#195:
  4 windows / 7 doors / 1 glazed_balcony / 8 carves), **Constitution +
  #8 No-SKP-no-progress**.
- **`_ULTIMO_SKP`:** `E:/Claude/_ULTIMO_SKP/` espelha o último `.skp`
  gerado (hook Stop global + `E:/Claude/sync_latest_skp.ps1`).

## Problemas abertos (NOC, 2026-06-05)

Placar **YELLOW**. Razões: 1 repo dirty (mobiliar — WIP de sessão viva,
hands-off); 2 dificuldades OPEN; 1 DEFERRED.

- **DIFF-004** (colisão de worktree multi-agent, MED, OPEN) — **ADIADO**
  até a sessão paralela fechar; reopen/atacar quando o tree estiver
  colisão-livre. Manifestou-se nesta sessão (branch trocada out-of-band
  `main`↔`feature` no tree principal).
- **DIFF-006** (constantes do builder hardcoded p/ planta_74, LOW, OPEN) —
  **teto de verificação**: exige build SU + consumidor real + tree sem
  colisão (já TENTADO+REVERTIDO em a31794e).
- **DIFF-001** (consensus = autoria humana, sem extrator PDF→consensus,
  HIGH) — DEFERRED/roadmap.
- DIFF-002 (escala/âncora física) MITIGATED · DIFF-003 (janela
  peitoril/verga) FIXED · DIFF-005 (julgamento visual não-auto) MITIGATED.
- **Room fidelity = WARN** para `planta_74`: 8 cells fechadas vs 11
  ambientes semânticos (open-plan funde r001/r002) — geometricamente
  honesto, não inventar paredes. Backlog: overlay `semantic_zones`.
- **Sem CI no GitHub** (`.github/workflows/` não existe): testes verdes só
  por disciplina local. Em 2026-06-06 isso escondia 2 quebras num install
  limpo, agora em PR: `matplotlib`/`numpy` não declarados no `pyproject`
  (suite nem coletava — #225) e 4 testes de consult acoplados a paths
  resolvidos no import-time (#226). Considerar um workflow mínimo de pytest.

## TODO — verificar live

- [ ] `git worktree list` — confirmar quais agentes estão ativos ANTES de
      qualquer op de branch/worktree (evita DIFF-004).
- [ ] `gh pr list --repo GFCDOTA/sketchup-mcp --state open` — PRs abertas
      não listadas aqui.
- [ ] NOC `:8765` → `/api/status` + `/api/brain-state` — placar + staleness.
