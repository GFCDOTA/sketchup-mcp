# Handoff — sketchup-mcp

> Fio da meada entre sessões. Última atualização: **2026-05-29 05:20 UTC** (post-PR #202 merge).
> Leia primeiro ao iniciar sessão.

## Estado de develop

- **HEAD**: `83a75cf` (PR #202 — FP-030 maturity jump ~35% → ~60%)
- **Anterior**: `43953f7` (PR #201), `f957391` (PR #200), `bdb8d77` (PR #199), `c8b27a9` (PR #198)
- **Testes**: 139 passed, 5 skipped
- **Branches locais limpas**

## Maturity jump landed (#202 merged)

Salto efetivo de ~35% → ~60% no Visual Oracle (cap honesto 70% sem bridge / 85% com bridge / 100% nunca):

- `tools/compose_side_by_side.py` — composer oficial substituindo ad-hoc PIL (PR #200)
- `tools/run_skp_visual_review.py` — 10 deterministic checks (era 6); composer integration; `--oracle none|chatgpt_bridge`; `--require-oracle`
- `tools/prompts/visual_oracle_reviewer.md` — prompt fixo com JSON estrito
- `fixtures/visual_oracle_negative/` — 3 fixtures sintéticas que comprovam FAIL
- `tests/test_side_by_side_composer.py`, `test_skp_visual_review_contract.py`, `test_visual_oracle_negative_fixtures.py` — 30 testes novos
- Maturity classification honesta em `regression_summary.md` (cap 70% sem bridge, 85% com bridge, 100% nunca)
- Dogfooded em `artifacts/review/planta_74/visual_oracle_bridge_20260529_maturity2/`

## Próximos itens (NÃO INICIAR sem trigger explícito do user)

User cravou explicitamente pós-#202:

> "Depois do merge, parar. Não abrir FP-031, CI mandatory gate,
> pixel-perfect, overlay/diff ou builder work agora."

Quando houver trigger, ordem natural de salto:

1. **Bridge real rodando** (`--oracle chatgpt_bridge` com bridge ativa) — sobe ~60% para ~65-75%
2. **Overlay/diff geométrico** (substitui side-by-side qualitativo) — sobe para ~80%
3. **Detectores positional** (misplaced_soft_barrier por bbox vs wall path) — sobe para ~85-90%
4. **FP-031 auto-fix loop** — só com FAIL real novo
5. **CI mandatory gate** — só depois do processo manual provar valor

## Convenções vigentes

- **Constitution**: 8 princípios load-bearing em `.claude/constitution.md`
- **Visual Oracle**: MVP + maturity 2 entregues + 2x dogfooded em `planta_74`

## Atualização pós-milestone (#200 — fresh validation)

### #200 — evidence(planta_74) Visual Oracle Gate dogfooding #2

Merge: `f957391` (2026-05-29 04:32 UTC).

User-requested fresh build após milestone closure. Exercitou
explicitamente o priority #1 do roadmap ("provar Visual Oracle
numa PR real de builder").

**Veredito final**: `WARN_documented` (sem FAIL).

```
PASS: wall_fidelity, door_fidelity, window_fidelity,
      scale_rotation, global_visual, gates_self_check (4/4)
WARN: room_fidelity (8 vs 11), sb007, sb_sliver (Group_1)
FAIL: none
```

**Artifacts em `artifacts/review/planta_74/manual_validation_20260529_041751/final/`**:
- `model.skp` (150.8 KB)
- `model_top.png`, `model_iso.png`
- `side_by_side_pdf_vs_skp.png` (245 KB, **ad-hoc PIL + pypdfium2**, NÃO promovido pra `tools/`)
- `geometry_report.json`, `visual_findings.json`
- `regression_summary.md`

**Ressalva importante (registrada pelo user)**: esta PR valida o
**fluxo do Visual Oracle Gate**, mas ainda **não é prova
completa numa PR real de builder**. A prova definitiva virá na
próxima PR que altere builder / consensus / renderer e o oracle
precisar comparar antes/depois de mudança funcional real.

**Side-by-side composer**: virou próximo item natural, mas
**permanece follow-up #2** — só iniciar com trigger explícito.

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
