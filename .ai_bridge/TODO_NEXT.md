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

## 🟡 P0 — Cycle 5 (Stage 1.6 follow-up): port `gate_g2` consumer

- **Color:** YELLOW — pure-Python smoke harness extension; no SU
  spawn (gate is `"deferred"` SKIP until Cycle 6 lands)
- **Authoritative spec:**
  `.ai_bridge/pr_bodies/PR_BODY_stage_1_6_followup.md` (ready-to-paste
  brief) + `docs/diagnostics/2026-05-08_stage_1_6_investigation.md`
  (full audit)
- **Goal:** add the 88-LOC harness change + 11 fixture tests from
  the orphan branch `feature/smoke-promotes-inspector-v2-gate`,
  with one trivial test relaxation (substring assertion in
  `test_pipeline_includes_gate_g2` to handle the multi-line tuple
  now that `gate_f0` lives in the pipeline).
- **Touchpoints:** `scripts/smoke/smoke_skp_export.py` (gate_g2
  consumer); `tests/test_smoke_gate_g2.py` (NEW); cherry-pick or
  fresh-author from the orphan tip `2417a20`.
- **Validation:** new gate SKIPs cleanly; smoke harness behaviour
  unchanged in default invocation; `pytest -q` no NEW failures.
- **What Cycle 5 does NOT do:** spawn SU; integrate
  `tools/autorun_inspector_plugin.rb`; modify `gate_f`. That's
  Cycle 6.

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
