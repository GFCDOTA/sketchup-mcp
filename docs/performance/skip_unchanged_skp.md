# Skip SketchUp Export When Consensus Unchanged

> Implements the most-impactful follow-up from
> `docs/performance/current_perf_baseline.md`: short-circuit the
> 8-second SU spawn when `consensus_model.json` has not changed.

## Why this matters

The real perf baseline shows `sketchup_export` is **8.0 s of the
8.76 s pipeline total — 91% of wall-clock**. Every other stage
combined runs in ~0.75 s. Re-exporting the same `.skp` from an
unchanged consensus is pure waste.

A content-hash skip eliminates this cost on repeat runs, which is
the dominant case during dev loops, smoke verification, and
benchmark iteration.

## Where the skip lives

`tools/skp_from_consensus.py` is the single bridge between Python
callers and SketchUp 2026. The skip lives there so every caller —
the smoke harness (`scripts/smoke/smoke_skp_export.py`), the
benchmark (`scripts/benchmark/bench_pipeline.py`), and the
standalone CLI — gets the benefit automatically.

## Mechanics

### Sidecar metadata file

After a successful export, `run()` writes a sidecar at
`<out_skp>.metadata.json` with:

```json
{
  "schema_version": "1.0.0",
  "consensus_sha256": "5e8263cf72af7cdb87edf68d0d09195267ae28e90f17738bac264c9e83cf303c",
  "skp_path": "C:\\...\\skip_demo.skp",
  "created_at": "2026-05-04T02:09:06Z",
  "git_commit": "2099de7104da6e34874f61c4438dbb23d11dfe5c",
  "sketchup_path": "C:\\Program Files\\SketchUp\\SketchUp 2026\\SketchUp\\SketchUp.exe",
  "command": "C:\\...\\SketchUp.exe C:\\...\\_bootstrap.skp"
}
```

The fields cover the user-requested set (`consensus_hash`,
`skp_path`, `created_at`, `git_commit`, `sketchup_path`, `command`)
plus a `schema_version` for forward compatibility.

### Skip decision

On entry to `run()`:

```
sha = sha256(consensus_model.json)
if not force_skp and out_skp exists and sidecar exists
   and sidecar.consensus_sha256 == sha:
       print("[skip] ... unchanged consensus")
       return {ok=True, skipped=True, ...}
```

Three guards: the existing `.skp`, the sidecar, and the hash match.
Any one missing → fall through to the normal SU launch path.

### Force flag

Bypasses the skip on demand:

- Function: `run(..., force_skp=True)`
- CLI: `python -m tools.skp_from_consensus ... --force-skp`
- Smoke harness: `--force-skp` propagates through gate F
- Bench: not yet exposed as a flag (baseline runs always start
  from a clean scratch dir, so the skip only fires on rerun with
  the same `--scratch` path).

### Stale-state cleanup

A previous run that wrote the `.skp` but crashed before writing
the sidecar would leave a `.skp` with no metadata. Behavior:
no skip (`should_skip()` requires both files), so the next run
re-exports cleanly. Conversely, an aborted re-export deletes both
the old `.skp` and the old sidecar before launching SU; mid-export
crashes leave neither file rather than a stale pair.

## End-to-end demonstration

Three sequential calls against the same `--out` path:

| Run | Flags | Behavior | Wall-clock | `.skp` size |
|---|---|---|---|---|
| 1 | (default) | fresh export, SU spawn | **8 s** | 59,054 B |
| 2 | (default) | `[skip]` SKIPPED_UNCHANGED_CONSENSUS | **<1 s** | 59,054 B (preserved) |
| 3 | `--force-skp` | SU spawn again, sidecar refreshed | **8 s** | 59,057 B |

Reproduces with:

```bash
.venv/Scripts/python.exe -m tools.skp_from_consensus \
    runs/vector/consensus_model.json \
    --out /tmp/skip_demo.skp \
    --sketchup "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe" \
    --timeout 60
# Run twice. Second run prints:
#   [skip] /tmp/skip_demo.skp unchanged consensus (sha 5e8263cf72af); skipped SU launch
#   SKIPPED_UNCHANGED_CONSENSUS sha=5e8263cf72af
```

## Bench integration

The bench's `sketchup_export` stage now reports `status="skipped"`
when `run()` short-circuits. The summary's `status_counts` reflects
this directly, and the `skip_savings_s` field (when timings exist)
estimates wall-clock saved.

Two consecutive bench invocations against the same `--scratch` dir:

| | Wall-clock | sketchup_export per run | Status |
|---|---|---|---|
| Invocation 1 (fresh) | **18 s** | 8.03 s | `ok ×2` |
| Invocation 2 (cached) | **2 s** | 0.006 s | `skipped ×2` |
| **Speedup** | **9×** | **1300×** | |

Reproduces with:

```bash
# First, fresh:
.venv/Scripts/python.exe scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf --runs 2 --warmup 0 \
    --scratch reports/_skip_demo_bench

# Second, cached (same --scratch):
.venv/Scripts/python.exe scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf --runs 2 --warmup 0 \
    --scratch reports/_skip_demo_bench
```

The cached invocation's report shows `"sketchup_export": {"status_counts": {"skipped": 2}, ...}`.

## Layered cache (defense in depth)

The smoke harness (`scripts/smoke/smoke_skp_export.py`) already had
its own cache layer at gate E (`runs/smoke/_skp_cache.json`). This
new sidecar metadata is at a different scope:

| Layer | Scope | Key |
|---|---|---|
| Smoke harness gate E | per smoke-run dir | `SHA(consensus + skp_from_consensus.py + consume_consensus.rb)` |
| `skp_from_consensus` sidecar | per `.skp` file | `SHA(consensus_model.json)` |

Both layers can hit and skip independently. The smoke layer
catches "we ran this exact pipeline already" (covers code drift in
the exporter scripts); the sidecar layer catches "this `.skp` is
already valid for this consensus". When both layers exist, the
smoke check fires first (gate F isn't even invoked); when only the
sidecar applies (e.g. someone running `tools.skp_from_consensus`
directly), the inner skip still saves the 8 s.

## Trade-offs

- **Cache key only covers `consensus_model.json` content.** It does
  NOT cover changes to `consume_consensus.rb` or the autorun plugins.
  That's a deliberate split with the smoke harness's outer key,
  which DOES include those. Standalone `tools.skp_from_consensus`
  callers who edit the Ruby exporter MUST pass `--force-skp` or
  delete the sidecar to re-export.
- **No locking.** Concurrent invocations on the same `--out` path
  may both write the sidecar; the last writer wins. Not a real
  concern for this single-user dev workflow.
- **Per-run scratch dirs in the bench.** `bench_pipeline.py` defaults
  to a fresh `reports/_bench_scratch/` per invocation. The skip
  only fires when the scratch is reused via `--scratch`. Acceptable
  — by-default the bench measures the worst case, and reuse is
  opt-in.

## Follow-ups (not in this PR)

1. **`perf/cache-infrastructure`** — `packages/cache/` with
   `cache_key/get/set/path` helpers. Could subsume both the smoke
   layer and the sidecar in a single content-addressed store. Not
   needed yet — both layers are tiny and self-contained.
2. **Cache-key extension to include `consume_consensus.rb`** —
   small change in `_compute_cache_key` (smoke) plus a parallel
   field in the sidecar. Defer until someone hits a stale-export
   bug; the smoke harness already handles this case for the
   common path.
3. **`bench --use-cache <dir>`** — explicit flag to make the bench
   measure cached behavior. Today it works via `--scratch` reuse,
   which is implicit.

## Related

- `docs/performance/current_perf_baseline.md` — the data point
  that motivated this work.
- `docs/validation/sketchup_2026_validation.md` — first run that
  confirmed the smoke harness's outer cache works.
- `CLAUDE.md` §3 — "SketchUp is the LAST gate" — which this PR
  upgrades to "SketchUp is the LAST gate, AND we don't even
  invoke it twice for the same input".
