# Ground Truth v1 — what it is, how to edit it, how to read the report

> Companion to `tools/fidelity/compare_generated_to_expected.py` and
> `ground_truth/schema/expected_model.schema.json`. The "minimum
> ground truth that already blocks real regression" — explicit
> answer to the design prompt that birthed this work.

---

## Why this exists

Before v1 the project had three layered validators:

- `tests/test_planta_74_truth_gate.py` — pins the deterministic
  pipeline output against a baseline JSON. **Self-referential**:
  it locks the pipeline against itself. Catches accidental drift
  but does not prove the detector got the building right.
- `tools/coherence_audit.py` — emits an uncertainty report. Has no
  external truth, only internal consistency.
- `tools/micro_truth_gate.py` — checks 1+ named rooms against a
  manually curated micro JSON. Per-room subset, not whole plant.

What was missing: **a whole-plant golden truth that says "this is
what the apartment IS" independent of the detector**. Without it,
a regression that breaks SUITE 01's polygon (the FP-012 leakage)
shows up only as a blurry "areas look weird" feeling — never as a
red CI status.

Ground Truth v1 fills that gap with the **minimum** content that
already blocks real regression on `planta_74`.

---

## The two truths, explicitly

This project deliberately separates:

| Layer | What | File | Used by |
|---|---|---|---|
| **Weak truth** | The original PDF — pixels + vector paths | `planta_74.pdf` | Visual overlays, manual review, future opening-position metrics |
| **Golden truth** | A versioned manual JSON describing the apartment as architectural reality | `ground_truth/planta_74/expected_model.json` | `tools.fidelity.compare_generated_to_expected` |

The fidelity engine **never** consults the PDF directly. The PDF
is the source of truth for the human annotator; the JSON is the
source of truth for the gate. Mixing them breaks both.

---

## What v1 contains, by design

Required fields (see schema for the full list):

- `plan_id`, `schema_version`, `unit`, `scale_source`
- `global_bbox` — apartment footprint in meters + tolerance %
- `expected_counts` — rooms / openings / walls + per-axis tolerance
- `rooms[]` — id, label, `expected_area_m2_range`, `must_be_closed`,
  `manual_confidence` (low/medium/high)
- `openings[]` — id, kind, `connects` (room-id pair), confidence
- `adjacency[]` — `(a, b)` edges between rooms with optional `via`
  opening id

Deliberately **excluded** from v1:

- Per-wall geometry (start/end at exact mm)
- Per-room polygon for IoU
- Opening positions along walls
- Materials, mobiliario, furniture
- Wall thicknesses
- Floor heights, parapet heights

Those are v2 once v1 stabilizes. The reason: v1's purpose is to
**bind the gate to architectural intent**, not pixel-perfect
fidelity. Pixel-perfect lives in `tests/baselines/` (deterministic
self-pin) and in future v2.

---

## Hard fail vs warning — how it's wired

`compare_generated_to_expected` distinguishes two severities:

**Hard fails** (cap `global_fidelity` at 0.69, fail `--strict`):
- `room_count_delta` outside tolerance
- `room_label_match_ratio < 0.7`
- `adjacency_f1 < 0.6` (when adjacency is asserted)
- Any room with `manual_confidence: high` failing `area_in_range`
  or `polygon_closed`
- Any room with `manual_confidence: high` missing entirely

**Warnings** (do not cap; surface in scorecard):
- `opening_count_delta` outside tolerance
- `global_bbox` drift > tolerance %
- Low/medium-confidence rooms failing `area_in_range`
- `0.6 ≤ adjacency_f1 < 0.8`

The `manual_confidence` knob is intentional. When you author a
new ground-truth row, start at `medium`. Promote to `high` only
once you've manually verified the room exists and its area/range
is architecturally correct (not just "matches today's detector").

---

## How to edit `expected_model.json`

1. Read the planta visually (PDF + the latest top-down preview
   under `runs/.../preview_top.png` or
   `docs/diagnostics/.../preview_*.png`).
2. For a NEW row: copy an existing room/opening dict, set `id`
   stable + lowercase + snake_case. Set `manual_confidence: medium`.
3. Set `expected_area_m2_range` generous (~ ±40% of expected
   value) on first commit. Tighten only after multiple runs of
   the gate confirm the detector lands consistently.
4. For rooms whose detector is BUGGY today (e.g. `SUITE 01`'s
   FP-012 leakage), pick the range that would be CORRECT after
   the fix lands. The gate intentionally fails today; that
   failure is the design.
5. Add a `notes[]` entry whenever you set or move a range, so
   the next agent knows why.

**Update procedure on a real range change:**

```
1. Open feature/<slug> branch off develop
2. Edit the JSON
3. Run python -m tools.fidelity.compare_generated_to_expected ...
4. Eyeball the report — does the new range still bind a real
   regression, or did you just relax the gate?
5. If you bumped a range UP: explain why in the PR body. If you
   bumped DOWN: even more so.
6. If you change the schema shape: bump schema_version and add a
   migration note to ground_truth_v1.md.
```

---

## How to read `fidelity_report.json`

Top-level fields:

- `global_fidelity` — single 0..1 number. Capped at 0.69 if any
  hard_fail. Don't read more into this than "did the gate fire".
- `sub_scores` — per-area floats: `room_score`, `count_score`,
  `adjacency_score`, `bbox_score`. Use these to triage.
- `hard_fails[]` / `warnings[]` — exact strings the gate would
  print. Searchable.
- `suggested_fixes[]` — heuristic next-step hints. Not exhaustive.
- `would_block_strict[]` — same as `hard_fails`, kept separate
  for forward-compat.
- `metrics.*` — per-metric raw values (kept for diffability across
  PRs and for future plotting).

When the report is RED (hard_fails > 0):

1. Search `metrics.rooms.rows[*]` for the offending labels.
2. Cross-reference `metrics.adjacency.false_negative` to see
   which expected edges are missing in the consensus.
3. Check `metrics.global_bbox.drift_pct` if scale feels off.

---

## Today's planta_74 baseline (snapshot 2026-05-07)

Run on `develop` at `fad28d9`, observed
`runs/validation_2026-05-07/c3_classified.json`:

```
global_fidelity = 0.69 (capped — 3 hard_fails)
sub_scores = {room_score: 0.75, count_score: 1.0,
              adjacency_score: 0.421, bbox_score: 1.0}
hard_fails = [
  area_in_range:SUITE 01 actual=69.905,  # FP-012
  area_in_range:SUITE 02 actual=32.028,  # FP-012 mild
  adjacency_f1=0.42<0.60                 # classifier gaps
]
warnings = []
```

The 3 hard_fails are KNOWN open bugs:

- SUITE 01 / SUITE 02 areas — fixed by `feature/concave-hull-room-clip-spike`
  (FP-012 Option A behind default-off flag) once promoted to default.
- adjacency_f1 — Cycle 6 (autorun inspector wiring + room-context
  classifier reaching cozinha + AS).

**That is the gate doing its job.** Until those branches land, the
fidelity report is RED. Once they land, all three should clear and
`global_fidelity` should jump to ~0.95.

---

## Limitations

- Only `planta_74` has a v1 expected model today. Multi-PDF corpus
  is roadmap P3.
- v1 does not check opening positions along walls. A door that
  connects the right rooms but at the wrong x-coord still passes.
- v1 doesn't check polygon shape; only area + closure. A
  rectangular SALA pretending to be triangular passes if the
  area happens to land in range.
- Adjacency is materialized via `openings.evidence.room_left/right`.
  An adjacency without a discrete opening object (open passage
  between SALA DE ESTAR and SALA DE JANTAR) is currently coded
  as an opening of `kind: interior_passage` in the GT, but the
  observed pipeline may or may not emit one — that's why the
  expected_model includes it as a `medium` confidence entry.

---

## Promote to hard CI blocker (post-Cycle 8b TODO)

The Fidelity Engine v1 step in `.github/workflows/quality_gates.yml`
ships in **advisory mode** (`continue-on-error: true`) on the first
release. Reason: today's run produces 3 hard_fails (FP-012 SUITE 01 /
SUITE 02 areas + adjacency_f1) — those are real bugs the engine
correctly surfaces, but they would turn `develop` red on every push
until the underlying fix lands.

**When Cycle 8b promotes the concave-hull-room-clip flag to default
and the 3 hard_fails clear** (verified via a green run of
`tools.fidelity.compare_generated_to_expected --strict` on develop),
remove `continue-on-error: true` from the
`Fidelity Engine v1 (advisory until Cycle 8b clears FP-012)` step in
`.github/workflows/quality_gates.yml`. That single-line removal
flips the gate to a hard merge blocker, completing the design intent.

Until that happens, the report is still emitted on every CI run and
uploaded as `fidelity_report.json` / `fidelity_scorecard.md` under
the `quality-gate-reports` artifact for human inspection.

---

## Next steps (v2 candidates, not part of this PR)

Listed in priority order. None of these is in scope for v1.

1. Per-room polygon IoU once SUITE 01's detector lands.
2. Opening position-along-wall error (in cm) once the consensus
   stabilizes its opening center coordinate.
3. Multi-plant corpus: 3+ additional plantas with v1 expected
   models. Tightens the metric distributions.
4. Synthetic ground truth: `expected_model.json` -> render PDF
   -> pipeline -> compare. Catches detector overfit.
5. CI integration: wire `tools.fidelity` into
   `.github/workflows/quality_gates.yml` (paired with the
   `feature/quality-gates-ci-workflow` PR).

---

## See also

- `ground_truth/schema/expected_model.schema.json` — the contract
- `ground_truth/planta_74/expected_model.json` — the live truth
- `tools/fidelity/compare_generated_to_expected.py` — the engine
- `tests/test_fidelity_engine.py` — 21 unit tests
- `tools/micro_truth_gate.py` — per-room subset (still useful)
- `tests/test_planta_74_truth_gate.py` — count baseline (different role)
- `docs/ground_truth_references.md` — public datasets survey
- `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`
  — FP-012, the bug the v1 gate currently surfaces
