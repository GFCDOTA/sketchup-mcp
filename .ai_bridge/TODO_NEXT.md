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
- **Cycle 12 cockpit MVP** (PR #68, merged 19:03Z): Streamlit
  read-only validator + pure-Python SVG renderer + 10 new tests +
  `[cockpit]` extra. develop @ `84eae72`. 578/595 passing.

## 🟢 P0 — Cockpit Slice 1.5 (Cycle 12b): PDF underlay

- **Color:** GREEN — additive, opt-in, no schema change
- **Felipe ordering:** explicitly first in queue post-Cycle-12.
  "Não mexer em Cycle 8c / polygon refinement / Stage 1.6 antes
  desse cockpit" + cockpit doc lists it as biggest visual win.
- **Goal:** render the source PDF (`pypdfium2`) as an `<image>`
  behind the SVG overlay so the user sees consensus *on top of*
  the original drawing. Still read-only.
- **Touchpoints:**
  - `cockpit/render_overlay.py` — accept optional PDF base bytes,
    emit `<image href="data:application/pdf...">` (or pre-render
    to PNG via pypdfium2 + base64).
  - `cockpit/app.py` — sidebar PDF picker (auto-discover
    `runs/<dir>/*.pdf` and `proto_*.pdf` siblings of consensus).
  - `pyproject.toml` — `pypdfium2` joins `[cockpit]` extra (or
    `[dl]`-style extra, decision pending).
- **Validation:** visual smoke on planta_74 (PDF + cockpit SVG
  align within ±2pt); existing 10 cockpit tests still green;
  no streamlit-import on core path.
- **Risk:** LOW. Pure additive. Coord alignment is the one
  watch-out — PDF user-space already matches consensus PT coords,
  so should be 1:1 with a y-flip we already do.

## 🟢 P1 — Cockpit Slice 1.5b (Cycle 12d): expected_model overlay

- **Color:** GREEN — toggle already exists in `OverlayToggles`,
  data is in `expected_model.json`, renderer just needs to draw.
- **Goal:** when GT picker is selected and `ground_truth_overlay`
  toggle is ON, draw expected room polygons as dashed outlines
  over the observed.
- **Touchpoints:** `cockpit/render_overlay.py` (extend
  `render_overlay_svg` to consume `expected_model` arg, already
  in signature).
- **Validation:** unit test against `ground_truth/planta_74_micro.json`;
  pixel-diff against current overlay limited to dashed outlines.
- **Risk:** LOW. Pure additive.

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
