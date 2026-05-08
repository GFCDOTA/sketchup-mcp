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

## Hover highlight (Cycle 12c — landed 2026-05-08)

Every rendered room polygon and opening circle now carries:

1. A `<title>` child element — browsers show this as a **native
   tooltip** on hover, no JS required. Tooltip content:
   - Rooms: `<NAME> · <area> m² · id=<id>`
   - Openings: `<kind> · decision=<decision> · <room_left> ↔ <room_right> · id=<id>`
2. A `class="hover-room"` / `class="hover-opening"` attribute paired
   with a CSS rule in the SVG's inline `<style>` block: hovering
   bumps the polygon's `fill-opacity` to 0.85 and thickens the
   stroke; hovering an opening thickens its outline. Cursor turns
   into a pointer to signal the element is informative.

The whole interaction is **CSS + native SVG `<title>`** — no
JavaScript, no Streamlit event wiring. Works in every browser AND
in GitHub's inline SVG renderer (try hovering a room in
`docs/diagnostics/2026-05-08_cockpit_demo_overlay.svg`).

XML escaping mirrors the existing label-escape contract: room names
containing `<`, `>`, or `&` are safely encoded inside the tooltip.

## Diff view (Cycle 12e — landed 2026-05-08)

The cockpit now compares **two consensus runs** side-by-side. Use
case: visually verify a baseline-shift PR (pre vs post Cycle 8b
concave-hull, or two synth iterations).

### How it works

1. Sidebar **Second consensus (run B, optional)** picker reuses the
   same auto-discovery as the primary picker. Default is `(none)`.
2. Toggle **Diff overlay (run B as dashed magenta)** in the Layers
   section. When ON + B is selected, every B room is drawn as a
   dashed magenta (`#c026d3`) outline OVER A's render. Walls /
   labels / openings come from A only.
3. New **Diff** inspector tab shows a per-room match table:
   `name`, `status` (matched / only_in_a / only_in_b), `area_a_m2`,
   `area_b_m2`, `delta_m2 (B−A)`, plus polygon vertex counts. Caption
   includes `by_status` histogram + `sum(matched Δ)`.

Match key is case-insensitive room name (same as the
expected-model overlay).

### What this unlocks

- **Baseline shift verification** — pull up the same plant before
  and after a fix; see at a glance which rooms moved, grew, or
  shrank.
- **Synth round-trip** — pre-roundtrip vs post-roundtrip consensus
  in one view; matched rooms with `Δ ≈ 0` confirm the round-trip
  preserved geometry.
- **Pipeline regression triage** — older "good" run vs current
  candidate; spot a phantom new room (`only_in_b`) or a vanished
  one (`only_in_a`) without grepping JSON.

## History / Fidelity view (Cycle 12f — landed 2026-05-08)

The cockpit now has a second top-level page — **History** — that
lists every consensus-bearing dir under `runs/`, surfaces fidelity
+ counts + image previews per run, and grades each one with a
**Pre-SKP Review** status before the SketchUp gate runs.

### Why this exists

CLAUDE.md §3 ("The SketchUp Rule") says SU is the LAST gate, not
the first. SKP cannot be the first time we "see" the planta. The
cockpit's job is to maximise what the human knows BEFORE paying the
60–90 s SU spawn cost.

The Single-run page (Cycles 12 → 12e) shows ONE consensus at a
time. The History page shows ALL of them, ranks them by fidelity,
and tells you which ones are safe to export.

### How it works

1. The new `cockpit/history_view.py` module is **pure Python** (no
   streamlit imports, no SketchUp dependency, no pipeline
   invocation). It walks `<repo>/runs/` for any directory that
   contains a consensus-shaped JSON (top-level `walls` + `rooms`),
   parses each artifact best-effort, and produces a `RunSummary`.
2. The cockpit shell adds a sidebar `View` selector (`Single run`
   | `History`). The History page consumes `RunSummary` objects and
   renders three sections.

### Page layout

#### 1. Master table

One row per run, sorted newest-first using
`consensus.metadata.generated_at` (falls back to a `YYYY-MM-DD`
substring in the run_id, then mtime). Columns: `run_id`, `branch`,
`commit` (8-char prefix), `stage`, `fidelity_score`, `hard_fails`
count, `warnings` count, `rooms` / `walls` / `openings` count,
`image_count`, `pre_skp` status badge, `recommendation`. A
status histogram below the table summarises how many runs are
PASS / WARN / FAIL.

#### 2. Run detail

A drilldown panel for any run picked from the dropdown. Three
columns:

- **Identifiers** — run_id, branch, commit, stage, generated_at
- **Counts** — rooms / walls / openings / soft_barriers
- **Pre-SKP Review** — status badge + recommendation + reasoning
  text + fidelity / hard_fails / warnings totals

Plus an **Artifacts** block listing every resolved file path
(consensus, fidelity_report, scorecard, expected_model, source_pdf)
and image previews (PNG/JPG render via `st.image`; SVG surfaces as
a relative-path link with file size).

#### 3. Compare two runs (before / after)

Two run selectors → a `RunDiff` panel: fidelity Δ, rooms Δ, walls
Δ, openings Δ; warnings new / resolved; hard_fails new / resolved;
per-room delta table (delegates to
`cockpit.render_overlay.diff_summary` so the geometry logic stays
shared with the Single-run Diff tab); side-by-side image rows.

### Pre-SKP Review status logic

Three tiers, advisory only — the cockpit does NOT block SKP export
in v0:

| Status | Condition | Recommendation |
|---|---|---|
| `PASS` | fidelity ≥ `pass_fidelity` AND zero hard_fails AND warnings ≤ `pass_warnings` | "safe to export SKP" |
| `WARN` | fidelity in `[warn_fidelity, pass_fidelity)` OR warnings exceed budget AND zero hard_fails | "review before SKP" |
| `FAIL` | fidelity < `warn_fidelity` OR ANY hard_fail OR no fidelity_report.json | "review before SKP" |

Defaults (v0; tunable via the History sidebar sliders so the user
can experiment without code change):

```
pass_fidelity   = 0.85   (mirrors the fidelity engine's healthy band)
warn_fidelity   = 0.69   (mirrors the fidelity engine's hard-fail cap)
pass_warnings   = 3      (CLAUDE.md §10 baseline = 2 warnings on planta_74)
```

These thresholds are **advisory** — they do NOT lower or raise the
fidelity engine's own `--strict` cutoffs. If the engine would block
strict (any hard_fail), the cockpit FAILs the run regardless of
fidelity.

### Acceptance criteria mapped to features (Felipe's words)

| Felipe's ask | Implemented in v0 |
|---|---|
| "I can open the cockpit and see a historical list of runs" | Master table |
| "I can see images/overlays generated in each run" | Run detail → image previews; Compare → side-by-side rows |
| "I can compare two runs" | Compare two runs section |
| "I can see fidelity before SKP" | `fidelity_score` column in master + Run detail panel |
| "I can know whether the pipeline is safe to export SKP or needs review" | Pre-SKP Review badge per run + recommendation |

### Boundary check (CLAUDE.md)

- §1.2 schema unchanged ✓
- §1.3 thresholds unchanged ✓ (pre-SKP review thresholds are NEW
  advisory ones, not engine thresholds)
- §1.4 Ruby/SU exporter untouched ✓
- §1.6 high-risk entrypoints untouched ✓
- §2 invariants intact (read-only) ✓
- §3 cockpit IS the cheap gate, runs without SU ✓ — and now
  surfaces the verdict BEFORE the gate

### Deferred to future cycles

- **Thumbnail rendering of complex artifacts** — when a run dir
  has neither PNG nor SVG previews, the History view shows a
  "no previews discovered" caption. Re-rendering an overlay from
  the consensus on demand (so EVERY run has a thumbnail) is
  deferred to Cycle 12g; the SVG renderer already exists in
  `cockpit/render_overlay.py` so this is a pure wiring task.
- **Filtering / sorting controls in the master table** — v0 ships
  one fixed sort (newest-first). Streamlit's native dataframe
  supports column-click sort already; bespoke filters
  (status=PASS, branch=feature/foo) are deferred.
- **Artifact drilldown from the table** — clicking a row to jump
  back to the Single-run page (with the consensus pre-selected) is
  a UX improvement deferred for now; the Single-run page already
  auto-discovers every consensus, so users can switch manually.

### Sample real-data smoke

`history_summary(REPO_ROOT)` against the live checkout returns 1
run (`runs/overpoly_audit/` — see test
`test_history_summary_on_real_repo_does_not_raise`). On a fully
populated checkout (`runs/feature_room_context_2026_05_06/` etc),
the page would list every cycle's run with its fidelity verdict.

## Remaining limitations (post-12f)

- No **PT_TO_M auto-detect** from `consensus.metadata`. Manual
  number_input.

## Next steps (remaining post-MVP candidates)

| Candidate | Why |
|---|---|
| Cycle 12g — thumbnail rendering for runs without PNG/SVG | Re-render the SVG overlay on demand so every History row has a preview. |
| `renderers/` migration | Architecture plan step 5; clears the 5 transitional `render_*.py` orphans. |
| Slice 2 — approve/reject + `review_overrides.json` | Needs FastAPI for POST. |
| Slice 3 — `proposed_actions.json` + pre-SKP gate F0 | Closes the validation-before-SKP loop. The Pre-SKP Review verdict added in Cycle 12f is the logical input to that gate. |

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
- `cockpit/history_view.py` — pure-Python multi-run discovery /
  summary / compare / Pre-SKP Review (Cycle 12f), unit-tested in
  `tests/test_cockpit_history_view.py`
- `cockpit/app.py` — Streamlit entry point
- `tools/fidelity/compare_generated_to_expected.py` — the
  fidelity engine the cockpit calls live
- CLAUDE.md §3 "The SketchUp Rule" — why the cockpit exists
  upstream of the SKP gate
- `feedback_autonomia_operacional_protocolo.md` — the YELLOW
  rules under which Cycle 12 was authorized


## Cycle 12g — on-demand thumbnails for runs without preview files

The History view introduced in Cycle 12f shows "no previews
discovered" for any run that does not carry a pre-rendered PNG/SVG
on disk. Cycle 12g closes that gap by rendering a small (320 px
wide, aspect-preserved) thumbnail directly from
`consensus_*.json` whenever no preview file is present, and caches
the result under `runs/<run_id>/_cockpit_cache/cockpit_thumbnail.png`.

### Module — `cockpit/thumbnails.py`

| Symbol | Purpose |
|---|---|
| `CACHE_DIRNAME` (`_cockpit_cache`) | Subdir of every run dir reserved for cockpit-only generated artefacts. |
| `THUMBNAIL_FILENAME` (`cockpit_thumbnail.png`) | Filename used inside the cache. |
| `DEFAULT_WIDTH_PX` (320) | Default raster width; height is derived from the consensus aspect ratio (clamped 80..240 px). |
| `thumbnail_path(run_dir)` | Pure helper — does not touch disk. |
| `ensure_thumbnail(run_dir, consensus_path, *, force=False)` | Returns the cached path; renders if missing or stale. Returns `None` on any failure (graceful degradation). |
| `render_consensus_thumbnail(consensus, width_px=320)` | Pure consensus to PNG bytes; raises only on programmer error (e.g. `width_px <= 0`). |

### Rendering approach — Pillow (option 2)

The renderer draws walls + rooms + openings directly via
`PIL.ImageDraw.Draw.polygon` and `.ellipse`. Color choices mirror
`cockpit/render_overlay.py`: walls in `#3b3326`, rooms in the same
hash-stable palette, openings in the same kind-coded RGB map.
Y-axis is flipped at draw time so PDF-up renders as visual-up,
matching the SVG view.

This avoids adding `cairosvg` (system-libcairo dependency, awkward
on Windows). The downside is mild duplication of the geometry
helpers; the upside is no new optional extra and a fully
self-contained pure-Python module that only imports Pillow at
render time.

### Cache strategy

- **Path**: `runs/<run_id>/_cockpit_cache/cockpit_thumbnail.png`.
  The whole `runs/` tree is gitignored (root `.gitignore`,
  `/runs/`), so generated thumbnails never enter the repo.
- **Invalidation**: stale when `consensus_path.stat().st_mtime`
  is greater than `thumbnail_path.stat().st_mtime`. Any stat
  failure also counts as stale (re-render rather than serve
  potentially wrong bytes).
- **`force=True`** bypasses the freshness check (debug aid).
- **Atomic writes**: render to `cockpit_thumbnail.png.tmp` then
  `Path.replace`, so a SIGKILL mid-write never leaves a corrupt
  half-PNG behind.

### History-view wiring

`cockpit.history_view.summarise_run` now invokes
`ensure_thumbnail` only when `image_paths` is empty AND a
consensus path was discovered. If the call returns a path, that
path is appended to `image_paths` so the History row renders the
thumbnail like any other preview. If it returns `None`, the row
keeps its "no previews" message — the cockpit never crashes
because of a missing thumbnail.

### Graceful degradation contract

Every failure mode returns `None` from `ensure_thumbnail` and logs
a warning:

| Failure | Behaviour |
|---|---|
| Pillow not installed (`ImportError`) | `None`, warning. |
| Consensus file missing | `None`, warning. |
| Consensus JSON malformed | `None`, warning. |
| Render exception (e.g. degenerate geometry) | `None`, warning, no partial cache. |
| Cache write blocked (read-only filesystem) | `None`, warning. |

This matches the Cycle 12f boundary: the cockpit must NEVER take
itself down because a thumbnail couldn't be rendered.

### Tests — `tests/test_cockpit_thumbnails.py`

19 unit tests cover:

- path shape (`thumbnail_path` always under `_cockpit_cache/`)
- cache creation (`ensure_thumbnail` warms the cache dir on first call)
- cache freshness (no re-render when consensus mtime <= thumb mtime)
- cache invalidation (re-render when consensus is newer)
- `force=True` re-renders unconditionally
- pure renderer returns valid PNG bytes (`\x89PNG\r\n\x1a\n` signature)
- empty consensus produces a beige rectangle without crashing
- custom `width_px` honoured
- `width_px <= 0` raises `ValueError`
- render failure (mocked exception) returns `None`, no partial file
- import failure (mocked `ImportError`) returns `None`
- corrupt JSON consensus returns `None`
- missing consensus file returns `None`
- `summarise_run` populates `image_paths` with the thumbnail when no other previews exist
- `summarise_run` does NOT trigger the thumbnail path when a real preview already exists
- `summarise_run` does NOT trigger when both consensus and previews are absent
- repeated calls with a fresh cache return the same path without rewriting
- default rendered width = `DEFAULT_WIDTH_PX` (320)

### Boundaries respected

- No streamlit import in either `thumbnails.py` or the
  `summarise_run` wiring — both stay pure-Python.
- No SketchUp dependency.
- No mutation of any pipeline artefact: writes go strictly to
  `runs/<run_id>/_cockpit_cache/`, a subdir reserved for the
  cockpit and ignored by git via the existing `/runs/` rule.
- No threshold or schema change.
- Existing `cockpit/render_overlay.py` is untouched: the SVG
  inspector remains the high-fidelity view; the PIL thumbnail is
  the History-row preview.
