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
- **Cycle 12 cockpit MVP** (PR #68, merged 19:03Z, `84eae72`):
  Streamlit read-only validator + pure-Python SVG renderer + 10
  new tests + `[cockpit]` extra.
- **Cycle 12b PDF underlay** (PR #70, merged 19:25Z, `8e1e225`):
  pypdfium2 → base64 PNG `<image>` behind the SVG; sidebar picker
  + DPI/opacity sliders; +4 tests (14/14 cockpit total); demo SVG
  with planta_74 baked in. Default opt-in `(none)`. develop @
  `8e1e225`. 99/99 in-scope passing.

## 🟢 P0 — Cycle 12d: render `expected_model` overlay layer

- **Color:** GREEN — toggle already exists in `OverlayToggles`,
  signature param `expected_model=None` already in
  `render_overlay_svg`, data is in `ground_truth/<plant>/expected_model.json`,
  renderer just needs to draw.
- **Goal:** when GT picker is selected and `ground_truth_overlay`
  toggle is ON, draw expected room polygons as dashed outlines
  in a contrasting color (per-room match status: green=found,
  orange=mismatched-area, red=missing, grey=extra-observed).
- **Touchpoints:** `cockpit/render_overlay.py` (extend renderer +
  add `_build_room_status_map(consensus, expected_model)`),
  optionally `cockpit/app.py` for a "GT match summary" panel.
- **Validation:** unit test asserting `<polygon stroke-dasharray=...>`
  present when `expected_model` provided + visual smoke on
  `runs/vector` vs `ground_truth/planta_74/expected_model.json`.
- **Risk:** LOW. Pure additive. Renderer-only change.

## 🟢 P1 — Cleanup hygiene scan (CLAUDE.md §15)

- **Color:** GREEN — additive, archive-not-delete
- **Goal:** post-12-PR-wave scan of stale .md / generated PNG /
  abandoned scripts.
- **Touchpoints:** root-level `.md`, `runs/_archive/`, top-level
  `proto_*.py` candidates, `docs/diagnostics/2026-05-0[1-7]_*`.
- **Validation:** nothing live broken; archive doc updated.
- **Risk:** LOW. Per §15: archive instead of delete; preserve
  baselines / ground_truth / regression artifacts.

## 🟡 P2 — Cockpit Slice 2: approve / reject + review_overrides.json

- **Color:** YELLOW — introduces FastAPI + persistence
- **Goal:** per-element approve/reject buttons; persisted to
  `runs/<dir>/review_overrides.json`; sha256 invalidation if
  consensus changes underneath.
- **Touchpoints:** new `api/cockpit_routes.py`, new
  `api/review_store.py`, `cockpit/app.py` button wiring.
- **Validation:** round-trip override file + sha256 invalidation
  test; doesn't break read-only contract on consensus itself.
- **Risk:** MEDIUM. First mutation surface in cockpit boundary —
  ADR update in `.ai_bridge/DECISIONS.md` required.

## 🟡 P2 — Cockpit Slice 3: proposed_actions.json + pre-SKP gate F0

- **Color:** YELLOW — new schema + smoke gate
- **Goal:** new `tools/propose_skp_actions.py` derives action plan
  from c3 + fidelity; `scripts/smoke/smoke_skp_export.py` adds
  Gate F0 with `--review-mode={off,warn,block}`. Default `off` so
  existing smokes keep passing.
- **Risk:** MEDIUM. Smoke gate is core CI surface; default-off
  protects baseline.

## 🔴 P2 — Multi-PDF corpus

- **Color:** RED — needs Felipe to provide 3+ different real
  planta PDFs. Synthetic round-trip (Cycle 11) covers algo
  validation; this would cover detector generalization.
- **Goal:** widen test surface beyond `planta_74` so detector
  retunes don't accidentally specialize.

## 🔴 P3 — Stage 1.6 / orphan inspector branch

- **Color:** RED — explicitly on hold per earlier session
- **Branches affected:** `feature/smoke-promotes-inspector-v2-gate`
  (orphan, never PR'd).
- **To unblock:** Felipe needs to lift Stage 1.6 hold.
