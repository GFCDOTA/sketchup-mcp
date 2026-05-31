# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-05-28 (sessão noturna autônoma). Decai rápido.

## Fila atual

### 1. Mergear PR #197 (Constitution #8 friction-tax refinements)

- **Objetivo:** Refinamentos da Constitution #8 em `develop` pra
  evitar friction tax (escape hatch, path triggers, intermediários
  não-commitados, anti-checklist-theater)
- **Por quê:** Refinamentos baseados em Q1 review do user; PR #196
  mergeou enquanto eu rodava o review, então virou PR follow-up
- **Status:** PR aberta, aguardando review do user
- **Critério de parada:** PR mergeada

### 2. Mergear PR #198 (FP-030 Visual Oracle Gate)

- **Objetivo:** Spec + skill + tool + schema + manifest + 19 fixture
  examples + 16 contract tests + dogfooding run em `develop`
- **Por quê:** Visual Oracle Gate operacionaliza Constitution #8
  ("No visual proof, no progress") com heurísticas determinísticas
- **Status:** PR aberta, dogfooded com `planta_74` → verdict=WARN
  documentado, artefatos em `artifacts/review/planta_74/visual_loop_current/final/`
- **Critério de parada:** PR mergeada

### 3. (follow-up) `tools/check_skp_proof_of_progress.py` CI gate

- **Objetivo:** Implementar o gate executável sugerido em
  `specs/skp_proof_of_progress_gate.md` § "Testes / gates
  automáticos"
- **Por quê:** Hoje a regra depende de reviewer humano cobrar;
  gate executável protege automaticamente
- **NÃO INICIAR** sem ok explícito do user — categoria 5 pendente

### 4. (follow-up) FP-030 auto-fix loop entre attempts

- **Objetivo:** Permitir que o `tools/run_skp_visual_review.py`
  aplique fixes source-supported entre attempts
- **Por quê:** Hoje o loop é documentário; auto-fix multiplica
  o valor
- **Requer:** taxonomy de fixes seguros + safe-edit policy
- **NÃO INICIAR** sem mais clareza do user

### 5. (follow-up) Side-by-side composite generator

- **Objetivo:** `tools/compose_side_by_side.py` que junta PDF
  underlay + SKP top + SKP iso em 1 PNG
- **Por quê:** Constitution #8 lista side-by-side como evidência
  obrigatória; hoje só existe no baseline canonical
- **Critério de parada:** tool integrado ao
  `tools/run_skp_visual_review.py` na promoção pro `final/`

## Backlog observado durante esta sessão

- Python install local: `AppData/Local/Programs/Python/Python312/`
  está vazio (binário removido). Working via `uv`-managed Python.
  Decidir se reinstalar ou aceitar uv-only (memory update pendente)
- `matplotlib` faltando em `pyproject.toml` (PR #193 introduziu
  uso em `tools/diagnose_wall_stubs.py`)
- SU 2026 processos podem ficar pendurados após runs interactive —
  documentar workflow de cleanup (kill antes de reuso)
- `regression_summary_template.md` precisa ser atualizado pra
  refletir o formato real usado neste PR (axes table sem "N/A"
  columns redundantes)

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor
claro pro produto** (gerar/revisar `.skp` fiel). Não inventar
trabalho cosmético. Ver `specs/product_goal.md` § "Critérios de
avanço real" e `memory/operational_rules.md` § "Continuar
automaticamente vs parar" (5 categorias).
