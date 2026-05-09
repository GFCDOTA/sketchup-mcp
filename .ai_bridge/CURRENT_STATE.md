# Current State — 2026-05-08 (mutation surface live + multi-PDF synth)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/post-mutation-wave-handoff-2026-05-08` (this commit)
- **develop @** `dc0aa14` — PR #88 (multi-PDF synth corpus) merged
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`,
  `quality_gates.yml`. Last 8 PRs all green.
- **Open PRs:** none.

## Session merge wall — 8 PRs from ADR-001 onwards

| PR | Title | SHA |
|---|---|---|
| #81 | docs(adr): ADR-001 — Validation Cockpit Mutation Surface | `4a8eb42` |
| #82 | feat(cockpit): Cycle 12g — on-demand thumbnail rendering | `1f200c5` |
| #83 | feat(cockpit): Slice 2 — overrides.py + Review tab | `dd2a199` |
| #84 | feat(cockpit): Slice 3 — apply_overrides + gate_f0 + history_view F0 read | `76739b3` |
| #85 | feat(cockpit): Cycle 12h — SVG source: manual annotation + inline override removal | `d454842` |
| #86 | docs(diagnostic): Stage 1.6 / orphan inspector branch investigation + brief | `c452bc5` |
| #87 | test(cockpit): cross-PR Slice 2 → Slice 3 mutation round-trip integration tests | `ef977a4` |
| #88 | feat(synth): multi-PDF synth corpus — 3 new topologies | `dc0aa14` |

## Mutation surface — feature matrix

| Component | File | Status |
|---|---|---|
| Schema contract | `docs/adr/ADR-001-validation-cockpit-mutation-surface.md` | ✅ shipped, locked |
| Override writer | `cockpit/overrides.py` (530+ LOC, 34 tests) | ✅ all 7 v1 types |
| Review UI | Review tab in `cockpit/app.py` | ✅ persists + audit trail + inline `× remove` |
| SVG `source: manual` annotation | `render_overlay_svg(..., overrides_view=...)` | ✅ optional kwarg, byte-equivalent default |
| Apply layer | `tools/apply_overrides.py` (CLI + pure function) | ✅ `amended_observed_v1` output |
| Apply-aware fidelity | `tools/fidelity/compare_generated_to_expected.py` `apply_overrides=True` | ✅ both pre/post fidelity scores per ADR §2.10.5 |
| Pre-SKP gate F0 | `gate_f0` in `scripts/smoke/smoke_skp_export.py` | ✅ `--review-mode={off,warn,block}`, default `off` |
| Pre-SKP UI | `cockpit/history_view.pre_skp_review()` | ✅ reads F0 report if present, falls back to in-memory |
| Round-trip integration | `tests/test_cockpit_mutation_integration.py` (16 tests) | ✅ zero API gaps |
| Thumbnails on-demand | `cockpit/thumbnails.py` | ✅ PIL-direct, mtime cache |

## Three trincos status — full board green

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable; smoke
  green; CI green.
- ✅ **Incerteza auditável** — coherence + plan truth + micro
  truth + Fidelity Engine v1 + cockpit visual review pre-SKP +
  human-decision audit trail + F0 verdict gate.
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity
  Engine + cockpit expected_model overlay + 4-topology synth
  corpus (L, T, +, long-hall, all fidelity 1.0).

## Active tools (refreshed)

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable |
| `tools/micro_truth_gate.py` | ✓ stable |
| `tools/skp_inspection_report.py` | ✓ stable |
| `tools/classify_openings_by_room_context.py` | ✓ stable + Stage 1 contract |
| `tools/inspect_walls_report.rb` | ✓ v2 schema; Stage 1.6 audit pending re-launch as Cycle 5/6 |
| `tools/fidelity/compare_generated_to_expected.py` | ✓ `apply_overrides=True` mode (Slice 3) |
| `tools/fidelity/synth_from_expected.py` | ✓ round-trip helper |
| `tools/rooms_from_seeds.py` | ✓ DEFAULT concave-hull (Cycle 8b) |
| `tools/synth/make_synthetic_vector_pdf.py` | ✓ 4 SPECs (L/T/+/hall5) all round-trip 1.0 |
| `tools/apply_overrides.py` | ✓ NEW — `amended_observed_v1` |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H + **gate_f0** (Slice 3) |
| `cockpit/render_overlay.py` | ✓ MVP + PdfUnderlay + expected_match_summary + diff_summary + hover/title + `source: manual` annotation |
| `cockpit/app.py` | ✓ 5 sidebar groups + 7 inspector tabs (incl. Review + Diff) |
| `cockpit/overrides.py` | ✓ NEW — 7 override types + audit trail + inline remove |
| `cockpit/thumbnails.py` | ✓ NEW — on-demand PIL rasteriser + cache |

## Test counts

- Pre-Cycle-12 develop (start of day): 568 PASS
- After cockpit read-only slice (12 / 12b / 12c / 12d / 12e / 12f): 626 PASS
- After parallel wave 1 (renderers/, History view, proto CLI): 744 PASS
- After ADR-001: 744 PASS (docs only)
- **After mutation wave (Slice 2 / 3 / 12g / 12h / Stage 1.6 audit / integration / multi-PDF synth): 776 PASS**
- Same 17 pre-existing raster failures (CLAUDE.md §10), 8 SKIP

**Net session delta: +208 tests across all PRs.**

## Tooling notes

- **gh CLI** lives at `C:\Program Files\GitHub CLI\gh.exe`; not on
  PATH in Git Bash. Use absolute path + always `--repo
  GFCDOTA/sketchup-mcp`. Auth keyring (account `fmodesto30`,
  scope `repo`). See LL-012 + cross-project memory
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.
- **Multi-agent worktree pattern** — pre-create worktrees via `git
  worktree add <path> -b <branch> develop`, dispatch agents pinned
  to their worktree. Used twice this session (3-agent + 4-agent
  waves), zero merge conflicts both times. Each agent's PR opens
  + merges independently.
- Cockpit launch: `pip install -e ".[cockpit]"` then `streamlit
  run cockpit/app.py`.

## Top of next-session queue

1. 🟡 **P0 — Cycle 5 (Stage 1.6 follow-up)** — pure-Python smoke
   harness extension; brief at
   `.ai_bridge/pr_bodies/PR_BODY_stage_1_6_followup.md`
2. 🟡 P1 — Cycle 6 (Stage 1.6 implementation) — SU-runtime work,
   needs focused fresh session
3. 🟢 P2 — Cycle 7 — `--inspect-strict` default
4. 🟡 P3 — Cockpit Phase 3 (FastAPI POST) — deferred until first
   real review case
5. 🔴 — REAL multi-PDF corpus (Felipe must provide PDFs)
