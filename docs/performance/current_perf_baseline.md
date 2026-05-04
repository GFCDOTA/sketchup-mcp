# Pipeline Performance Baseline

> First real measurement of `scripts/benchmark/bench_pipeline.py`
> against `planta_74.pdf` on the developer machine.
> Captured 2026-05-04, branch `perf/capture-real-baseline`.

## Environment

| | |
|---|---|
| Date | 2026-05-04 |
| Branch | `perf/capture-real-baseline` |
| Python | 3.12.13 |
| Platform | Windows-11-10.0.26200-SP0 |
| PDF | `planta_74.pdf` (175,850 bytes, sha256 `81722670c0281ee4…`) |
| Bench config | `--runs 3 --warmup 1` |
| SketchUp | 2026 install at canonical path; bootstrap template auto-copied (FP-007) |
| Total wall-clock per run | ~9 s (sequential) |

The full report lives at `reports/perf_baseline.json` (gitignored,
regeneratable). The 3 raw runs and the median/min/max/CV summary
are both preserved there.

## Stage timings (median of 3 runs after 1 warmup)

| Stage | Median (s) | Min (s) | Max (s) | CV | RSS after (MiB) |
|---|---:|---:|---:|---:|---:|
| `vector_consensus` | 0.030 | 0.028 | 0.031 | 5.2% | 102.2 |
| `extract_room_labels` | 0.014 | 0.014 | 0.014 | 2.0% | 102.3 |
| `rooms_from_seeds` | 0.495 | 0.462 | 0.510 | 5.1% | 102.7 |
| `extract_openings_vector` | 0.019 | 0.019 | 0.021 | 5.0% | 101.7 |
| `render_axon_top` | 0.192 | 0.188 | 0.200 | 3.1% | 114.8 |
| `sketchup_export` | 8.006 | 8.006 | 8.007 | 0.01% | 102.2 |
| `validation` | 0.001 | 0.001 | 0.001 | 11.1% | 102.2 |
| **Total (median)** | **8.76** | | | | |

CV is the coefficient of variation (`stdev / mean`). Per the
performance specialist's threshold (`docs/learning/agent_improvements.md`
AI-003), a stage with CV > 10% should be flagged as a noisy
measurement. Only `validation` crosses that bar — but it runs in
~1 ms and the absolute jitter is sub-millisecond, so the high CV
is ruler-precision noise rather than a real performance signal.

## Observations

1. **SketchUp dominates.** `sketchup_export` is **8.0 s of the 8.76 s
   total — 91 % of wall-clock time**. Everything else combined is
   ~0.75 s. This empirically validates the constitution rule
   (CLAUDE.md §3): SketchUp must be the LAST gate, and the smoke
   harness's content-hash cache (`runs/smoke/_skp_cache.json`)
   converts the second-and-later identical export from 8 s to ~0 s
   per `docs/validation/sketchup_2026_validation.md` Run 3.
2. **`sketchup_export` CV is 0.01 %** because the cost is dominated
   by a fixed SU 2026 spawn time + the autorun plugin's own
   2-second flush wait inside `tools/skp_from_consensus.py`. Sub-second
   variation in the actual save is invisible at this scale.
3. **`rooms_from_seeds` is the second-largest stage at 495 ms.**
   The bulk is the rasterize → flood → polygonize pipeline; CV is
   tight (5 %) so the cost is consistent run-to-run.
4. **`render_axon_top` peaks RSS at ~115 MiB** (+13 MiB delta vs
   pre-render) due to matplotlib's figure machinery. Other stages
   stay flat around 100–103 MiB.
5. **`validation`'s 1 ms timing** is `validator.run.main(["--once"])`
   exiting via `SystemExit` immediately because there is no
   PNG manifest under `runs/<plan>/` to validate in CI-clean state.
   This is the documented "skipped via SystemExit ≈ ok" path in
   `bench_pipeline.py`.
6. **`vector_consensus` is 30 ms**, well under the 100 ms boundary
   that would force us to think about caching the PDF parse.

## Compared to the placeholder `perf_baseline.example.json`

The example file shipped in PR #4 contained illustrative numbers
that did not match a real run; the actual measurements are
substantially faster across the board:

| Stage | Example | Real | Delta |
|---|---:|---:|---|
| `vector_consensus` | 0.612 s | 0.030 s | **20× faster** |
| `extract_room_labels` | 0.218 s | 0.014 s | **15× faster** |
| `rooms_from_seeds` | 1.847 s | 0.495 s | **3.7× faster** |
| `extract_openings_vector` | 0.493 s | 0.019 s | **26× faster** |
| `render_axon_top` | 1.234 s | 0.192 s | **6.4× faster** |
| `sketchup_export` | (skipped) | 8.006 s | first real measurement |
| `validation` | 2.341 s | 0.001 s | n/a (validator runs different code path) |

Treat this baseline as the truth; the example file is a
documentation placeholder.

## Bugs caught while running this baseline

Three bugs in `scripts/benchmark/bench_pipeline.py` blocked the
first attempt at producing real numbers; all three are fixed in
this branch:

1. **Wrong API for every tool.** The bench tried to call
   `tools.<x>.main(argv)` on every stage, but the vector tools
   expose library functions (`build`, `extract_labels`, `detect_rooms`,
   `enrich_consensus`, `render`, `run`), not `main` callables.
   Every stage failed with `ImportError: cannot import name 'main'`,
   timing zero, and producing a 7×0 s "report".

   **Fix:** call the real functions in-process with the right
   arguments. The bench now also writes intermediate artifacts
   (`consensus_model.json`, `labels.json`) that `detect_rooms`
   and `enrich_consensus` need.

2. **SU 2026 trial Welcome dialog blocked `sketchup_export`** with
   the same root cause as `FP-007` / `LL-009`. SU launched but
   nothing wrote `out.skp` within 180 s, so the stage failed
   while consuming all the timeout budget.

   **Fix:** copy `Temp01a - Simple.skp` into the scratch dir as
   `_bootstrap.skp` before invoking `tools.skp_from_consensus.run`,
   and pass it explicitly via the `bootstrap_skp` kwarg. Same
   workaround as `gate_f` in `scripts/smoke/smoke_skp_export.py`.

3. **`UnicodeEncodeError` on Windows console** when printing the
   per-stage status markers `✓ ✗ —`. cp1252 (the Windows console
   default) cannot encode them, and the bench died before writing
   the JSON report.

   **Fix:** use ASCII markers `[OK] / [FAIL] / [SKIP]`. Cleaner
   in logs and works everywhere.

A fourth latent bug — a `ZeroDivisionError` in `_summarize_runs`
when every timing was 0 — was hit transiently while the API
mismatch was masking errors as zero-duration successes. Fixed
defensively (`statistics.mean(timings) > 0` guard).

## Reproducing this baseline

```bash
# From repo root, with venv populated (uv pip install -e ".[dev]"):
.venv/Scripts/python.exe scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --runs 3 --warmup 1 \
    --out reports/perf_baseline.json
```

Console output ends with:

```
[bench] Report written to reports/perf_baseline.json
[bench] Total stages: 7
[bench] Total time (ok stages, median of 3): 8.76s
```

Without SketchUp installed (e.g. on Linux CI), `sketchup_export`
auto-skips and the total drops to ~0.75 s.

## What this enables

- **Regression detection.** Future PRs can rerun the bench and
  compare stage timings; any stage > 20 % slower vs this baseline
  is a flag for the `performance-specialist` agent
  (`docs/learning/validation_matrix.md`).
- **Cache priority.** `sketchup_export` is by far the most
  expensive stage; the smoke harness's content-hash cache
  (`runs/smoke/_skp_cache.json`) already eliminates it on
  unchanged consensus inputs. After SU, the next-largest stage is
  `rooms_from_seeds` at 495 ms — a candidate for the
  `perf/cache-raster-stage` follow-up if iteration on
  `tools/build_vector_consensus.py` ever becomes the bottleneck.
- **CV monitoring.** All non-trivial stages are below 10 % CV, so
  median is a reliable summary statistic. The
  `performance-specialist` may downgrade verdicts to DISCUSS if
  any future run shows CV > 10 %.

## Follow-ups (not in this PR)

1. **`perf/cache-infrastructure`** — `packages/cache/` with
   `cache_key/get/set/path` (no callers yet). The numbers above
   make the case for `sketchup_export` being the first caller,
   but that work is already covered by the smoke harness's
   content-hash cache. The next-tier candidates by absolute cost
   are `rooms_from_seeds` (495 ms) and `render_axon_top` (192 ms).
2. **CI integration** — gates A–D + `vector_consensus` together
   take ~75 ms (`vector_consensus` + `extract_room_labels` +
   `rooms_from_seeds` + `extract_openings_vector` minus the
   195-ms render). A reasonable PR-time budget — could be wired
   into `.github/workflows/ci.yml` if the matplotlib import does
   not blow the install time too much.
3. **`reports/perf_baseline.example.json`** — the placeholder file
   should either be deleted or rewritten with synthetic numbers
   labelled as such, to avoid future authors comparing real runs
   against fictitious values. Tracked separately as a small
   docs-only follow-up.
