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
  tab. **Catches FP-012 leakage on planta_74 visually.** +4 tests
  (18/18 cockpit total).
- **Hygiene audit ledger** (PR #73, `c788df9`): root-level files
  cross-referenced; no archives this cycle (every candidate has a
  live reference path); ledger at
  `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md`.
- 6 PRs total this session. develop @ `c788df9`.
- **gh CLI tooling unblocked** — see LL-012 +
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.

## 🟢 P0 — Cycle 12c: hover highlight on rooms / openings

- **Color:** GREEN — additive, opt-in (no breaking change)
- **Goal:** add `<title>` tooltips + a small CSS rule that
  highlights the polygon under the cursor (`fill-opacity` jump,
  outline thicken). Optionally add JS-driven cross-highlighting
  between SVG and the inspector table.
- **Touchpoints:** `cockpit/render_overlay.py` (emit `<title>`
  child elements + maybe `<style>` block); optional
  `cockpit/app.py` event wiring via `streamlit-extras` if available.
- **Validation:** unit test asserting `<title>` present per room +
  per opening with the expected name; visual smoke.
- **Risk:** LOW. Pure additive — no new render path triggered
  unless the cursor moves over an element.

## 🟢 P1 — Cycle 12e: diff view (run A vs run B)

- **Color:** GREEN — additive, dual-consensus rendering
- **Goal:** sidebar second consensus picker; when both are picked,
  render side-by-side OR overlay-with-diff. Per-room area delta
  in inspector. Useful for baseline-shift PRs (e.g. visualise the
  pre/post Cycle-8b concave-hull change).
- **Touchpoints:** `cockpit/render_overlay.py` (add a
  `render_diff_svg(consensus_a, consensus_b)` helper or extend the
  existing renderer with a `consensus_b` param), `cockpit/app.py`
  sidebar second-picker.
- **Validation:** unit tests on the diff helper + visual smoke.
- **Risk:** LOW. Pure additive.

## 🟢 P1 — `renderers/` migration (architecture plan step 5)

- **Color:** GREEN — clears the 4 transitional `render_*.py`
  orphans flagged in PR #73's hygiene audit.
- **Goal:** move `render_debug.py`, `render_native.py`,
  `render_semantic.py`, `render_proto_overlays.py`,
  `render_with_openings.py` into `packages/renderers/` per
  `docs/architecture/target_repo_architecture.md` step 5.
- **Touchpoints:** new `packages/renderers/` tree; deprecation
  wrappers at the original root paths; `OVERVIEW.md` +
  `docs/png_history_protocol.md` reference updates.
- **Validation:** root scripts still importable (deprecation
  wrapper) + `python -m packages.renderers.<name>` works.
- **Risk:** MEDIUM. Repo-shape change. Should be its own PR.

## 🟡 P2 — Refactor `proto_*.py` + `render_sidebyside.py` to CLI args

- **Color:** YELLOW — kills the hardcoded `C:/Users/felip_local/`
  paths flagged in `pyproject.toml [tool.ruff].extend-exclude`.
  Once done, un-exclude them from ruff.
- **Goal:** convert hardcoded paths to `argparse` CLI args.
- **Touchpoints:** `proto_colored.py`, `proto_red.py`,
  `render_sidebyside.py`, `pyproject.toml [tool.ruff]` cleanup.
- **Validation:** `python proto_colored.py --plant planta_74` (or
  similar) reproduces previous output; ruff turns from
  excluded → checked.

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
