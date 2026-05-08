# adjacency_f1 = 0.67 plateau — Cycle 6 alt analysis (2026-05-08)

> Diagnostic only. Outcome: **do NOT change `classify_openings_by_room_context.py`.**
> The remaining adjacency mismatches are root-caused upstream in
> `rooms_from_seeds.py` polygon quality and in the absence of an
> opening object for one open-passage edge. Cycle 8c is the proper
> fix path; this PR captures the analysis so the next agent doesn't
> re-investigate.

## Symptom

Post-Cycle-8b (concave-hull default ratio 0.50), the Fidelity
Engine v1 emits a warning:

```
warning:adjacency_f1=0.67<0.80
```

The hard-fail floor (0.60) is cleared, so the gate doesn't block
merges. But the recall+precision gap is real and recurring.

## Numbers

| Metric | Value |
|---|---|
| Expected adjacency edges | 8 |
| Observed adjacency edges | 10 |
| True positives | 6 |
| False positives | 4 |
| False negatives | 2 |
| Precision | 0.600 |
| Recall | 0.750 |
| F1 | 0.667 |

### True positives (6, OK)

```
A.S.        <-> COZINHA              (door, opening o004)
BANHO 01    <-> SUITE 01             (door, opening o003)
BANHO 02    <-> SUITE 02             (door, opening o005)
COZINHA     <-> SALA DE JANTAR       (door, opening o007)
SALA DE ESTAR <-> TERRACO SOCIAL     (glazed_balcony, g001)
SUITE 02    <-> TERRACO TECNICO      (glazed_balcony, g002)
```

### False negatives (2, expected but observed pipeline does not assert)

```
LAVABO        <-> SALA DE JANTAR
SALA DE ESTAR <-> SALA DE JANTAR
```

### False positives (4, observed but not expected)

```
A.S.     <-> SALA DE ESTAR
A.S.     <-> TERRACO SOCIAL
BANHO 02 <-> LAVABO
BANHO 02 <-> SUITE 01
```

## Root-cause breakdown

`classify_openings_by_room_context.py` for each opening:
1. Probe two sides of the host wall at offset
   `eps = thickness*0.6 + 1.0` (≈ 4.24 pt for the 5.4 pt walls).
2. Try polygon-containment lookup at each probe.
3. Fall back to nearest-seed (Euclidean to room `seed_pt`) if no
   polygon contains the probe.
4. If both probes return the same room ("self-adjacent"),
   disambiguate by picking the second-nearest seed for one side.

This logic is sound when polygons are clean. **Each adjacency
mismatch traces to an upstream defect in the polygons:**

### FP `BANHO 02 <-> SUITE 01`  (opening o010, host wall w011)

- Probes at (328.8, 582.9) and (328.8, 591.4)
- Both probes hit polygons by containment: BANHO 02 (north) +
  **SUITE 01 (south)**.
- SUITE 01 polygon (615 vertices, bbox 234×191 pt = ~55 m² as
  bbox) STILL leaks into the corridor area south of BANHO 02
  even at concave-hull ratio 0.50. The architecturally-correct
  pair is `BANHO 02 <-> SUITE 02`, but SUITE 02's polygon
  doesn't reach this wall — it's truncated by the concave hull.

### FN `LAVABO <-> SALA DE JANTAR`  (opening o009, host wall w006)

- Probes at (335.9, 623.7) and (335.9, 632.2)
- **No polygon contains either probe at eps=4.24** (LAVABO
  polygon bbox x=260-320 — probe x=335.9 is east of LAVABO;
  SALA DE JANTAR polygon bbox x=130-316 — same problem on its
  east edge).
- Fallback nearest-seed: LAVABO closest to both probes (~42-46 pt).
- Disambiguation picks BANHO 02 as second-nearest (77 pt) for one
  side — wrong by architecture.
- Architecturally correct neighbour SALA DE JANTAR is 146 pt
  away from the probe, the THIRD-nearest, never picked.

### FP `A.S. <-> SALA DE ESTAR` and `A.S. <-> TERRACO SOCIAL`

- A.S. polygon (after concave hull r=0.50) is a thin sliver
  (bbox ~66×400 pt, area 2.52 m²). It runs vertically along the
  west edge of the building, adjacent to TERRACO SOCIAL (south)
  AND to a non-architectural strip (north).
- Two openings (o008 window, o012 window) are placed on walls
  shared with TERRACO SOCIAL. `o006` (interior_passage) is
  classified `A.S. <-> SALA DE ESTAR` because of polygon
  proximity, but architecturally A.S. doesn't connect to SALA
  DE ESTAR — there's a wall between them.

### FN `SALA DE ESTAR <-> SALA DE JANTAR`

- This is an **open passage** (no discrete opening object) in
  the actual planta — the "social area" flows freely between
  the two rooms.
- The pipeline does not emit an opening for this edge, so
  `classify_openings_by_room_context` has nothing to attribute
  the adjacency to.
- This FN is **not fixable in `classify_*`** by design; it
  requires either:
  - Adding a synthetic "open_passage" opening when two rooms
    share a wall AND there's no carved opening on it, OR
  - Changing the adjacency metric to include "polygon-edge-share"
    rather than "via opening object".

## Why fix-in-classifier won't help

I prototyped two alternatives in this investigation:

1. **Nearest-vertex** (instead of nearest-seed): collapses to
   self-adjacent in most cases because polygon edges hug walls.
   Worse than nearest-seed.
2. **Side-filtered nearest-seed** (filter by side of the wall):
   for `o009` it picks `BANHO 02` on the y- side and `LAVABO` on
   the y+ side — same wrong result as today, because no seed for
   the architectural truth (`SALA DE JANTAR`) is on the y- side
   in this region.

Both failure modes — leaked polygons (SUITE 01) and shrunken
polygons (LAVABO, SALA DE JANTAR not reaching the wall) — are
**`rooms_from_seeds.py` output defects**. The classifier is
working with bad inputs.

## What COULD fix this

Cycle 8c (proposed, not in this PR):

- **Polygon "grow-by-thickness" pre-step:** expand each room
  polygon by `wall_thickness/2` so polygons always reach the
  walls. Resolves LAVABO + SALA DE JANTAR not-reaching-wall FNs.
- **Alpha-shape per room** (Voronoi seed-based polygon
  refinement). Resolves SUITE 01 leakage by tightening polygons
  to actual wall-bounded regions.
- **Synthetic `open_passage` opening** when two adjacent room
  polygons share a wall edge that has no carved opening.
  Resolves the SALA DE ESTAR <-> SALA DE JANTAR FN.

These are non-trivial geometric changes. Out of scope for this
PR.

## Decision

**Do not modify `classify_openings_by_room_context.py`** in
this PR. The classifier is correct given its inputs.

Mark `adjacency_f1 ∈ [0.65, 0.80]` as the expected
post-Cycle-8b plateau. The fidelity engine already surfaces
this band as a warning, not a hard_fail (threshold 0.80 for
warning, 0.60 for hard_fail). No threshold change.

Add **FP-013** to `docs/learning/failure_patterns.md` so the
next agent doesn't re-investigate.

## See also

- `tools/classify_openings_by_room_context.py:172`
  (`find_rooms_flanking_wall`) — the function being analysed
- `docs/diagnostics/2026-05-08_cycle8b_after_concave_r050.png`
  — visual showing SUITE 01 leakage and A.S. sliver
- `tools/fidelity/compare_generated_to_expected.py:_metric_adjacency`
  — where the adjacency_f1 thresholds are encoded
- `.ai_bridge/GPT_REQUESTS.md` + `GPT_RESPONSES.md` 2026-05-08
  cycle6alt entry — full LLM consult
- LL-011 `docs/learning/lessons_learned.md` — the empirical-override
  pattern that informed this PR's "don't modify classifier" choice
