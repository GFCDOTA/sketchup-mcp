# Current State — 2026-05-08 (Cockpit feature-complete)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/post-cycle12e-handoff-feature-complete` (this commit)
- **develop @** `e090272` — PR #76 (Cycle 12e diff view) merged
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`,
  `quality_gates.yml`. Last 9 develop runs all green.
- **Open PRs:** none.

## This session — 9 PRs merged

| PR | Title | Merge SHA |
|---|---|---|
| #68 | feat(cockpit): Cycle 12 — Validation Cockpit MVP | `84eae72` |
| #69 | chore(ai_bridge): post-Cycle-12 handoff refresh + LL-012 | `6b8e8c6` |
| #70 | feat(cockpit): Cycle 12b — PDF underlay | `8e1e225` |
| #72 | chore(ai_bridge): post-Cycle-12b refresh (parallel) | `fe48f73` |
| #71 | feat(cockpit): Cycle 12d — expected_model overlay | `d1a8acc` |
| #73 | chore(hygiene): post-Cycle-12d audit ledger | `c788df9` |
| #74 | chore(ai_bridge): post-Cycle-12d session wrap | `40c3c3b` |
| #75 | feat(cockpit): Cycle 12c — hover highlight | `38c3c54` |
| #76 | feat(cockpit): Cycle 12e — diff view | `e090272` |

## Cockpit feature matrix — ALL 5 SLICES SHIPPED

| Slice | Status | What it does |
|---|---|---|
| 12 — MVP | ✅ | SVG overlay + 4 layer toggles + 4 inspector tabs |
| 12b — PDF underlay | ✅ | pypdfium2 raster behind SVG; opacity + DPI sliders |
| 12d — expected_model overlay | ✅ | 5-state status palette on observed rooms + Expected tab |
| 12c — hover highlight | ✅ | `<title>` tooltips + CSS `:hover`; no JS |
| 12e — diff view | ✅ | Second-consensus picker + dashed-magenta overlay + Diff tab |

**Read-only slice is feature-complete.** Mutation slices (Slice 2 / 3) deferred.

## Three trincos status

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable, smoke
  green, CI green
- ✅ **Incerteza auditável** — coherence_audit + plan truth gate +
  micro truth gate + Fidelity Engine v1 (HARD blocker post-Cycle-8b)
  + cockpit visual review pre-SKP
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity Engine
  + cockpit expected_model overlay catching FP-012 visually

## Active tools

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable |
| `tools/micro_truth_gate.py` | ✓ stable |
| `tools/skp_inspection_report.py` | ✓ stable |
| `tools/classify_openings_by_room_context.py` | ✓ stable + Stage 1 contract |
| `tools/inspect_walls_report.rb` | ✓ v2 schema + Lint clean |
| `tools/fidelity/compare_generated_to_expected.py` | ✓ called LIVE by cockpit |
| `tools/fidelity/synth_from_expected.py` | ✓ round-trip helper |
| `tools/rooms_from_seeds.py` | ✓ DEFAULT concave-hull (Cycle 8b) |
| `tools/synth/make_synthetic_vector_pdf.py` | ✓ Cycle 11c/11d round-trip closed |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H |
| `cockpit/render_overlay.py` | ✓ MVP + PdfUnderlay + expected_match_summary + diff_summary + hover/title |
| `cockpit/app.py` | ✓ 5 sidebar groups + 6 inspector tabs |
| `scripts/cockpit_make_demo_pdf_underlay.py` | ✓ regenerates 12b demo SVG |

## Test counts

- Pre-Cycle-12 develop: 568 PASS, 17 FAIL (raster legacy), 8 SKIP
- Post-Cycle-12e develop: **594 PASS** (+26 cockpit tests across
  the wave), 17 FAIL (same raster set), 8 SKIP

## Tooling notes

- **gh CLI** lives at `C:\Program Files\GitHub CLI\gh.exe` and is
  NOT on the Git Bash PATH. Always invoke via absolute path:
  `"/c/Program Files/GitHub CLI/gh.exe"` and always use
  `--repo GFCDOTA/sketchup-mcp` for cwd-independent commands.
  Auth keyring-backed (account `fmodesto30`, scope `repo`). See
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`
  + LL-012 in `docs/learning/lessons_learned.md`.
- Cockpit launch: `pip install -e ".[cockpit]"` then
  `streamlit run cockpit/app.py`. The `cockpit` package is in
  `setuptools.packages.find` so `pip install -e` registers it.

## Top of next-session queue

1. 🟢 P0 — `renderers/` migration per architecture plan step 5
2. 🟡 P1 — `proto_*.py` + `render_sidebyside.py` CLI-arg refactor
3. 🟡 P2 — Cockpit Slice 2 (FastAPI POST overrides) — first mutation surface
4. 🟡 P2 — Cockpit Slice 3 (proposed_actions + pre-SKP gate F0)
5. 🔴 — Stage 1.6, Multi-PDF corpus (Felipe-blocked)
