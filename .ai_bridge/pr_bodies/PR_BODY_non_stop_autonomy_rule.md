# docs(claude): §17 Non-Stop Autonomy Rule — DONE IS NOT STOP

**Branch**: `docs/non-stop-autonomy-rule` → `develop`
**Commit**: `f60d99e`
**Compare URL**: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...docs/non-stop-autonomy-rule

## Summary

- Adds `CLAUDE.md §17 Non-Stop Autonomy Rule` codifying the
  user-issued behavioral rule **"DONE IS NOT STOP. DONE MEANS PICK
  NEXT HIGHEST-ROI TASK."**
- Reinforces existing §14 Autonomous Continuation Protocol with: a
  twelve-question gate that must be answered before any stop, an
  exhaustive list of real-blocker exit conditions, and an end-of-cycle
  reporting format (`Cycle Completed / Evidence / Recorded State /
  Next Highest-ROI Task / Continuing`).
- §17 operates strictly *inside* the existing safety boundary —
  §1, §2, §3, §9, the develop-first git flow, and the validation gates
  retain absolute precedence. The rule never authorizes risky actions.

The same rule is also persisted as cross-project user memory
(`feedback_done_is_not_stop.md`) so it loads automatically into every
future Claude Code session even outside this repo.

## What changed

- `CLAUDE.md` — new §17 (~80 lines, after §16 Review Frequency)
- `CLAUDE.md` — §13 Last-updated marker bumped with 2026-05-07 entry
  describing the §17 addition

## What did NOT change

- No source code, no schema, no thresholds, no Ruby/SU exporter, no
  Python tooling, no tests, no CI workflows.
- No change to §1/§2/§3 hard rules. No change to §14/§15/§16 (only
  cross-referenced).
- Markdown only diff (+83 lines, 0 deletions).

## Validation

- N/A: pure markdown change, no executable surface.
- `ruff check` not applicable (no `.py` touched).
- `pytest` not applicable (no test surface impacted).
- `git diff --stat develop...HEAD` confirms exactly 1 file changed,
  +83 / -0.

## Risks

None. The rule changes future-Claude behavior (more autonomous
continuation), but only within the safety envelope already enforced
by §1/§2/§3/§9 + hooks. Worst case: a future session continues
into a Cycle 8/9 the user did not explicitly request — recoverable
by the user invoking the explicit stop blockers (e.g., "context
limit", "human approval required").

## Rollback

```bash
git push origin --delete docs/non-stop-autonomy-rule  # after merge: revert
git revert <merge-sha>                                 # post-merge full rollback
```

## Next steps

After merge, the rule is in force. The follow-up branches already
queued in `.ai_bridge/TODO_NEXT.md` (`feature/micro-truth-expand-planta-74-cycle7`
and a clean cherry-pick of the AI Bridge scaffolding) should land in
order, then Cycle 8 (RuboCop) or the SUITE 01 polygon-oversize bug.
