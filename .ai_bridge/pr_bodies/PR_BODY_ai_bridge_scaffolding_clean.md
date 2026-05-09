# docs(ai-bridge): persistent agent communication via .ai_bridge/

**Branch**: `docs/ai-bridge-scaffolding-clean` → `develop`
**Commits**: `2250cdf` `1d57647` `146cab5` `a95176e` (4)
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/ai-bridge-scaffolding-clean

> **Replaces** the original `feature/ai-bridge-scaffolding` PR which
> was stacked on top of PR #52 (gate G2). This branch is a clean
> cherry-pick off `develop` containing only the .ai_bridge/ commits.

## Summary

- Bootstraps the `.ai_bridge/` protocol — a per-repo directory of
  versioned markdown files used by Claude / GPT / future agents to
  preserve continuity across sessions and across multiple AI tools.
- Includes a fully populated initial state seeded from this repo as
  of 2026-05-07, plus three live updates (validation cycle, Cycle 7
  ground-truth expansion, surfaced SUITE 01 polygon issue).
- Pure documentation. No source, schema, threshold, Ruby/SU,
  test, or CI change.

## What changed

- `.ai_bridge/README.md` — protocol overview
- `.ai_bridge/PROJECT_CONTEXT.md` — stable project context (mission,
  pipeline, paths, hard rules, canonical commands, baseline)
- `.ai_bridge/CURRENT_STATE.md` — branch + last objective + open problems
- `.ai_bridge/HANDOFF.md` — most-recent session's exit state
- `.ai_bridge/TODO_NEXT.md` — ROI-ordered queue
- `.ai_bridge/GPT_REQUESTS.md`, `GPT_RESPONSES.md`,
  `DECISIONS.md`, `LESSONS.md`, `QUESTIONS_FOR_NEXT_AGENT.md` —
  templates + current-state seed entries

## What did NOT change

- No `.py`, no `.rb`, no schema, no threshold.
- Specifically does **not** include the gate G2 commit (`2417a20`)
  that the previous stacking accidentally pulled in. Gate G2 lives
  exclusively in PR #52 where it belongs.

## Validation

- N/A: pure markdown / directory creation.
- `git diff --stat develop...HEAD` → 13 files, **all under `.ai_bridge/`**
  (10 protocol files + 3 PR body artifacts under `.ai_bridge/pr_bodies/`).
- `git diff --name-only develop...HEAD | grep -v '^.ai_bridge/'` →
  empty (confirms no source contamination).

## Risks

- None for the codebase. Risk is meta: future agents must avoid
  putting credentials or large logs into `.ai_bridge/` (per the
  protocol's own §safety). The user's cross-project memory rule
  `feedback_ai_bridge_protocol.md` already encodes this.

## Rollback

```bash
git push origin --delete docs/ai-bridge-scaffolding-clean
git push origin --delete feature/ai-bridge-scaffolding   # contaminated original
# post-merge:
git revert <merge-sha>
```

## Why this PR exists in addition to / instead of the original

The original `feature/ai-bridge-scaffolding` was created on top of
the `feature/smoke-promotes-inspector-v2-gate` (PR #52) branch instead
of off `develop`, so a PR from it would have mixed two ideas
(violates CLAUDE.md §4 "one PR = one idea"). This branch resolves
that by cherry-picking only the four `.ai_bridge` commits onto a
fresh branch off `develop`.

After this PR merges, the original `feature/ai-bridge-scaffolding`
branch should be deleted (local + remote) per CLAUDE.md §0.

## Next steps

After merge:

1. Delete `feature/ai-bridge-scaffolding` (local + remote).
2. Future sessions read `.ai_bridge/HANDOFF.md` first as documented
   in `.ai_bridge/README.md`.
3. Pending work surfaced in `TODO_NEXT.md` includes the SUITE 01
   oversized-polygon investigation and Cycle 8 (RuboCop CI).
