# Current State — 2026-05-08 (Cycle 12 cockpit MVP)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `feature/validation-cockpit-mvp-cycle12` (pushed, 2 commits ahead of `develop`)
- **develop @** `07fd499` (last known clean point)
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`, `quality_gates.yml`. Last 4 develop runs all green pre-PR.
- **Open PRs:** Cycle 12 cockpit (compare URL ready in `HANDOFF.md`; PR body in `.ai_bridge/pr_bodies/PR_BODY_cockpit_cycle12.md`)
- **Local branches alive:** `dashboard/architecture-sre-radar`, `dashboard/project-roadmap`, `feature/smoke-promotes-inspector-v2-gate` (all RED-blocked Stage 1.6 / out-of-scope)

## Last objective (just completed)

**Cycle 12 — Validation Cockpit MVP** shipped. Streamlit-based local UI for visualizing what the planta extraction pipeline understood from a PDF, before paying the SKP cost. Read-only by design; gated behind `[cockpit]` extra so core pipeline + CI stay lean.

This PR replaces the original (untracked, only sketched) plan to build the cockpit as `tools/dashboard/cockpit/` vanilla JS + FastAPI. Decision recorded in `DECISIONS.md` under 2026-05-08 — Hybrid path: Slice 1 stays Streamlit; Slice 2/3 will introduce FastAPI when persistence becomes necessary.

## Three trincos status

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable, smoke green, CI green
- ✅ **Incerteza auditável** — coherence_audit + plan truth gate + micro truth gate (4 rooms via Cycle 7) + Fidelity Engine v1 advisory (#58)
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity Engine v1 (whole-plant) shipped (#58); cockpit now lets a human review *before* SKP, closing the visual loop between consensus and the SU export step.

## Active tools

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable, schema 1.0 |
| `tools/micro_truth_gate.py` | ✓ stable, schema 1.0 |
| `tools/skp_inspection_report.py` | ✓ stable, schema 1.0 |
| `tools/classify_openings_by_room_context.py` | ✓ stable + Stage 1 contract |
| `tools/inspect_walls_report.rb` | ✓ v2 schema (PR #49) + Lint clean (PR #55) |
| `tools/fidelity/compare_generated_to_expected.py` | ✓ schema 1.0, 21 unit tests; called LIVE by cockpit |
| `tools/fidelity/synth_from_expected.py` | ✓ round-trip helper, 4 guard tests |
| `tools/rooms_from_seeds.py` | ✓ stable + opt-in `--use-concave-hull` (FP-012 spike, default OFF) |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H |
| **`cockpit/render_overlay.py`** | **✓ NEW — pure SVG renderer + summary helpers** |
| **`cockpit/app.py`** | **✓ NEW — Streamlit MVP, read-only viewer** |
| **`tests/test_cockpit_render_overlay.py`** | **✓ NEW — 10 unit tests** |

## Tests

Re-validated 2026-05-08 on `feature/validation-cockpit-mvp-cycle12`:

- Plan Truth Gate: **15/15 PASS**
- Micro Truth Gate: **20/20 PASS** (4 rooms scoring 1.0)
- Coherence Audit: **21/21 PASS**
- Concave-hull spike unit tests: **4/4 PASS**
- Fidelity Engine: **21/21 PASS**
- Fidelity round-trip: **4/4 PASS**
- **Cockpit renderer: 10/10 PASS** (NEW)
- **Total: 95/95 PASS** in ~3 s
- Live smoke: `streamlit run cockpit/app.py` boots, renders SVG overlay, no errors

## Next ROIs

| Item | Color | Notes |
|---|---|---|
| Open + merge Cycle 12 PR | 🟢 GREEN | manual via compare URL; merge once CI green |
| **Cycle 8b — promote concave-hull default + recalibrar baselines** | 🟡 YELLOW | needs ratio decision (0.30 / 0.55); will consult LLM local; clears the 3 advisory-mode FP-012 hard_fails |
| Cockpit Slice 2 — approve/reject + `review_overrides.json` (FastAPI) | 🟢 GREEN | additive, needs Slice 1 merged first |
| Cockpit Slice 3 — `proposed_actions.json` + pre-SKP gate F0 | 🟢 GREEN | builds on Slice 2 |
| Cockpit Slice 1.5 — PDF underlay (Cycle 12b) | 🟢 GREEN | smaller, big visual win |
| Multi-PDF corpus | 🔴 RED | needs Felipe to provide additional PDFs |
| Cycle 6 (Stage 1.6) — autorun inspector wiring | 🔴 RED | Stage 1.6 explicitly held |

## Operational protocol

`feedback_autonomia_operacional_protocolo.md` is the active rule:
- GREEN: execute without asking
- YELLOW: execute with reinforced validation
- RED: stop and report
- ChatGPT bridge / Ollama local: consult directly, no Felipe-as-router
- PR CLEAN + verde + escopo esperado → merge without asking

`feedback_pre_existing_work_pivot.md` (NEW cross-project rule, 2026-05-08): on conflict between fresh plan and pre-existing committed work, preserve and pivot if objective stays the same; only ask when discarding > preserving, objective changes, or destructive risk.
