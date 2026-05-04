# Window Detector Validation

> Companion to `tools/extract_openings_vector.py` window detection.
> Records what the detector does, what shipped in this PR, and the
> honest finding from running it against `planta_74.pdf`.

## What the detector does

`tools/extract_openings_vector.py` now emits openings of **two
kinds**:

| Kind | Detector | Geometry origin | Heuristic |
|---|---|---|---|
| `door` | `_arc_candidates` + `_dedupe_arcs` (existing) | `svg_arc` | stroked path, bbox aspect 0.4..2.5, side 15..100 pt, ≥ 1 cubic Bezier |
| `window` | `_window_candidates` (new) | `svg_segments` | stroked path, bbox aspect ≥ 3, long side 25..250 pt, short side ≤ thickness × 1.5, center within thickness × 0.6 of a wall, **and** long side < 70 % of that wall's length |

Doors run first; windows are filtered against existing arc bboxes
(≥ 50 % overlap with an arc → drop the window).

## Result on planta_74.pdf

```
[ok] 12 doors + 0 windows detected from planta_74.pdf
```

12 doors unchanged (same ids, walls, widths, confidences as before
this PR). **Zero windows.** The metadata records this honestly:

```json
{
  "openings_extractor": "vector_arc_window_v1",
  "svg_arc_opening_count": 12,
  "svg_window_opening_count": 0
}
```

## Why zero windows on this PDF

The first iteration of the heuristic produced **20 candidates**.
Inspection showed that all 20 had `window_width / wall_length` ≈
1.02 — they were the wall's own **stroked outline**, not glazing
lines. Concretely:

| | First pass (loose) | Final (with wall-length-ratio guard) |
|---|---:|---:|
| Window candidates emitted | 20 | 0 |
| All on a unique wall | yes (each "window" matched its wall's outline) | n/a |
| Mean width / wall length | 1.02 | n/a |

The fix: any candidate whose long side is ≥ 70 % of the matched
wall's length is dropped — almost certainly the wall's own stroked
outline, not an opening drawn inside the wall band. After this
guard, planta_74 emits zero windows.

This is the **honest** output. Per
`docs/learning/lessons_learned.md` and the memory entry
`feedback_nao_fabricar_sem_medidas` — extraction must report what
the PDF actually drew, not what we wished it had drawn. Windows in
this particular PDF are not authored as separate vector primitives
distinguishable from the wall outlines; they are baked into the
same drawing context as the walls. Any "window detection" we tried
to force in this PDF would be fabrication.

## What this means for the .skp

The `.skp` file produced by `tools/consume_consensus.rb` is
**unchanged** — it still has 33 walls, 12 door openings, 0 windows.
The visual on disk is identical to PR #14's snapshot. The only
thing that changed is the JSON contract: future PDFs that DO author
windows as elongated stroked paths will get them detected
automatically.

The next-priority item to actually open vão (door cuts) on the
.skp is `feature/skp-carve-openings`, which is gated on explicit
user authorization per `CLAUDE.md` §1 hard rule #4.

## What changed in this PR

- `tools/extract_openings_vector.py`:
  - `WindowCandidate` dataclass, mirroring `ArcCandidate`'s shape.
  - `_is_window_shape(bbox, n_cubic, thickness)` — pure classifier.
  - `_window_candidates(page, region, thickness)` — page scanner.
  - `_window_to_wall(window, walls, thickness)` — projection +
    distance + wall-length-ratio guards.
  - `_window_overlaps_arc(window, arc_bboxes)` — dedupe vs doors.
  - `_window_confidence(window, dist, thickness)` — confidence
    formula, separate from the door formula (windows have no
    hinge/swing).
  - `_emit_window_opening(window, wall, proj, dist, thickness, idx)`
    — opening dict construction.
  - `detect_openings()` — now runs both door and window passes.
  - CLI prints both counts and lists each kind separately.
  - `metadata.openings_extractor` = `"vector_arc_window_v1"`,
    `metadata.svg_window_opening_count` added.

- `tests/test_window_detector.py` — 20 unit tests on the pure
  geometry helpers (no PDF needed).

## Trade-offs and follow-ups

- **The aspect filter (≥ 3) replaces the no-cubic filter.**
  PDF generators routinely emit cubic Bezier primitives even for
  straight lines. Filtering by `n_cubic == 0` discarded ~600
  candidates on planta_74. The aspect filter is what discriminates
  windows from door arcs (which are square-ish, 0.4..2.5).
- **The wall-length-ratio guard (< 70 %) is the new key invariant.**
  Wall outlines run the full length of the wall; real openings
  occupy only a fraction. This guard is the reason planta_74 drops
  from 20 false positives to 0 emissions.
- **No room_a / room_b assignment.** Windows, like doors, leave
  room-side determination as a downstream concern.
- **Constants are tuned for 1:50 / 1:100 plantas with
  `wall_thickness_pts ≈ 5.4`.** Other scales may need a sweep.
- **Future PR: alternative author idioms.** Some PDFs author
  windows as filled paths (the dark glazing rectangle), not stroked
  outlines. A second-pass detector for filled-path windows could
  ship later if encountered. Out of scope here.

## Reproducing this validation

```bash
# Re-run window detection with the updated detector (writes
# back to runs/vector/consensus_model.json):
.venv/Scripts/python.exe -m tools.extract_openings_vector \
    planta_74.pdf \
    --consensus runs/vector/consensus_model.json \
    --mode replace

# Confirm the smoke harness still passes end-to-end:
.venv/Scripts/python.exe scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --skip-skp
```

Expected output: `12 doors + 0 windows detected`, smoke verdict PASS.
