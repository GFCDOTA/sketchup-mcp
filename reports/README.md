# reports/

> **Status:** Canonical
> **Type:** Directory README — explains layout, not policy
> **Updated:** 2026-05-24
> **Policy:** [`../docs/REPO_HYGIENE.md`](../docs/REPO_HYGIENE.md) §5 (tracked vs ignored)

Per-cycle reports produced by the repo-governance tooling. Layout:

| Path | Owner | Lifecycle |
|---|---|---|
| `current/repo_health_report.md` | `tools/repo_health_gate.py` | overwrite each run |
| `current/project_state_report.md` | `scripts/project_state_check.py` | overwrite each run |
| `current/*.json` | gate JSON dumps | **gitignored** (markdown is the canonical record) |
| `archive/YYYY-MM/<name>.md` | `tools/repo_health_gate.py --mode fix` | rolled in monthly; preserved as forensic history |
| `perf_baseline.example.json` | benchmarks | template file, hand-edited |

## How to refresh

```bash
python tools/repo_health_gate.py --mode audit
python scripts/project_state_check.py > reports/current/project_state_report.md
```

(Or in CI, see `.github/workflows/repo_health.yml`.)

## Rotation rule

`current/*.md` files older than 30 days get moved to
`archive/YYYY-MM/` by `repo_health_gate.py --mode fix` (detector
W004 / fixer F-OLD-REPORT). Manual rotation is also fine — every
move is logged in the next gate report.
