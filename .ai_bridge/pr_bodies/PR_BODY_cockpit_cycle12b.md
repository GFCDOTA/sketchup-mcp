# Cycle 12b — Cockpit PDF underlay

## Summary

- Pick a PDF in the cockpit sidebar; the page is rasterised via `pypdfium2` and renders behind the SVG overlay so "is the consensus on top of the right walls?" becomes a one-glance answer.
- Default is opt-in (`(none)`) so the rasterisation cost is only paid when the user asks for it.
- Builds directly on Cycle 12 (PR #68). Keeps every boundary intact: read-only, no SketchUp dependency, no schema / threshold / Ruby change.

## What changed

| Path | Why |
|---|---|
| `cockpit/render_overlay.py` | `PdfUnderlay` dataclass + `pdf_page_to_data_url(pdf_path, dpi, opacity)` rasterizer + `render_overlay_svg(..., pdf_underlay=None)`. When the underlay is supplied, viewBox is anchored to the PDF page bounds and the bitmap is placed OUTSIDE the y-flip group so it renders right-side-up while the consensus polygons keep their PDF-up coord system. |
| `cockpit/app.py` | Sidebar "PDF underlay" group: auto-discover candidates (run siblings > repo root > under `runs/`), opacity slider (default 0.55), DPI select_slider (72/96/144/200/300; default 144). Caption surfaces the underlay path + DPI + opacity so "what am I looking at?" is always one glance. |
| `tests/test_cockpit_render_overlay.py` | 4 new tests — `<image>` element + viewBox + data URL when underlay supplied, default path unchanged when no underlay, viewBox switches to PDF page bounds, real-PDF round-trip via `synth_l2.pdf` / `planta_74.pdf`. |
| `docs/validation_cockpit.md` | Replaces the v0 "No PDF base layer" limitation with a "PDF underlay (Cycle 12b)" section: how it works (picker → rasteriser → renderer), the demo, what it unlocks (wall-offset / phantom-opening / missing-terraço eyeball checks). |
| `docs/diagnostics/2026-05-08_cockpit_demo_overlay_with_pdf.svg` | 487 KB self-contained demo SVG with `planta_74.pdf` baked in as a base64 PNG. Renders inline in browsers and in PR diff viewers. |
| `scripts/cockpit_make_demo_pdf_underlay.py` | Deterministic generator for the demo SVG. Pure read-only against existing artefacts; never mutates `runs/` or `ground_truth/`. |

## What did NOT change

- **Schema** (`docs/SCHEMA-V2.md`, `consensus_model.json`) — cockpit reads only.
- **Geometry thresholds** — none touched.
- **Ruby / SketchUp exporter** — untouched.
- **Pipeline invariants** (CLAUDE.md §2): no inference, no fallback, no GT leakage.
- **High-risk entrypoints** (CLAUDE.md §1.6): `api/app.py`, `main.py`, `sketchup_mcp_server/server.py` — untouched.
- **No baseline / no fidelity / no smoke gate** changes.
- **No new dependency** — `pypdfium2` is already a core dep used by the vector pipeline.

## Validation

- `pytest tests/test_cockpit_render_overlay.py -v` → **14/14 PASS** in 0.24 s (10 baseline + 4 new).
- Live smoke: `streamlit run cockpit/app.py` boots with the PDF picker visible; `preview_screenshot` confirmed default and underlay-on rendering for `runs/cycle11c/c0.json` and `runs/vector/consensus_model.json`.
- Demo SVG generation:
  - `using consensus=runs\vector\consensus_model.json + pdf=planta_74.pdf`
  - `page bounds: 595.0 x 842.0 pt`
  - `data URL length: 484 986 chars`
  - `wrote docs\diagnostics\2026-05-08_cockpit_demo_overlay_with_pdf.svg (498 543 bytes)`
- Visual check via `python -m http.server 8765 --directory docs` → in-browser screenshot of `2026-05-08_cockpit_demo_overlay_with_pdf.svg` shows the planta_74 PDF rendered behind 11 colored room polygons (COZINHA / SALA DE JANTAR / SALA DE ESTAR / LAVABO / SUITE 01 / SUITE 02 / BANHO 01 / BANHO 02 / A.S. / TERRACO SOCIAL / TERRACO TECNICO) with consensus walls and door circles aligned to the original drawing strokes.

## Risks

| Risk | Mitigation |
|---|---|
| 144-DPI base64 PNG ~485 KB ships per session, may slow Streamlit reruns | DPI is user-tunable down to 72; default opacity hides minor render cost; rasterisation path opt-in (default `(none)`). |
| `pypdfium2` rasterisation fails on some malformed PDF | Wrapped in try/except in `app.py`; user gets a `st.error` not a Streamlit crash. |
| Renderer behaviour with `pdf_underlay=None` could regress | Explicit `test_render_overlay_without_pdf_underlay_omits_image` + the existing 10 baseline tests run on the no-underlay path; all 10 still pass. |
| viewBox anchoring change drops some consensus polygons outside visible area when PDF margins are huge | Polygons are in PDF user space, so `0 0 page_w page_h` is the correct universal bounds; no clipping in practice. Manual override would be a future Cycle 12c. |

## Rollback

```pwsh
git revert <merge-sha>
git push origin develop
```

No schema, threshold, or pipeline state to revert — purely additive.

## Next steps (post-merge candidates)

| Candidate | Why |
|---|---|
| Cycle 12c — opening / room highlight on hover (interactive selection) | Bigger triage UX win for openings classifier debugging. |
| Cycle 12d — render `expected_model` overlay layer | Visual fidelity check: where does observed disagree with GT? |
| Cycle 12e — run-vs-run diff view | Useful for baseline-shift PRs (e.g. Cycle 8b SUITE 01 69→26 m²). |
| Slice 2 — approve/reject + `review_overrides.json` | Needs FastAPI for POST. |
| Slice 3 — `proposed_actions.json` + pre-SKP gate F0 | Closes the validation-before-SKP loop. |

🤖 Generated with [Claude Code](https://claude.com/claude-code)
