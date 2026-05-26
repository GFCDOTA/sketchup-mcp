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
| 2026-05-24 | (PR #156 repair) | Wall-hosted window semantics + canonical wall shell + quadrado canonical reference promoted from `feature/window-aperture-semantics` (PR #156 head `8799466`) onto current develop via cherry-pick + adapt in worktree `sketchup-mcp-pr156-repair`. Three cherry-picked commits (rebased onto `7ff2182`): `fix(openings): enforce wall-hosted window semantics`, `fix(walls): canonicalize wall shell and remove residual sliver geometry`, `chore(quadrado): promote canonical success reference + smoke gate`. Plus one new commit `test(failure-patterns): add FP-024 + FP-025 to KNOWN_FP_REGRESSIONS` that closes the `test_every_fp_in_md_has_a_catalog_entry` gate. Net effect: `fixtures/quadrado/*` (2 fixtures), `docs/specs/_assets/quadrado_canonical_*` (3 assets), `tests/test_quadrado_canonical_smoke.py` (14 tests), `tests/test_wall_shell_canonical.py` (15 tests), `tests/test_window_aperture_contract.py` (15 tests), `tests/test_window_aperture_geometry.py` (9 tests), `tools/quadrado/render_view.{py,rb}`, `docs/adr/ADR-007-window-aperture-3d-carve.md`, `docs/specs/quadrado_demo_spec.md`. CLAUDE.md gains §19 (window) + §20 (wall shell). `docs/learning/{lessons_learned.md,failure_patterns.md}` gain LL-016/017 + FP-024/025. `project_state_check.py` PASS goes from 32/0/9 (with 9 SOFT) to **41/0/0** (all canonical artifacts now on develop). |
| 2026-05-24 | (Wave 2 allowlist) | Repo Health Gate Wave 2 — root-script allowlist (no file moves). Added `ROOT_PY_KEEP_AT_ROOT` (10 entries with cited rationale) + new I003 detector ("intentional-root-script") to `tools/repo_health_gate.py`. Honours the prior 3-audit "preserve-only" decision (`docs/ops/repo_hygiene_audit_2026-05-10.md` §211; `.ai_bridge/HANDOFF.md`). **W001 baseline now 0**; I003 surfaces 10 keepers (informational, does not gate CI). Promotion rule: when a cited trigger fires (raster retired / wrappers' clients all migrated / maintainer confirms "not used"), remove the allowlist entry — the file then re-fires W001 until moved. The allowlist is **not** permission to add new root scripts. |
| 2026-05-24 | (PR #148 repair) | SDD spec YAML linter + contract scaffolding promoted from `feat/spec-linter-and-scaffolding` (PR #148, base = `chore/docs-foundations`, dead) onto current develop via single-commit cherry-pick in worktree `sketchup-mcp-pr148-repair`. Picks only `9f4307f` (the unique work of #148); the other 3 commits in #148's chain (`70ddc0a` SDD framework Phase 1, `2062b6a` Phase 2 CI gate from auto-closed #146, `87b88bb` CONTRIBUTING+pipeline_overview from #163) were already on develop or out of scope. Net effect: `tools/lint_specs.py` (CLI linter for `specs/**/*.spec.yaml`), `tools/new_spec_contract.py` (scaffolding generator), `tests/test_lint_specs.py` + `tests/test_new_spec_contract.py` (29 tests), `.github/workflows/spec_harness.yml` (non-blocking spec-harness CI as Phase 2 observational gate). Conflict was modify/delete on `.github/workflows/spec_harness.yml` (file referenced by 9f4307f but absent on develop since #146 closed); resolved by keeping the workflow file (it is self-contained — only needs the `tools/spec_harness.py` + `specs/**` already on develop via #145). Note: `pyyaml` is a runtime dependency of `tools/{spec_harness,lint_specs}.py` but not yet declared in `pyproject.toml [dev]`; tracked as follow-up. |
| 2026-05-24 | (PR #149 repair) | Workflow concurrency + PyYAML pin + README doc map promoted from `chore/workflow-and-deps-hardening` (PR #149, base = `feat/spec-linter-and-scaffolding`, dead — PR #148 closed) onto current develop via single-commit cherry-pick in worktree `sketchup-mcp-pr149-repair`. Picks only `18e5a0c` (the unique work of #149); the other 5 commits in #149's chain (`87c2f4f` ADR-005 SDD formalisation [PR #150], `9f4307f` spec linter [PR #166], `87b88bb` CONTRIBUTING/pipeline_overview [PR #163], `2062b6a` Phase 2 CI gate [#146 dead], `70ddc0a` SDD framework Phase 1 [PR #145]) were already on develop or out of scope. Net effect: `.github/workflows/ci.yml` + `.github/workflows/spec_harness.yml` (both gain `concurrency` block — cancel in-flight runs on same PR / branch to save CI minutes), `README.md` (doc-map block at top: CLAUDE.md / CONTRIBUTING / OVERVIEW / pipeline_overview / spec_driven_development / AGENTS pointers), `pyproject.toml` (explicit PyYAML `>=6.0,<7.0` pin — closes the unstated transitive dep from `mcp` / `anthropic` that the SDD framework had been relying on since PR #145). Cherry-pick auto-merged `spec_harness.yml` cleanly with PR #166's version. Outstanding from #149's chain (NOT in this PR): ADR-005 (255-line spec-driven-development ADR; tracked as follow-up). |
| 2026-05-24 | (ADR-005 restore) | Restored `docs/adr/ADR-005-spec-driven-development.md` from the dead-chain orphan commit `87c2f4f` (PR #150 — closed when its base `chore/workflow-and-deps-hardening` died). The other 9 files touched by `87c2f4f` (su_runner_safety + tests, CLAUDE.md §18, FP-023/024/025, LL-015/016/017, failure-patterns regression catalog, consolidation-hygiene diagnostic dated 2026-05-23) were either already on develop via intermediate PRs (#153, #161, #162, #164) or stale snapshots superseded by current docs — none of them brought across. Added a 2026-05-24 row to ADR-005's own decision log noting the implementation drift (PR #146 closed → `tools/spec_coverage_report.py` + `tools/audit_soft_barriers.py` referenced inside the ADR are NOT in develop; framework decision stands, tool catalogue narrowed). Also filled in `docs/adr/README.md` index rows for ADR-003 / ADR-004 / ADR-005 / ADR-007 (only ADR-001/002 listed before — index was stale). Net effect: 2 docs added/modified, 0 code touched, 0 tests added. |
| 2026-05-24 | (PR #144 repair) | Floor_r001 split via near-miss SB extension + Voronoi promoted from `fix/floor-r001-soft-barrier-buffered-split` (PR #144, head `a9999e3`, stacked on top of PR #143's commit `5d38ba2`) onto current develop via single-commit cherry-pick in worktree `sketchup-mcp-pr144-repair`. Picks only `a9999e3` (the #144 unique commit); the #143 base commit (`tools/audit_soft_barriers.py`, `tools/diagnose_room_polygons.py`, plan-shell `--layer-mode` harness) is deferred to a separate cycle. Two opt-in layers, both **default OFF** (production byte-equivalent unless caller opts in): (1) `tools/polygonize_rooms.py` `extend_near_miss_sbs` — probes SB endpoints up to `gap_tol_pt` (default 8 pt) with FP-006 + semantic-origin + post-extension-validation guards; (2) `tools/rooms_from_seeds.py` `voronoi_subdivide_merged_cells` — Voronoi-bisects a polygonize cell when ≥ 2 seeds share it. Standalone runner `tools/apply_room_polygon_fixes.py` chains both + emits `<out>.fix_provenance.json`. New: `tests/test_room_polygon_fixes.py` (25 tests, including the planta_74 regression `test_planta_74_voronoi_splits_r001_into_three` + the falsification `test_planta_74_sb_extension_alone_does_not_split_r001`). New: `FP-016` row in `docs/learning/failure_patterns.md` + `KNOWN_FP_REGRESSIONS` entry. Renumbered §12 → §8 in `docs/adr/ADR-003-plan-shell-exporter.md` (current develop ADR ended at §7) and adjusted intra-ADR refs from "§12" → "§8" in the FP-016 doc + KNOWN_FP entry. References inside §8 to `tools/audit_soft_barriers.py` and `tools/diagnose_room_polygons.py` describe the eventual end-state (the #143 follow-up) — those tools are NOT yet on develop; called out explicitly inside §8. No fixture, baseline, gate, schema, threshold, Ruby/SU exporter, or CI workflow changed. |
| 2026-05-24 | (PR #143 partial — diagnostic tools) | Extracted Part A of `fix/plan-shell-frente2-diagnostic-layers-and-audits` (PR #143, head `5d38ba2`) onto current develop via selective file checkout in worktree `sketchup-mcp-pr143-tools`. Kept ONLY the two standalone, read-only diagnostic tools (`tools/audit_soft_barriers.py` + `tools/diagnose_room_polygons.py` — both already referenced by the now-merged ADR-005 §6 / ADR-003 §8). Did NOT bring `--layer-mode` work that conflicts with the wall-shell canonicalisation + window-aperture rewrite from #164 (`tools/build_plan_shell_skp.{py,rb}` modifications, `tests/test_build_plan_shell.py` additions, ADR-003 §11 doc). Added 22 smoke tests (`tests/test_diagnose_room_polygons.py` 12 tests + `tests/test_audit_soft_barriers.py` 10 tests) covering the pure-Python `classify()` decision boundaries (reject > 50% overlap / keep / warn), the `diagnose()` report shape against the quadrado canonical fixture (1 room, 0 suspicious merges), and CLI `--help` smoke. No PDF needed for either test suite. Tools have ZERO runtime dependencies on the rest of PR #143 — they import only stdlib + shapely + matplotlib + pypdfium2 (all already in `pyproject.toml`). PR #143 remains open; Part B (`--layer-mode`) is tracked as separate evaluation cycle (likely needs reimplementation over the post-#164 plan-shell exporter rather than cherry-pick). |
| 2026-05-24 | (Slice 6b) | room_polygon_override producer rule + cockpit consumer chain (ADR-002 §4 Slice 6b). Closes the consumer half of the polygon-override loop opened by Slice 6a (PR #124 `f01a9ae`). Producer (`tools/propose_skp_actions.py`) gains `_rule_polygon_correction` — parses fidelity warnings of shape "ROOM area X: observed Y m^2 vs expected [LO, HI]" and emits `expand_room_polygon` / `shrink_room_polygon` chips with a uniform-centroid-scaled `suggested_polygon_pts`. Confidence pinned at 0.55 (< LOW_CONFIDENCE_THRESHOLD) so cockpit treats as DRAFT. Cockpit (`cockpit/proposed_actions.py`) gains `POLYGON_PROPOSED_ACTION_TYPES` + polygon branch in `proposed_action_to_override_payload` mapping → `room_polygon_override` with `edit_method="from_proposed_action"` + `from_proposed_action_id` audit-link. Cockpit Review tab (`cockpit/app.py`) gains "✏️ Edit polygon" expander per room (text-area + edit_method radio + Save button) + `_save_room_polygon_override` helper that runs hard + soft validators before `save_override`. Polygon chips do NOT auto-save: "Open in editor" seeds the text-area via `session_state` (`room_poly_text_<eid>` / `room_poly_open_<eid>` / `room_poly_chip_id_<eid>` / `room_poly_method_<eid>`), human reviews/edits, then clicks Save — honours the "no automatic destructive polygon edits" rule. New tests: `tests/test_propose_skp_actions_polygon.py` (22) + `tests/test_cockpit_proposed_actions_polygon.py` (15). Slice 4 chip mappings (classify_opening / mark_low_confidence / request_human_review) unchanged. No schema bump, no consensus mutation, no SKP-exporter change (overrides remain SKP-blind per ADR-002 §2.8). |
| 2026-05-25 | (Artifact policy) | New canonical doc `docs/ARTIFACT_POLICY.md` + `CLAUDE.md` §23 codify that `.skp` is the project's primary deliverable. Establishes `artifacts/human_review/<plant>/` (Felipe-facing — must contain `.skp`) and `artifacts/agent_inputs/<plant>/` (agent/test plane — JSON/reports or pointer doc) as the canonical two-folder split for tracked deliverables. Promotes the canonical quadrado SKP from `runs/quadrado_v4_canonical/quadrado.skp` (sha256 `28fddd…b5a9cf`, 66,609 bytes, built 2026-05-24 03:20 post-#164) to `artifacts/human_review/quadrado/quadrado_canonical_with_window.skp` alongside the matching render PNG + per-plant README documenting provenance + regen command. `tools/repo_health_gate.py` updated: (i) `artifacts/` added to `CANONICAL_TOP_LEVEL_DIRS` so E003 does not fire when the dir is first introduced; (ii) `artifacts/human_review/` + `artifacts/agent_inputs/` added to `GENERATED_ALLOWED_PREFIXES` so tracked `.skp` (and other generated suffixes) under those paths do not fire E002. Three new gate tests (`tests/test_repo_health_gate.py`): tracked `.skp` under `artifacts/human_review/` does NOT fire E002; rogue `.skp` outside the allow-list DOES fire E002 (bury-the-deliverable guard); `artifacts/` does not fire E003 in PR mode. The rule "No PR may claim SKP success unless the reviewable `.skp` is committed in `artifacts/human_review/`" is now policy. Existing tracked `fixtures/planta_74/skp_final_model.skp` stays at its current path per the forward-looking migration plan in ARTIFACT_POLICY §6 — no mass-move. LFS escape hatch documented for `.skp` > 5 MB. |
| 2026-05-25 | (Quadrado uniform fixture, JSON-only) | New fixture `fixtures/quadrado/consensus_uniform_4windows.json` — geometrically uniform quadrado variant with 4 identical windows (one centered per wall, all 30 pt wide), intended as the **fidelity reference** for the quadrado plant. Resolves the asymmetric-window heterogeneity in the existing canonical (single south window): "todas as paredes devem ser da mesma maneira, sem separações". The pre-existing `consensus_with_window.json` (single window, asymmetric) STAYS as the window-aperture contract reference (locked by 15 `tests/test_window_aperture_contract.py` tests). New `tests/test_quadrado_uniform_fixture.py` (12 tests) locks the uniformity invariants: 4 walls / 1 room / 4 openings; each window centered on its wall midpoint (delta < 1e-6); all widths identical (30 pt); all `kind_v5 == "window"`; cardinal ids `win_south/north/west/east` cover all 4 sides. **SKP build deferred to follow-up PR** — per CLAUDE.md §23 artifact policy this PR does NOT claim "SKP generated successfully"; the JSON fixture is the deliverable here. The `.skp` + render + geometry_report.json land in `artifacts/human_review/quadrado/quadrado_uniform_4windows.{skp,png}` once `tools/build_plan_shell_skp.py` is run (SU 2026 spawn — kept as separate step for the maintainer to authorize / execute). |
| 2026-05-25 | (Track orphan SU diagnostic tools) | Tracked 4 SU diagnostic launchers + Ruby builders that have been sitting untracked in the working tree despite already being cited as live tooling in committed docs: `tools/build_room_ring_skp.{py,rb}` (the single-room ring-exporter precursor that ADR-003 §1 credits with proving the face-with-hole + one-pushpull paradigm later scaled into `build_plan_shell_skp`) and `tools/dump_skp_groups.{py,rb}` (non-disruptive group dumper documented under "Live debugging" in `CONTRIBUTING.md`; `failure_patterns.md` FP-014 references `build_room_ring_skp.py` as using `disarm_sketchup_autoruns` in its launch try/finally). Net effect: +727 LOC across the 4 files, 0 deletions, 0 existing files modified. No tests yet — both tools require SU 2026 GUI runtime per `CLAUDE.md` §3 + §18 (the SketchUp Rule + SU runner mode protocol); a CI-safe smoke harness (env-detect SU 2026, skip cleanly when absent) is the natural follow-up. Production exporter `consume_consensus.rb` and successor `build_plan_shell_skp.{py,rb}` untouched. |
| 2026-05-25 | (Dashboard Roadmap + SRE Radar tabs, resurrected) | Cherry-picked the two long-orphan dashboard commits `992bb79` (2026-05-04 "dashboard: add project roadmap status view") and `f77af4f` (2026-05-04 "dashboard: add architecture SRE radar") that had been sitting on local-only branches `dashboard/project-roadmap` + `dashboard/architecture-sre-radar` for ~3 weeks without ever being pushed or PR'd. Onto current `origin/develop` in a fresh `feature/dashboard-radar-and-roadmap` branch; both picks applied cleanly (zero conflict — the work was purely additive `docs/dashboard/`, `scripts/dashboard/`, `tests/dashboard/`, `tools/dashboard/`). New: `scripts/dashboard/generate_architecture_radar.py` (525 LOC, stdlib-only repo-health manifest generator), `tools/dashboard/architecture_radar.example.json` + 4 sibling example manifests with graceful fallback, `tests/dashboard/test_generate_architecture_radar.py` (7 tests, all PASS locally), `docs/dashboard/architecture_sre_radar.md` + `docs/dashboard/project_status_dashboard.md` (companion docs with `Status: Active` headers per REPO_HYGIENE §2). `tools/dashboard/index.html` gains "Roadmap" (kbd 6, hash `#roadmap`) and "SRE Radar" (kbd 7, hash `#radar`) tabs driven by JSON manifests with `.example.json` fallback. Net effect: +2417 LOC across 11 files, 0 existing tests/scripts/Ruby touched. The 2 source branches will be deleted after this cherry-pick PR lands. |
| 2026-05-26 | (PR #180 — md hygiene pass 2) | Content-based `.md` cleanup beyond the 2026-05-10 audit's grep-only verdict. Deleted `PROMPT-FELIPE.md` (root, 142 lines, F1-cycle onboarding prompt 2026-04-21) — cross-refs only in `_archive/` (frozen) + auto-generated audit reports; `CLAUDE.md` + `.ai_bridge/HANDOFF.md` + `docs/PROJECT_STATE.md` are the canonical onboarding stack. Moved 4 stale docs to new `docs/_archive/2026-05-md-cleanup/`: `docs/SOLUTION.md` (F1-cycle writeup 2026-04-21, companion to already-archived `_archive/2026-04-f1-cycle/SOLUTION-FINAL.md`) + 3 unimplemented cache design docs `docs/performance/cache_{design,keys,rollout_plan}.md` (DL-006 status: "Documented only. PR 1 to be opened" — bloating `docs/performance/` without active implementation). Updated 2 refs in lockstep: `tools/repo_health_gate.py` (`ROOT_MD_EXEMPT` minus `PROMPT-FELIPE.md`) + `docs/learning/decision_log.md:76-78` (DL-006 cache paths point at archive). Auto-regen: `reports/current/repo_health_report.md`. Validation: `python tools/repo_health_gate.py --mode audit` → ERROR 0, W001 0, W002 48→45, I003 10. Total `.md` tracked 140→139. No algorithm/schema/threshold/Ruby/SU touched. Archive preserves DL-006 cross-refs; no dangling pointers. |
| 2026-05-26 | (md hygiene pass 3 — F1 archive prune) | Deepest `.md` cleanup so far. Deleted 10 F1-cycle archive files with **zero active references** outside the archive itself (only self-refs in archived siblings): `docs/_archive/2026-04-f1-cycle/{ANALYSIS-OVERVIEW,ANALYSIS,CAUSA-RAIZ,CROSS-PDF-VALIDATION,DOCS-CONSOLIDATION-TODO,OPENINGS-EXPLOSION-AUDIT,OPENINGS-REFINEMENT,ORPHAN-RESIDUAL-AUDIT,PROMPT-NEXT-CLAUDE,VALIDATION-F1-REPORT}.md` (-~75 KB). Plus deleted `docs/diagnostics/2026-05-09_dogfood_amended_overlay.svg` (15 KB, zero refs, autonomous-loop dogfood wave concluded). Updated `OVERVIEW.md` to drop the 3 stale links to `docs/{ANALYSIS,CAUSA-RAIZ}.md` (those root paths never actually existed; were broken pointers from pre-2026-05-04 archive move) — replaced with refs to surviving canonical docs + `_archive/2026-04-f1-cycle/SOLUTION-FINAL.md` for historical context. Rewrote `docs/_archive/2026-04-f1-cycle/README.md` table to reflect the 5 surviving files + their "why kept" rationale (each cited by active code or canonical doc): `F1-DASHBOARD.html`, `OVER-POLYGONIZATION-ANALYSIS.md` (load-bearing — `tools/repo_health_gate.py` I003 rationale for `analyze_overpoly.py`), `SOLUTION-FINAL.md`, `SVG-INGEST-INTEGRATION.md`, `SVG-MAIN-PLAN-ISOLATION.md`. Auto-regen: `reports/current/repo_health_report.md`. Total `.md` tracked 139→129. No code/schema/threshold/Ruby/SU touched. Git history preserves deleted content. |
| 2026-05-26 | (cleanup pass 4 — orphan tool + FP-012 PNGs + cache archive) | Continued hygiene cycle after PR #181. Deleted 8 more files: (1) `tools/render_pending_paint_zones.py` (8 KB, zero refs, never wired into any pipeline); (2) 4 FP-012 diagnostic PNGs from the `2026-05-07`/`2026-05-08_cycle8b_*` series — FP-012 (convex-hull room leak) was fixed in Cycle 8b per CLAUDE.md §10 "Recently fixed"; PNGs have zero active refs (-~390 KB); (3) the 3 `cache_*.md` files in `docs/_archive/2026-05-md-cleanup/` (PR #180's archive landing — unimplemented design proposals, only refs are self-archive + decision_log). Inlined the DL-006 cache decision into `docs/learning/decision_log.md` so the SHA256-key principle persists without the verbose cache_design/keys/rollout proposal docs; called out that the cache pattern is already partially-implemented for SKP export via `<out_skp>.metadata.json` sidecar (CLAUDE.md §3 step 5). Auto-regen: `reports/current/repo_health_report.md`. Net: -8 files, ~450 KB freed. No algorithm/schema/threshold/Ruby/SU/CI touched. |
