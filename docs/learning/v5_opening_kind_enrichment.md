# V5 — Opening kind enrichment (schema-additive)

**Date:** 2026-05-04
**Branch:** `skp/v5-opening-kind-enrichment`
**Reviewer:** ChatGPT (browser session at
`https://chatgpt.com/c/69f90cab-...` — bridge offline, ChatGPT
desktop window not visible to UIAutomation; consultation went through
the browser)

## Why

The visual diff against the Matterport tour
(`docs/tour/matterport_visual_findings_74m2.md` V5 verdict) flagged
that several openings render as thin orange strips on the SKP. The
"why" is semantic, not geometric: the existing pipeline emits
`kind: door | window` (geometric type) and `geometry_origin: svg_arc |
svg_segments` (how the path looked in the source PDF), neither of
which tells the SKP exporter what the opening *means* —
swinging-door vs glazed-balcony vs wide-open passage all flatten to
the same orange strip.

The fix needs to happen in two parts:

1. **Tag the consensus** with a semantic class per opening (this PR).
2. **Branch the Ruby renderer** on that class (future PR — touches
   `tools/consume_consensus.rb`, CLAUDE.md §1.4 forbidden zone, needs
   explicit human approval).

This PR does part 1 only — schema-additive, opt-in, no Ruby change,
no SKP visual change.

## What

`tools/classify_opening_kind.py` adds two optional fields per opening:

| Field | Values |
|---|---|
| `kind_v5` | `door_arc` \| `open_passage` \| `glazed_balcony` \| `window` |
| `kind_v5_reason` | short text explaining the chosen label |

Plus a metadata stamp: `metadata.opening_kind_v5_classifier.{version, counts, n_openings_input, n_openings_output}`.

### Classifier (heuristic, conservative, auditable)

| Input signal | Output `kind_v5` |
|---|---|
| `geometry_origin == "svg_arc"` | `door_arc` (arc symbol = real door swing) |
| `geometry_origin == "svg_segments"` AND opening center in/near a TERRACO/VARANDA room | `glazed_balcony` |
| `geometry_origin == "svg_segments"` elsewhere | `window` |
| `geometry_origin == "wall_gap"` (future detector) | `open_passage` |
| `geometry_origin` missing | `open_passage` (conservative; never invents a `door_arc`) |

The TERRACO room match uses substring `\b(TERRA|VARANDA)` on
`room.name` (case-insensitive) — covers `TERRACO SOCIAL`,
`TERRACO TECNICO`, `TERRAÇO`, `VARANDA`, `VARANDA SOCIAL`. Point-in-
polygon (ray-casting, stdlib only) decides which room contains the
opening's `center`; bbox-with-margin handles host-wall openings whose
center sits exactly on the room boundary.

### Wiring

Two ways to invoke:

```bash
# CLI flag on the existing extractor:
python -m tools.extract_openings_vector planta.pdf \
    --consensus runs/vector/consensus_model.json \
    --classify-kind \
    --mode merge

# Or programmatically:
from tools.classify_opening_kind import classify_openings
classify_openings(consensus)   # in-place, schema-additive
```

Default OFF; the existing CLI behavior is unchanged unless
`--classify-kind` is passed. The Ruby exporter
(`tools/consume_consensus.rb`) is NOT touched — it ignores `kind_v5`
today exactly as before.

## Result on planta_74

Running the full chain `build_vector_consensus` + `extract_room_labels`
+ `rooms_from_seeds` + `extract_openings_vector --classify-kind` on
`planta_74.pdf`:

```
opening count: 12
kind_v5 distribution:
  door_arc:        12   (every detected opening is an arc-door)
  open_passage:     0
  glazed_balcony:   0
  window:           0
```

So: planta_74 has only swinging doors with arc symbols; no segment-
based windows, no wall gaps without arcs, no glazed balconies.
**The classifier produces zero false positives** on this baseline,
which is the strict requirement from the ChatGPT review:

> "door_arc não inventado sem evidência"

## What stays open

* **Ruby renderer branch on `kind_v5`.** Future PR (forbidden-zone
  edit per CLAUDE.md §1.4 — needs explicit human approval). Once
  added, glazed balconies render with a glass material + sliding
  symbol, open passages render with no door symbol at all (just an
  empty wall break), and the strips → V5 visual issue resolves at
  the SKP.
* **Wall-gap detector that emits `geometry_origin: "wall_gap"`.**
  Brazilian sales-brochure PDFs with `kitchen ↔ living` open passages
  don't draw arcs there — the gap is implied by the absence of a
  wall segment. A scanner that finds `t`-shaped wall configurations
  with one branch missing would emit those as new openings; this
  PR's classifier is already ready to label them `open_passage`.
* **`glazed_balcony` evidence beyond room-name match.** Today the
  classifier promotes `svg_segments` to `glazed_balcony` based purely
  on the host room's name. A more robust signal would also check the
  opening's width relative to the wall length (sliding doors are
  typically ≥ 60% of the wall) and the wall's adjacency to building
  exterior.

## Tests

`tests/test_classify_opening_kind.py` — 11 tests:

| Test | Pinpoint |
|---|---|
| `test_classify_one_svg_arc_yields_door_arc` | arc evidence → door_arc |
| `test_classify_one_svg_segments_in_terraco_yields_glazed_balcony` | terraço adjacency rule |
| `test_classify_one_svg_segments_outside_terraco_yields_window` | non-terraço window |
| `test_classify_one_wall_gap_yields_open_passage` | future wall-gap detector path |
| `test_door_arc_not_invented_without_evidence` | conservative default — never door_arc without arc |
| `test_classify_openings_is_schema_additive` | existing fields untouched |
| `test_classify_openings_preserves_count_and_global_invariants` | walls/rooms/openings/soft_barriers count invariant |
| `test_classify_openings_stamps_metadata_with_counts` | metadata stamp shape |
| `test_at_least_one_open_passage_in_synthetic_fixture` | open_passage label is exercised |
| `test_old_consensus_without_classifier_is_still_valid` | backward-compat |
| `test_live_planta_74_all_door_arc` | live consensus baseline |

## Cross-links

* Visual evidence: `docs/tour/matterport_visual_findings_74m2.md` V5 verdict
* Ruby exporter (untouched): `tools/consume_consensus.rb`
* Existing extractor: `tools/extract_openings_vector.py`
* CLAUDE.md §1.4 — Ruby/SU exporter rule (this PR respects it)
* CLAUDE.md §1.2 — schema rule (additive only — `kind_v5` and
  `kind_v5_reason` are new optional fields, not breaking changes)
