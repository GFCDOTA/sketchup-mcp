# Agent Improvements

> Adjustments to specialist agent definitions based on observed
> performance. Each entry references the agent file affected and the
> incident that motivated the change.

## AI-001 — `repo-auditor` should compare against previous report

**Date:** 2026-05-03 (proposed) → 2026-05-04 (applied)
**Agent:** `.claude/agents/repo-auditor.md`
**Incident:** First version produced a report but didn't track
NEW vs RESOLVED vs PERSISTING findings. Without a delta, every run
looks the same to a reviewer.
**Improvement:** Add a "Diff vs previous run" section to the report
output. Findings are derived from the per-section report into a
flat list with stable `(kind, key)` identity, then compared via set
arithmetic against the most recent prior `repo_audit_<ts>.json`
snapshot. The auditor now writes both the canonical
`repo_audit.{md,json}` and a timestamped snapshot per run.
**Status:** Applied in v2 (PR `agents/repo-auditor-v2`).
`load_findings_from_snapshot` includes a v1 fallback that
re-derives findings from old reports without a `findings` array,
so the diff works across the v1→v2 boundary.

## AI-002 — `sketchup-specialist` needs reproduce hint when no inspect_report

**Date:** 2026-05-03
**Agent:** `.claude/agents/sketchup-specialist.md`
**Incident:** Reviewing a SU exporter PR without a fresh
`inspect_report.json` in the PR was leaving the verdict at
🟡 DISCUSS without telling the author what to do.
**Improvement:** Output format now includes "Reproduce" code block
with the exact commands to generate a fresh inspect_report locally.
**Status:** Applied in v1.

## AI-003 — `performance-specialist` should report CV explicitly

**Date:** 2026-05-03
**Agent:** `.claude/agents/performance-specialist.md`
**Incident:** Some bench runs had high variance (CV > 10%) and the
verdict was being computed off the median without flagging that
the measurement was noisy.
**Improvement:** Always report CV in the output table. If
CV > 10%, downgrade verdict to DISCUSS regardless of median delta.
**Status:** Documented in agent file under "Stability of measurement".

## AI-004 — `geometry-specialist` should ignore baseline-known-failures

**Date:** 2026-05-03
**Agent:** `.claude/agents/geometry-specialist.md`
**Incident:** Geometry reviews were flagging failures in
`tests/test_text_filter.py` etc. as PR regressions even when the PR
didn't touch `classify/service.py`.
**Improvement:** Section "Known baseline failures to ignore" added
explicitly. Tests in BASELINE_KNOWN_FAILURES set are not regression
signals unless the PR touches `classify/service.py`.
**Status:** Applied in v1.

## AI-005 — `ci-guardian` proposes via PR draft, never direct

**Date:** 2026-05-03
**Agent:** `.claude/agents/ci-guardian.md`
**Incident:** None observed yet, but high-risk: an agent with write
permission to `.github/workflows/` could break CI silently if it
committed directly.
**Improvement:** Allowed-files entry for ci-guardian explicitly
states "ONLY via PR draft, never direct commit to main". Belt-and-
suspenders: the `pre_bash_guard.py` hook also blocks pushes to main.
**Status:** Applied in v1.

## AI-006 — `docs-maintainer` cannot touch CLAUDE.md without approval

**Date:** 2026-05-03
**Agent:** `.claude/agents/docs-maintainer.md`
**Incident:** None observed yet, but high-risk: docs maintainer
could rewrite CLAUDE.md and silently change rules every other agent
inherits from.
**Improvement:** CLAUDE.md and AGENTS.md explicitly forbidden in
the agent file. To propose changes, open a PR draft and ping the
user in a comment.
**Status:** Applied in v1.

## AI-007 — `agent-coordinator` should route by file path patterns

**Date:** 2026-05-03 (initial design)
**Agent:** `.claude/agents/agent-coordinator.md`
**Incident:** Initial design didn't have a clear routing table —
the coordinator would have to "guess" which specialist to invoke.
**Improvement:** Added explicit "Specialist routing table" mapping
file path patterns to agent names. Multi-category PRs invoke
multiple specialists. Disagreements escalate to user with the more
conservative verdict winning.
**Status:** Applied in v1.

## AI-008 — All agents must have "Critical rules (duplicated)" section

**Date:** 2026-05-03
**Agent:** all `.claude/agents/*.md`
**Incident:** Subagents may be invoked without the full CLAUDE.md
in their context (depending on Claude Code internals + compaction
state).
**Improvement:** Every agent file ends with "Critical rules
(duplicated)" containing the 3-5 most important constraints. That
way, even a context-stripped agent retains the safety guarantees.
**Status:** Applied in v1.

## AI-009 — repo-auditor must use ls-remote for remote claims (2026-05-XX)

**Date:** 2026-05-04
**Trigger:** During the 2026-05-04 multi-specialist audit, the auditor concluded that `develop` did not exist remote-side based only on `git branch -a` output, when in fact the local clone hadn't fetched.
**Pattern:** Any agent claim about the existence/state of a remote ref MUST be backed by `git ls-remote --heads origin <name>` (or equivalent), not by inspecting local refs only.
**Action:** Update `.claude/agents/repo-auditor.md` to add this rule under "Mandatory checks". (NOT done in this PR — Stream A is docs-only. Tracked as a follow-up: `agents/repo-auditor-remote-check`.)

## Template for new entry

```markdown
## AI-NNN — <change in one line>

**Date:** YYYY-MM-DD (or YYYY-MM-DD (proposed))
**Agent:** `.claude/agents/<name>.md`
**Incident:** <what happened that revealed the gap>
**Improvement:** <what was changed in the agent definition>
**Status:** Applied | Pending | Reverted (with reason)
```

## Process for proposing improvements

1. Observe the gap (review report, audit finding, user complaint).
2. Document it here as `AI-NNN` (proposed).
3. Open a PR via `/improve-agents` slash command — that command
   ensures one specialist per PR, evidence cited, scope tight.
4. Specialist coordination review on the PR.
5. After merge, update status here to "Applied".
