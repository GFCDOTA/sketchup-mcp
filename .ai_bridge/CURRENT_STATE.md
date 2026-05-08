# Current State — 2026-05-08 (post Cycle 12d + hygiene audit)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/post-cycle12d-handoff-final-2026-05-08` (this commit)
- **develop @** `c788df9` — PR #73 (hygiene audit ledger) merged
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`,
  `quality_gates.yml`. PR #73 went green CLEAN on all 3
  (test 25s, quality-gates 21s, ruby-syntax 6s).
- **Open PRs:** none.
- **Local branches alive:** `dashboard/architecture-sre-radar`,
  `dashboard/project-roadmap`, `feature/smoke-promotes-inspector-v2-gate`
  (all RED-blocked Stage 1.6 / out-of-scope).

## This session — 6 PRs merged

| PR | Title | Merge SHA |
|---|---|---|
| #68 | feat(cockpit): Cycle 12 — Validation Cockpit MVP | `84eae72` |
| #69 | chore(ai_bridge): post-Cycle-12-merge handoff refresh + LL-012 | `6b8e8c6` |
| #70 | feat(cockpit): Cycle 12b — PDF underlay | `8e1e225` |
| #72 | chore(ai_bridge): post-Cycle-12b refresh + Cycle 12d promoted (parallel) | `fe48f73` |
| #71 | feat(cockpit): Cycle 12d — expected_model overlay | `d1a8acc` |
| #73 | chore(hygiene): post-Cycle-12d audit ledger | `c788df9` |

## Three trincos status

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable, smoke
  green, CI green
- ✅ **Incerteza auditável** — coherence_audit + plan truth gate +
  micro truth gate (4 rooms via Cycle 7) + Fidelity Engine v1
  (HARD blocker post-Cycle-8b) + cockpit visual review pre-SKP
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity Engine
  v1 + Cycle 12 cockpit + Cycle 12d expected_model overlay (catches
  FP-012 leakage visually)

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
| `tools/rooms_from_seeds.py` | ✓ DEFAULT `--use-concave-hull=True` (Cycle 8b) |
| `tools/synth/make_synthetic_vector_pdf.py` | ✓ Cycle 11c/11d round-trip closed |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H |
| `cockpit/render_overlay.py` | ✓ MVP + PdfUnderlay + expected_match_summary (Cycles 12 / 12b / 12d) |
| `cockpit/app.py` | ✓ 5 sidebar groups (consensus, GT, PDF, layers, scale) + 5 inspector tabs |
| `scripts/cockpit_make_demo_pdf_underlay.py` | ✓ regenerates the 12b demo SVG |

## Test counts

- Pre-Cycle-12 develop: 568 PASS, 17 FAIL (raster legacy), 8 SKIP
- Post-Cycle-12d develop: **582 PASS** (+14 cockpit tests across
  the wave), 17 FAIL (same raster set), 8 SKIP

## Cockpit feature matrix

| Slice | Status | What it does |
|---|---|---|
| 12 — MVP | ✅ shipped | SVG overlay + 4 layer toggles + 4 inspector tabs |
| 12b — PDF underlay | ✅ shipped | Rasterised PDF page behind the SVG; opacity + DPI sliders |
| 12d — expected_model overlay | ✅ shipped | 5-state status palette on observed room outlines + Expected inspector tab |
| 12c — hover highlight | 🟢 P0 next | `<title>` tooltips + CSS hover effect |
| 12e — diff view | 🟢 P1 | side-by-side run A vs run B + per-room delta |
| Slice 2 — review_overrides | 🟡 P2 | first mutation surface; needs FastAPI POST |
| Slice 3 — proposed_actions | 🟡 P2 | new schema + pre-SKP gate F0 |

## Tooling notes

- **gh CLI** lives at `C:\Program Files\GitHub CLI\gh.exe` and is
  NOT on the Git Bash PATH that Claude Code runs in. Always invoke
  via absolute path: `"/c/Program Files/GitHub CLI/gh.exe"` and
  always use `--repo GFCDOTA/sketchup-mcp` for cwd-independent
  commands. Auth is keyring-backed (account `fmodesto30`, scope
  `repo`). See `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`
  + LL-012 in `docs/learning/lessons_learned.md`.
- Cockpit launch: `pip install -e ".[cockpit]"` then
  `streamlit run cockpit/app.py`. The `cockpit` package was added
  to `setuptools.packages.find` so `pip install -e` registers it
  properly (PR #68 / `f11e13c`).
