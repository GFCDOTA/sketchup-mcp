---
description: Autonomous maintenance loop. Picks the safest next task from the roadmap, validates, and opens a PR to develop.
---

# /afk-maintain

Run autonomous maintenance safely. The user is AFK; no questions
asked. Conservative defaults always win.

## Rules (read CLAUDE.md if anything is ambiguous)

- Branch from `develop`, never `main`.
- PR target is `develop`.
- No direct commits to `main` or `develop`.
- No functional pipeline change without an explicit task PR.
- No geometry threshold change.
- No Ruby/SketchUp change unless the task is specifically a SketchUp
  validation or fix.
- Prefer docs, benchmarks, smoke gates, auditor improvements,
  and cache infrastructure.

## Sequence

1. **Sync develop**

   ```bash
   git checkout develop
   git pull origin develop
   git status -s
   ```

   If working tree dirty: bail out and report.

2. **Run the auditor**

   ```bash
   python agents/auditor/run_audit.py --out reports/
   ```

   Read `reports/repo_audit.md`. Note new findings since last run.

3. **Check CI status**

   ```bash
   gh run list --limit 5
   ```

   If `gh` not authenticated, fall back to:

   ```bash
   curl -s "https://api.github.com/repos/GFCDOTA/sketchup-mcp/actions/runs?per_page=5&branch=develop" \
     | python -c "import json,sys;[print(r['conclusion'],r['head_sha'][:7],r['display_title'][:60]) for r in json.load(sys.stdin)['workflow_runs'][:5]]"
   ```

4. **Pick the safest next task** from `docs/operational_roadmap.md` (Now > Next).
   Match against rules above. Skip anything in "Human decision required".

5. **Create branch** from develop with appropriate prefix:

   ```bash
   git checkout -b <prefix>/<slug>
   ```

6. **Implement small change** consistent with the task.

7. **Validate before commit**:

   ```bash
   python -m pytest -q --tb=line --no-header [+ same --deselect set as CI]
   python -m ruff check .
   ```

   If new failures vs baseline (200 passed / 16 failed / 2 skipped):
   - Halt
   - Document the surprise in `reports/`
   - Do NOT commit

8. **Push branch and open PR** against `develop`:

   ```bash
   git push -u origin <branch>
   gh pr create --base develop --head <branch> \
     --title "<prefix>: <description>" \
     --body "$(use the standard PR template)"
   ```

   If `gh` not authenticated: print the PR URL
   `https://github.com/GFCDOTA/sketchup-mcp/pull/new/<branch>`.

9. **Update report**:

   `reports/afk_maintenance_<timestamp>.md` with what was attempted,
   what landed, what's pending.

## When to stop

- After ONE PR opened (don't snowball).
- If the auditor reports a critical finding that needs human input.
- If CI is red on develop (don't add more PRs to a broken main).
- If the task you picked turns out to need decisions you can't make
  conservatively.

## Output format

```markdown
# AFK Maintenance Run — <timestamp>

## Pre-state
- branch: develop @ <sha>
- working tree: clean
- last CI: ✅ green (run <id>)

## Auditor findings
- N new, M resolved
- Critical: <list>

## Task picked
<from docs/operational_roadmap.md>

## Branch / PR
- branch: <name>
- PR: https://github.com/GFCDOTA/sketchup-mcp/pull/<N> (or URL to open)

## Validation
- pytest: ...
- ruff: ...

## Status
✅ Done — PR ready for human review
🟡 Halted — see reports/...
🔴 Failed — see reports/...

## Next recommended task
<from docs/operational_roadmap.md>
```
