# scripts/

Utility runners that live outside the regular `pytest` suite.

## `validate_multiplant.py` — F11 multi-plant validation

Regression gate for the whole PDF pipeline. Every planta under active care owns a
`<name>_expected.json` fixture in `runs/validation/` that freezes what the
pipeline should produce for it. The runner walks all fixtures, runs
`model.pipeline.run_pdf_pipeline` for each, compares counts + connectivity +
optional topology-snapshot hash, and writes a timestamped CSV report.

### Running

```bash
E:/Python312/python.exe scripts/validate_multiplant.py
```

Exit codes:

- `0` — every fixture passed every gate (and determinism check stayed stable).
- `1` — at least one fixture failed or the determinism hash drifted.
- `2` — misconfiguration (missing fixture dir, bad JSON, PDF not found on disk).

Useful flags:

- `--skip-pipeline` — just print the fixture inventory without running anything.
  Handy to confirm what the runner will hit.
- `--no-determinism-check` — skip the 3x stability rerun for the GOLDEN plant.
- `--determinism-check NAME` — target a different fixture for the 3x rerun.
  Automatically no-ops when the selected fixture has no
  `expected_topology_snapshot_sha256` (range-style fixtures don't have a
  determinism contract to enforce).

### Fixture formats

The runner supports two styles in `runs/validation/*_expected.json`:

**GOLDEN (exact counts + hash gate)** — use for frozen, known-clean inputs like
`p12_red`:

```json
{
  "pdf_filename": "p12_red.pdf",
  "pdf_sha256_optional": null,
  "expected_walls": 33,
  "expected_walls_tolerance": 2,
  "expected_rooms": 19,
  "expected_rooms_tolerance": 0,
  "expected_openings": 6,
  "expected_openings_tolerance": 1,
  "expected_largest_ratio_min": 1.0,
  "expected_orphan_node_max": 0,
  "expected_topology_snapshot_sha256": "39b4138f4fd5613ed897824657b0329445d2eb332a6a1d810da75933ba4b5ce3",
  "notes": "baseline limpo (pré-vermelhado), gate GOLDEN"
}
```

**RANGE (healthy bands, no hash gate)** — use for noisy real plants still being
calibrated, like `planta_74`:

```json
{
  "pdf_filename": "planta_74.pdf",
  "expected_walls_range": [120, 240],
  "expected_rooms_range": [11, 35],
  "expected_openings_range": [8, 30],
  "expected_largest_ratio_min": 0.90,
  "expected_orphan_node_max": 5,
  "notes": "planta real noisy, faixas amplas até F6 calibrar"
}
```

A fixture can omit any gate — absent keys mean "don't check this dimension".

### Adding a new plant

1. Drop the PDF somewhere on-disk — the runner searches first the repo root
   (for general fixtures like `planta_74.pdf`) and then `runs/proto/` (for
   protocol-specific bodies like `p12_red.pdf`). If you need another search
   location, extend `PDF_SEARCH_DIRS` in the script.
2. (Optional) If the plant needs a `peitoris` array the same way p12 does, add
   the JSON alongside the PDF and register the mapping in `PEITORIS_MAP` at the
   top of `validate_multiplant.py`.
3. Run the pipeline once manually to collect the numbers you want to freeze:
   ```bash
   E:/Python312/python.exe -c "
   import json, sys; sys.path.insert(0, '.')
   from pathlib import Path
   from model.pipeline import run_pdf_pipeline
   out = Path('runs/_tmp_new_plant'); out.mkdir(parents=True, exist_ok=True)
   res = run_pdf_pipeline(
       pdf_bytes=Path('path/to/new.pdf').read_bytes(),
       filename='new.pdf',
       output_dir=out,
   )
   obs = res.observed_model
   conn = obs['metadata']['connectivity']
   print('walls', len(obs['walls']))
   print('rooms', len(obs['rooms']))
   print('openings', len(obs.get('openings', [])))
   print('ratio', conn['largest_component_ratio'])
   print('orphan', conn['orphan_node_count'])
   print('hash', obs['metadata']['topology_snapshot_sha256'])
   "
   ```
4. Create `runs/validation/<plant_name>_expected.json` using either format
   above. Start RANGE-style unless you know the plant is already stable enough
   to freeze exact counts.
5. Rerun `scripts/validate_multiplant.py` and confirm the new fixture PASSes.

### Report format

The runner writes `runs/validation/report_YYYYMMDD_HHMMSS.csv`. Columns:

| Column | Meaning |
| --- | --- |
| `plant_name` | Fixture stem (e.g. `p12_red`). |
| `pdf_filename` | PDF referenced by the fixture. |
| `walls_got` / `walls_ok` | Observed wall count + whether it hit the gate. |
| `rooms_got` / `rooms_ok` | Observed room count + whether it hit the gate. |
| `openings_got` / `openings_ok` | Observed opening count + gate status. |
| `ratio_got` / `ratio_ok` | `largest_component_ratio` + whether it met the min. |
| `orphan_got` / `orphan_ok` | `orphan_node_count` + whether it stayed within max. |
| `hash_got` / `hash_ok` | `topology_snapshot_sha256` + whether it matched the frozen value (GOLDEN-only — `hash_ok=True` when no hash gate is configured). |
| `overall_ok` | AND of all gate columns. Tied to the runner's exit code. |
| `error` | Populated when the pipeline itself raised (missing PDF, etc.). |
| `failures` | Semicolon-separated human-readable reasons for any `overall_ok=False`. |

### Interpreting failures

- **`hash_got` drifted on a GOLDEN fixture** — the topology/classify/openings
  layer changed in a way that affects p12. Investigate the diff before
  refreezing the hash; drifting the GOLDEN hash is a decision, not a side
  effect.
- **`walls_ok=False` + `rooms_ok=True`** — extraction changed segment counts
  without reshaping the room graph. Often dedup/merge tweaks.
- **`ratio_ok=False`** — walls fragmented into disconnected components again;
  check `connectivity_report.json` in `runs/` for the offending run.
- **`orphan_ok=False`** — hardening regressed on noise filtering for the noisy
  range-style plants.

The determinism line in stdout distinguishes a real regression from a flaky
hash (`divergent hashes: [...]`) — report that separately if it shows up.
