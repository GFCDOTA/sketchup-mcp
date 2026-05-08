# Current State — 2026-05-08 (post Cycle 12b merge)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/post-cycle12b-handoff-refresh` (this commit)
- **develop @** `8e1e225` — PR #70 (Cycle 12b PDF underlay) merged
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`, `quality_gates.yml`. Last 3 develop runs all green pre-merge.
- **Open PRs:** none (post-merge cleanup PR is being prepared on this branch)
- **Local branches alive:** `dashboard/architecture-sre-radar`, `dashboard/project-roadmap`, `feature/smoke-promotes-inspector-v2-gate` (all RED-blocked Stage 1.6 / out-of-scope)

## Last objective (just completed)

**Cycle 12b — PDF underlay** MERGED via PR #70 (`8e1e225`). 7 files, 462 insertions, 42 deletions. 4 new cockpit unit tests (14/14 total green). PR body followed CLAUDE.md §4; CI green; squash-merged + branch deleted via `gh pr merge --squash --delete-branch`. No new dependency (pypdfium2 already core).

The cockpit can now render a PDF page behind the SVG overlay so "is the consensus on top of the right walls?" becomes a one-glance answer. Default is opt-in (`(none)` picker), so rasterisation is paid only when the user asks for it.

## Three trincos status

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable, smoke green, CI green
- ✅ **Incerteza auditável** — coherence_audit + plan truth gate + micro truth gate (4 rooms via Cycle 7) + Fidelity Engine v1 (HARD blocker post-Cycle-8b)
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity Engine v1 (whole-plant) + cockpit visual review BEFORE SKP **with PDF underlay alignment check**

## Active tools

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable, schema 1.0 |
| `tools/micro_truth_gate.py` | ✓ stable, schema 1.0 |
| `tools/skp_inspection_report.py` | ✓ stable, schema 1.0 |
| `tools/classify_openings_by_room_context.py` | ✓ stable + Stage 1 contract |
| `tools/inspect_walls_report.rb` | ✓ v2 schema (PR #49) + Lint clean (PR #55) |
| `tools/fidelity/compare_generated_to_expected.py` | ✓ schema 1.0; called LIVE by cockpit |
| `tools/fidelity/synth_from_expected.py` | ✓ round-trip helper |
| `tools/rooms_from_seeds.py` | ✓ DEFAULT `--use-concave-hull=True` (Cycle 8b promoted; ratio 0.5 cleared FP-012) |
| `tools/synth/make_synthetic_vector_pdf.py` | ✓ Cycle 11c/11d round-trip closed |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H |
| `cockpit/render_overlay.py` | ✓ pure SVG renderer + summary helpers + **PdfUnderlay** (12b) |
| `cockpit/app.py` | ✓ Streamlit shell w/ sidebar pickers + 4 tabs + **PDF underlay group** (12b) |
| `scripts/cockpit_make_demo_pdf_underlay.py` | ✓ NEW — deterministic demo SVG generator |

## Tests

Re-validated 2026-05-08 on `develop @ 8e1e225`:

- Plan Truth Gate: **15/15 PASS**
- Micro Truth Gate: **20/20 PASS** (4 rooms scoring 1.0)
- Coherence Audit: **21/21 PASS**
- Concave-hull spike unit tests: **4/4 PASS**
- Fidelity Engine: **21/21 PASS**
- Fidelity round-trip: **4/4 PASS**
- Cockpit renderer: **14/14 PASS** (10 baseline + 4 PdfUnderlay)
- **Total in-scope: 99/99 PASS** (+4 from Cycle 12b)

## Next ROIs

| Item | Color | Notes |
|---|---|---|
| Refresh `.ai_bridge/*` (this PR) | 🟢 GREEN | factual update, additive |
| **Cycle 12d — render expected_model overlay** | 🟢 GREEN | toggle + signature param already exist, just wire renderer; smallest cockpit follow-up; visual fidelity check |
| **Cycle 12c — interactive room/opening highlight on hover** | 🟢 GREEN | better triage UX; needs JS bridge or Streamlit components |
| **Cycle 12e — run-vs-run diff view** | 🟢 GREEN | useful for baseline-shift PRs (e.g. Cycle 8b SUITE 01 69→26 m²) |
| Cockpit Slice 2 — approve/reject + `review_overrides.json` (FastAPI) | 🟢 GREEN | additive, needs Slice 1+1.5 stable (we're there) |
| Cockpit Slice 3 — `proposed_actions.json` + pre-SKP gate F0 | 🟢 GREEN | builds on Slice 2 |
| Multi-PDF corpus | 🔴 RED | needs Felipe to provide additional PDFs |
| Cycle 6 (Stage 1.6) — autorun inspector wiring | 🔴 RED | Stage 1.6 explicitly held |

## Operational protocol (active)

- `feedback_autonomia_operacional_protocolo.md` — GREEN/YELLOW/RED loop + auto-merge clean+green + don't ask per-PR
- `feedback_gh_first_then_manual.md` — gh CLI by absolute path is default; manual is fallback only
- `feedback_pre_existing_work_pivot.md` — preserve existing work; pivot if objective matches; only ask when discarding > preserving
- `feedback_done_is_not_stop.md` — branch verde+merged is not session end; trigger next ROI

## Tooling notes

- **gh CLI** at `C:\Program Files\GitHub CLI\gh.exe` (v2.92.0, account `fmodesto30`, scopes `repo,gist,read:org,admin:public_key`). Always invoke via absolute path + `--repo GFCDOTA/sketchup-mcp`.
- **Cockpit launch:** `pip install -e ".[cockpit]"` then `streamlit run cockpit/app.py`. The `cockpit` package is in `setuptools.packages.find` (fixed PR #68 commit `f11e13c`).
- **Cockpit demo regeneration:** `python scripts/cockpit_make_demo_pdf_underlay.py` produces the canonical Cycle-12b demo SVG with planta_74 baked in.
