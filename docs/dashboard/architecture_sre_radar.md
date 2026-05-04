# SRE Radar tab — `architecture_radar.json`

The dashboard's **SRE Radar** tab (`tools/dashboard/index.html`, `http://localhost:8765/dashboard/#radar`) answers a different question than the Roadmap tab: not "what are we shipping?" but "is the repo healthy?".

It surfaces five categories of signal, each scored 0–100, plus an aggregate `overall.health_score`:

| Score | Drives |
|---|---|
| `docs_health` | Markdown saturation + drift findings (broken refs) |
| `service_health` | Existence + `--help` probe of the registered services |
| `automation_health` | Mirrors `service_health` for now (CI presence will expand it) |
| `repo_hygiene` | Root .py count, `sys.path` hacks, hardcoded paths |
| `product_quality` | Drift + saturation as a proxy until visual SKP scoring lands |

`overall.status` derives from `health_score`:
- `≥ 80` → **healthy**
- `60–79` → **warning**
- `< 60` → **critical**

## Source of truth

The tab loads JSON in this order (silent fallback):

1. `tools/dashboard/architecture_radar.json` — generator output
2. `tools/dashboard/architecture_radar.example.json` — committed snapshot
3. Empty state with run instructions if both 404

## Generator

`scripts/dashboard/generate_architecture_radar.py` is stdlib-only and never aborts on a partial failure (sections that throw end up in `errors[]`).

```bash
# Fast path — no subprocess probes, just file walks (≈0.1s on this repo)
python scripts/dashboard/generate_architecture_radar.py --no-command-checks

# Full probe — runs each registered service with --help, ≤10s per service
python scripts/dashboard/generate_architecture_radar.py
```

CLI flags:
- `--out PATH` (default `tools/dashboard/architecture_radar.json`)
- `--repo-root PATH` (default `.`)
- `--no-command-checks` — skip the `--help` probes (use in CI to keep runs cheap)
- `--json-only` — print to stdout instead of writing to `--out`

The generator commits no files; the dashboard reads the example until you run the generator yourself or wire it into a CI step.

## What it scans

### Markdown saturation
Walks all `*.md` under the repo (excluding `vendor/`, `node_modules/`, `_archive/`, `.venv/`, dot-dirs). For each file:

| Signal | Adds |
|---|---|
| `> 1000 lines` | +35 |
| `> 500 lines` (and not crit) | +20 |
| `> 80 KB` | +10 |
| `> 5 TODO/FIXME/OUTDATED` | +10 |
| `planned` and `done` mixed | +10 |

Cap = 100. Buckets: `< 25` healthy, `25–54` warning, `≥ 55` saturated. The top 10 are shipped to the dashboard for display.

### Drift (docs ↔ code)
Picks a fixed list of authoritative docs (`CLAUDE.md`, `docs/operational_roadmap.md`, `docs/ROADMAP.md`, `OVERVIEW.md`, `tools/dashboard/README.md`), greps for `(?:tools|scripts|agents|...)/...\.(py|rb|md|json|html|yml|yaml)` patterns, and existence-checks each match. Unresolved references become `drift_findings[]` with severity `medium`.

### Service health
A literal registry inside the generator:

| Name | Path | Category |
|---|---|---|
| smoke_skp_export | `scripts/smoke/smoke_skp_export.py` | smoke |
| bench_pipeline | `scripts/benchmark/bench_pipeline.py` | benchmark |
| repo_auditor | `agents/auditor/run_audit.py` | agent |
| skp_from_consensus | `tools/skp_from_consensus.py` | sketchup |
| build_vector_consensus | `tools/build_vector_consensus.py` | pipeline |
| validator | `validator/run.py` | validator |
| main | `main.py` | pipeline |
| dashboard_index | `tools/dashboard/index.html` | dashboard |

For each: `exists` via `Path.exists()`, then optionally `help_passed` via `subprocess.run([sys.executable, path, "--help"], timeout=10)`. `--no-command-checks` skips the subprocess and reports `help_passed: null`.

### Repo hygiene
- `root_python_files`: `*.py` directly at the repo root
- `sys_path_hacks`: regex hits for `sys.path.insert(...)` / `append(...)`
- `hardcoded_paths`: regex hits for `[A-Z]:[\/](?:Users|Claude|Sketchup|SU2026)`

### Recommendations
Built from the four signals above and ranked by `(impact, effort, category)`. Each has a suggested branch name to make starting the work cheap.

## Schema (v1.0.0)

```jsonc
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601",
  "git": { "branch": "...", "commit": "abc12345" },
  "overall": { "health_score": 62, "status": "warning", "summary": "repo hygiene" },
  "scores": { "overall": 62, "docs_health": 88, "service_health": 70,
              "automation_health": 70, "repo_hygiene": 0, "product_quality": 82 },
  "markdown": { "total_files": 62, "healthy_count": 60, "warning_count": 2,
                "saturated_count": 0, "top_saturated": [/* up to 10 */] },
  "drift_findings": [
    {"doc": "OVERVIEW.md", "ref": "tools/autorun_consume.rb",
     "severity": "medium", "message": "..."}
  ],
  "services": [
    {"name": "smoke_skp_export", "path": "...", "category": "smoke",
     "exists": true, "help_passed": null, "elapsed_ms": null, "risk": "unknown"}
  ],
  "hygiene": {
    "root_python_files": ["..."], "root_python_count": 17,
    "sys_path_hacks": ["..."], "hardcoded_paths": ["..."]
  },
  "recommendations": [
    {"title": "...", "category": "documentation|service|hygiene",
     "impact": "low|medium|high", "effort": "low|medium|high",
     "risk": "low|medium|high", "suggested_branch": "...",
     "why": "...", "validation": "..."}
  ],
  "errors": [],
  "command_checks": false
}
```

## Tests

`tests/dashboard/test_generate_architecture_radar.py` ships seven structural tests (all on synthetic `tmp_path` repos, no internet, no real-repo coupling):

1. `test_generates_valid_json` — schema_version + sections present
2. `test_saturated_doc_detected` — 1500-line + TODOs + planned/done doc lands in `top_saturated`
3. `test_broken_ref_detected` — drift catches a referenced file that doesn't exist
4. `test_missing_service_marked_exists_false` — a missing path becomes `exists: false`
5. `test_no_command_checks_flag` — `--no-command-checks` does not invoke service subprocess (only `git`)
6. `test_recommendations_present_when_score_high` — saturation triggers a doc-related rec
7. `test_does_not_crash_on_missing_command` — service probes failing don't bubble up

Run them with:

```bash
pytest tests/dashboard -q
```

## Future work (not in this PR)

- Wire the generator into CI as a non-blocking step (write `architecture_radar.json` artifact)
- Have the same generator emit the four PR-1 manifests (quality_history, pipeline_timing, repo_health_history, project_status), so the example files become snapshots produced from real data on every commit
- Add SKP visual quality signals to `product_quality` (currently a proxy)
