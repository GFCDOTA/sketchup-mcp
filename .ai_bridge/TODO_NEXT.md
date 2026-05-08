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

## 🟡 P0 — Cockpit Slice 2: review_overrides.json read/write

- **Color:** YELLOW — first mutation surface for the cockpit
- **Authoritative spec:** `docs/adr/ADR-001-validation-cockpit-mutation-surface.md` § 3
- **Goal:** the cockpit reads + writes `runs/<run_id>/review_overrides.json`
  for the active run via Streamlit + filesystem (NO FastAPI yet —
  see ADR § 5 alternative C).
- **Touchpoints:**
  - `cockpit/overrides.py` (NEW) — pure helper:
    `load_overrides(run_dir, expected_consensus_sha) -> dict`,
    `save_override(run_dir, override_payload, audit_actor) -> dict`.
    Hash-validates; appends to audit_trail. No streamlit imports.
  - `cockpit/app.py` — new "Review" tab: dropdown per opening for
    re-classify, dropdown per room for re-label, "mark suspect"
    toggle, "reject" button, master "block SKP export" toggle.
  - `tests/test_cockpit_overrides.py` — round-trip, audit-trail
    append-only, sha256-invalidation, schema validation. ≥10 tests.
  - `docs/validation_cockpit.md` — Slice 2 section.
- **What Slice 2 does NOT do:** modify consensus, compute amended
  fidelity, run smoke, block anything. Pipeline still ignores the
  file.
- **Acceptance (from ADR § 3 acceptance):** I can open the cockpit,
  override an opening's kind, close, re-open, see the override
  persisted, see the audit trail, see `source: manual` annotation
  on the SVG.

## 🟡 P1 — Cockpit Slice 3: apply_overrides.py + gate_f0

- **Color:** YELLOW — pipeline starts honouring overrides
- **Authoritative spec:** ADR-001 § 4
- **Goal:** pipeline reads overrides via thin layer; smoke harness
  gains gate_f0; cockpit's Pre-SKP Review reads the F0 verdict
  instead of computing locally.
- **Touchpoints:**
  - `tools/apply_overrides.py` (NEW) — CLI: reads consensus +
    overrides → writes `amended_observed.json`. Pure function plus
    a thin CLI shell.
  - `tools/fidelity/compare_generated_to_expected.py` — new optional
    `apply_overrides: bool = False` param. Default off preserves
    existing baseline.
  - `scripts/smoke/smoke_skp_export.py` — new `gate_f0` BEFORE
    `gate_f`; emits `pre_skp_review_report.json`; honours
    `--review-mode={off,warn,block}` (default `off` keeps CI green).
  - `cockpit/history_view.py` — `pre_skp_review()` reads
    `pre_skp_review_report.json` if present, falls back to in-memory
    computation otherwise.
  - Tests: amended-observed schema, fidelity in apply-overrides
    mode, gate_f0 verdict matrix, --review-mode CLI matrix.
  - `docs/validation/sketchup_smoke_workflow.md` — gate_f0 added.
- **What Slice 3 does NOT do:** flip `--review-mode` default to
  `block` (separate follow-up after one real review case); change
  any existing fidelity threshold; add UI.

## 🟢 P2 — Cycle 12g: on-demand thumbnail rendering

- **Color:** GREEN — additive, opt-in, pure renderer extension
- **Goal:** Cycle 12f's History view shows "no previews discovered"
  for runs that lack PNG/SVG preview files. Add an on-demand
  rasterisation that generates a small thumbnail from
  `consensus_*.json` if no preview exists.
- **Touchpoints:** `cockpit/history_view.py` (thumbnail-on-demand
  helper), maybe a small cache under `runs/<run_id>/_cockpit_cache/`.
- **Risk:** LOW. Cache means it costs nothing on subsequent loads.

## 🟡 P3 — Cockpit Phase 3: FastAPI POST + multi-user

- **Color:** YELLOW — DEFERRED until Slice 2 + 3 prove the contract
- **Authoritative spec:** ADR-001 § 2.9 Phase 3 (no detail yet —
  ADR-002 will land when this becomes real)
- **Why deferred:** ADR § 5 alternative C — premature complexity for
  a single-user local tool. Streamlit + filesystem JSON is enough
  through Slice 2. Re-evaluate after the first real review case
  pushes the limits of the local-only contract.

## 🔴 P2 — Multi-PDF corpus

- **Color:** RED — needs Felipe to provide 3+ different real
  planta PDFs. Synthetic round-trip (Cycle 11) covers algo
  validation; this would cover detector generalisation.

## 🔴 P3 — Stage 1.6 / orphan inspector branch

- **Color:** RED — explicitly on hold per earlier session
- **Branches affected:** `feature/smoke-promotes-inspector-v2-gate`
  (orphan, never PR'd).
- **To unblock:** Felipe needs to lift Stage 1.6 hold.
