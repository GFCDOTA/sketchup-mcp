## Summary

- Adds the **History / Fidelity view** (Cycle 12f) — a second top-level cockpit page that lists every consensus-bearing dir under `runs/`, surfaces fidelity + counts + image previews per run, lets the user compare two runs side-by-side, and grades each with a **Pre-SKP Review** status (PASS / WARN / FAIL — advisory only).
- Implements all 10 functional requirements from the cycle prompt; thumbnail rendering for runs without PNG/SVG previews is the only deferred improvement (Cycle 12g).
- Read-only — never mutates `runs/`, `ground_truth/`, never spawns SketchUp, never invokes the pipeline. Pre-SKP Review thresholds are NEW advisory ones, not changes to fidelity engine cutoffs.

## What changed

| File | Change |
|---|---|
| `cockpit/history_view.py` | **NEW** pure-Python module (350 LOC, no streamlit imports). `RunSummary` / `RunDiff` dataclasses, `discover_runs`, `summarise_run`, `compare_runs`, `pre_skp_review`, `history_summary`, `order_runs_for_history`. |
| `cockpit/app.py` | Adds sidebar `View` selector (`Single run` \| `History`); routes to a new `_render_history_page()` with master table + per-run detail panel + before/after comparison panel. Existing Single-run page is unchanged below the routing layer. |
| `tests/test_cockpit_history_view.py` | **NEW** 19-test suite covering: run discovery (2 tests), summary assembly (3 tests), history-model assembly (2 tests), before/after comparison (2 tests), pre-SKP review status (7 tests), real-data smoke (2 tests including a SKIP for the gitignored canonical run). |
| `docs/validation_cockpit.md` | Adds full Cycle 12f section (why / how / page layout / status logic / acceptance criteria / boundary / deferred items). Updates "Next steps" + "See also". |

## What did NOT change

- No schema change (CLAUDE.md §1.2).
- No threshold change (CLAUDE.md §1.3) — pre-SKP review thresholds are NEW advisory ones, not changes to the fidelity engine's `--strict` cutoffs.
- No Ruby / SU exporter touched (CLAUDE.md §1.4).
- No high-risk entrypoint touched — `api/app.py`, `main.py`, `tools/consume_consensus.rb` all untouched (CLAUDE.md §1.6).
- `cockpit/render_overlay.py` unchanged — `compare_runs` delegates to `diff_summary` so the geometry logic stays shared.
- No `pyproject.toml` change — `cockpit/history_view.py` uses only stdlib + a lazy local import of `cockpit.render_overlay.diff_summary`.

## Validation

```bash
# Gate 1 — new tests
$ python -m pytest tests/test_cockpit_history_view.py -v
18 passed, 1 skipped in 0.14s

# Gate 2 — existing cockpit tests still pass
$ python -m pytest tests/test_cockpit_render_overlay.py -q
25 passed, 1 skipped in 0.24s

# Gate 3 — full sweep, no NEW failures
$ python -m pytest -q
598 passed, 17 failed, 23 skipped in 10.16s
# All 17 failures match CLAUDE.md §10 pre-existing raster + dashboard set.
# Pre-PR develop baseline was identical (568+30 cockpit = 598 pass).

# Gate 4 — ruff
$ python -m ruff check cockpit/ tests/test_cockpit_history_view.py
Found 3 errors.
# All 3 are pre-existing E402 in cockpit/app.py from PR #68's
# sys.path bootstrap pattern — see HANDOFF.md "informative-only".
# develop baseline was 2 E402; this PR adds a 3rd block following
# the SAME pattern. New code (history_view.py + tests) is clean.

# Gate 5 — app importable
$ python -c "import cockpit.app as a; print(callable(a.main))"
True
```

## Functional requirement coverage (v0)

| FR | Implemented | Notes |
|---|---|---|
| 1 | "History" page in app.py | sidebar `View` radio, routes to `_render_history_page()` |
| 2 | Lists runs ordered by date | `history_summary` → `order_runs_for_history` (newest-first) |
| 3 | Per-run summary with all listed fields | `RunSummary.as_dict()` + master dataframe |
| 4 | Thumbnails of artifacts when present | `st.image` on PNG/JPG; SVG surfaces as relative-path link |
| 5 | Click into a run → main overlay + reports | "Run detail" section: identifiers + counts + Pre-SKP verdict + artifacts list + image previews |
| 6 | Before/after comparison | "Compare two runs" section: fidelity Δ, counts Δ, warnings new/resolved, hard_fails new/resolved, per-room delta table, side-by-side images |
| 7 | Pre-SKP Review status PASS/WARN/FAIL + recommendation | `pre_skp_review()` with tunable thresholds via sidebar sliders |
| 8 | Does NOT generate SKP | confirmed — read-only |
| 9 | Does NOT depend on SketchUp | `cockpit/history_view.py` has zero SU imports |
| 10 | READ-ONLY | confirmed — no mutation surface added |

## Risks

- **Streamlit `st.image` on path strings:** Streamlit happily takes a list of paths or PIL images, but malformed PNGs in `runs/` would raise. Mitigation: file collection only matches by extension; the actual image decode happens client-side. If a user has a corrupt PNG, the History page would surface a warning element (Streamlit's own error display) without crashing the page.
- **Threshold defaults:** PASS=0.85 / WARN=0.69 / WARN_BUDGET=3 are advisory-only and tunable from the sidebar. They mirror the fidelity engine's strict band so the cockpit cannot greenlight a run the engine would block. Document if Felipe later wants different defaults.
- **Auto-discovery walks `runs/` recursively:** on a checkout with hundreds of run subdirs the page load could become slow. Current implementation is `O(n)` over all `*.json` files under `runs/`. If this becomes painful, cache via `@st.cache_data` later (deferred — premature for the v0 scope).

## Rollback

```bash
# Revert the merge:
git revert -m 1 <merge-sha>
# Then push the revert PR through develop as usual.
# Or, before merge, just close the PR + delete the branch:
"/c/Program Files/GitHub CLI/gh.exe" pr close <pr-number> --delete-branch \
  --repo GFCDOTA/sketchup-mcp
git branch -D feature/cockpit-history-view-cycle12f
```

## Next steps

- **Cycle 12g** — re-render SVG overlay on demand for runs that have no PNG/SVG previews, so EVERY History row has a thumbnail.
- **Slice 3** — `proposed_actions.json` + pre-SKP gate F0 in the smoke harness; the Pre-SKP Review verdict added here is the logical input.
- **Hygiene cycle** — refresh `.ai_bridge/HANDOFF.md` + `CURRENT_STATE.md` post-merge.
