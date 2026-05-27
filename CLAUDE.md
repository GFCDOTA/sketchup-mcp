# CLAUDE.md — sketchup-mcp (minimal)

> Operational note for Claude. The repo was pruned to the minimal
> "generate `.skp` from a planta consensus" pipeline. Everything
> outside that scope was removed; this file is short on purpose.

## Mission

```
consensus.json -> tools/build_plan_shell_skp.{py,rb} -> .skp + renders
```

`consensus.json` describes axis-aligned walls + openings + rooms +
soft barriers in PDF-points coordinates. The builder produces a
single-shell `.skp` with the wall shell + floors + window apertures
(3D, peitoril + verga preserved) + door/passage carves (2D
full-height).

## Canonical reference: quadrado

The quadrado fixture is the smoke gate for every change:

| Role | Path |
|---|---|
| Input consensus (1 window) | `fixtures/quadrado/consensus_with_window.json` |
| Expected shell polygon | `docs/specs/_assets/quadrado_canonical_shell_polygon.json` |
| Expected geometry report | `docs/specs/_assets/quadrado_canonical_geometry_report.json` |
| Reference render | `docs/specs/_assets/quadrado_canonical_success_render.png` |
| Spec | `docs/specs/quadrado_demo_spec.md` |

**Run it:**

```bash
python -m tools.build_plan_shell_skp \
  fixtures/quadrado/consensus_with_window.json \
  --out runs/quadrado/quadrado.skp

python tools/quadrado/render_view.py \
  runs/quadrado/quadrado.skp --out runs/quadrado/render.png
```

## Real plant: planta_74

```bash
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp
```

PDF source at repo root: `planta_74.pdf`.

## Hard rules

1. **NEVER invent walls / rooms / openings.** The consensus is the
   source of truth — if a wall isn't in `consensus.json`, it doesn't
   land in the `.skp`.
2. **NEVER carve windows full-height.** Windows MUST preserve wall
   mass below sill and above head (`build_window_aperture_3d` does
   this; doors and porta-vidro stay on the 2D full-height path).
3. **NEVER mutate input fixtures** under `fixtures/quadrado/` or
   `fixtures/planta_74/` without explicit human approval — the
   smoke tests pin against them.
4. **NEVER push to `main` directly.** Open PR `feature/<x>` or
   `chore/<x>` -> `develop`; `main` only receives `develop`.

## Tests

```bash
python -m pytest tests/ -v
```

5 canonical test files lock the contract:
- `test_quadrado_canonical_smoke.py` — the canonical success gate
- `test_wall_shell_canonical.py` — no notches / no slivers
- `test_window_aperture_contract.py` — window vs door routing
- `test_window_aperture_geometry.py` — SKP-level invariants (some skip without SU)
- `test_build_plan_shell.py` — pure-Python primitive coverage

All Python-only — no SU required for the contract suite; geometry
tests skip cleanly when no `.skp` is available.

## SketchUp setup

SU 2026 must be installed at:
`C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe`

The Ruby exporter runs as an autorun plugin from
`%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins\` — the Python
launcher writes a control file and invokes the Ruby script via SU.

## SU runner mode — DO NOT pass `--mode headless` for local builds

Mode default is `interactive` (does NOT auto-terminate SU). For local
runs (a human is at the keyboard), ALWAYS use the default — the SU
window stays open after the `.skp` is saved so you can inspect
visually.

`--mode headless` is for CI only (terminates the launched SU child
PID after the done marker fires). On a local machine it makes SU
"close by itself" the moment the build finishes, which looks like a
bug. **Never pass `--mode headless` from a developer terminal.**

```bash
# CORRECT — SU stays open after build, you can inspect
python -m tools.build_plan_shell_skp <consensus.json> --out <out.skp>

# WRONG locally — SU closes itself after build
python -m tools.build_plan_shell_skp <consensus.json> --out <out.skp> --mode headless
```
