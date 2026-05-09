# Multi-PDF synth corpus — Cycle 11e (2026-05-08)

> **Honest scope note up front:** this corpus expansion broadens the
> *algorithmic* round-trip surface of the extraction pipeline. It does
> **NOT** cover detector generalisation on **REAL** PDFs. Real-PDF
> coverage remains a 🔴 Felipe-blocked item — we still need a vetted
> corpus of 3+ real apartment plant PDFs (see
> `.ai_bridge/TODO_NEXT.md`). This PR is a **partial advance** on the
> RED item: substituting "Felipe provides 3+ real PDFs" with synthetic
> expansion of the round-trip test surface.

## Why expand the synth corpus?

Cycle 11c shipped `tools/synth/make_synthetic_vector_pdf.py` with a
single 2-room L-shape spec (`EXAMPLE_SPEC_2_ROOM_L`, "synth_l2").
Cycle 11d widened the L's wall-gap so the opening + adjacency
round-trip closes at fidelity = 1.0.

A **single topology** doesn't exercise enough of the pipeline. The L
is essentially convex, two rooms only, one opening. A regression in
the watershed or the room-context classifier could pass the L test
unnoticed if it only trips on:

- 3+ rooms competing for the same wall_gap during watershed
- non-rectangular envelopes (T, +, corridor)
- mixed public/private room pairs vs the
  `PRIVATE_PAIR_DOOR_MAX_M=1.50 m` rule
- `concave_hull` envelope vs rectangular envelope tradeoffs

This cycle adds **three new topologies** (T, plus, long-hall) so the
round-trip surface covers these.

## What ships

### Three new SPECS in `tools/synth/make_synthetic_vector_pdf.py`

| Spec id | Topology               | Rooms | Openings (gaps)                  | Notes |
|---------|------------------------|-------|----------------------------------|-------|
| `t3`    | 3-room T               | 3     | 1 wall_gap (50 pt)               | One closed divider + one gap; HALL + 2 top rooms |
| `plus4` | 4-room cross (1+3)     | 4     | 3 wall_gaps (50 pt each)         | 1 central SALA + 3 wings (N, W, E); south side closed |
| `hall5` | 5-room corridor        | 5     | 4 wall_gaps (35 pt each)         | Mixed room types (SALA, QUARTO, COZINHA, SUITE, LAVABO) |

A `SPECS` dict registers them so the CLI (`--spec t3|plus4|hall5`) and
the test parametrize stay in sync.

### Three paired ground-truth files

- `ground_truth/synth_t3/expected_model.json`
- `ground_truth/synth_plus4/expected_model.json`
- `ground_truth/synth_hall5/expected_model.json`

Each file follows the existing `expected_model_v1` schema used by
`tools/fidelity/compare_generated_to_expected.py`. Room confidence is
intentionally `medium` rather than `high` for area checks (the
synthetic geometry doesn't pin physical units), keeping area
mismatches as warnings rather than hard fails.

### One new test file

`tests/test_synth_multi_pdf_corpus.py` — parametrizes over the three
new specs and runs:

1. PDF generation (`write_pdf`)
2. `tools.build_vector_consensus` (with `--detect-openings`)
3. `tools.extract_room_labels`
4. `tools.rooms_from_seeds` (with `--canonicalize-rooms`,
   `--no-concave-hull`)
5. `tools.extract_openings_vector` (with `--detect-wall-gaps`,
   `--classify-kind`, `--mode replace`)
6. `tools.classify_openings_by_room_context`
7. `tools.fidelity.compare_generated_to_expected`

Asserts `global_fidelity >= 0.85`, `hard_fails == []`, and exact room
count match. Skips with a clear message when `python -m tools.X` is
not invocable from the harness (some Python installs use
`python._pth` to force `-I` isolated mode, which blocks PYTHONPATH).

### Round-trip results (Cycle 11e baseline)

| Spec     | Walls | Rooms | Openings detected | Fidelity | Hard fails | Warnings |
|----------|-------|-------|-------------------|----------|------------|----------|
| `t3`     | 7     | 3     | 1 interior_passage | 1.0      | 0          | 0        |
| `plus4`  | 16    | 4     | 3 interior_passage | 1.0      | 0          | 0        |
| `hall5`  | 12    | 5     | 3 passage + 1 door | 1.0      | 0          | 0        |

All three round-trip cleanly with the same `--no-concave-hull` flag.

## Design constraints discovered along the way

These were learned the hard way during this cycle and are recorded
here so future spec authors don't trip on them.

### 1. Room labels MUST match `ROOM_KEYWORDS` in `tools/extract_room_labels.py`

The label extractor only emits text matching its keyword whitelist
(`SALA`, `SUITE`, `COZINHA`, `QUARTO`, `BANHO`, `LAVABO`, `TERRACO`,
…). My first draft used `HALL T` / `N WING` — the extractor silently
dropped them. Fix: every label uses a canonical room keyword + a
short suffix to keep names unique.

### 2. Concave-hull envelope carves non-rectangular topologies

`tools/rooms_from_seeds.py` defaults to
`shapely.concave_hull` over wall endpoints (Cycle 8b fix for FP-012).
On the L plant this is a win — the envelope hugs the building outline
and stops watershed leakage into exterior. On a T or + plant, however,
the concave hull traces *inward* at every wing junction, leaving the
HALL polygon as a sliver:

```
T topology, default concave_hull:
  COZINHA T (HALL): bbox 26..317 × 26..134 (left half only)
  831 verts (jagged, watershed-edge)
T topology, --no-concave-hull (rectangular envelope):
  COZINHA T (HALL): bbox 26..614 × 26..134 (full strip)
  4 verts (clean rectangle)
```

The new specs all use `--no-concave-hull` for this reason. The L
spec keeps the default.

### 3. `PRIVATE_PAIR_DOOR_MAX_M = 1.50 m` rejects all-private corridors

The all-`QUARTO` first draft of `hall5` ended with all four openings
dropped:

```
[room-context] kept=0 dropped=4
```

Cause: `tools/classify_openings_by_room_context.py:_classify_pair`
caps private↔private gap width at 1.50 m. A 50 pt gap = 1.76 m, so
every divider was rejected. Two fixes work:

- mix at least one public room into each adjacent pair (the chosen
  fix for `hall5` — SALA / COZINHA / LAVABO interleaved with
  QUARTO / SUITE);
- narrow the gap to under 1.50 m (`hall5` uses 35 pt = 1.23 m so the
  classifier emits `interior_passage` for mixed pairs and
  `interior_door` for the SUITE↔LAVABO private pair).

### 4. Multi-seed competition for the same wall_gap

Watershed expands every seed simultaneously through every wall_gap.
When two top-room seeds both compete for a HALL gap, the closer one
wins more area through it, but both sides bleed into HALL and break
its polygon. The first `t3` draft put one gap *under each top room*,
giving two seeds racing for HALL's interior. Result: HALL got a
sliver-quad polygon in the wrong corner (label-to-polygon mismapping
under watershed pressure).

Fix: **one** wall_gap per room boundary, and never two gaps both
flowing into the same room. `t3` keeps one closed divider (between
HALL and TOP_LEFT) plus one gap (between HALL and TOP_RIGHT). `plus4`
similarly has 3 wings with their own gaps to the central SALA — three
seeds racing for the SALA interior, but SALA's seed is centered and
the wings are well-separated so the watershed splits cleanly.

## Limitations and what we did NOT cover

This corpus expansion is **synthetic-broadening only**. It explicitly
does NOT validate:

- **detector generalisation on real PDFs** — every PDF in
  `runs/synth_*/` is hand-rolled with predictable geometry. Real
  apartment plants have arc walls, stipple hatches, peitoris,
  cabinets, dimensioning lines, etc. None of those are exercised.
- **scale anchoring** — every synth uses `PT_TO_M=0.0352` (the
  planta_74 default) without a real wall-thickness probe. `m²`
  values in expected_models are therefore deliberately wide ranges,
  not pinned. Real PDFs need `PT_TO_M = wall_thickness_pts / 0.19`
  per `feedback_pdf_scale_anchor`.
- **door-arc opening detection** — the synth PDFs draw walls as
  filled rectangles only; no Bezier arcs. The arc detector (the
  primary path for real-PDF doors) is untouched. wall_gap detection
  is the only opening primitive exercised.
- **soft barriers** (peitoris, grades, glazed-balcony stripes) — the
  synth content stream emits zero soft barriers. `extract_openings_vector`
  classifies wall_gaps cleanly because there's nothing else to
  confuse it.
- **room-context classifier on EXTERIOR openings** — every gap in
  the corpus is interior-to-interior. The exterior path
  (`is_open_air_room` true on one side) is not exercised.

## Real-PDF coverage status

🔴 **Still Felipe-blocked.** We need a corpus of 3+ vetted real
apartment plant PDFs to exercise:

- arc-based door detection (the primary opening primitive in real
  brochures)
- mixed wall styles (filled hatch, stippled, double-line)
- peitoril / soft_barrier separation
- text-anchored scale calibration
- room labels with actual project naming conventions (not just the
  `ROOM_KEYWORDS` whitelist)

Until that corpus lands, real-PDF round-trip remains untestable. This
PR ships the synth-broadening half of the work; the real-PDF half
stays open in `.ai_bridge/TODO_NEXT.md` as a RED item.

## How to add a new spec

For the next spec author, the playbook (validated this cycle):

1. Pick a topology with ≥1 distinct property the existing specs
   don't cover (different room count, envelope shape, opening
   layout).
2. Write the `WallRect`/`TextLabel` definitions in
   `tools/synth/make_synthetic_vector_pdf.py`. Constraints:
   - Wall thickness `T = 6.0` pt is shared.
   - Wall gaps must be **30 ≤ gap_pts ≤ 250** (the
     `tools/detect_wall_gaps.py` band). 50 pt is comfortable.
   - Label text MUST contain a substring from
     `ROOM_KEYWORDS` in `tools/extract_room_labels.py`.
   - Label `(x, y)` must place the seed firmly inside its room — the
     text-center for Helvetica 10 pt is ~25 pt right of `x`.
   - One wall_gap per room boundary; never two gaps both flowing
     into the same room (multi-seed watershed competition).
   - For private↔private pairs, gap width < 1.50 m
     (`PRIVATE_PAIR_DOOR_MAX_M`).
3. Add to the `SPECS` dict so CLI/test enumerate the new id.
4. Generate a PDF and run the 5-stage pipeline manually with
   `--no-concave-hull` (unless your topology is genuinely convex).
5. Write the paired `ground_truth/synth_<id>/expected_model.json`.
   Use `manual_confidence: "medium"` for room areas (synth metrics
   are wide ranges) and `"high"` for opening adjacency (you control
   the topology exactly).
6. Add the spec id to `NEW_SPECS` in
   `tests/test_synth_multi_pdf_corpus.py` (the test parametrizes
   automatically).
7. Run `pytest tests/test_synth_multi_pdf_corpus.py -v` — must pass.
