# SketchUp 2026 Validation

> End-to-end exercise of `scripts/smoke/smoke_skp_export.py` against
> `runs/vector/consensus_model.json` on a real Windows SU 2026
> install. Captures the run, two bugs found, and the recommended
> follow-ups.

## Environment

| | |
|---|---|
| Date | 2026-05-04 |
| Branch | `validate/sketchup-2026-export` |
| Consensus | `runs/vector/consensus_model.json` (46,240 bytes, sha256 `5e8263cf72af...`) |
| Python | 3.12.13 (uv-managed) |
| SketchUp | `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe` (canonical install) |
| Plugins dir | `%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins` (default) |
| Bootstrap template | `…\Templates\Temp01a - Simple.skp` (auto-copied by gate F) |
| OS | Windows 11 Pro 10.0.26200 |

The previous-iteration baseline for `planta_74` in the vector pipeline
is **33 walls, 11 rooms, 12 openings** (CLAUDE.md §10). Gate C reads
back exactly those numbers, confirming the consensus is unchanged.

## Runs captured

Three invocations exercised every code path of the harness.

### Run 1 — `--skip-skp` (cheap gates only)

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --skip-skp
```

| Gate | Status | Notes |
|---|---|---|
| A. Preparation | PASS | out_dir created; sketchup not required |
| B. Acquire consensus | PASS | loaded 46,240 bytes |
| C. JSON structural | PASS | walls=33, rooms=11, openings=12 |
| D. Preview PNG | PASS | top + axon rendered (~285 KiB axon, ~71 KiB top) |
| E. Hash + cache | PASS | cache miss; cache_key=`70dfe49ba280…` |
| F. Export .skp | SKIP | `--skip-skp` |
| G. Validate .skp | SKIP | `--skip-skp` |

Duration: **~3 s**. Verdict: PASS. Out dir:
`runs/smoke/20260504T004928Z/`.

### Run 2 — `--force-skp --timeout 240` (full pipeline)

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --force-skp \
    --timeout 240
```

| Gate | Status | Notes |
|---|---|---|
| A | PASS | sketchup resolved |
| B | PASS | same consensus |
| C | PASS | 33/11/12 |
| D | PASS | previews regenerated |
| E | PASS | `--force-skp`; cache_key=`70dfe49ba280…` |
| F. Export .skp | PASS | exported `model.skp` (SU launched, autorun fired, quit clean) |
| G. Validate .skp | PASS | `.skp` size **59,068 bytes** |
| H. Reports | PASS | `sketchup_smoke_report.{json,md}` + cache marker refreshed |

Duration: **~13 s** (SU spawn + autorun export + 2-s flush wait).
Verdict: PASS. Out dir: `runs/smoke/20260504T010231Z/`.

Artifacts produced:

| File | Size | Source |
|---|---|---|
| `model.skp` | 58 KiB | Final SketchUp model (the deliverable) |
| `model.skb` | 0 B | SU's auto-backup (empty on first save, harmless) |
| `_bootstrap.skp` | 169 KiB | Template copy to dodge SU 2026 trial Welcome dialog (FP-007) |
| `preview_top.png` | 71 KiB | Top view, matplotlib (gate D) |
| `preview_axon.png` | 284 KiB | Axonometric, matplotlib (gate D) |
| `sketchup_smoke_report.md` | 907 B | Human-readable report |
| `sketchup_smoke_report.json` | 2.5 KiB | Machine-readable report |
| `skp_from_consensus.log` | 256 B | Sidecar log of SU subprocess (rc + stdout + stderr) |

The cache marker `runs/smoke/_skp_cache.json` was rewritten with the
`70dfe49ba280…` key pointing at this run.

### Run 3 — re-run without flags (cache hit)

```bash
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json
```

| Gate | Status | Notes |
|---|---|---|
| A | PASS | |
| B | PASS | |
| C | PASS | |
| D | PASS | previews regenerated unconditionally (cheap) |
| E | PASS | **cache hit**; previous run `20260504T010231Z` produced `model.skp` |
| F | SKIP | cache hit |
| G | SKIP | cache hit; previous `.skp` not re-validated |
| H | PASS | report written; cache marker untouched |

Duration: **~1 s**. Verdict: PASS. Out dir: `runs/smoke/20260504T010321Z/`.

This is the AFK / dev-loop default behavior: cheap gates run, SU
stays out of the way, the harness still publishes a report so the
artifact trail is continuous.

## Bugs found and fixed in this branch

### Bug 1 — `gate_f` passed `--out` as a directory

`tools.skp_from_consensus` interprets `--out` as a `.skp` **file**
path (it calls `out_skp.parent.mkdir(...)` and `out_skp.unlink()`).
The harness was forwarding the per-run directory, which already
existed thanks to gate A. The unlink-on-directory raised an
unhandled exception inside `tools.skp_from_consensus` and the
harness reported it as gate F failing immediately.

**Fix:** gate F now constructs `out_dir / "model.skp"` and forwards
that. Gates G and H reference back via `args._skp_path`.

### Bug 2 — SU 2026 trial Welcome dialog blocked the autorun plugin

After Bug 1 was fixed, the second failure mode was the documented
`FP-007` / `LL-009`: SU launched, sat on the Welcome dialog, never
ran the autorun plugin, and exited with code 1 once the parent's
poll loop timed out. `tools.skp_from_consensus` already passes a
positional `.skp` to dodge the dialog **if one exists in
`out_skp.parent`** — but the per-run dir is fresh and empty, so the
auto-pick found nothing.

**Fix:** gate F best-effort copies the SU 2026 template
`Temp01a - Simple.skp` into `out_dir/_bootstrap.skp` before
invoking `tools.skp_from_consensus`. The pre-existing auto-pick
sees it and uses it. Run 2 above produced `model.skp` cleanly on
the first attempt.

### Side improvement — sidecar log file

Gate F now writes the full subprocess output (rc, stdout, stderr)
to `out_dir / skp_from_consensus.log` and adds it to `g.artifacts`.
The `g.message` only carries the last 3 lines of output, so when
debugging future failures the full log is one click away rather
than reconstructed from a 300-char truncated message.

## What still works around the SU 2026 trial

- The Welcome dialog block is bypassed via the bootstrap template
  copy. This is a workaround, not a fix — if SU 2026 ever ships a
  paid version that doesn't show the dialog, the bootstrap copy
  becomes a no-op. The runtime cost is one `shutil.copy2` of a
  ~170 KiB file per run, negligible.
- The autorun plugin in `%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins`
  is the operative piece. The harness does not install or remove
  it; it expects it to already be in place. (See
  `tools/autorun_*.rb` for the plugin source.)

## Recommended follow-ups (not in this PR)

1. **`feature/skp-carve-openings`** — `consume_consensus.rb` still
   does not carve doors/windows out of the wall geometry. The
   `model.skp` produced today has the door arcs as separate visual
   geometry but the wall extrusion is solid. This is documented
   in `CLAUDE.md` §10 and stays in the operational roadmap's
   `Later` bucket.
2. **`feature/window-detector`** — `extract_openings_vector.py`
   only emits doors, not windows. The exterior wall openings on
   the right (BANHO 01) currently render as door arcs.
3. **`docs/validation/sketchup_smoke_visual_qa.md`** — a checklist
   for the rare cases when a human eyeball is needed (e.g., per
   the visual checklist in `.claude/commands/validate-skp.md`).
4. **CI integration of `--skip-skp`** — gates A–E are deterministic
   and free; running them on every PR (with `--skip-skp`) would
   catch consensus regressions without spawning SU. Not in this
   PR; would want a dedicated workflow file.

## Reproducing this validation

```bash
# 1. From repo root, ensure venv exists and deps are installed:
uv venv --python 3.12
uv pip install -e ".[dev]"

# 2. Cheap sanity (no SU):
.venv/Scripts/python.exe scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --skip-skp

# 3. Full pipeline (SU launches, ~13 s):
.venv/Scripts/python.exe scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --force-skp \
    --timeout 240

# 4. Cache hit verification (re-run, ~1 s, F/G should SKIP):
.venv/Scripts/python.exe scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json
```

The reports under `runs/smoke/<ts>/sketchup_smoke_report.md`
mirror the tables above. The cache marker
`runs/smoke/_skp_cache.json` is the single source of truth for
"have we already exported this consensus".

## Verdict

The harness is operational on a real SU 2026 install. The cheap
gates produce honest signals. The expensive gate is correctly
gated by content hash. Two real bugs were caught by exercising
the contract end-to-end — both fixed in the same branch. The
operational roadmap can promote `validate/sketchup-2026-export`
out of the Now bucket and into Recently shipped after this PR
merges.
