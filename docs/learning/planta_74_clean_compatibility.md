# `planta_74_clean.pdf` is rasterized — vector pipeline incompatibility

**Date:** 2026-05-04
**Branch where this was diagnosed:** `skp/investigate-planta-74-clean`
**Diagnostic script:** `scripts/investigation/planta_74_clean_diff.py`

## Symptom

Running step 1 of the documented pipeline (`OVERVIEW.md §4.4`) on
`planta_74_clean.pdf` returned a generic error:

```
$ python -m tools.build_vector_consensus planta_74_clean.pdf --out runs/v/c.json --detect-openings
[err] no wall paths detected
```

while the same command on `planta_74.pdf` succeeded with `[ok] 33 walls,
12 openings`. The error message was misleading — it implied an extractor
filter problem, but the real cause was different.

## Root cause (path-level diff)

`scripts/investigation/planta_74_clean_diff.py` walks every `path` object
on page 1 of both PDFs via `pypdfium2` (the same library
`tools/build_vector_consensus.py` uses) and reports counts:

| Inventory metric | `planta_74.pdf` | `planta_74_clean.pdf` |
|---|---:|---:|
| Page size (PDF points) | 595 × 842 (A4) | **856 × 1212** |
| Total path objects | **1454** | **0** |
| Filled-only paths | 149 | 0 |
| Stroked-only paths | 1305 | 0 |
| Walls extracted by `_identify_wall_paths` | 33 (median thickness 5.4 pt) | 0 |

The "clean" PDF has **zero vector path objects**. It is almost certainly
a "print to PDF" of a rasterized image (or a scan), wrapping a single
bitmap into a PDF page. There is nothing for the vector extractor to
read — by design.

Visual confirmation in `runs/planta_74_clean_debug/`:

* `paths_original.png` — every bbox of every path drawn at its true PDF
  coordinates: 1454 rectangles, walls in blue, structure in orange,
  full apartment outline visible.
* `paths_clean.png` — empty canvas.

## Decision

**No fallback in the vector pipeline.** Adding a raster fallback inside
`tools/build_vector_consensus.py` would couple two pipelines that
intentionally live separate (`ingest/`, `roi/`, `extract/`,
`classify/`, `topology/`, `model/` for raster — see `OVERVIEW.md §2.1`).
The raster pipeline is reachable via `python main.py extract <pdf>`.

**Improvement:** make `build_vector_consensus.py` surface the diagnosis
inline so a future operator doesn't have to re-do this investigation:

* When `len(paths) == 0` → explicit "PDF appears rasterized" message
  with `drawings=0`, `page_size=WxH`, and a pointer to the raster
  pipeline.
* When `len(paths) > 0` but the wall filter returns empty → diagnostic
  counters (`drawings=N filled_only=K stroked_only=M`) so the operator
  can tell whether walls are stroke-based or under a different fill
  rule, and a pointer to this doc.

Implementation: see the early-return branches in
`tools/build_vector_consensus.py:build()`. Test fixture + assertion in
`tests/test_vector_consensus_rasterized_input.py`.

## What we did NOT do

* Did **not** modify `_identify_wall_paths` thresholds (CLAUDE.md §1.3).
* Did **not** add a raster fallback inside the vector pipeline.
* Did **not** convert `planta_74_clean.pdf` to vector — that PDF likely
  was generated from a rasterized source and recovering the original
  vector data is impossible from the bitmap alone.
* Did **not** validate `--canonicalize-rooms` against the clean PDF —
  the clean PDF never reaches the canonicalize step (extractor returns
  empty, the chain stops there).

## Operational guidance

When a PDF errors out with the new "PDF appears rasterized" message:

1. Confirm by running `scripts/investigation/planta_74_clean_diff.py`
   (or any path-counting tool) — `drawings=0` confirms the diagnosis.
2. If the user has access to the original vector source: ask for it.
3. If only the rasterized PDF is available: use the raster pipeline
   (`python main.py extract <pdf>`) which is built for that case.
4. Document the conversion path in the project's intake notes so the
   same PDF doesn't reach the vector pipeline twice.

## Cross-links

* Vector pipeline overview: `OVERVIEW.md §2.2`, §4.4
* Raster pipeline overview: `OVERVIEW.md §2.1`
* CLAUDE.md §1.3 — geometry threshold rule (untouched here)
* CLAUDE.md §2 — "Não inventar paredes ou cômodos" (an empty result is
  the honest output for a rasterized input)
* Diagnostic script: `scripts/investigation/planta_74_clean_diff.py`
* Run artifacts (gitignored): `runs/planta_74_clean_debug/`
