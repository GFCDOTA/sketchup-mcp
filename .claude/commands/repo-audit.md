---
description: Run the read-only repo auditor and review findings.
---

# /repo-audit

Run the auditor, write report, summarize.

## Sequence

1. **Run the auditor**:

   ```bash
   python agents/auditor/run_audit.py --out reports/
   ```

2. **Read the markdown report**:

   ```bash
   cat reports/repo_audit.md
   ```

3. **If there's a previous report**, save it as snapshot first:

   ```bash
   cp reports/repo_audit.md reports/repo_audit_$(date +%Y%m%dT%H%M%S).md
   ```

4. **Summarize back to the user**:
   - Total findings (NEW / RESOLVED / PERSISTING vs previous run)
   - 🔴 Critical count
   - 🟡 Attention count
   - Top 3 actionable recommendations
   - Path to full report

## What this does NOT do

- ❌ Does NOT modify any file outside `reports/`
- ❌ Does NOT touch git state
- ❌ Does NOT run pipeline code
- ❌ Does NOT install packages
- ❌ Does NOT delete files
- ❌ Does NOT create PRs

## When to invoke

- Before any refactor (capture baseline)
- After every merge (catch surprises)
- Weekly on a cron (Phase futura: workflow agendado)
- On user demand

## Recovery

The report files in `reports/repo_audit*.md` and
`reports/repo_audit*.json` are overwritten on each run. They are also
gitignored (see `reports/.gitignore`), so they never enter the repo.
To recover an old report: re-run the auditor with the same git checkout.
