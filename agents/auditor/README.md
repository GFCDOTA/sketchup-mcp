# Repo Auditor (read-only agent)

> First specialist agent of the project. Read-only — observes
> repo state, writes report, never modifies code.

## Quick start

```bash
# Run audit, write reports/repo_audit.{md,json}
python agents/auditor/run_audit.py

# Custom output directory
python agents/auditor/run_audit.py --out path/to/dir/

# JSON only (skip markdown)
python agents/auditor/run_audit.py --json-only
```

## What it checks

| Category | Source |
|---|---|
| Git status + branch + HEAD | `git status -s`, `git rev-parse` |
| runs/ subdirs + tracked files + categories | filesystem + `git ls-files runs/` |
| Ruff violations (count + by code) | `python -m ruff check . --statistics` |
| Pytest collection (count + errors) | `python -m pytest --collect-only -q` |
| Root-level Python files (suspicious if not in expected set) | `glob *.py` in repo root |
| Render scripts inventory (root, tools/, scripts/, scripts/preview/) | `glob render_*.py` |
| sys.path shims (count + sample) | `git grep -n "sys.path"` |
| subprocess usage (count + sample) | `git grep -n "subprocess\."` |
| Hardcoded paths (CI risk) | `git grep` for `C:/Users/`, `E:/Claude/`, `/home/` |
| Patches inventory (active + archived) | `glob patches/*.py` |
| Large files (> 1 MB) versioned | `git ls-files` + stat |
| TODO/FIXME/XXX markers (count + by file) | `git grep -cnE` |
| Entry points sanity (`--help` works) | direct invocation with timeout |

## What it does NOT do

- ❌ Does NOT modify any file outside `reports/`
- ❌ Does NOT run pipeline code (no `extract`, no `bench`)
- ❌ Does NOT touch git state (no commits, no branches, no fetch)
- ❌ Does NOT install packages
- ❌ Does NOT delete files
- ❌ Does NOT create PRs (out of scope for v1)

## Output

Two files in `--out` directory (default: `reports/`):

- `reports/repo_audit.md` — human-readable, sections for each category
- `reports/repo_audit.json` — machine-readable, same data structured

Both files are OVERWRITTEN on each run. For history, copy them out
manually with timestamp before next run, or use the workflow that
uploads as artifact (Phase futura).

## When to run

- Manually: any time you want a snapshot
- Pre-PR: confirm baseline before opening
- Post-merge: confirm no surprises landed
- Scheduled (Phase futura): `.github/workflows/repo-auditor.yml`
  cron weekly, uploads report as artifact

## Permissions (per `docs/agents/repo_auditor.md`)

- ✅ Can write: `reports/repo_audit.md`, `reports/repo_audit.json`
- ❌ Cannot write: anything else
- ✅ Can read: any file in repo
- ❌ Cannot create PRs (no auth in v1)
- ❌ Cannot delete files

## Contract reference

Full contract: [`docs/agents/repo_auditor.md`](../../docs/agents/repo_auditor.md)

Operating model (universal rules): [`docs/agents/agent_operating_model.md`](../../docs/agents/agent_operating_model.md)

## Limitations

1. `git grep` is pattern-based — may miss obfuscated paths
2. `--help` sanity may fail for entry points that need extra args
3. Pico de memória não medido (use `bench_pipeline.py` pra isso)
4. Não diffa contra report anterior (Phase v2)
5. Não detecta deps ausentes (Phase v2)
