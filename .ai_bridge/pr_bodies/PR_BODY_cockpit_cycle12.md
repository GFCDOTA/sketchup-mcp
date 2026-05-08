# Cycle 12 — Validation Cockpit MVP (read-only Streamlit UI)

## Summary

- New optional Streamlit app (`cockpit/`) that lets a human visually validate what the planta extraction pipeline understood from a PDF **before** spending 60–90 s on SKP generation. Implements CLAUDE.md §3 ("SketchUp is the final gate") by extending the JSON-structural validation step to also be visual.
- Pure-Python SVG renderer (`cockpit/render_overlay.py`, zero hard deps) is fully unit-tested; Streamlit is gated behind a `[cockpit]` extra so the core pipeline stays lean.
- Read-only by design — never writes to `runs/`, `ground_truth/`, the consensus, or anything else. No SketchUp dependency.

## What changed

| Path | Why |
|---|---|
| `cockpit/__init__.py` | Package docstring + entry-point note |
| `cockpit/render_overlay.py` | 308 LOC pure-Python renderer + summary helpers (walls / rooms / labels / openings / GT toggle) |
| `cockpit/app.py` | 281 LOC Streamlit shell: sidebar (consensus picker + GT picker + layer toggles + PT_TO_M slider), 3:2 split (overlay + inspector tabs), live fidelity engine call when GT selected. Includes sys.path bootstrap so the app launches from any cwd. |
| `tests/test_cockpit_render_overlay.py` | 10 unit tests for the renderer (walls/rooms/openings/labels toggle behaviour, XML escape, empty consensus, planta_74 smoke) |
| `pyproject.toml` | Adds `[project.optional-dependencies] cockpit = ["streamlit>=1.57,<2.0"]`; adds `"cockpit*"` to `[tool.setuptools.packages.find]` so the package is actually installed by `pip install -e .[cockpit]` |
| `docs/validation_cockpit.md` | How-to + UI map + boundary statement + post-MVP candidate list |
| `docs/diagnostics/2026-05-08_cockpit_demo_overlay.svg` | Demo SVG of the canonical `feature_room_context_2026_05_06` consensus rendered with all toggles ON |
| `docs/diagnostics/2026-05-08_cockpit_demo_axon_top.png` | Reference render via existing `tools/render_axon.py` for visual comparison |

## What did NOT change

- **Schema** (`docs/SCHEMA-V2.md`, `consensus_model.json`) — cockpit reads, never modifies.
- **Geometry thresholds** (none touched: `len(strokes) > 200`, `snap_tolerance`, `WALL_HEIGHT_M`, `PARAPET_*` all intact).
- **Ruby/SketchUp exporter** (`tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`, autorun plugins, `tools/su_boot.rb`) — untouched.
- **Pipeline invariants** (CLAUDE.md §2): no inference, no fallback, no GT leakage; cockpit is purely observational.
- **High-risk entrypoints** (CLAUDE.md §1.6): `api/app.py`, `main.py`, `sketchup_mcp_server/server.py` — untouched.
- **No baseline / no fidelity / no smoke gate** changes.

## Validation

- `pytest tests/test_cockpit_render_overlay.py -q` → **10/10 PASS** in 0.02 s
- Live smoke: `streamlit run cockpit/app.py` boots successfully and renders `runs/cycle11c/c0.json` overlay; sidebar shows 3 consensus candidates auto-discovered; tabs Rooms / Openings / Fidelity / Meta render without errors. Initial `ModuleNotFoundError` was caught and fixed in commit `f11e13c` (sys.path bootstrap + package include).
- Renderer is dependency-free → its tests run in the existing CI without installing the `[cockpit]` extra.

## Risks

| Risk | Mitigation |
|---|---|
| Streamlit transitive deps (altair, pandas, pyarrow, gitpython) bloat the install | Gated behind `[cockpit]` extra; core pipeline never imports them |
| Future change to `consensus_model.json` schema breaks the renderer | Renderer uses `.get(...) or default` everywhere; smoke tests on planta_74 baseline catch shape regressions |
| Demo SVG/PNG in `docs/diagnostics/` drifts from current pipeline output | Filenames are date-stamped (`2026-05-08_*`) so future updates land as new artefacts; not a regression target |
| GT picker calls `compare_generated_to_expected` live; engine failure surfaces in UI | Wrapped in try/except `BLE001`; user gets `st.error(...)` not a Streamlit crash |

## Rollback

```pwsh
git revert f11e13c 30246d6
git push origin develop  # if already merged
# OR before merge:
git push --delete origin feature/validation-cockpit-mvp-cycle12
git branch -D feature/validation-cockpit-mvp-cycle12
```

No schema, threshold, or pipeline state to revert — the cockpit is purely additive.

## Next steps (post-merge candidates, not in this PR)

| Candidate | Why |
|---|---|
| Cycle 12b — PDF underlay (`pypdfium2` page rendered behind the SVG) | Biggest visual win after MVP; needs pt→px alignment |
| Cycle 12c — interactive room/opening highlight on hover | Better triage UX |
| Cycle 12d — render `expected_model` overlay layer | Real visual fidelity check |
| Cycle 12e — run-vs-run diff view | Useful for baseline-shift PRs (e.g. Cycle 8b SUITE 01 69→26 m²) |
| Slice 2 — approve/reject per element + `review_overrides.json` persistence | Needs FastAPI for state mutation |
| Slice 3 — `proposed_actions.json` schema + pre-SKP gate F0 in `scripts/smoke/smoke_skp_export.py` | Closes the validation-before-SKP loop |

🤖 Generated with [Claude Code](https://claude.com/claude-code)
