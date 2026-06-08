# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-06-06. Decai rápido.

## Fila atual

### 1. Mergear os PRs de unbreak/higiene (#225, #226)

- **Objetivo:** landar o `fix(deps)` matplotlib+numpy (#225 — sem ele o
  `pytest` nem coleta num install limpo) e o `fix(cockpit)` consult paths
  em call-time (#226 — conserta 4 testes).
- **Por quê:** o suite de testes precisa rodar verde num clone fresco;
  hoje quebra na coleção. #226 depende de #225 pro verde total.
- **Critério de parada:** ambos mergeados; `pytest tests/ -q` = 467 passed.

### 2. Decidir o atuador do NOC (#222 + #223)

- **Objetivo:** revisar/mergear `feat/noc-dispatcher` (#222) e a doc
  `NOC_DISPATCHER.md` (#223, depois do #222).
- **Por quê:** o dispatcher fecha o loop de tasks seguras/auto-verificáveis.
  Muda o `:8765` vivo — bem-railed (lock, worktree isolado, nunca
  main/auto-merge, aparência→VISUAL_REVIEW), mas é decisão do Felipe.
- **Critério de parada:** PRs mergeados ou veredito de ajuste.

### 3. (follow-up) `tools/check_skp_proof_of_progress.py` CI gate

- **Objetivo:** implementar o gate executável de
  `specs/skp_proof_of_progress_gate.md`.
- **Por quê:** hoje a regra "No SKP, no progress" depende de reviewer humano.
- **NÃO INICIAR** sem ok explícito do Felipe. Arquivo ainda não existe.

### 4. (infra) Workflow mínimo de pytest no GitHub Actions

- **Objetivo:** `.github/workflows/` com `pip install -e ".[dev]" && pytest`.
- **Por quê:** o repo **não tem CI**; as 2 quebras de hoje (#225, #226)
  passaram batidas por meses. Um gate de coleção+pytest pega regressões.
- **Critério de parada:** workflow verde num clone fresco.

### 5. (produto) Overlay `semantic_zones` p/ room fidelity da planta_74

- **Objetivo:** separar os 8 cells geométricos dos 11 ambientes semânticos
  (open-plan funde r001/r002) sem inventar paredes.
- **Por quê:** room fidelity = WARN honesto; o overlay resolve sem violar
  Hard Rule #1. **Requer SketchUp** — não dá pra validar em sessão remota.

## Backlog observado

- `compose_side_by_side.py` **já existe** (item antigo concluído).
- `chore/refresh-current-state`: conteúdo único (refresh de `current_state.md`)
  foi folded em `chore/refresh-stale-docs`; fechar a branch após o merge.
- SU 2026 pode deixar processos pendurados após runs interactive — kill antes de reuso.

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor claro pro
produto** (gerar/revisar `.skp` fiel). Não inventar trabalho cosmético.
Ver `specs/product_goal.md` § "Critérios de avanço real" e
`memory/operational_rules.md` § "Continuar automaticamente vs parar".
