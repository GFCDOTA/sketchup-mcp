# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-07-11. Decai rápido.

## Fila atual

### 1. Mover os 4 `test_*.py` órfãos de `tools/` pra `tests/`

- **Objetivo:** `tools/test_auto_camera.py`, `tools/test_geometry_sanity.py`
  (renomear — colide com o de tests/), `tools/test_gpt_review.py` e
  `tools/test_suite01_scale_gate.py` nunca rodam (pytest `testpaths=tests`,
  CI idem) — são regressão silenciosa, incluindo o guardião da trava
  de escala PT_TO_M=0.0259.
- **Cuidado:** atualizar `.claude/skills/gpt-review-gate/SKILL.md:45`
  (referencia `tools/test_gpt_review.py`) no mesmo commit; verificar
  que rodam sem SketchUp antes de entrar no CI.

### 2. Ressincronizar `uv.lock` com o `pyproject.toml`

- **Objetivo:** lock congelado em 2026-06-03 sem numpy/matplotlib/
  jsonschema nem extras mcp/rag. `uv lock` + commit chore.

### 3. (follow-up) `tools/check_skp_proof_of_progress.py` CI gate

- Gate executável de `specs/skp_proof_of_progress_gate.md`.
  **NÃO INICIAR** sem ok explícito do Felipe. Arquivo ainda não existe.

### 4. Fixes menores de docs apontados na auditoria 2026-07-11

- `roadmap.md` (M3 semantic_zones entregue; FP-032..040 ausentes),
  `.claude/docs/index.md` e `.claude/README.md` (contagens/árvore
  desatualizadas), `interior_phased_plan.md` (estampar HISTÓRICO),
  `current_state.md` (5 pontos decaídos listados na auditoria).

### 5. (produto) Crescer o corpus do RAG (FP-035 core fechado)

- O write-back está vivo; cada curadoria sua alimenta o retrieve.
  Rodar drains/curadoria em lote pra engordar o corpus.

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor claro pro
produto** (gerar/revisar `.skp` fiel). Não inventar trabalho cosmético.
Ver `specs/product_goal.md` § "Critérios de avanço real".
