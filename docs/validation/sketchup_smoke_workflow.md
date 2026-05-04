# SketchUp Smoke Workflow

> Companion to `scripts/smoke/smoke_skp_export.py`. Documents the
> gate contract, the CLI, the cache, and the typical invocations.
> The constitution rule (CLAUDE.md §3) is enforced here:
> **SketchUp is the LAST gate, never the first**.

## Why this exists

Spawning SketchUp 2026 costs 5–90 seconds. Iterating on a small fix
shouldn't require a coffee break. The smoke harness gates the
expensive step behind cheap ones:

```
A → B → C → D → E → F → G → H
prep   read  shape preview cache SU   .skp   reports
                                      check valid
```

Any FAIL short-circuits to H so a report is always written.

## Gates

| Gate | Name | Cost | What it does |
|---|---|---|---|
| A | Preparation | <1 s | Make `out_dir`, resolve sketchup.exe (env or default). |
| B | Acquire consensus | <1 s | Load `consensus_model.json`, hash it. |
| C | JSON structural | <1 s | Walls/rooms/openings shape sanity. |
| D | Preview PNG | 2–4 s | `tools.render_axon` for top + axon (no SU). |
| E | Hash + cache | <1 s | Build cache key from consensus + skp source. Compare to last marker. |
| F | Export .skp | 5–90 s | `tools.skp_from_consensus` (skipped on `--skip-skp` or cache hit). |
| G | Validate .skp | <1 s | File exists; size > 1 KiB. |
| H | Reports | <1 s | Write `sketchup_smoke_report.{json,md}`; refresh cache marker. |

The harness exits 0 if every non-skipped gate passes, 1 otherwise.

## CLI

```
python scripts/smoke/smoke_skp_export.py \
    [--consensus PATH]      \
    [--out-dir DIR]         \
    [--sketchup PATH]       \
    [--plugins DIR]         \
    [--timeout SECS]        \
    [--skip-skp]            \
    [--force-skp]           \
    [--open]
```

| Flag | Default | Meaning |
|---|---|---|
| `--consensus` | `runs/vector/consensus_model.json` | Path to consensus JSON. |
| `--out-dir` | `runs/smoke/<UTC ts>` | Per-run artifact dir. |
| `--sketchup` | env `SKETCHUP_EXE` or `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe` | SU executable. |
| `--plugins` | (none) | Forwarded to `tools.skp_from_consensus`. |
| `--timeout` | 180 | SU export timeout, seconds. |
| `--skip-skp` | off | Run A–E + H only. No SU spawn. |
| `--force-skp` | off | Bypass cache hit. Always run F. |
| `--open` | reserved | Hook for future "leave SU open after save"; currently no-op. |

`--skip-skp` and `--force-skp` come from `LL-008` (always offer both).

## Typical invocations

### Dev loop on a vector consensus

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --skip-skp
```

Cheap gates only. Reports appear in `runs/smoke/<ts>/`.

### First export of a new consensus

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json
```

Will spawn SU for F because the cache marker either doesn't exist or
disagrees with the new content hash.

### After fixing the Ruby exporter, force a re-export

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --force-skp
```

`tools/consume_consensus.rb` is in the cache key, so its content hash
already invalidates the marker — but `--force-skp` makes the intent
explicit when iterating.

### CI / Linux

CI does not have SketchUp installed, so always pass `--skip-skp`:

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --skip-skp
```

The harness fails A on Linux without `--skip-skp`, by design.

## Cache key

The cache key is `SHA256(consensus_sha || sha(skp_from_consensus.py) || sha(consume_consensus.rb))`.

If any of those files changes, the key changes and the cache misses.
This catches Ruby fixes (`commit 7fbd531` style — parapet filter)
without needing the developer to remember to invalidate.

The cache marker lives one level up from the per-run directory:

```
runs/smoke/_skp_cache.json
runs/smoke/<ts>/sketchup_smoke_report.{json,md}
runs/smoke/<ts>/preview_top.png
runs/smoke/<ts>/preview_axon.png
runs/smoke/<ts>/<model>.skp
```

`_skp_cache.json` is small (< 1 KiB) and only written when the run
ends in `verdict=pass` AND F actually produced (or hit on) a `.skp`.

## Reports

`sketchup_smoke_report.md` is meant for humans:

```markdown
# SketchUp Smoke Report
- consensus: `runs/vector/consensus_model.json`
- out_dir: `runs/smoke/20260503T120000Z`
- consensus sha256: `a1b2c3d4e5f6...`
- cache_key: `f6e5d4c3b2a1...`
- cache_hit: false
- started: 2026-05-03T12:00:00Z
- finished: 2026-05-03T12:00:42Z
- verdict: **PASS**

## Gates
| Gate | Status | Message |
|---|---|---|
| A. Preparation       | PASS | out_dir=..., sketchup=... |
| B. Acquire consensus | PASS | loaded consensus_model.json (180 KiB) |
| C. JSON structural   | PASS | walls=33, rooms=11, openings=12 |
| D. Preview PNG       | PASS | rendered top + axon previews |
| E. Hash + cache      | PASS | cache miss; cache_key=f6e5d4c3b2a1 |
| F. Export .skp       | PASS | exported model.skp |
| G. Validate .skp     | PASS | .skp size 142,336 bytes |
| H. Reports           | PASS | wrote sketchup_smoke_report.{json,md} |
```

`sketchup_smoke_report.json` mirrors the same data structurally.

## Bootstrap .skp template (FP-007)

`tools.skp_from_consensus` already passes a positional `.skp` to SU
to dodge the SU 2026 trial Welcome dialog. If `out_dir` is empty and
no template is present, supply one with:

```bash
cp "/c/Program Files/SketchUp/SketchUp 2026/SketchUp/resources/en-US/Templates/Temp01a - Simple.skp" \
   runs/smoke/<ts>/_bootstrap.skp
```

The harness ignores files starting with `_bootstrap` when picking
the produced `.skp` for gate G.

## Failure modes and what they mean

| Symptom | Likely cause | Where to look |
|---|---|---|
| A FAIL — sketchup not found | running on Linux/CI without `--skip-skp`, or trial install moved | `--sketchup`, env `SKETCHUP_EXE` |
| B FAIL — consensus not found | wrong path or build_vector_consensus didn't run | re-run vector pipeline |
| C FAIL — missing/invalid keys | upstream produced a malformed consensus | `tools/build_vector_consensus.py` |
| D FAIL — render_axon error | matplotlib missing in the venv | `pip install -e ".[dev]"` |
| F FAIL — rc != 0 | SU error; check stderr in the report | `runs/smoke/<ts>/sketchup_smoke_report.md` |
| F FAIL — no .skp produced | autorun plugin didn't fire (Welcome dialog?) | `tools/autorun_*.rb`, `LL-009`, `FP-007` |
| G FAIL — size < 1 KiB | empty .skp written | enable inspector, see `tools/inspect_walls_report.rb` |

## Extending

- New cheap gate (e.g. metric diff against baseline): insert between
  C and D, follow the `GateResult` contract.
- New SU-dependent gate (e.g. inspector report): insert between G
  and H, gate behind `--skip-skp` and `cache_hit`.
- Cache key change: extend `CACHE_KEY_INPUTS`; bump nothing else,
  the next run misses by definition.

## Related

- `CLAUDE.md` §3 — the rule.
- `LL-001`, `LL-008`, `LL-009` — lessons.
- `FP-001`, `FP-007` — failure patterns.
- `DL-005` — decision log.
- `.claude/commands/validate-skp.md` — the slash-command playbook
  that drives this harness during sessions.
