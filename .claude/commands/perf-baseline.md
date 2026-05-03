---
description: Capture pipeline performance baseline using scripts/benchmark/bench_pipeline.py.
---

# /perf-baseline

Run the benchmark on canonical PDFs and update the baseline. Read-only
over pipeline code.

## Sequence

1. **Pick PDF**: prefer `planta_74.pdf` if present; else accept
   `--pdf <path>`. If no canonical PDF: bail and document the blocker.

2. **Run benchmark**:

   ```bash
   python scripts/benchmark/bench_pipeline.py \
     --pdf planta_74.pdf \
     --runs 3 --warmup 1 \
     --label "baseline-$(git rev-parse --short HEAD)" \
     --out reports/perf_baseline.json
   ```

3. **Inspect output**:

   ```bash
   jq '.summary' reports/perf_baseline.json
   ```

4. **Compare with previous baseline** (if any):

   ```bash
   diff <(jq '.summary' reports/perf_baseline_prev.json) \
        <(jq '.summary' reports/perf_baseline.json)
   ```

5. **Write baseline doc**: update or create
   `docs/performance/current_perf_baseline.md` with:
   - Date, commit, machine, Python version
   - PDF used + SHA256
   - Stage timings (median/min/max/CV)
   - Bottleneck identification
   - Optional opportunities ranking

## What this does NOT do

- ❌ Does NOT modify pipeline code
- ❌ Does NOT modify thresholds
- ❌ Does NOT optimize anything
- ❌ Does NOT commit `reports/perf_baseline.json` (gitignored)
- ❌ Does NOT spawn SketchUp unless --pdf has a special preset

## When SketchUp would be invoked

The benchmark includes a `sketchup_export` stage. It is automatically
skipped if SU2026 is not installed at the default path. To force-skip
even when installed: temporarily move the binary or pass `--skip-skp`
(if the bench script supports it; check `bench_pipeline.py --help`).

## Output

If you want to commit a baseline change (because algorithm or env
changed), open a small PR:

```bash
git checkout develop
git checkout -b perf/update-baseline-$(date +%Y%m%d)
# the doc is the only thing committed
git add docs/performance/current_perf_baseline.md
git commit -m "perf: update baseline after <commit/event>"
git push -u origin perf/update-baseline-$(date +%Y%m%d)
gh pr create --base develop --head perf/update-baseline-... \
  --title "perf: update perf baseline doc" --body "..."
```

`reports/perf_baseline.json` itself stays local (gitignored).
