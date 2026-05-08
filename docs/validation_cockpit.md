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

## Limitations (v0)

- No **PDF base layer**. The cockpit only shows the extracted
  consensus, not the source PDF behind it. Adding a
  `pypdfium2`-rendered PDF page underneath the SVG is a
  Cycle 12b candidate — needs careful coord alignment.
- No **ground-truth overlay** rendering. The toggle exists in
  the UI but the renderer doesn't yet draw expected polygons.
- No **interactive room/opening selection**. Clicking a room
  doesn't highlight it. Static SVG only. Cycle 12c.
- No **side-by-side runs**. Pick one consensus at a time.
- No **PT_TO_M auto-detect** from `consensus.metadata`. Manual.

These are deliberate v0 cuts to ship the MVP fast. The renderer
+ inspector cover the "did the pipeline get the right rooms" use
case today.

## Next steps (post-MVP candidates)

| Candidate | Why |
|---|---|
| Cycle 12b — PDF underlay | The biggest visual win after MVP. |
| Cycle 12c — opening / room highlight on hover | Better triage UX. |
| Cycle 12d — render expected_model overlay | Real visual fidelity check. |
| Cycle 12e — diff view | run A vs run B, useful for baseline-shift PRs. |

None of these are in the v0 PR.

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
