# Vector openings extractor — v0

Closes the open invariant in `tools/build_vector_consensus.py:299`:

```python
"openings": [],   # filled in by a downstream gap-detection pass
```

…by adding `tools/extract_openings_vector.py`, an arc-based detector
that runs as a post-step on the consensus produced by the vector
pipeline. With this, `consensus_model.json` for `planta_74.pdf` now
carries 12 doors instead of 0 — meaning `consume_consensus.rb` can
finally carve openings into the .skp instead of leaving every wall
full-height through every doorway.

---

## Pipeline (canonical order for vectorial PDFs)

```bash
# 1. walls + soft barriers from filled paths
python -m tools.build_vector_consensus planta_74.pdf \
       --out runs/vector/consensus_model.json

# 2. text labels (Cozinha, Suíte 01, ...) from the PDF
python -m tools.extract_room_labels planta_74.pdf \
       --out runs/vector/labels.json

# 3. rooms by flood-fill seeded on label positions
python -m tools.rooms_from_seeds runs/vector/consensus_model.json \
       runs/vector/labels.json

# 4. NEW: door openings from PDF arc paths
python -m tools.extract_openings_vector planta_74.pdf \
       --consensus runs/vector/consensus_model.json --mode replace
```

`--mode replace` clears any pre-existing openings (legacy
`door_NNN`-style bridges from `tools/polygonize_rooms.py`) before
writing the svg_arc set. Use `--mode merge` (default) to *append* svg_arc
openings to whatever's already there, useful when both extractors are
desired side-by-side.

---

## Algorithm (v0)

Brazilian sales-brochure plantas draw doors as TWO stroked-only paths:
a leaf rectangle and a swing arc. The swing arc has 4–8 segments,
of which 1–2 are cubic Beziers. The wall extractor in
`build_vector_consensus.py` deliberately filters out stroked-only paths
(to keep walls clean), so arcs survive untouched in the page object
list.

Detection:

1. **Iterate every PDF page object** inside `consensus.planta_region`.
2. **Filter** to stroked-only paths whose bbox is 15–100 pts on each
   side, aspect 0.4–2.5, and contain ≥ 1 cubic Bezier segment. At
   typical 1:50/1:100 architectural scales, residential doors (~80 cm)
   project to ~30–60 PDF pts.
3. **Dedupe** candidates whose bboxes overlap > 50% of the smaller
   one's area (door leaf + swing arc collapse to one entry; the
   richer-in-cubic-segments candidate wins).
4. **Project** each arc's four bbox corners onto every wall. The
   minimum-distance corner is the hinge; its projection on the wall is
   the opening center. Match accepted only if hinge-to-wall ≤
   `wall_thickness * 1.5` (~8 pts at the planta_74 scale).
5. **Synthesize** an opening dict matching schema 1.0.0:

   ```jsonc
   {
     "id":               "o002",
     "center":           [321.196, 627.937],   // PDF pts on wall centerline
     "chord_pt":         [305.5, 658.4],       // arc bbox center
     "kind":             "door",
     "geometry_origin":  "svg_arc",
     "confidence":       0.80,                  // 0..1
     "hinge_side":       "left",                // wall start->end normal
     "hinge_corner_pt":  [290.4, 654.7],
     "swing_deg":        90,
     "wall_id":          "w006",
     "opening_width_pts": 61.1,                 // arc envelope long side
     "arc_bbox_pts":     [...],
     "arc_n_seg":        8,
     "arc_n_cubic":      2,
     "wall_dist_pts":    2.44
   }
   ```

Confidence = `0.4*aspect_score + 0.3*has_cubic + 0.3*(1 - dist/threshold)`.

---

## What this v0 does NOT do (yet)

- **No room_a / room_b assignment.** Schema 1.0.0 wants the two rooms
  on either side of each opening. Current output leaves those out;
  consume_consensus.rb falls back to "carve void" mode without room
  context.
- **No swing direction.** `swing_deg: 90` is hardcoded. The arc's
  Bezier control points encode the actual sweep angle; that's a
  follow-up parse.
- **No window detection.** Windows aren't drawn as arcs — they appear
  as thin parallel double-line stroked paths along walls. Detection
  needs a different filter (parallel-path pairs near walls).
- **No double doors.** Two adjacent door arcs (e.g. closet) get
  detected as separate openings; whether to fuse them is a
  schema/Ruby-side decision.

---

## Verification

`tools/render_openings_overlay.py` rasterizes the source PDF cropped to
the planta region and overlays detected openings as orange circles
(centers projected on walls), green dots (hinge corners), and a green
line connecting them.

```bash
python -m tools.render_openings_overlay planta_74.pdf \
       --consensus runs/vector/consensus_model.json \
       --out runs/vector/openings_overlay.png --scale 4
```

The overlay is auto-registered in `runs/png_history/manifest.jsonl`
(kind `openings_overlay`) so the validator can pick it up later.

For `planta_74.pdf`:
- 18 raw arc candidates inside the planta region
- 12 after dedup (leaf+arc pairs collapsed)
- 12 successfully matched to a wall (none dropped for distance)
- Confidences: 0.67 .. 0.92, mean 0.80

12 doors aligns with manual count:
entrada + 2× suíte + 2× banho + lavabo + cozinha + AS + 2× terraço.

---

## Files added

- `tools/extract_openings_vector.py` — detector + `enrich_consensus` helper
- `tools/render_openings_overlay.py` — visual sanity check
- this document

## Files modified

- `tools/build_vector_consensus.py` — adds optional `--detect-openings`
  flag (off by default; canonical pipeline runs detection as a
  separate post-step so the rooms pass can complete first).

---

## Memory references

- `project_pipeline_v7_vector_first` — vector-first wall extraction
  rationale.
- `project_consensus_model_schema` — schema 1.0.0 fields including
  the opening shape this implementation targets.
- `project_porta_como_opening_parametrico` — parametric opening model
  (offset_m on host wall) — v0 emits `wall_id` + `center` which is
  enough for `consume_consensus.rb` to compute that offset.
- `feedback_nao_fabricar_sem_medidas` — extractor only emits where the
  PDF actually drew an arc; nothing is fabricated.
