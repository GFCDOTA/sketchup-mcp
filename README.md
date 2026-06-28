# sketchup-mcp

[![ci](https://github.com/GFCDOTA/sketchup-mcp/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/GFCDOTA/sketchup-mcp/actions/workflows/ci.yml)

**PDF architectural floor plan → a faithful SketchUp `.skp` model.**

Given a `consensus.json` describing the walls, openings and rooms of an
apartment plan (in PDF-point coordinates), this project builds a SketchUp
`.skp`: a wall shell extruded to ceiling height, doors/passages carved
full-height, windows carved as 3D apertures that **preserve the sill
(*peitoril*) and lintel (*verga*)** — plus auto-rendered previews, a geometry
report, an optional auto-furnished variant, and a suite of fidelity gates.

The `.skp` is the deliverable that matters. Everything else — gates, tests,
renders, the decision oracle — exists to make that model **provably faithful to
the source PDF**.

> **About the name:** despite the `-mcp` suffix, this repo is currently a
> generation **pipeline + verification harness**, not a Model-Context-Protocol
> server. The name is historical.

| | |
|---|---|
| Version | `0.2.0` |
| Language | Python 3.11+ · Ruby (SketchUp) |
| Platform | Windows + SketchUp 2026 (the `.skp` build step) |
| Core deps | `shapely`, `pypdfium2`, `Pillow` |
| Tests | 41 Python-only contract/gate suites (no SketchUp needed) |
| License | Proprietary |

---

## Quickstart

```bash
# 1. Install (reads pyproject.toml)
pip install -e ".[dev]"

# 2. Run the contract + gate tests — Python only, no SketchUp required
python -m pytest tests/ -q

# 3. Build the canonical micro-fixture SKP  (requires SketchUp 2026)
python -m tools.build_plan_shell_skp \
  fixtures/quadrado/consensus_with_window.json \
  --out runs/quadrado/quadrado.skp

# 4. Build the real apartment (planta_74) SKP
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp

# 5. Run the deterministic fidelity gate suite (CI / pre-commit)
python -m tools.run_deterministic_gates --fixture planta_74
```

> `runs/` is **scratch** (gitignored). The canonical, shipped deliverable
> lives at `artifacts/planta_74/planta_74.skp`. See *Artifacts* below.

---

## Pipeline

```
consensus.json  (walls + openings + rooms, in PDF-point coords)
   │
   ▼
[Python] tools/build_plan_shell_skp.py
   - merge wall footprints              (shapely.unary_union)
   - canonicalise corners               (no notches / no slivers)
   - 2D carve full-height openings      (doors, passages, glazed balcony)
   - emit window apertures separately   (for the 3D post-extrude carve)
   │
   ▼
_shell_polygon.json
   │
   ▼
[Ruby/SU] tools/build_plan_shell_skp.rb   (autorun plugin)
   - extrude wall shell to ceiling height
   - 3D carve windows, preserving peitoril + verga
   - add separate floor + window-glass groups
   │
   ▼
model.skp  +  model_iso.png  +  model_top.png  +  geometry_report.json
```

---

## Fidelity gates

The hard part isn't building *a* model — it's proving the model matches the PDF.
Two layers guard that:

**Deterministic gates** — fast, objective, run in CI / pre-commit via
`tools/run_deterministic_gates.py`. Each is a standalone checker:

- `wall_exact_match_gate.py` / `position_fidelity_gate.py` — wall geometry &
  placement vs the consensus
- `railing_exact_match_gate.py` / `parapet_not_railing_fallback_gate.py` —
  railing vs solid parapet handling
- `kitchen_wall_regression_gate.py` — pins a known-good kitchen/living wall
- `soft_barrier_source_audit.py` — soft barriers only exist if sourced
- `opening_audit.py` / `opening_aperture_audit.py` / `opening_host_audit.py` —
  opening routing & host-wall correctness
- `wall_overlap_audit.py` · `render_bbox_audit.py` · `diagnose_wall_stubs.py`

**Visual review** — for changes where only the *appearance* vs the PDF can
judge correctness (the one human gate):

- `run_skp_visual_review.py` — the Visual Oracle Gate (detects floating doors,
  orphan glass, window-count mismatch, bad apertures, floor leaks)
- `visual_regression_gate.py` — PDF × BEFORE × AFTER comparison; a geometry
  change is an improvement only if AFTER reads closer to the PDF
- `pdf_overlay_verify.py` · `overlay_diff.py` · `compose_side_by_side.py`
- `negative_dogfood.py` — proves the visual gate actually catches known-bad models

> A passing pytest run, a clean exit code, or a tweaked score is **not** visual
> proof. Geometry changes must be validated against the PDF visually.

---

## Auto-furnish (interiors)

An optional layer furnishes a built shell with parametric planned furniture and
renders styled variants for human comparison:

- `furnish_apartment.py` · `furnish_plan.{py,rb}` — orchestrators
- `bedroom_designer.py` · `bedroom_layout.py` · `kitchen_layout.py` ·
  `bathroom_layout.py` — per-room layout brains
- `room_type.py` · `layout_candidates.py` · `layout_rules.py` — classification
  & rule cards (`references/design_rules/`)
- `place_bedroom_skp.py` · `place_layout_skp.{py,rb}` — placement into the `.skp`
- `make_synthetic_{bedrooms,rooms}.py` — synthetic fixtures for layout tests

---

## Decision oracle & cockpit (`localhost:8765`)

Non-trivial decisions (merge / fixture / WARN-carry) are routed to an HTTP
oracle instead of blocking on a human in chat:

- `tools/claude_bridge/` — the cockpit server (`server.py`, `dashboard.html`)
  and its launchers (`start.ps1`, `launch_cockpit.ps1`); serves `/` (dashboard)
  and `POST /ask` (the gate) on `:8765`
- `tools/ask_gpt_gate.py` · `tools/oracle_providers.py` · `gate_*.py` — the
  client + provider plumbing

The bridge runs in **mode B** (delegated autonomy): it decides the deterministic
/ technical / merge calls from evidence. The **only** human gate is
`VISUAL_REVIEW`. If `:8765` is down, the gate degrades to `SKIPPED_OFFLINE` — it
never fabricates a verdict.

---

## Repo layout

```
tools/
  build_plan_shell_skp.{py,rb}   # core: 2D shell geometry  +  3D SketchUp builder
  spatial_model.py               # spatial model helpers
  regenerate_consensus.py        # (re)derive a consensus
  su_runner_safety.py            # SU runtime-mode helper (interactive / headless)
  disarm_sketchup_autoruns.py    # clean orphan autorun plugin files
  run_deterministic_gates.py     # the runnable gate suite (CI / pre-commit)
  *_gate.py / *_audit.py         # individual fidelity gates & audits
  run_skp_visual_review.py       # Visual Oracle Gate (visual findings)
  visual_regression_gate.py      # PDF × BEFORE × AFTER comparison
  furnish_*.{py,rb} / *_layout.py / bedroom_designer.py   # auto-furnish
  promote_{artifact,canonical}.py# runs/  → artifacts/ promotion
  claude_bridge/                 # cockpit + decision oracle (:8765)
  pdf_knowledge/                 # ingest reference PDFs into a searchable index
  prompts/                       # LLM prompt templates (visual oracle, consult gate)
  quadrado/                      # render helper for the micro-fixture

fixtures/
  quadrado/consensus_with_window.json                        # canonical micro-fixture
  planta_74/consensus_with_human_walls_and_soft_barriers.json# real apartment
  synthetic_rooms/                                           # synthetic room/bedroom layout-test inputs
  visual_oracle_examples/ , visual_oracle_negative/          # visual-gate fixtures

artifacts/                       # tracked canonical deliverables
  planta_74/planta_74.skp                       # ← THE deliverable
  planta_74/planta_74_{iso,top,floors_top}.png  # auto renders
  planta_74/geometry_report.json
  review/                                        # promoted before/after evidence

tests/                           # 41 Python-only contract / gate suites
docs/                            # specs + assets
references/design_rules/         # furniture rule cards + schema
schemas/visual_findings.schema.json
runs/                            # scratch — gitignored, never committed
.claude/                         # agent operating instructions, memory, skills
.ai_bridge/                      # cross-agent handoff protocol
planta_74.pdf                    # source PDF (ground truth)
```

---

## Consensus schema (informal)

```json
{
  "wall_thickness_pts": 5.4,
  "walls": [
    {"id": "w_bottom", "start": [100, 100], "end": [213.684, 100],
     "thickness": 5.4, "orientation": "h"}
  ],
  "rooms": [
    {"id": "r_main", "name": "QUADRADO",
     "polygon_pts": [[102.7,102.7], [210.984,102.7],
                     [210.984,210.984], [102.7,210.984]]}
  ],
  "openings": [
    {"id": "win_south", "wall_id": "w_bottom",
     "kind_v5": "window", "center": [156.842, 100.0],
     "opening_width_pts": 30.0, "geometry_origin": "svg_segments"}
  ],
  "soft_barriers": []
}
```

**`kind_v5` routing** — decides how an opening is carved:

- `interior_door` / `interior_passage` / `glazed_balcony` → **2D full-height** carve
- `window` → **3D post-extrude aperture** (preserves peitoril / verga)

**`geometry_origin`** — decides *whether* to carve:

- `svg_arc` / `svg_segments` / `human_annotation` → carve
- `wall_gap` → leave alone (the gap is already in the wall data)

---

## Hard rules (for contributors & agents)

These are load-bearing — breaking one is a regression:

1. **Never invent geometry.** The consensus is the source of truth: if a wall /
   room / opening isn't in `consensus.json`, it doesn't enter the `.skp`.
2. **Never carve windows full-height.** Windows keep wall mass below the sill and
   above the lintel (3D aperture path). Doors / passages / glazed balconies use
   the 2D full-height path.
3. **Never mutate input fixtures** under `fixtures/quadrado/` or
   `fixtures/planta_74/` without explicit human approval — the smoke suite pins
   against them.
4. **`main` is never pushed directly.** Work on `feature/<x>` or `chore/<x>`
   branches off `origin/develop`; `main` only receives `develop` via merge.
5. **`--mode headless` is CI-only.** Local dev defaults to `interactive` so
   SketchUp stays open for inspection.
6. **`runs/` is scratch.** Evidence SKPs must be *promoted* to
   `artifacts/<plant>/` (see `tools/promote_artifact.py`), never committed from
   `runs/`.

Full operating context for agents lives in `.claude/` (`CLAUDE.md`, `memory/`,
`specs/`, `skills/`).

---

## Requirements

- **Python 3.11+**
- **SketchUp 2026** at `C:\Program Files\SketchUp\SketchUp 2026\` (Windows) — for
  the `.skp` build/render steps. The Python tests and gates run without it.
- `shapely`, `pypdfium2`, `Pillow` (auto-installed via `pip install -e ".[dev]"`)

## License

Proprietary © Felipe (GFCDOTA).
