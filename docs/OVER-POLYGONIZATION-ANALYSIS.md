# Over-polygonization analysis — planta_74.pdf

**Run:** `runs/overpoly_audit/` on commit `f2b896c` (branch `fix/dedup-colinear-planta74`).
**Input:** `planta_74.pdf`
**Tool:** `python main.py extract planta_74.pdf --out runs/overpoly_audit`
**Analyzer:** `analyze_overpoly.py` (this worktree).
**Goal:** characterize the 48 rooms produced post-F3-hardening, identify the over-polygonization
patterns still leaking through, and recommend a geometric filter reusable by Agent 13
(branch `feat/topology-sliver-filter`).

**Scope:** analysis and threshold recommendation only. No filter implemented here.

---

## 1. Extraction result (baseline)

- `rooms`: 48
- `room_topology_check.json`:
  - `status=pass`: 48/48
  - `status=fail`: 0
  - `nested_pairs`: `[]` (no nested polygons — topology check is passing but is clearly
    under-constrained; it does not catch slivers or colinear fragmentation).
  - `min_area_threshold`: 525.33 (so several rooms below 900 pass only because this threshold
    is too permissive).
- `scores`: `geometry=0.25`, `topology=1.0`, `rooms=0.89`.
- `bounds` page 0: x=[121.0, 1105.4], y=[288.1, 885.0] → 984 × 597 px (≈100 dpi render).

The topology pass rate is misleading: every sliver and thin strip passes. The 48-room count
is itself the anomaly — visual inspection confirms ~16-20 legitimate rooms are expected.

## 2. Geometric distributions

| Metric        | min   | median | max    |
| :------------ | ----: | -----: | -----: |
| area (px²)    | 739   | 3401   | 40591  |
| aspect_ratio  | 1.10  | 3.20   | 43.87  |
| compactness   | 0.036 | 0.442  | 0.783  |
| vertices      | 3     | 4      | 11     |

### Vertex histogram (striking)

| vertices | count |
| -------: | ----: |
| 3        | **21** |
| 4        | 15    |
| 5        | 6     |
| 6        | 1     |
| 7        | 2     |
| 8        | 1     |
| 9        | 1     |
| 11       | 1     |

**21 of 48 rooms are 3-vertex triangles.** A well-formed floor plan contains almost zero
legitimate triangular rooms; the bulk of these are slivers created by colinear walls that
were not fully deduplicated.

## 3. Category classification

Rule of thumb used by `categorize()` in `analyze_overpoly.py`:

- `sliver_triangle`: `vertices == 3 AND (area < 2000 OR aspect > 3)`
- `small_triangle`: `vertices == 3` but compact enough to be ambiguous (aspect ≤ 2.5, compact ≥ 0.4)
- `thin_strip`: `vertices == 4 AND aspect > 5`
- `degenerate`: `compactness < 0.10` (catches anything slipping through above)
- `tiny`: `area < 500`
- `borderline`: `500 ≤ area < 1500` and no other flag
- `legitimate`: everything else

| Category           | count | rooms |
| :----------------- | ----: | :---- |
| legitimate         | 20    | 1, 6, 8, 9, 10, 20, 21, 23, 24, 25, 30, 31, 32, 33, 34, 40, 41, 42, 44, 45 |
| sliver_triangle    | 16    | 3, 4, 7, 11, 12, 14, 15, 16, 18, 19, 36, 37, 38, 39, 43, 46 |
| thin_strip         | 7     | 2, 5, 26, 28, 29, 35, 47 |
| small_triangle     | 5     | 13, 17, 22, 27, 48 |
| tiny / borderline  | 0     | — |

**Legitimacy caveats:**

- `room-6` (labelled *legitimate*) has aspect=7.83, compact=0.258. Area 23383 px². Likely
  either (a) a legitimate long corridor, or (b) a fat residue of colinear fragmentation
  across the R2/R3/R4/R5 band. The `combo_FINAL` filter below drops it; `combo_FINAL_v3`
  keeps it via an `area ≥ 5000` escape hatch. **Action for Agent 13:** surface `room-6` in
  the filter audit log so the human decides.
- `room-2` is the textbook adversarial example: area=24858 (largest thin_strip), aspect=12.9,
  compact=0.10 — a long diagonal parallelogram that looks "big enough to be real" but is
  actually the top band of the colinear artefact chain R2→R3→R4→R5.
- `small_triangle` (R13, R17, R22, R27, R48): triangles with aspect ≤ 2.5 and compact
  ≥ 0.42. Geometrically "decent" but spatially they are colinear-wall artefacts between
  legitimate rooms. Visual inspection (see `overlay_audited.png`) confirms none are real.

## 4. Top / bottom rooms by area

### Top 10 (area desc)

| room     | area   | verts | perim | bbox_w | bbox_h | aspect | compact | category        |
| :------- | -----: | ----: | ----: | -----: | -----: | -----: | ------: | :-------------- |
| room-41  | 40591  | 9     | 993   | 341    | 184    | 1.85   | 0.518   | legitimate      |
| room-9   | 40376  | 7     | 1029  | 418    | 130    | 3.22   | 0.479   | legitimate      |
| room-45  | 35967  | 11    | 888   | 333    | 134    | 2.48   | 0.573   | legitimate      |
| room-2   | 24858  | 4     | 1741  | 838    | 65     | 12.90  | 0.103   | **thin_strip**  |
| room-6   | 23383  | 5     | 1068  | 507    | 65     | 7.83   | 0.258   | legitimate (?)  |
| room-10  | 21167  | 5     | 782   | 319    | 75     | 4.27   | 0.435   | legitimate      |
| room-23  | 19719  | 7     | 771   | 319    | 68     | 4.70   | 0.417   | legitimate      |
| room-8   | 18097  | 5     | 553   | 135    | 171    | 1.27   | 0.744   | legitimate      |
| room-3   | 16058  | 3     | 1243  | 597    | 54     | 11.05  | 0.131   | **sliver_triangle** |
| room-40  | 16055  | 4     | 586   | 221    | 78     | 2.82   | 0.588   | legitimate      |

Key insight: **area alone is not a filter**. `room-3` (16k px²) is a huge colinear sliver,
and `room-2` (25k px²) is a huge thin strip. Only compactness + aspect catch them.

### Bottom 10 (area asc)

| room     | area  | verts | perim | aspect | compact | category        |
| :------- | ----: | ----: | ----: | -----: | ------: | :-------------- |
| room-11  | 739   | 3     | 194   | 5.54   | 0.247   | sliver_triangle |
| room-46  | 808   | 3     | 134   | 1.35   | 0.565   | sliver_triangle |
| room-35  | 940   | 4     | 234   | 6.18   | 0.216   | thin_strip      |
| room-43  | 946   | 3     | 235   | 3.19   | 0.216   | sliver_triangle |
| room-12  | 959   | 3     | 164   | 2.19   | 0.449   | sliver_triangle |
| room-37  | 1114  | 3     | 222   | 5.12   | 0.283   | sliver_triangle |
| room-29  | 1148  | 4     | 471   | 22.43  | 0.065   | thin_strip      |
| room-16  | 1158  | 3     | 638   | 43.87  | 0.036   | sliver_triangle |
| room-18  | 1253  | 3     | 169   | 1.42   | 0.552   | sliver_triangle |
| room-14  | 1285  | 3     | 177   | 2.01   | 0.514   | sliver_triangle |

## 5. Threshold sweep

Full data: `runs/overpoly_audit/threshold_sweep.json`.

| # | scenario                      | keeps | filter                                                                 |
| -: | :--------------------------- | ----: | :--------------------------------------------------------------------- |
| 0 | baseline                       | 48 | (no filter)                                                            |
| 1 | `area ≥ 500`                   | 48 | area alone never fires at 500                                          |
| 2 | `area ≥ 1000`                  | 43 | kills 5 of the smallest                                                |
| 3 | `area ≥ 1500`                  | 37 | too permissive                                                         |
| 4 | `area ≥ 2000`                  | 31 | still keeps huge triangles (R3, R4) and thin strips (R2)               |
| 5 | `vertices ≥ 4`                 | 27 | drops all 21 triangles (incl. 5 small_triangle candidates)             |
| 6 | drop `(v==3 AND area<1500)`    | 40 | drops 8 triangles                                                      |
| 7 | drop `aspect > 5`              | 31 | drops thin strips + wide triangles + R6 corridor                        |
| 8 | drop `compactness < 0.10`      | 43 | only kills the most extreme                                            |
| 9 | drop `compactness < 0.15`      | 37 | more aggressive; still keeps 16 slivers                                |
| 10 | `area≥1000 AND (v≥4 OR area≥2000) AND compact≥0.15 AND aspect≤5` | 24 | "strict" — keeps small_triangles wrongly |
| 11 | `area≥1000 AND (v≥4 OR compact≥0.25) AND aspect≤6` | 28 | still too loose |
| 12 | `area≥1500 AND v≥4 AND compact≥0.20 AND aspect≤6` | **19** | **RECOMMENDED** |
| 13 | `area≥1500 AND v≥4 AND compact≥0.25 AND aspect≤6` | 19 | identical keeps to #12 |
| 14 | `v≥4 AND compact≥0.20 AND aspect≤6` | 19 | same keeps — area gate is not binding at this point |
| 15 | `area≥2000 AND v≥4 AND compact≥0.25 AND aspect≤5` | 18 | tighter; drops room-6 (corridor) and room-31 (small bath) |
| 16 | `(v≥4 AND aspect≤5 AND compact≥0.20) OR (area≥5000 AND compact≥0.25)` | 20 | matches the 20-legitimate set but ad-hoc |
| 17 | `(recommended #12) OR (area≥5000 AND compact≥0.20)` | 21 | escape hatch lets R5 back in — **reject** |

## 6. Recommendation for Agent 13

**Primary filter:**

```
KEEP room if:
  area >= 1500            (px², ~15 cm² @ 100 dpi)
  AND vertices >= 4
  AND compactness >= 0.20 (4·π·A / P²)
  AND aspect_ratio <= 6   (max(bbox_w, bbox_h) / min(...))
```

This keeps **19 of 48** rooms on `planta_74.pdf`, matching the set of rooms that visual
inspection flags as plausible. It drops every `sliver_triangle`, every `thin_strip`, every
`small_triangle` (which visual audit confirms are all colinear-wall artefacts), and one
borderline corridor (`room-6`).

### Surviving rooms (19)

`room-1, room-8, room-9, room-10, room-20, room-21, room-23, room-24, room-25, room-30,
room-31, room-32, room-33, room-34, room-40, room-41, room-42, room-44, room-45`

### Borderline cases to surface in the filter audit log

| room     | area  | verts | aspect | compact | why borderline                                                   |
| :------- | ----: | ----: | -----: | ------: | :--------------------------------------------------------------- |
| room-6   | 23383 | 5     | 7.83   | 0.258   | may be a real long corridor (dropped because aspect > 6)         |
| room-31  | 1924  | 4     | 1.10   | 0.783   | small bath / closet, very compact (dropped if area threshold≥2000) |
| room-21  | 2657  | 4     | 1.55   | 0.754   | small bath above room-31, very compact                           |
| room-34  | 3618  | 5     | 4.39   | 0.340   | passes all gates but aspect-to-compactness ratio is unusual      |

### Edge cases to document

- **Closet 2 × 3 m at 100 dpi** → ~7.9 × 11.8 px for a 1:100 plan, but this plan renders
  at roughly 100 dpi for 984 × 597 px covering the whole floor, so 2×3 m rooms are
  ~60×90 px = ~5400 px². An `area >= 1500` floor is safely below even a small lavatory.
- **True triangular cutouts (chamfered corners, stairwells)** legitimately produce 3-vertex
  polygons. Strict `vertices >= 4` would reject them. Since planta_74 has none, this is
  safe here but Agent 13 should confirm on other fixtures before merging.
- **Long corridors** (aspect 6-12, compactness 0.15-0.30) are architecturally real and
  the current filter drops them. If corridors matter downstream, widen to `aspect <= 10`
  AND add a dedicated "corridor" category that bypasses the v≥4 clause, at the cost of
  letting `room-2` back in. Safer path: let Agent 13's filter write dropped rooms to
  `room_filter_audit.json` so the human can whitelist specific IDs.

### Implementation notes for Agent 13

1. Compute `compactness` as `4·π·area / perimeter²` — not `area / perimeter²` (scale-free
   is the point).
2. `aspect_ratio` = `max(bbox_w, bbox_h) / max(min(bbox_w, bbox_h), epsilon)` with
   `epsilon=1e-6`.
3. Log dropped rooms with all four metrics + the dominant drop reason
   (`reason: "aspect_ratio > 6"` etc.) so the audit PR can show a diff of
   48 → 19 with justifications. Do NOT silently delete.
4. Do NOT apply this filter upstream of `room_topology_check.json` — the topology
   pass rate is currently 48/48 and will become 19/19, which is fine, but the filter
   must run after topology assessment so both artefact lists survive.
5. `nested_pairs` is empty on this fixture, so nested detection is **not** part of the
   filter. Keep it as a future signal for other plans.

## 7. Artefacts produced

- `runs/overpoly_audit/observed_model.json` — extractor output (48 rooms).
- `runs/overpoly_audit/room_topology_check.json` — 48/48 pass, nested_pairs=[].
- `runs/overpoly_audit/per_room_metrics.json` — per-room geometry + category (this analysis).
- `runs/overpoly_audit/threshold_sweep.json` — full sweep of 25 scenarios.
- `runs/overpoly_audit/over_polygon_categorized.png` — overlay painted by category
  (green=legitimate, red=sliver, orange=thin_strip, grey=small_triangle).
- `analyze_overpoly.py` — reproducible script; re-run with
  `.venv/Scripts/python.exe analyze_overpoly.py`.

## 8. Caveats

- **Single fixture.** All thresholds were tuned against `planta_74.pdf`. Agent 13 must
  sanity-check at least one other plan before merging.
- **No ground truth.** The "20 legitimate" baseline is visual inspection, not an
  annotated set. Room 6 could legitimately be a corridor; rooms 2-5 are too fragmented
  to have ground truth without re-segmenting the source PDF.
- **Topology check under-constrained.** The current `room_topology_check.json` is
  effectively a smoke test (`min_area_threshold=525`). Widening it to include aspect
  and compactness checks is out of scope here but worth filing as follow-up.
