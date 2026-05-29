# Handoff — sketchup-mcp

> Fio da meada entre sessões. Última atualização: **2026-05-29 02:04 UTC**.
> Leia primeiro ao iniciar sessão.

## Estado de develop

- **HEAD**: `c8b27a9` (PR #198 — FP-030 Visual Oracle Gate MVP)
- **Anterior**: `8d4462f` (PR #197), `510140d` (PR #196), `04cb25b` (PR #195), `c299d44` (PR #194)
- **Testes**: 109 passed, 5 skipped (sem regressão; 5 skipped são geometry tests que esperam quadrado SKP pre-built)
- **Constitution**: 8 princípios load-bearing cravados em `.claude/constitution.md`
- **Visual Oracle**: MVP entregue + dogfooded na `planta_74`

## PRs mergeadas neste ciclo (28 → 29 de maio)

### #197 — Constitution #8 friction-tax refinements

Merge: `8d4462f`.

Refinou Constitution #8 baseado em análise do user (Q1 review pré-merge,
ChatGPT bridge offline durante a sessão):

- "Toda PR" → **"SKP-affecting PR"** (path-triggered)
- Escape hatch `SKP-proof: N/A` com Reason + Justification
- Política em camadas: commitar SEMPRE só `final/`, intermediários em `/runs/` ou CI
- **Git LFS — não usar ainda** (só se total > 200-500MB)
- **Pixel-perfect — não fazer hard gate** (renders são evidência humana)
- Anti-checklist-theater: cada axis exige **evidência específica concreta**; `PASS — ok` ≡ WARN
- `N/A` permitido por axis com justificativa
- 10 hard gates categóricos (1-7 humano cobra, 8-10 automatizáveis)

### #198 — FP-030 Visual Oracle Gate MVP

Merge: `c8b27a9`.

Implementou o Visual Oracle Gate operacionalizando Constitution #8:

**Core rules:**
```
No SKP, no progress.
No visual proof, no progress.
The user is not the visual regression detector.
```

**Entregáveis (10/10 + 1 bonus):**

| # | Path |
|---|---|
| 1 | `docs/specs/FP-030_visual_oracle_gate.md` |
| 2 | `.claude/skills/skp-visual-self-correction/SKILL.md` |
| 3 | `fixtures/visual_oracle_examples/manifest.json` (19 examples, 5 confidence tiers) |
| 4 | `schemas/visual_findings.schema.json` (v1) |
| 5 | `tools/run_skp_visual_review.py` (MVP runner, 6 heurísticas determinísticas) |
| 6 | Execução real na `planta_74` ✅ |
| 7 | `artifacts/review/planta_74/visual_loop_current/final/model.skp` |
| 8 | `final/model_top.png` + `final/model_iso.png` |
| 9 | `final/visual_findings.json` (com 2 WARN findings + 1 verified PASS) |
| 10 | `final/regression_summary.md` |
| +1 | `tests/test_visual_oracle_contract.py` (20 testes) |

**Heurísticas determinísticas implementadas:**

1. `gates_self_check_fail`
2. `window_count_mismatch`
3. `floating_door`
4. `orphan_glass_panel`
5. `bad_window_aperture`
6. `floor_leak`

**Confidence tiers (5):**

- `good_real_baseline` (strong PASS)
- `bad_real_confirmed` (strong FAIL)
- `bad_real_ambiguous` (**WARN only**, nunca hard FAIL)
- `good_synthetic_teaching` (didactic)
- `bad_synthetic_teaching` (didactic, com caveat)

## Estado final do `planta_74`

**Veredito**: `WARN_documented` (sem FAIL real)

### Camada 1 (contract tests)
- 109 passed, 5 skipped

### Camada 2 (`gates_self_check`)
- `plan_shell_group_exists`: ✅ true
- `wall_shell_is_single_group`: ✅ true
- `floors_separated_from_walls`: ✅ true
- `default_material_faces_zero`: ✅ true

### Camada 3 (rubric humano, Claude inline)

| Axis | Verdict | Origem |
|---|---|---|
| `wall_fidelity` | **WARN** | 2 findings (sb007 sem PDF label, sb_sliver) — não FAIL |
| `door_fidelity` | PASS | 7 DoorLeaf_Group, z_min ≈ 0 |
| `window_fidelity` | PASS | 4 WindowGlass_Group, height 1.2m, peitoril preservado |
| `room_fidelity` | **WARN** | 8 cells vs 11 ambients (open-plan, lessons_learned.md #4) |
| `scale_rotation` | PASS | Claude inline review |
| `global_visual` | PASS | Claude inline review |

### Iteração 2 (verificação contra PDF)

User abriu `model.skp` no SU 2026 e enviou screenshot. Cross-check contra `planta_74.pdf`:

| Group | Source | Verdict | Evidência |
|---|---|---|---|
| `SoftBarrier_Group_5` | sb005 (17 vértices) | ✅ **PASS** | PDF etiqueta `PEITORIL H=1,10M` entre TERRACO TECNICO e SUITE 02; bbox + altura batem |
| `SoftBarrier_Group_7` | sb007 (25 vértices) | ⚠️ **WARN** | PDF sem etiqueta explícita nessa área (BANHO 02); plausível mas não confirmado |
| `SoftBarrier_Group_1` | (não mapeia consensus) | ⚠️ **WARN finding** | Sliver 0.01m² invisível; **não patcheado** — threshold de sliver é policy choice |

## Próximos passos

### NÃO abrir agora

- **FP-031 / auto-fix loop**: só abrir quando houver FAIL real detectado OU decisão explícita do user. Implementação requer:
  - Fix taxonomy (mapping finding_type → fix candidato)
  - Source attribution per finding
  - Safe-edit policy
  - Convergence detection
- **Patch do `SoftBarrier_Group_1` sliver**: só fixar quando o sliver virar visualmente relevante OU houver evidência de que threshold é melhor que mantê-lo
- **Confirmação `SoftBarrier_Group_7`**: aguardar user revisar PDF (ou anotar truth card) antes de promoção para PASS

### Backlog observado (em `.claude/plans/next_actions.md`)

1. `tools/check_skp_proof_of_progress.py` — gate CI executável (categoria 5 pendente, **NÃO INICIAR** sem ok)
2. Dogfooding em próxima PR de builder
3. Validar Python install local do user (3.12 oficial apagado, working via `uv`-managed)
4. `matplotlib` em `pyproject.toml` (PR #193 introduziu uso sem declarar)
5. Side-by-side composite generator

### Operational rules vigentes

- **Slice complete IS valid stop** (`.claude/memory/operational_rules.md`)
- **Continuar automaticamente só com encaixe nas 5 categorias produto-ROI**: SKP fidelity / artifact quality / failing gate / active PR cleanup / user-requested milestone
- **NÃO criar novo ciclo de governance/docs/refactor só porque não há blocker RED**

## Bridge status

- `localhost:8765` (ChatGPT bridge) testada **offline** durante sessão noturna 2026-05-28
- Q1 (Constitution #8 friction tax) resolvida com análise do próprio user
- Q2 / Q3 ainda em backlog, esperando trigger real

## Reproduzir o último build de `planta_74`

```bash
# Pré-requisito: SU 2026 + Python 3.12 (via uv)
# uv venv --python 3.12
# uv pip install -e ".[dev]"
# uv pip install matplotlib  # workaround temporário até PR de fix do pyproject

python -m tools.run_skp_visual_review \
  --fixture planta_74 \
  --out artifacts/review/planta_74/visual_loop_current \
  --max-attempts 3

# Esperado: attempt_0 → verdict=WARN, 0 deterministic findings, stop early
# Output em artifacts/review/planta_74/visual_loop_current/final/
```

## Contato / autoria desta sessão

- **Operador**: Felipe (GFCDOTA)
- **Agente**: Claude Code 4.7 (1M context) — sessão autônoma 2026-05-28 → 2026-05-29
- **Bridge ChatGPT**: offline durante o trabalho — fallback foi análise do user direto
