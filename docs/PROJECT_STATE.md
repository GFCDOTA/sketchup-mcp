# PROJECT_STATE — sketchup-mcp

> **Status:** Canonical
> **Type:** Single source of truth for project state
> **Updated:** 2026-05-24
> **Maintainer responsibility:** every cycle that lands meaningful work
> updates this file as part of the commit (see [`HANDOFF.md`](HANDOFF.md)
> §"How to update").

This document is the canonical answer to:

1. What is the project?
2. Where is it now?
3. What works?
4. What does not?
5. What are the rules nobody can forget?
6. What are the canonical fixtures and artifacts?
7. How do you continue from another computer?

If anything in another `.md` contradicts this file, **this file wins**
(except [`CLAUDE.md`](../CLAUDE.md) §0–§3, which are inviolable
constitution). When in doubt, fix the contradicting doc, not this one.

---

## 1. What this repo is

`PDF/floorplan → extraction → consensus_model.json → validation → renders → SketchUp .skp`

A pipeline that ingests architectural floor plans (PDF) and produces a
3D SketchUp `.skp` model honest enough for furniture/layout planning —
NOT precision CAD.

Two extraction tracks coexist:
- **Raster** (`ingest/`, `roi/`, `extract/`, `classify/`, `topology/`,
  `openings/`, `model/`) — legacy, OUTDATED for `planta_74`. Kept for
  evidence/diagnostic value, NOT canonical output.
- **Vector** (`tools/build_vector_consensus.py`,
  `tools/extract_room_labels.py`, `tools/rooms_from_seeds.py`,
  `tools/extract_openings_vector.py`,
  `tools/classify_openings_by_room_context.py`) — current canonical
  pipeline for `planta_74` and similar vectorial PDFs.

The Ruby/SketchUp export side (`tools/build_plan_shell_skp.{py,rb}`,
`tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`,
`tools/skp_from_consensus.py`) is the **final gate** — it must only run
after the cheap gates pass.

Full architecture diagram + onboarding: [`../OVERVIEW.md`](../OVERVIEW.md).
Operational constitution: [`../CLAUDE.md`](../CLAUDE.md).

---

## 2. Current state — 2026-05-24

| Field | Value |
|---|---|
| `develop` HEAD | `14212ea` — `feat(safety): SU runner mode protocol — clean cherry-pick from #150 (#153)` |
| In-flight feature branch | `feature/window-aperture-semantics` — 3 commits ahead of develop |
| Branch being worked here | `chore/repo-governance-anti-forgetting` (this branch — repo governance + anti-forgetting protocol) |
| Schema version | `consensus_model.json` v1.0; `observed_model.json` v2.1.0 |
| Canonical fixture | `fixtures/quadrado/` (proves wall-shell + window aperture semantics end-to-end) |
| Real-data baseline | `planta_74.pdf` → 33 walls / 11 rooms / 11 openings / 8 soft_barriers |

### Last good shipped commit

`14212ea` on `develop` — SU runner mode protocol. Anything after this
is on a feature branch and not yet merged to develop.

### Feature branch in flight

`feature/window-aperture-semantics` carries the **canonical wall-shell
+ window aperture semantics work** (2026-05-24, this session). Three
commits not yet on develop:

| SHA | Title | Why it matters |
|---|---|---|
| `7e56dc7` | `fix(openings): enforce wall-hosted window semantics` | Windows are partial-height apertures hosted by walls, NOT door-like full-height voids. See §5 rule 2. |
| `ebdac1a` | `fix(walls): canonicalize wall shell and remove residual sliver geometry` | Wall shell is built from ring/polygon logic with corner extension + post-boolean canonicalisation. See §5 rule 1. |
| `8799466` | `chore(quadrado): promote canonical success reference + smoke gate` | `fixtures/quadrado/` is the canonical reference for wall-shell + window semantics; CI-ready smoke gate guards it. See §4. |

When this branch merges into develop, this PROJECT_STATE.md should be
refreshed and the rows above moved to "Recently merged".

---

## 3. What works

- **Vector pipeline** on `planta_74` end-to-end:
  walls → soft_barriers → rooms via flood-fill → openings (vector arcs
  + wall_gaps) → room-context kind classification.
  Reproduce from clone: [`../OVERVIEW.md`](../OVERVIEW.md) §4.4.
- **Validation gates** all green on `planta_74` baseline:
  - Plan Truth Gate (`tests/test_planta_74_truth_gate.py`)
  - Coherence audit (`tools/coherence_audit.py --strict`)
  - Micro Truth Gate (`tools/micro_truth_gate.py --strict`)
  - Fidelity Engine v1 (`tools/fidelity/compare_generated_to_expected.py`)
- **SketchUp export** (when SU 2026 is installed):
  `tools/skp_from_consensus.py` or `tools/build_plan_shell_skp.py`.
  Skip-unchanged-by-content-hash works
  (`docs/performance/skip_unchanged_skp.md`).
- **Validation cockpit** (Streamlit UI, `cockpit/app.py`) — read +
  overrides + Pre-SKP review pane all live.
- **Quadrado canonical smoke gate** — 14 tests in
  `tests/test_quadrado_canonical_smoke.py` lock the wall-shell + window
  aperture contract against the canonical fixture.
- **Human ground-truth pipelines** for openings, walls, and
  soft-barriers (paint → JSON → consensus); see
  `docs/learning/human_openings_truth_protocol.md` and
  `docs/protocols/human_soft_barriers_protocol.md`.

## 4. Canonical artifacts (DO NOT re-derive — read these paths first)

### Quadrado fixture (the wall-shell + window canonical reference)

| Role | Path |
|---|---|
| Input consensus (with window) | `fixtures/quadrado/consensus_with_window.json` |
| Input consensus (empty room) | `fixtures/quadrado/consensus_empty.json` |
| Expected `_shell_polygon.json` | `docs/specs/_assets/quadrado_canonical_shell_polygon.json` |
| Expected geometry report | `docs/specs/_assets/quadrado_canonical_geometry_report.json` |
| Reference 3D render | `docs/specs/_assets/quadrado_canonical_success_render.png` |
| Render helpers | `tools/quadrado/render_view.{py,rb}` |
| Smoke gate (CI-ready) | `tests/test_quadrado_canonical_smoke.py` (14 tests) |
| Spec | `docs/specs/quadrado_demo_spec.md` |

Reproduce: `python -m tools.build_plan_shell_skp fixtures/quadrado/consensus_with_window.json --out runs/<dir>/quadrado.skp`

### planta_74 baseline (real-data canonical)

| Role | Path |
|---|---|
| Source PDF | `planta_74.pdf` |
| Vector consensus (canonical) | produced by 5-step flow in `OVERVIEW.md` §4.4; locked at 33/11/11/8 |
| Truth gate baseline | `tests/baselines/planta_74.json` |
| Ground truth (whole-plant) | `ground_truth/planta_74/expected_model.json` |
| Ground truth (micro) | `ground_truth/planta_74_micro.json` |
| Human openings annotation | `fixtures/planta_74/human_openings_annotation.png` (mandatory truth — detector loses every conflict) |
| Human walls annotation | `fixtures/planta_74/human_walls_annotation.png` |
| Augmented consensus (with humans) | `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` |

### Generated outputs (NOT canonical, NOT source of truth)

- `runs/**` — gitignored. Each run is reproducible from its source via
  the commands in `OVERVIEW.md` §4.4.
- `out/` — gitignored.
- `review/` — gitignored.
- `runs/png_history/manifest.jsonl` — append-only manifest of all
  generated PNGs (gitignored as part of `runs/`).
- `runs/<id>/_cockpit_cache/` — cockpit thumbnail cache (gitignored).

---

## 5. Permanent rules — MUST NOT be forgotten

See [`ANTI_FORGETTING.md`](ANTI_FORGETTING.md) for the canonical
list with reasoning. The most load-bearing rules:

1. **Wall shell continuity.** Wall footprints extend by half-thickness
   at BOTH endpoints along the wall's own axis. After `unary_union` and
   carve, the resulting polygon passes through
   `canonicalise_axis_aligned_polygon(poly)` which drops any vertex
   sandwiched between two same-cardinal-direction edges. Axis-aligned
   input → axis-aligned output with no stepped notches, no slivers, no
   overhanging segments. Reference:
   `tools/build_plan_shell_skp.py wall_footprint()` +
   `canonicalise_axis_aligned_polygon()`.
   Gates: `tests/test_wall_shell_canonical.py` (15 tests) + planta_74
   idempotency.

2. **Window aperture semantics.** Window openings are partial-height
   apertures hosted by walls. They preserve wall mass below (peitoril)
   and above (verga) the opening and are NEVER represented as door-like
   full-height voids. `kind_v5 == "window"` routes to
   `build_window_aperture_3d` (3D post-extrude carve); doors / passages /
   glazed_balcony stay on the 2D full-height path. Reference:
   `tools/build_plan_shell_skp.{py,rb}` +
   `WINDOW_APERTURE_KINDS`.
   Gates: `tests/test_window_aperture_contract.py` (15) +
   `tests/test_window_aperture_geometry.py` (9).

3. **Post-boolean cleanup is mandatory.** Any carving / offset /
   boolean / union that produces a wall shell must be followed by a
   canonicalisation pass. Without it, axis-aligned input can produce
   non-axis-aligned output, redundant collinear vertices, or stepped
   corners. The `slivers_removed` and `redundant_vertices_dropped`
   stats are emitted so regressions are visible.

4. **Quadrado is the canonical fixture for wall-shell + window.** When
   validating a pipeline change against the quadrado, ALWAYS use the
   versioned inputs at `fixtures/quadrado/*.json` and compare against
   the versioned reference outputs at `docs/specs/_assets/*`. NEVER
   invent a parallel fixture under `runs/` (gitignored) and call it
   canonical. If a reference output needs to change, justify in the PR
   body — `docs/specs/quadrado_demo_spec.md` calls this out
   explicitly.

5. **Real plantas start from existing canonical artifacts, not parallel
   demos.** Do not create a new "demo" pipeline when a baseline /
   fixture / consensus already exists for the target PDF. Reuse and
   extend.

6. **Progress only counts when it lands as test / fixture / gate /
   ADR / CLAUDE.md rule / PROJECT_STATE update / committed code.**
   Anything that lives only in chat history or in a local untracked
   file is not progress — it is at risk of being forgotten the next
   session or on the next machine.

7. **Pipeline invariants** from [`../CLAUDE.md`](../CLAUDE.md) §2
   and [`../AGENTS.md`](../AGENTS.md) §2 — never invent rooms or walls,
   never mask `rooms=0`, never use bbox as room substitute, never
   couple to a specific PDF, never skip debug artifacts
   (`debug_walls.svg`, `debug_junctions.svg`,
   `connectivity_report.json`), never leak ground truth into extractor
   output.

8. **Git flow** — branch from `develop`, PR into `develop`, `main`
   only receives PRs from `develop`. Never commit directly on `main`
   or `develop`. See [`../CLAUDE.md`](../CLAUDE.md) §0.

---

## 6. Active gates (run these on every change touching the pipeline)

See [`GATES.md`](GATES.md) for the full catalogue with commands and
expected output. Quick reference:

| Gate | Cost | Command (short form) |
|---|---|---|
| ruff (lint) | <2s | `ruff check .` |
| pytest (unit) | ~25s | `pytest -q` |
| Plan Truth Gate | <3s | `pytest tests/test_planta_74_truth_gate.py -v` |
| Quadrado smoke | <5s | `pytest tests/test_quadrado_canonical_smoke.py -v` |
| Wall-shell canonical | <5s | `pytest tests/test_wall_shell_canonical.py -v` |
| Window aperture contract | <5s | `pytest tests/test_window_aperture_contract.py -v` |
| Coherence audit | <2s | `python -m tools.coherence_audit runs/vector/consensus_classified.json --out-dir runs/vector` |
| Micro Truth Gate | <2s | `python -m tools.micro_truth_gate runs/vector/consensus_classified.json --ground-truth ground_truth/planta_74_micro.json --out runs/vector/micro_truth_report.json` |
| Fidelity Engine v1 | <2s | `python -m tools.fidelity.compare_generated_to_expected runs/vector/consensus_classified.json --expected ground_truth/planta_74/expected_model.json --out runs/vector/fidelity_report.json` |
| Project state check | <2s | `python scripts/project_state_check.py` |
| Smoke (full + SKP) | 60–90s | `python -m scripts.smoke.smoke_skp_export ...` |

---

## 7. Next steps (carry forward)

This file does NOT replace [`HANDOFF.md`](HANDOFF.md) or
[`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md). It lists
the **stable** next steps; the per-session queue lives there.

Stable items as of 2026-05-24:

1. **Merge `feature/window-aperture-semantics` into `develop`.** PR
   needed; once merged, refresh §2 of this file.
2. **Slice 6a — `room_polygon_override` schema + apply layer**
   (ADR-002 §4). Touches `cockpit/overrides.py`,
   `tools/apply_overrides.py`,
   `tools/fidelity/compare_generated_to_expected.py`. ~25 new tests.
3. **Cycle 6 (Stage 1.6 SU integration)** — wire autorun inspector
   into smoke `gate_f`. SU runtime; focused fresh session needed.
4. **Real multi-PDF corpus** — Felipe-blocked (needs 3+ real planta
   PDFs that aren't `planta_74`). Synth corpus (4 topologies) is the
   algorithmic-coverage substitute.

---

## 8. How to update this file

This file changes when **the project's stable answers change** —
not on every PR. Update triggers:

- A new pipeline stage lands and §1 / §3 description is now wrong.
- A new permanent rule is locked in (add to §5 + cross-reference the
  full text in `ANTI_FORGETTING.md`).
- A new canonical fixture is promoted (add to §4).
- A baseline shifts (e.g., `planta_74` count moves off 33/11/11/8) —
  update §2 + §4.
- A new validation gate becomes mandatory (add to §6).

For ephemeral per-session state (current branch tip, open PR queue,
last commit SHA, scratch notes) → use
[`HANDOFF.md`](HANDOFF.md) and
[`../.ai_bridge/CURRENT_STATE.md`](../.ai_bridge/CURRENT_STATE.md).

Every update of this file MUST come with:
- a commit message that lists the section(s) touched;
- a one-line diff entry at the bottom of the file under §9.

---

## 9. Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial canonical state doc. §1–§7 derived from CLAUDE.md, OVERVIEW.md, AGENTS.md, and the 2026-05-24 quadrado + wall-shell + window aperture cycle. |
| 2026-05-24 | (Wave 1 cleanup) | Repo Health Gate Wave 1 — root-prototype cleanup. Deleted 3 unreferenced root scripts (`proto_runner.py`, `proto_skel.py`, `proto_v2.py`); moved 3 test-referenced scripts to `tools/legacy/` (`proto_colored.py`, `proto_red.py`, `render_sidebyside.py`). New scaffolding: `tools/legacy/README.md`. Test reference update in `tests/test_proto_cli.py`. W001 count: 16 → 10. No fixture, baseline, gate, or canonical artifact changed; 5 deprecation-wrapper `render_*.py` and 5 other root scripts (`analyze_overpoly` etc.) remain at root, listed under "intentionally deferred" in [`../reports/current/repo_health_report.md`](../reports/current/repo_health_report.md). |
| 2026-05-24 | (Wave 2 allowlist) | Repo Health Gate Wave 2 — root-script allowlist (no file moves). Added `ROOT_PY_KEEP_AT_ROOT` (10 entries with cited rationale) + new I003 detector ("intentional-root-script") to `tools/repo_health_gate.py`. Honours the prior 3-audit "preserve-only" decision (`docs/ops/repo_hygiene_audit_2026-05-10.md` §211; `.ai_bridge/HANDOFF.md`). **W001 baseline now 0**; I003 surfaces 10 keepers (informational, does not gate CI). Promotion rule: when a cited trigger fires (raster retired / wrappers' clients all migrated / maintainer confirms "not used"), remove the allowlist entry — the file then re-fires W001 until moved. The allowlist is **not** permission to add new root scripts. |
