# Current State — 2026-05-08 (post Cycle 12 merge)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/post-cycle12-handoff-refresh` (this commit)
- **develop @** `84eae72` (merge commit of PR #68 — Cycle 12 cockpit MVP)
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`,
  `quality_gates.yml`. PR #68 went green CLEAN on all 3 (test 27s,
  quality-gates 15s, ruby-syntax 5s).
- **Open PRs:** none (post-merge cleanup PR is being prepared on
  this branch).
- **Local branches alive:** `dashboard/architecture-sre-radar`,
  `dashboard/project-roadmap`, `feature/smoke-promotes-inspector-v2-gate`
  (all RED-blocked Stage 1.6 / out-of-scope).

## Last objective (just completed)

**Cycle 12 — Validation Cockpit MVP** MERGED via PR #68
(`84eae72`). 13 files, 1223 insertions, 41 deletions. 10 new cockpit
unit tests added, all green. 0 new failures vs. develop baseline.
Streamlit pinned as optional `[cockpit]` extra; core pipeline
contract intact.

The cockpit is the human-in-the-loop checkpoint between the
extraction pipeline and the SKP gate. Read-only — never writes back
to consensus / GT files. See `docs/validation_cockpit.md`.

## Three trincos status

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable, smoke
  green, CI green
- ✅ **Incerteza auditável** — coherence_audit + plan truth gate +
  micro truth gate (4 rooms via Cycle 7) + Fidelity Engine v1
  (HARD blocker post-Cycle-8b)
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity Engine
  v1 (whole-plant) + cockpit visual review BEFORE SKP

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
| `tools/rooms_from_seeds.py` | ✓ DEFAULT `--use-concave-hull=True` (Cycle 8b promoted; ratio 0.5 cleared FP-012) |
| `tools/synth/make_synthetic_vector_pdf.py` | ✓ Cycle 11c/11d round-trip closed |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H |
| `cockpit/render_overlay.py` | ✓ pure SVG renderer + summary helpers (Cycle 12) |
| `cockpit/app.py` | ✓ Streamlit shell w/ sidebar pickers + 4 tabs (Cycle 12) |

## Known baselines

- `planta_74` vector pipeline: 33 walls, 11 rooms, 11 openings,
  8 soft_barriers
- Total room polygon area: 104.78 m² (post-Cycle-8b concave-hull,
  ratio 0.5)
- Fidelity Engine v1: global=0.917, 0 hard_fails, 2 advisory
  warnings (TERRACO TECNICO area marginal, adjacency_f1=0.67 →
  documented as FP-013)

## Test counts

- Pre-Cycle-12 develop: 568 PASS, 17 FAIL (raster legacy, CLAUDE.md
  §10), 8 SKIP
- Post-Cycle-12 develop: **578 PASS** (+10 cockpit tests), 17 FAIL
  (same raster set), 8 SKIP

## Tooling notes

- **gh CLI** lives at `C:\Program Files\GitHub CLI\gh.exe` and is
  NOT on the Git Bash PATH that Claude Code runs in. Always invoke
  via absolute path: `"/c/Program Files/GitHub CLI/gh.exe"` and
  always use `--repo GFCDOTA/sketchup-mcp` for cwd-independent
  commands. Auth is keyring-backed (account `fmodesto30`, scope
  `repo`). See `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.
- Cockpit launch: `pip install -e ".[cockpit]"` then `streamlit run
  cockpit/app.py`. The `cockpit` package was added to
  `setuptools.packages.find` so `pip install -e` registers it
  properly (was bug fixed in commit `f11e13c`).
