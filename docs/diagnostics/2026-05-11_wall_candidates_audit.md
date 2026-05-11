# Wall candidates audit — FP-014 P0 stage-1 investigation

> **Status:** **OPEN — informs the FP-014 P0 next-cycle decision.**
> Pure diagnostic; no production code changed by this audit.
> **Date:** 2026-05-11
> **Branch:** `feat/vector-wall-candidates-audit`
> **Companion:** `docs/diagnostics/2026-05-09_skp_visual_failure_fp014.md`
> §"Stage 1 wall extraction" — canonical FP-014 root cause document.
> **Tooling:** `tools/wall_candidates_audit.py`,
> `tools/centerline_polygonize_diagnostic.py`.

## Context

FP-014 P0 polygonize output on `planta_74.pdf` (PR #112 + #113) caps at
**7 distinct rooms** out of 11 expected. The 4-room merge
(A.S. ∣ TERRACO SOCIAL ∣ COZINHA ∣ TERRACO TECNICO) and 2-room merge
(SALA DE JANTAR ∣ SALA DE ESTAR) emit honest `seeds_share_cell`
warnings — the walls between them simply do not exist in
`consensus.walls`.

The GPT-validated next-cycle hypothesis (`docs/diagnostics/
2026-05-09_skp_visual_failure_fp014_gpt_validation.md` and the user
chat-thread refinement on 2026-05-11) was:

> Build_vector_consensus._identify_wall_paths is silently dropping
> divider paths via the color + thickness clustering threshold.
> A multi-PDF empirical sweep should expose the rejected dividers.

This audit re-runs the wall classifier with instrumentation, dumps
every filled path with its rejection reason, and overlays the result on
the rendered PDF. Then it tests an alternative motor
(centerline + `shapely.polygonize`) as a control.

## Findings

### 1. Filled-path clustering is NOT the bottleneck

Running the audit on `planta_74.pdf`:

```
total paths:        1454
filled candidates:   149
accepted walls:       33   (matches the locked baseline)
rejected wall-like:  116
color clusters:        6
best cluster RGBA: (78, 78, 78, 255), members=37, score=27.95
```

The cluster table (full data in
`runs/audit/planta_74_audit.md` and `*.json`):

| cid | RGBA | members | median t | tight ≤30% | darkness | score | best |
|---|---|---:|---:|---:|---:|---:|:---:|
| 1 | (78,78,78,255) | 37 | 5.40 | 89% | 0.69 | 27.95 | **YES** |
| 2 | (127,127,127,255) | 63 | 0.60 | 49% | 0.50 | 23.28 | — |
| 3 | (164,164,164,255) | 4  | 3.60 | 75% | 0.36 |  2.04 | — |
| 5 | (255,255,255,255) | 4  | 8.73 | 75% | 0.00 |  1.50 | — |
| 4 | (226,226,226,255) | 15 | 19.80 | 13% | 0.11 |  1.11 | — |
| 0 | (0,0,0,255) | 1 | 0.00 | 0% | 0.00 |  0.00 | — |

The winning cluster captures 33 of 37 candidates of its color (89%
tightness; 4 dropped only because their thickness drifts > 30 % from
median). The other clusters are NOT dividers:

- **Cluster 2 (127,127,127, t≈0.6 pt)** — sub-pixel thin gray lines.
  Inspection shows these are dimension ticks + line endcaps from the
  hatching system. Median thickness 0.6 pt is incompatible with any
  wall (real walls cluster at 5.4 pt).
- **Cluster 3 (164,164,164, 4 members)** — light gray, only 4 paths;
  too few to score above 2.
- **Cluster 4 (226,226,226, 15 members, t≈19.8 pt)** — light-gray
  filled boxes. Visually these are **fixtures** (sinks, toilets,
  counters, máquinas de lavar). They are SQUARE/rectangular furniture
  outlines, not wall dividers.
- **Cluster 5 (white, 4 members)** — title-block / legend boxes.
- **Cluster 0 (black, 1 member, t=0)** — degenerate.

**Tightening or relaxing the 30 % threshold by ±10 % would not
recruit any divider.** The runner-up cluster (cluster 2) has median
thickness 0.6 pt — categorically incompatible with the 5.4 pt wall
thickness regardless of the band. The bottleneck is not threshold
selection; it is that **structural divider walls between
A.S./TERRACO SOCIAL/COZINHA/TERRACO TECNICO are not present as
filled paths in the source PDF.**

**Threshold sweep deliberately skipped:** GPT recommended sweeping ±30 %
on planta_74 + planta_p10 + planta_p12. Only planta_74 is a vector PDF
in this repo (the other two are referenced in CLAUDE.md §10 but the
PDFs themselves are not committed; `planta_74_clean.pdf` and
`test_plan.pdf` are raster — 1 image object each, zero filled paths,
incompatible with the vector classifier). With a single-corpus sample
and the empirical evidence above (best-cluster runner-up is
sub-pixel-thin, not a divider), a sweep adds no decision value.
**Documented as a known limitation: multi-PDF threshold sweep requires
adding new vector test fixtures.**

### 2. Stroked thin lines exist but are dominated by hatches

A secondary hypothesis: the missing dividers might be drawn as
thin stroked lines (not filled rectangles) and would therefore never
be inspected by `_identify_wall_paths`. The audit added a
`_wall_like_stroke` filter:

```
- stroke_on, no fill
- long_dim ≥ 25 pt          (excludes dimension ticks)
- short_dim ≤ 3 pt          (excludes fixtures)
- aspect long/short ≥ 5     (excludes squares)
- center inside planta_region   (excludes title block)
- NOT contained > 50% inside any accepted wall (excludes
  dimension-line strokes drawn along walls)
```

Yields **85 stroked wall-like paths** inside the planta region. But the
overlay (`runs/audit/planta_74_audit_overlay.png`) shows that ≥70 % of
these orange-outlined matches are **hatch patterns**:

- 7 consecutive horizontal lines at y=628–675, x=336–548, spaced 8 pt
  — clearly a piso/cerâmica decorative hatch
- 5 lines at y=597–621
- 8+ lines at y=535–590
- etc.

The remaining 15-or-so isolated thin lines might be peitoril edges
(`idx 490` at y=403, x=103–260, long=156 pt) or wall outlines
(`idx 680/689/692` at y=507–515, x=133–213, 3 lines spaced 4 pt apart
between A.S. and COZINHA centroids). They are PLAUSIBLE divider
candidates but indistinguishable from hatches without additional
heuristics:

- A "hatch" is a group of ≥ 3 parallel lines spaced < `wall_thickness`
- A "divider outline" is 2 lines spaced exactly = `wall_thickness`
  (representing the two edges of a thin wall)

Building that classifier is its own PR (~150 LOC, needs threshold
tuning + multi-PDF validation). It would NOT help the FP-014 P0 fix
landing this cycle.

### 3. Centerline + shapely.polygonize is strictly worse

`tools/centerline_polygonize_diagnostic.py` tests the alternative motor
the GPT thread mentioned as a "second motor candidate":

| Approach | n_cells | distinct rooms | merged cells |
|---|---:|---:|---:|
| Box-difference (production) | 12 | **7** | 2 |
| Centerline + polygonize | 12 | **3** | 2 (one massive 6-room merge) |

Side-by-side comparison: `runs/audit/planta_74_centerline_diagnostic.png`.

Centerline-polygonize collapses **A.S. ∣ TERRACO SOCIAL ∣ COZINHA ∣
SALA DE JANTAR ∣ SALA DE ESTAR ∣ TERRACO TECNICO** into one cell, and
**SUITE 01 ∣ BANHO 01** into another. SUITE 02 + BANHO 02 don't get
their own cells at all (the centerline approach left holes where their
seeds fell).

Why it's worse: the box-difference approach uses `end_extend=t` to
seal T-junctions where wall fragments don't quite touch. Centerlines
(1D lines, zero thickness) lose this property; cells leak through
door-arc gaps that the box-difference closes via wall-edge overlap.

**Box-difference (the existing production motor) is the correct primary
approach for vector PDFs whose walls are filled rectangles.**

## Conclusion

The hypothesis that the 4+2 cell merges in planta_74 polygonize output
come from wall-extraction threshold over-rejection is **REFUTED**. The
classifier behaves correctly: it accepts every filled path that
matches the wall fingerprint (consistent thin dimension, dark fill).

The missing dividers between A.S./TERRACO SOCIAL/COZINHA/TERRACO TECNICO
are **not drawn as filled paths** in `planta_74.pdf`. They might be
drawn as thin stroked lines (indistinguishable from cerâmica hatches
without further work) OR simply **don't exist in the PDF source** and
the rooms are separated semantically only (labels, piso-color change,
or implicit by floor-plan convention).

This recasts the FP-014 P0 cell-merge problem from
**"threshold over-rejection"** to **"PDF has structural-vs-semantic
divider ambiguity"** — a different problem with different fixes.

## Recommended next steps

In priority order:

1. **Ship PR-A2 with 7 honest rooms** (`refactor/rooms-polygonize-default`)
   — flip baseline default to polygonize with the `seeds_share_cell`
   warning explicit. Accepts the honest geometry. The merge warnings
   ARE the fidelity signal; F0 γ structural_checks can promote them
   from informational to advisory once the baseline shifts.
   - Documents the 4+2-cell merge as a **known limitation** with the
     evidence chain pointing to this audit.

2. **Use `human_annotation` walls for reviewer-confirmed dividers**
   — already supported by `consume_consensus.rb` since PR #111
   (2026-05-10). For reviewers who confirm visually that walls exist
   between merged rooms, the patch path is:
   ```
   consensus.walls.append({
     "id": "h_w001",
     "start": [x0, y0], "end": [x1, y1],
     "orientation": "h"|"v",
     "thickness": consensus.wall_thickness_pts,
     "geometry_origin": "human_annotation",
   })
   ```
   Polygonize will re-run with the new wall present.

3. **Detect peitoril-outline pairs (defer, ~150 LOC)** — implement
   `_classify_stroke_pairs` to find 2 parallel stroked lines spaced
   exactly `wall_thickness` apart and promote them to walls (with
   `geometry_origin="stroke_outline"`). Includes hatch-pattern
   rejection (group of ≥ 3 parallel lines spaced < `wall_thickness`
   = hatch, not wall). Needs multi-PDF validation.

4. **Add `planta_p10.pdf` + `planta_p12.pdf` to the fixtures**
   — CLAUDE.md §10 references them but they aren't committed.
   Required before any threshold-sweep PR can produce defensible
   evidence per CLAUDE.md §1.3.

## Artefacts shipped with this audit

```
tools/wall_candidates_audit.py             — diagnostic CLI
tools/centerline_polygonize_diagnostic.py  — alternative-motor control
docs/diagnostics/2026-05-11_wall_audit/
  planta_74_audit.md              — per-cluster summary table
  planta_74_audit_overlay.png     — PDF + classification overlay
  planta_74_centerline_diagnostic.png  — box-diff vs centerline side-by-side
docs/diagnostics/2026-05-11_wall_candidates_audit.md — this report
```

The full per-path JSON dump (`*_audit.json`,
`*_centerline_diagnostic.json`) is regenerable from the CLI commands
below; not committed (large, runs/ is gitignored).

## Reproducible commands

```powershell
# Audit
.venv\Scripts\python.exe -m tools.wall_candidates_audit planta_74.pdf `
    --out-json runs/audit/planta_74_audit.json `
    --out-overlay runs/audit/planta_74_audit_overlay.png `
    --out-summary runs/audit/planta_74_audit.md

# Centerline comparison
.venv\Scripts\python.exe -m tools.centerline_polygonize_diagnostic `
    planta_74.pdf `
    --out runs/audit/planta_74_centerline_diagnostic.json `
    --out-png runs/audit/planta_74_centerline_diagnostic.png
```
