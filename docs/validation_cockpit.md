# Validation Cockpit — local UI for pre-SKP review

> Cycle 12 (2026-05-08). Streamlit app that lets a human visually
> validate what the pipeline understood from a PDF before
> spending 60–90 s on SKP generation. Read-only — never writes
> back to consensus / GT files.

## Why this exists

The pipeline emits JSON artefacts (`consensus_with_room_context.json`,
`fidelity_report.json`, `coherence_report.json`, `micro_truth_report.json`)
plus matplotlib PNG previews. None of those are interactive: you
can't toggle "show only walls", switch between two runs, or inspect
a single opening's confidence without grepping JSON.

Cycle 8b cleared the FP-012 hard-fails. Cycle 11 closed the
synth-vector-PDF round-trip. The remaining gap before scaling
the pipeline to more PDFs is **a human-in-the-loop checkpoint**:

```
PDF -> pipeline -> consensus -> [HUMAN GLANCE] -> SKP
                                       ^
                              this is the cockpit
```

## What it shows

### Left column — top-down overlay

SVG-rendered top-down view of the consensus, in PDF user-space
coordinates. Layers togglable from the sidebar:

| Layer | What |
|---|---|
| **Walls** | Filled rectangles in the wall fill colour (`#3b3326`). |
| **Rooms** | Translucent polygons coloured per stable hash of the room name. |
| **Labels** | Room name + computed `area_m2` rendered at polygon centroid. |
| **Openings** | Coloured circles on each opening's center: orange = interior_door, soft-orange = interior_passage, blue = window, green = glazed_balcony, red = exterior_door, grey = unknown. Black border = decision="clean", grey border = decision="debug". |
| **Ground truth overlay** | Reserved (planned: render expected_model.json polygons over the observed). |
| **Warnings** | Surfaces `metadata.coherence.would_block_strict` entries. |

### Right column — inspector tabs

| Tab | Content |
|---|---|
| **Rooms** | Table: id, name, area_m2, polygon_verts, openings_touching, method. |
| **Openings** | Table: id, kind_v5, decision, room_left, room_right, confidence, width_m, host_wall. |
| **Fidelity** | If a `ground_truth/<plant>/expected_model.json` is selected: live `compare(...)` run with `global_fidelity`, sub_scores, hard_fails, warnings, suggested_fixes. |
| **Meta** | Raw `consensus.metadata` + schema_version. |

### Sidebar

- **Consensus picker** — auto-discovers `*.json` under `runs/`
  whose top-level keys look like a c3 (rooms + walls). Defaults to
  the first `c3*` or `*classified*` file found.
- **Ground truth picker** — auto-discovers
  `ground_truth/<plant>/expected_model.json`. Optional; if none
  picked, the Fidelity tab explains why it's empty.
- **Layer toggles** — six checkboxes for the layers above.
- **PT_TO_M scale knob** — defaults to `0.19/5.4`. Lets you
  override the pt→m conversion if you know the wall thickness
  is calibrated differently.

## How to run

```bash
# Install the optional [cockpit] extra (one-time):
pip install -e ".[cockpit]"

# Or just streamlit if you already have the project installed:
pip install streamlit

# Then from the repo root:
streamlit run cockpit/app.py
```

Streamlit will print a URL (usually `http://localhost:8501`).
Open it in your browser. The app auto-discovers everything; you
shouldn't need any CLI flags.

## Dependency footprint

`streamlit` (and its transitive deps: altair, pandas, pyarrow,
gitpython, etc.) is pinned as an OPTIONAL extra in
`pyproject.toml`:

```toml
[project.optional-dependencies]
cockpit = [
  "streamlit>=1.57,<2.0",
]
```

The core pipeline (`tools/`, `tests/`, smoke harness) does NOT
import streamlit. The renderer in `cockpit/render_overlay.py`
is pure Python + stdlib and is unit-tested independently of
streamlit.

## Cockpit boundary

The cockpit is **read-only** by design:
- never writes to `runs/`
- never writes to `ground_truth/`
- never spawns SketchUp
- never invokes the pipeline (only consumes its output)
- never mutates the consensus dict

This is a deliberate firewall: the cockpit is a diagnostic,
not a control surface. If a human wants to change something,
they edit the consensus / GT JSON manually and re-load the
cockpit. Eventually a "lock-in" button could promote the
human-validated consensus to a frozen artefact (post-MVP).

## Demo artefact

`docs/diagnostics/2026-05-08_cockpit_demo_overlay.svg` — the
top-down SVG the cockpit would render for the canonical
`runs/feature_room_context_2026_05_06/consensus_with_room_context.json`
with all toggles ON. GitHub renders SVG inline in markdown and
in the PR diff. Open it in a browser tab to see what the
pipeline understood.

`docs/diagnostics/2026-05-08_cockpit_demo_axon_top.png` — the
same consensus rendered via the existing `tools/render_axon.py`
(matplotlib top mode), included as a familiar reference point
to compare against the new SVG output.

## PDF underlay (Cycle 12b — landed 2026-05-08)

The cockpit now renders the source PDF page rasterised behind the
SVG overlay so you can visually confirm "is the consensus on top of
the right walls?" instead of staring at an empty canvas with vector
shapes.

### How it works

1. Sidebar **PDF underlay** picker auto-discovers candidates: PDFs
   sibling to the active consensus, then repo-root PDFs
   (`planta_74.pdf`, `synth_*.pdf`, etc.), then anything under
   `runs/`. Default is `(none)` — no rasterisation cost paid until
   the user opts in.
2. When a PDF is picked, `cockpit.render_overlay.pdf_page_to_data_url`
   uses `pypdfium2` to rasterise the chosen page at the picked DPI
   (72/96/144/200/300; default 144). The result is a base64-encoded
   PNG embedded as an `<image>` element inside the SVG.
3. The renderer anchors the SVG `viewBox` to the PDF page bounds
   (`0 0 page_w_pt page_h_pt`) so the bitmap and the consensus
   polygons share the same coordinate system. The bitmap goes
   OUTSIDE the y-flip group (its native orientation is top-down);
   the vector overlay group keeps its `scale(1, -1)` so PDF-up
   stays visual-up.
4. The opacity slider (default 0.55) blends the bitmap with the
   beige cockpit background so the consensus stays legible.

### Demo

`docs/diagnostics/2026-05-08_cockpit_demo_overlay_with_pdf.svg` —
self-contained SVG with the rasterised `planta_74.pdf` baked in as a
base64 data URL. Open in a browser to compare against
`docs/diagnostics/2026-05-08_cockpit_demo_overlay.svg` (the
no-underlay version from Cycle 12). Generator script:
`scripts/cockpit_make_demo_pdf_underlay.py`.

### What this unlocks

- **Wall offset eyeball check** — see if a wall in the consensus
  drifted off the original drawing's wall stroke.
- **Phantom opening detection** — see if a door arc in the consensus
  is actually drawn on the PDF.
- **Missing terraço detection** — see if the consensus failed to
  pick up a balcony shape that the PDF clearly draws.

## Ground-truth overlay (Cycle 12d — landed 2026-05-08)

When the **Ground truth overlay** sidebar toggle is ON AND a
`ground_truth/<plant>/expected_model.json` is selected, every
observed room outline is recoloured to its match status against the
expected `expected_area_m2_range`:

| Status | Color | Meaning |
|---|---|---|
| `in_range` | green `#16a34a` | observed area inside the expected range |
| `out_of_range_low` | orange `#f59e0b` | observed area below `expected_min` |
| `out_of_range_high` | deeper orange `#ea580c` | observed area above `expected_max` |
| `missing_polygon` | red `#dc2626` | expected room with NO observed match |
| `unmatched_observed` | grey `#9ca3af` | observed room with no expected entry |

Outline width is bumped from `0.4` to `2.0` so the colour reads even
at zoomed-out fit-to-screen.

Match key is a case-insensitive comparison between observed `name`
and expected `label`. Phantom expected rooms (no observed match)
appear in the inspector's **Expected** tab as `missing_polygon` rows
but cannot be drawn on the SVG — the GT schema carries
`expected_area_m2_range` and `expected_bbox_m`, not polygon
coordinates.

The new **Expected** inspector tab pairs with the SVG re-coloring
and shows the full match table textually, with status badges and
per-room `observed_m2` vs `expected_min`/`expected_max`. Useful for
screenshotting into a PR review when the SVG is too dense to read
at a glance.

### Smoke on planta_74

Running the cockpit on the canonical `planta_74` consensus +
`ground_truth/planta_74/expected_model.json` immediately surfaces
the FP-012 (convex-hull) leakage as **two** `out_of_range_high`
rows (SUITE 01 at 69.91 m² vs expected `[10, 28]`; SUITE 02 at
32.03 m² vs `[10, 22]`) — the same suites that motivated the
Cycle 8b concave-hull promote.

## Remaining limitations (post-12d)

- No **interactive room/opening selection**. Clicking a room
  doesn't highlight it. Static SVG only. Cycle 12c.
- No **side-by-side runs**. Pick one consensus at a time.
- No **PT_TO_M auto-detect** from `consensus.metadata`. Manual
  number_input.

## Next steps (remaining post-MVP candidates)

| Candidate | Why |
|---|---|
| Cycle 12c — opening / room highlight on hover | Better triage UX. |
| Cycle 12e — diff view | run A vs run B, useful for baseline-shift PRs. |
| Slice 2 — approve/reject + `review_overrides.json` | Needs FastAPI for POST. |
| Slice 3 — `proposed_actions.json` + pre-SKP gate F0 | Closes the validation-before-SKP loop. |

## Non-goals (explicitly)

- **NOT** a SketchUp viewer. The cockpit operates BEFORE the
  SKP step (CLAUDE.md §3 "SketchUp is the LAST gate" — the
  cockpit's job is to maximise what we know before paying the
  60–90 s SU spawn cost).
- **NOT** a CAD editor. No drag, no resize, no commit.
- **NOT** an alternative pipeline runner. It only consumes
  artefacts.

## See also

- `cockpit/render_overlay.py` — pure renderer, unit-tested in
  `tests/test_cockpit_render_overlay.py`
- `cockpit/app.py` — Streamlit entry point
- `tools/fidelity/compare_generated_to_expected.py` — the
  fidelity engine the cockpit calls live
- CLAUDE.md §3 "The SketchUp Rule" — why the cockpit exists
  upstream of the SKP gate
- `feedback_autonomia_operacional_protocolo.md` — the YELLOW
  rules under which Cycle 12 was authorized
