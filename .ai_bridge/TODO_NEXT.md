# TODO Next — ROI-ordered

> Continuous queue. Top items execute first. Update as items land
> or new ones surface.
>
> **Ordering rule (per `feedback_autonomia_operacional_protocolo.md`):**
> GREEN first, then YELLOW with validation, then RED only after
> human unblock.

## Format

Each entry:
- **Color** — 🟢 GREEN / 🟡 YELLOW / 🔴 RED
- **Priority** — P0 / P1 / P2 / P3
- **Evidence** — why this matters
- **Touchpoints** — files / commands likely involved
- **Validation** — how to know it worked
- **Risk** — what can break

---

## ✅ DONE (2026-05-08 — full day wave)

- 9-PR queue zerada (Wave A → E).
- Cycle 8b: concave-hull promoted to default at ratio 0.5; FP-012
  cleared; fidelity engine flipped from advisory → HARD merge
  blocker in `quality_gates.yml`.
- Cycle 6 alt: adjacency_f1=0.67 plateau diagnosed and documented
  as FP-013 (root cause: room polygon defects upstream).
- Cycle 11b/11c/11d: vector-PDF inventory + synthetic vector PDF
  generator + wall-gap widened so opening + adjacency round-trip
  closes (fidelity = 1.0 on `synth_l2`).
- **Cycle 12 cockpit MVP** (PR #68, `84eae72`).
- **Cycle 12b PDF underlay** (PR #70, `8e1e225`).
- **Cycle 12d expected_model overlay** (PR #71, `d1a8acc`):
  match-status renderer (5-state palette) + Expected inspector
  tab. **Catches FP-012 leakage on planta_74 visually.**
- **Hygiene audit ledger** (PR #73, `c788df9`): no archives this
  cycle (every candidate has a live reference path); ledger at
  `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md`.
- **Cycle 12c hover highlight** (PR #75, `38c3c54`): `<title>`
  tooltips + CSS `:hover` on rooms/openings. Pure CSS, no JS.
- **Cycle 12e diff view** (PR #76, `e090272`): second consensus
  picker + dashed-magenta overlay + Diff inspector tab + per-room
  delta. **Cockpit read-only slice now feature-complete.**
- **9 PRs total this session.** develop @ `e090272`.
  26/26 cockpit unit tests pass.
- **gh CLI tooling unblocked** — see LL-012 +
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.

## ✅ DONE — 2026-05-08 parallel wave (PRs #78, #79, #80)

- **PR #80 — `renderers/` migration step 5** (`a87185c`): 5 root
  `render_*.py` → `renderers/` package via `git mv`; deprecation
  wrappers + DeprecationWarning + 8 new tests. Function-ised each
  module so `renderers.<name>.render(...)` works programmatically.
- **PR #79 — Cycle 12f cockpit History/Fidelity view** (`a1d04ff`):
  new `cockpit/history_view.py` (350 LOC pure-Python) + History /
  Compare / Detail views + Pre-SKP Review status (PASS/WARN/FAIL,
  advisory). 19 new tests. All 10 FRs implemented in v0; thumbnails
  for runs without preview files deferred to Cycle 12g.
- **PR #78 — proto/render_sidebyside CLI refactor** (`0655f0a`):
  3 scripts → argparse; 3 entries cleared from
  `[tool.ruff].extend-exclude`; 5 new smoke tests. CI hiccup
  (skimage missing in `[dev]`) handled mid-flight via lazy import.
- 3 PRs landed in parallel via 3 worktrees. develop @ `a87185c`.
  Net session delta: 626 PASS / 17 FAIL (raster legacy) / 8 SKIP —
  +58 tests vs pre-session baseline.

## ✅ DONE — this PR (ADR-001)

- **`docs/adr/` directory created** (first ADR in the repo).
- **ADR-001 — Validation Cockpit Mutation Surface** shipped at
  `docs/adr/ADR-001-validation-cockpit-mutation-surface.md`.
  Defines the contract for `review_overrides_v1`,
  `proposed_actions_v1`, `pre_skp_review_v1`,
  `amended_observed_v1` schemas; 7 override types; 6 proposed-
  action types; F0 gate PASS/WARN/FAIL semantics + `--review-mode`
  CLI; 8 safety invariants; phased pipeline-consumption rollout
  (Slice 2 → Slice 3 → future FastAPI Phase 3).
- `docs/adr/README.md` — index + ADR template + promotion rules
  (when an ADR-lite graduates to a full ADR).
- `.ai_bridge/DECISIONS.md` — entry pointing at ADR-001.
- This file refreshed: Slice 2 + Slice 3 entries below are now
  derived directly from ADR-001 § 3 + § 4.

## ✅ DONE — 2026-05-08 mutation-wave (PRs #82–#88)

- **PR #82 — Cycle 12g thumbnail on-demand** (`1f200c5`):
  `cockpit/thumbnails.py` (282 LOC PIL-direct rasteriser); cache
  under `runs/<run_id>/_cockpit_cache/`; 19 tests.
- **PR #83 — Slice 2 cockpit/overrides.py + Review tab**
  (`dd2a199`): all 7 v1 override types live; 30 tests; Streamlit
  Review tab persists to `runs/<run_id>/review_overrides.json`.
- **PR #84 — Slice 3 apply_overrides + gate_f0 + history_view F0
  read** (`76739b3`): pipeline-side consumer + new `gate_f0` in
  smoke harness with `--review-mode={off,warn,block}` (default
  `off` keeps CI byte-equivalent); fidelity engine
  `apply_overrides=True` mode emits both `global_fidelity` and
  `global_fidelity_pre_override`; 69 tests.
- **PR #85 — Cycle 12h SVG `source: manual` annotation + inline
  override removal** (`d454842`): closes Slice 2's two deferred
  items; `× remove` button writes append-only `event: delete`
  audit entries; 6 new tests.
- **PR #86 — Stage 1.6 investigation + follow-up brief**
  (`c452bc5`): docs-only audit of orphan branch
  `feature/smoke-promotes-inspector-v2-gate`; concludes `gate_f0`
  + proposed `gate_g2` are complementary; brief at
  `.ai_bridge/pr_bodies/PR_BODY_stage_1_6_followup.md`.
- **PR #87 — cross-PR mutation integration tests** (`ef977a4`):
  16 tests exercising Slice 2 → Slice 3 round-trip end-to-end on
  hand-crafted minimal fixtures; **zero API gaps** between the
  two slices.
- **PR #88 — multi-PDF synth corpus** (`dc0aa14`): 3 new
  topologies (T, +, long-hall) round-tripped at fidelity = 1.0;
  `ground_truth/synth_{t3,plus4,hall5}/`; 10 new tests. RED →
  partial-YELLOW substitution: synth coverage broadens, real-PDF
  coverage stays Felipe-blocked.
- 7 PRs since ADR-001. develop @ `dc0aa14`. **776 PASS** (+150
  vs session start).

## ✅ DONE — 2026-05-09 autonomous-loop wave (PRs #90–#99)

10 PRs end-to-end through the autonomous `<<autonomous-loop-dynamic>>`
runtime, closing the override-aware F0 verdict loop completely + a
real-data dogfood that proved the contract holds:

- **PR #90 — Cycle 5** (`cfd7f8a`): gate_g2 inspector v2 consumer
  ported from the orphan branch (Stage 1.6 follow-up half 1; SKIPs
  cleanly until Cycle 6 wires the producer)
- **PR #91 — Cycle 13** (`86cb1f3`): `tools/propose_skp_actions.py`
  producer for `proposed_actions_v1` (4 detection rules, 23 tests,
  uuid5 idempotence)
- **PR #92 — Slice 4** (`dc8048d`): cockpit Review tab consumes
  proposed_actions.json + chips with one-click apply +
  `source_proposed_action_id` audit-link
- **PR #93 — Cycle 13b** (`1789227`): smoke harness gate_f0_pa
  emits proposed_actions.json into out_dir (opt-in via
  `--emit-proposed-actions`)
- **PR #94 — Slice 5a** (`c469d00`): gate_e_amend writes
  `amended_observed.json` when `review_overrides.json` exists
  (auto-default)
- **PR #95 — Slice 5b** (`341e2c8`): gate_e_fidelity_amended runs
  fidelity engine in `apply_overrides=True` mode, emits both pre/post
  scores per ADR §2.10.5
- **PR #96 — Slice 5c** (`08bb8e7`): gate F0 PREFERS
  `fidelity_report_amended.json` over the raw report; surfaces
  pre/post/Δ in `pre_skp_review_v1`
- **PR #97 — Slice 4-extra** (`bc5281c`): cockpit Pre-SKP pane
  shows `🧑 amended` badge + post/pre/Δ caption
- **PR #98 — sys.path fix + dogfood report** (`d01bc76`): real
  end-to-end exercise on planta_74 + UX gap #1 fixed in-flight
  (smoke harness sys.path bootstrap)
- **PR #99 — Slice 5d** (`f7ee221`): per-sub-score Δ surfaced in
  `pre_skp_review_v1` + cockpit collapsible "🔍 sub-score Δ"
  expander (closes UX gap #3 from dogfood)

**Validation:** 568 PASS baseline → **889 PASS** (+321), 17 raster
legacy failures (CLAUDE.md §10) unchanged, 8 SKIP. Zero new failures
across the wave. develop @ `f7ee221`.

**Dogfood evidence (PR #98):** 3 overrides created via cockpit API
on the canonical planta_74 baseline; consensus sha256 byte-identical
before/after (ADR §2.10.1 invariant proved). adjacency_score moved
-0.088 (caught + reported honestly per §2.10.5; Slice 5d ships the
visibility fix).

## 🟡 P1 — ADR-002: room_polygon_override (dogfood UX gap #2)

- **Color:** YELLOW — schema-extending architectural decision,
  NOT autonomous-loop-friendly
- **Why this matters:** the dogfood (PR #98) found the most common
  real failure mode — room polygon area out of expected range
  (FP-012-style leakage on SUITE 01 = 69.91 m² vs expected
  `[10, 28]`) — has NO direct override type in v1. Reviewer's
  only option is `reject_element` on the entire room, which usually
  hurts fidelity more than it helps (count_score then drops).
- **Goal:** ADR-002 defining `room_polygon_override` schema, apply
  semantics, and how it interacts with `apply_overrides.py`.
  Consider symmetric option: producer-side
  `expand/shrink_room_polygon` proposed_actions (already in ADR-001
  §2.6 spec, just no producer yet).
- **Why deferred from autonomous loop:** schema extension touches
  multiple files (override schema, apply_overrides, fidelity engine
  apply mode, cockpit overrides.py + Review tab + chip promotion
  mapping). Deserves Felipe's input on direction before committing.
- **Recommended sequencing:**
  1. Draft ADR-002 (decision: new override type vs proposed_action
     surface + UI hints)
  2. If new override type: extend `cockpit/overrides.py` schema +
     `tools/apply_overrides.py` apply logic + cockpit Review tab
     UX (polygon edit picker is the hard part)
  3. Tests for round-trip + apply + fidelity recompute
  4. Dogfood the new path on the same SUITE 01 case from PR #98

## 🟡 P1 — Cycle 6 (Stage 1.6 implementation): wire autorun inspector into `gate_f`

- **Color:** YELLOW — touches SU runtime; deserves its own
  focused session
- **Goal:** every successful `gate_f` leaves `inspect_report.json`
  via `tools/autorun_inspector_plugin.rb`; `gate_g2` stops
  SKIPping and starts validating it.
- **Touchpoints:** `scripts/smoke/smoke_skp_export.py` (gate_f
  extension); `tools/autorun_inspector_plugin.rb` (existing,
  untouched logic — just hooked in); CI workflow may need a
  Windows-runner with SU 2026 (TBD).
- **Risk:** MEDIUM — first SU spawn wired into the smoke harness
  beyond gate_f's existing SU usage.

## 🟢 P2 — Cycle 7: promote `--inspect-strict` to default in CI

- **Color:** GREEN — additive flag flip after Cycle 6 stabilises
- **When:** after Cycle 6 runs green for several days on develop.
- **Risk:** LOW — feature-flag flip; rollback is one revert.

## 🟡 P3 — Cockpit Phase 3: FastAPI POST + multi-user

- **Color:** YELLOW — DEFERRED until first real review case shows
  the local-only contract is insufficient
- **Authoritative spec:** ADR-001 § 2.9 Phase 3 (no detail yet —
  ADR-002 will land when this becomes real)
- **Why deferred:** ADR § 5 alternative C — premature complexity
  for a single-user local tool. The Slice 2 + 3 + 12h surface is
  a complete local-only review loop. Re-evaluate after the first
  real review case pushes the limits.

## 🔴 P2 — REAL multi-PDF corpus

- **Color:** RED — needs Felipe to provide 3+ different real
  planta PDFs. PR #88 (synth corpus) covers 4 topologies in synth
  but does NOT cover detector generalisation on real-world PDFs
  (arc walls, peitoris, soft barriers, scale anchoring,
  project-specific labels).
- **What's already covered (synth):** L, T, +, long-hall — 4
  topologies, all round-tripping at fidelity = 1.0. Algorithmic
  generalisation surface is now broad enough that algo
  regressions surface fast.
- **What's missing:** detector behaviour on real-world drawing
  conventions. No substitute exists for actual PDFs.
