# Roadmap tab — `project_status.json`

The dashboard's **Roadmap** tab (`tools/dashboard/index.html`, accessible at `http://localhost:8765/dashboard/#roadmap`) renders a project cockpit answering "where are we, what's done, what's blocked, what's next" without forcing the reader to open `docs/operational_roadmap.md`, `docs/ROADMAP.md`, `CLAUDE.md`, and `docs/performance/current_perf_baseline.md` separately.

## Source of truth

The tab loads JSON in this order (silent fallback, no errors thrown):

1. `tools/dashboard/project_status.json` — real, hand-edited or generator-produced
2. `tools/dashboard/project_status.example.json` — committed example, always present
3. Empty state with instructions if both fail

There is **no generator yet**. The `.example.json` is hand-edited; treat it as the canonical source until a generator lands. Keep its content honest — do not invent metrics, only cite what's in the codebase or in `docs/performance/current_perf_baseline.md`.

## Schema (v1.0.0)

```jsonc
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601",
  "project": {
    "name": "...",
    "mission": "...",
    "current_focus": "..."
  },
  "summary": {
    "overall_status": "in_progress | healthy | warning | blocked",
    "current_phase": "...",
    "next_recommended_action": "...",
    "main_risk": "..."
  },
  "metrics": {
    "ci_status": "green | red | unknown",
    "smoke_gate": "available | broken | unknown",
    "sketchup_export_bottleneck_percent": 91,
    "cached_rerun_time": "<1s",
    "last_measured_total_s": 8.76,
    "last_baseline_date": "YYYY-MM-DD"
    // any extra numeric metric is rendered as a card
  },
  "lanes": [
    {
      "id": "platform | product | governance | ...",
      "title": "Display name",
      "status": "done | in_progress | mostly_done | blocked",
      "items": [
        {"title": "...", "status": "done | in_progress | next | blocked", "blocked_by": "optional"}
      ]
    }
  ],
  "blocked": [
    {"title": "...", "reason": "...", "needed_decision": "..."}
  ],
  "next_steps": ["ordered list of strings"]
}
```

## How to edit

1. Open `tools/dashboard/project_status.example.json`.
2. Update lanes / metrics / next_steps based on the latest reality (cross-check `docs/operational_roadmap.md` and `docs/ROADMAP.md`).
3. Bump `generated_at` to the edit date.
4. `git add` the file and ship it in the same PR as the change it describes.

Do **not** fabricate metrics — pull numbers from `docs/performance/current_perf_baseline.md`, `reports/repo_audit.json`, or actual command runs.

## Status colors (UI)

- `done` → green (`--ok`)
- `in_progress` → blue (`--accent`)
- `mostly_done` → blue
- `next` → muted gray (`--muted`)
- `blocked` → orange/red (`--warn` / `--err`)

## Companion manifests (charts)

Three additional manifests live next to `project_status.example.json` and each powers a chart on the Roadmap tab. Same loading rule: `<name>.json` real (optional) → `<name>.example.json` (committed) → empty state.

### `quality_history.example.json`

Walls / rooms / openings per run, sorted by mtime — feeds the "Qualidade da extração ao longo dos runs" line chart.

```jsonc
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601",
  "points": [
    {"run": "baseline_2026-04-29", "mtime": "ISO-8601", "walls": 230, "rooms": 30, "openings": 71}
  ]
}
```

Source of truth (when a generator is wired): aggregate `runs/*/observed_model.json`. Counts derive from `len(walls)`, `len(rooms)`, `len(openings)`.

### `pipeline_timing.example.json`

Per-stage median seconds for the horizontal bar chart "Tempo por estágio do pipeline" — bars dominating ≥80% of the total are highlighted in red.

```jsonc
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601",
  "source": { "baseline_timestamp": "...", "git_commit": "abc12345", "label": "..." },
  "total_median_s": 9.005,
  "stages": [
    {"stage": "sketchup_export", "elapsed_s_median": 8.0269, "elapsed_s_max": 8.0286, "cv": 0.0003, "status_ok": 2, "pct_of_total": 89.1}
  ]
}
```

Source of truth: `reports/perf_baseline.json` → `summary` (one entry per stage with `elapsed_s_median`, `elapsed_s_max`, `elapsed_s_cv`, `status_counts.ok`).

### `repo_health_history.example.json`

Ruff violations + pytest collected + `runs/` subdir count across `reports/repo_audit_*.json` snapshots. Two y-axes (left = ruff, right = pytest/runs) so they share one chart without flattening each other.

```jsonc
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601",
  "points": [
    {"timestamp": "ISO-8601", "commit": "abc12345", "ruff_violations": 146, "pytest_collected": 317, "pytest_errors": 0, "runs_subdir_count": 19}
  ]
}
```

Source of truth: every `reports/repo_audit_*.json` (sorted by `timestamp`).

## Next step in this dashboard initiative

A second PR (`dashboard/architecture-sre-radar`) adds an **SRE Radar** tab on top of this same JSON-loading pattern. The Radar reuses `_fetchJsonOrNull` and the lane/card/chart style established here, but adds a Python generator (`scripts/dashboard/generate_architecture_radar.py`) that scans the repo for documentation saturation, drift, service health, and architectural debt — so it can update its own JSON automatically. The same generator can later emit the three companion manifests above to replace these hand-edited examples.
