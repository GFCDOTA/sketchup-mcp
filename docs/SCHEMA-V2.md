# observed_model.json schema v2.2.0 (draft)

The contract between the Python pipeline (`plan-extract-v2`) and downstream
consumers — primarily the Ruby/SketchUp bridge (ROADMAP Fase 6), plus QA
tooling and regression tests. This document is the human-readable complement
to `docs/schema/observed_model.schema.json` (JSON Schema Draft 2020-12).

The schema is **append-only**. Fields evolve forward by adding new optional
keys; existing keys do not change semantics within a minor version. Major
bumps are reserved for breaking changes (none yet).

Field order below follows the physical output order of `build_observed_model`
+ `_run_pipeline_from_walls` in `model/pipeline.py`.

## schema_version
`"2.2.0"` — bump from 2.1.0 to reflect the `metadata.openings_refinement`
audit trail (SVG path) and the formal documentation of the `svg` source_type.
Semantic-versioned string. Consumers SHOULD pin to the major component (`2`).

## run_id
Hex UUID (`uuid4().hex`). Identifies this run for telemetry / log correlation
only. Not a content hash — see `metadata.topology_snapshot_sha256` for
content-stable identifiers.

## source
Provenance of the input document.

| field | type | notes |
|---|---|---|
| `filename` | string \| null | Original filename. `null` when invoked with in-memory raster (debug). |
| `source_type` | `"pdf"` \| `"svg"` \| `"raster"` | Ingest path taken. See below. |
| `page_count` | int | >= 1. |
| `sha256` | string \| null | Hex SHA-256 of the raw input bytes. `null` for `raster` source_type. |
| `viewbox_width` | number | SVG only. Root `<svg>` viewBox width in user-units. |
| `viewbox_height` | number | SVG only. Root `<svg>` viewBox height. |
| `stroke_width_median` | number | SVG only. Median stroke-width seen in accepted paths. Seeds opening thresholds in `detect_openings`. |
| `stroke_width_samples` | number[] | SVG only. Distinct stroke-width values observed. |

`source_type` drives which fields of `metadata` will be present:
- `pdf`: raster pipeline (`run_pdf_pipeline`). No `main_component`, no `openings_refinement`.
- `svg`: vector pipeline (`run_svg_pipeline`). Adds `main_component` and `openings_refinement`.
- `raster`: debug-only entry (`run_raster_pipeline`) for synthetic numpy arrays.

## bounds
Axis-aligned per-page bbox, computed from the final *split* walls (not the
raw candidates). Shape:

```json
{"pages": [{"page_index": 0, "min_x": 69.204, "min_y": 193.528, "max_x": 734.421, "max_y": 583.225}]}
```

One entry per page with at least one wall.

## roi
Per-page ROI detection result (`detect_architectural_roi`). Raster path only.
Empty list (`[]`) on the SVG path and on synthetic raster inputs where ROI
was skipped (e.g. `clean_input_skip_roi`).

```json
{"applied": true, "bbox": {"min_x": 46, "min_y": 252, "max_x": 1159, "max_y": 916},
 "fallback_reason": null, "component_pixel_count": 88137,
 "component_bbox_area": 610644, "component_count": 1712}
```

`fallback_reason` when `applied=false`: `"empty_image"`, `"no_components"`,
`"no_dominant_component"`, or `"clean_input_skip_roi"`.

## walls
Topology-split wall segments. Each segment references its pre-split parent
via `parent_wall_id`.

```json
{"wall_id": "segment-2", "parent_wall_id": "wall-189", "page_index": 0,
 "start": [70.671, 193.528], "end": [173.825, 208.14],
 "thickness": 6.25, "orientation": "horizontal",
 "source": "svg", "confidence": 1.0}
```

`orientation`: `"horizontal"` | `"vertical"` only — diagonals are not
currently represented in this contract (CLAUDE.md §4 discusses this).

`source`: the producer of the wall. Known values: `"hough_horizontal"`,
`"hough_vertical"` (raster), `"svg"` (vector ingest), `"opening_bridge"`
(ghost wall inserted by `detect_openings` to close a door gap).
**Open-ended**: new detectors (LSD, CubiCasa5K) may add new strings.

`confidence`: `[0, 1]`. Opening bridges use `0.5`; SVG walls `1.0`; raster
walls inherit the Hough retention score.

## junctions
Graph nodes derived by `build_topology`.

```json
{"junction_id": "junction-1", "point": [69.204, 583.171],
 "degree": 3, "kind": "tee"}
```

`kind` is degree-derived:
- `degree=1` → `"end"`
- `degree=2` → `"pass_through"`
- `degree=3` → `"tee"`
- `degree>=4` → `"cross"`

## rooms
Polygons from `shapely.polygonize` over the split-wall graph. **Empty is a
valid observation** (CLAUDE.md invariant #1): consumers MUST handle `rooms=[]`
without substituting the bbox.

```json
{"room_id": "room-1",
 "polygon": [[173.825, 208.14], [...], ...],
 "area": 11297.12,
 "centroid": [132.88, 267.32]}
```

The ring is NOT guaranteed to be explicitly closed (last vertex may or may
not repeat the first). Consumers SHOULD re-close defensively.

## scores
**Observational**, not quality gates (CLAUDE.md invariant #6).

| field | formula | range |
|---|---|---|
| `geometry` | raster: `walls_kept / candidates_in`; svg: `1.0` | [0, 1] |
| `topology` | `(intra_page_connectivity_ratio + 1/max_components_within_page) / 2` | [0, 1] |
| `rooms` | `0.5 + rooms_count / edge_count` clamped to 1.0 | [0, 1] |

Consumers SHOULD NOT use these as pass/fail thresholds — they reflect what the
extractor observed, not ground truth.

## metadata
Required keys: `rooms_detected`, `topology_quality`, `connectivity`,
`warnings`. Optional keys appear only on specific pipeline paths.

### metadata.topology_quality
`"good"` if `scores.topology >= 0.8`, `"fair"` if `>= 0.5`, else `"poor"`.

### metadata.connectivity
Graph metrics from `ConnectivityReport.to_dict()`:

```json
{"node_count": 75, "edge_count": 124, "component_count": 1,
 "component_sizes": [75], "largest_component_ratio": 1.0,
 "rooms_detected": 23, "page_count": 1,
 "max_components_within_page": 1,
 "min_intra_page_connectivity_ratio": 1.0,
 "orphan_component_count": 0, "orphan_node_count": 0}
```

### metadata.warnings
Duplicated from the top-level `warnings` array for backward compat.

### metadata.main_component (v2.2.0 — SVG only, optional)

Result of `topology.main_component_filter.select_main_component`, which
drops walls outside the dominant architectural component (carimbo, legenda,
mini-plan, rodape on SVG).

```json
{"component_count": 6, "selected_wall_count": 630,
 "second_wall_count": 336, "selected_bbox_area": 276985.31,
 "second_bbox_area": 250119.63, "dominance_applied": true,
 "walls_dropped": 393}
```

`dominance_applied=false` means the ratio gate did not trip and no walls
were dropped (defensive fallback when ambiguous).

### metadata.openings_refinement (v2.2.0 new — SVG only, optional)

Audit trail of the four post-detection filters applied to openings in the
SVG path. Shape matches the four reports in `openings/pruning.py`:

```json
{
  "prune_orphan": {"input_count": 68, "dropped_orphan": 28, "kept": 40},
  "min_width": {"input_count": 40, "dropped_below_min": 3, "kept": 37, "threshold_px": 21.875},
  "dedup_collinear": {"input_count": 37, "merged": 11, "kept": 26, "gap_threshold_px": 25.0},
  "postfilter_roomless": {"input_count": 26, "dropped_roomless": 2, "kept": 24, "min_area": 976.562}
}
```

Invariants: `input_count(stage_i+1) == kept(stage_i)`.

### metadata.topology_snapshot_sha256 (optional)

SHA-256 hex of the canonicalized `(walls, junctions)` tuple (see
`topology.service`). Stable across cosmetic `run_id` changes and used by
regression tests to detect topology drift. Missing only when the pipeline
fails before topology construction.

## warnings
Top-level array of structured warning codes. Mirror of `metadata.warnings`.
Non-exhaustive list used today:
- `"no_wall_candidates"`
- `"all_candidates_filtered"`
- `"walls_disconnected"`
- `"many_orphan_components"` (>= 5 orphan components)
- `"rooms_not_detected"`
- `"roi_fallback_used"`
- `"no_walls"`

Consumers MUST treat this as open-ended.

## openings
Doors, passages and windows, each a colinear gap between two walls.

```json
{"opening_id": "opening-2", "page_index": 0, "orientation": "horizontal",
 "center": [199.351, 219.286], "width": 46.075,
 "wall_a": "wall-197", "wall_b": "wall-451", "kind": "door"}
```

`kind`: `"door"` | `"window"` | `"passage"`.
- `"window"`: center falls inside (expanded) bbox of a passed-in peitoril.
- `"passage"`: `width > door_max` threshold.
- `"door"`: default.

**Known aliasing**: `wall_a`/`wall_b` refer to pre-split wall ids from the
`detect_openings` stage. After topology splits a wall, the referenced id may
not appear in `walls[].wall_id`; it may match a `parent_wall_id` instead.
Consumers looking up walls by opening endpoint SHOULD check both
`wall_id` and `parent_wall_id`.

## peitoris
Pass-through: window-sill hints provided by the caller, used by
`detect_openings` to reclassify openings as `"window"`. The pipeline does
not detect peitoris itself.

Minimal shape (only `bbox` is read):

```json
[{"bbox": [x1, y1, x2, y2]}]
```

Extra keys are preserved unchanged.

## Required vs optional

**Top-level required** (always present):
- `schema_version`, `run_id`, `source`, `walls`, `rooms`, `junctions`,
  `openings`, `metadata`, `bounds`, `scores`, `warnings`, `roi`, `peitoris`

**Within `metadata`, required**:
- `rooms_detected`, `topology_quality`, `connectivity`, `warnings`

**Within `metadata`, optional** (path-dependent):
- `main_component` — present only on the SVG path (after `select_main_component`)
- `openings_refinement` — present only on the SVG path (v2.2.0+)
- `topology_snapshot_sha256` — present on both paths when topology built successfully

## Deprecations
None at v2.2.0.

Historical note (not a deprecation): the top-level `warnings` array mirrors
`metadata.warnings` for backward compatibility. Both are kept.

## Compatibility matrix

| source_type | metadata.main_component | metadata.openings_refinement | roi |
|---|---|---|---|
| `pdf` | absent | absent | one entry per page |
| `svg` | present | present | `[]` |
| `raster` | absent | absent | one entry (`applied` may be `false`) |

## Validation

A formal JSON Schema is in `docs/schema/observed_model.schema.json`
(Draft 2020-12). The CI test `tests/test_schema_v2.py` validates real pipeline
outputs against it. Install `jsonschema>=4.0` (already in `requirements.txt`)
to run the validation locally:

```bash
.venv/Scripts/python.exe -m pytest tests/test_schema_v2.py -v
```
