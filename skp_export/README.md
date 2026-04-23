# skp_export — observed_model.json -> .skp bridge

Two-sided bridge that turns the pipeline's `observed_model.json`
(schema 2.x) into a SketchUp `.skp` model.

```
                Python CLI                               Ruby (SketchUp)
observed_model.json  ->  validate schema  ->  locate SketchUp  ->  build walls
                                                                        |
                                                                        v
                                                                   plant.skp
```

## Quick start

Dry run (no SketchUp required, validates schema and counts entities):

```bash
python -m skp_export --run-dir runs/proto/p12_v1_run --dry-run
```

Prints a single grep-friendly line:

```
walls=33 rooms=18 openings=6 peitoris=2 junctions=65
```

Full run (auto-detects SketchUp):

```bash
python -m skp_export --run-dir runs/proto/p12_v1_run \
    --door-lib path/to/Porta_70_80cm.skp \
    --output-name plant.skp
```

## CLI options

| flag | default | notes |
| --- | --- | --- |
| `--run-dir` | required | directory containing `observed_model.json` |
| `--door-lib` | `None` | `.skp` file with the door component (falls back to procedural door if omitted) |
| `--dry-run` | off | validate + summarise, skip SketchUp |
| `--output-name` | `plant.skp` | name of the output file inside `--run-dir` |
| `--sketchup-exe` | auto | override `SketchUp.exe` path (auto: registry + Program Files) |
| `--timeout` | `90` | seconds to wait for SketchUp before killing the subprocess |
| `--verbose` / `-v` | off | debug logging to stderr |

## Exit codes

| code | meaning |
| --- | --- |
| 0 | success (dry-run, or SketchUp wrote the `.skp`) |
| 1 | general error — missing `--run-dir`, IO, bad `--sketchup-exe` path |
| 2 | SketchUp not found on this host. Re-run with `--dry-run` for **Path B** (CI). |
| 3 | `observed_model.json` failed schema v2 validation |

Ruby-side errors propagate through the subprocess exit code (anything
outside [0, 3] is a Ruby failure; see stderr for the traceback).

## Schema v2

Lives at `skp_export/schema/observed_model_v2.json`. Validated with
`Draft7Validator` from [`jsonschema`](https://pypi.org/project/jsonschema/).

Required top-level keys: `schema_version`, `run_id`, `source`,
`bounds`, `roi`, `walls`, `junctions`, `rooms`, `scores`, `metadata`,
`warnings`, `openings`, `peitoris`.

Each wall carries `wall_id`, `page_index`, `start`, `end`,
`thickness`, `orientation`, `source`, `confidence`. Each opening
carries `opening_id`, `orientation`, `center`, `width`, `wall_a`,
`wall_b`, `kind`. Rooms carry `room_id`, `polygon`, `area`,
`centroid`.

Add `jsonschema>=4` via `requirements-dev.txt` — it is not in the
runtime `requirements.txt` so the production image stays lean.

## Locating SketchUp

`bridge.locate_sketchup()` probes, in order:

1. `HKLM\SOFTWARE\SketchUp\SketchUp 20XX\InstallLocation` (and
   `HKCU`) for every year from 2025 down to 2016.
2. `%ProgramFiles%\SketchUp\SketchUp 20XX\SketchUp.exe` (and
   `%ProgramW6432%`).

Returns the first hit. Returns `None` outside Windows.

## Path A vs Path B

* **Path A (default)** — SketchUp detected, Python invokes
  `SketchUp.exe -RubyStartup skp_export/main.rb -- --run-dir DIR ...`.
  The Ruby side builds the model and writes `<run_dir>/plant.skp`.
* **Path B (fallback)** — when SketchUp is missing, the CLI prints a
  warning and returns exit 2. CI / Linux builds are expected to run
  with `--dry-run` instead.

## Ruby scaffold (unchanged from V6.1)

The 6 Ruby files preserve the V6.1-validated pipeline:

- `main.rb` — entry point, orchestrates walls / openings / doors
- `rebuild_walls.rb` — extrudes walls as solid boxes; optional carve
- `apply_openings.rb` — `apply_cut_into_wall` + `apply_existing_gap`
- `place_door_component.rb` — `scale_x = wall_thickness / 0.19`,
  transformation order `trn * rot * scale_trn`
- `validate.rb` — post-build `.skp` sanity check
- `lib/json_parser.rb` — schema 2.x loader
- `lib/units.rb` — px <-> m (DPI 150, 0.0066 m/px calibration)

## Troubleshooting

- **Exit 3, `walls: <root>: 'walls' is a required property`** — the
  pipeline produced an incomplete `observed_model.json`. Regenerate
  with `run_p12.py` / `run_planta74.py` and confirm the scores are
  non-zero.
- **Exit 2, no SketchUp** — install SketchUp 2021+ or pass
  `--sketchup-exe` explicitly.
- **Ruby raises `no active SketchUp model`** — SketchUp could not
  open a new model. Ensure it is not already running with an
  unsaved document.
- **Door component not scaling** — confirm the component's native
  bounding-box X is 0.19 m, as baked into
  `place_door_component.rb`.

## CI (F13)

`make all` mirrors the full developer gate: lint + pytest + multiplant
validation + skp dry-run + smoke extraction of both fixtures.

- Local regression: `make test` (expects >=149 pass / 15 pre-existing fail).
- Schema fixtures: `make validate` — emits `runs/validation/report_*.csv`.
- Path B dry-run: `make skp-dryrun` (skipped if `skp_export/__main__.py` is
  not committed yet on this branch).

The GitHub Actions workflow (`.github/workflows/ci.yml`) replicates the
same four stages and runs on every `pull_request` plus pushes to
`fix/**` / `feat/**` / `main`. The `skp-dryrun` job detects the Python
CLI via `hashFiles` and skips gracefully when F8 hasn't landed, so the
workflow stays green during staged rollouts.

Troubleshooting Path B on CI:

- If the dry-run exits non-zero with a schema error, regenerate the
  fixture with `python run_p12.py` / `python run_planta74.py` — the Ruby
  side is never touched in Path B.
- `jsonschema` is pinned via `requirements-dev.txt`; the CI job installs
  it automatically when that file exists.
- `PYTHONPATH` is set to the repo root in the workflow env so
  `python -m skp_export` resolves the package when invoked from a
  shallow clone.

## V6.1 baseline (preserved)

- Component: `Porta de 70/80cm.skp` (native bbox X = 0.19 m)
- Walls alvenaria (0.14 m): `scale_x = 0.737`
- Walls drywall (0.075 m): `scale_x = 0.395`
- Transformation order: `trn * rot * scale_trn` (scale **first**)
- Rotation: `-90 deg` around X to stand the door upright
- Y flip: PDF Y grows downward, SketchUp Y grows north
