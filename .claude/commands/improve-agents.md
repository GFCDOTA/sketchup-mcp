---
description: Propose updates to specialist agent definitions based on lessons learned. Auditor-driven, human-approved.
---

# /improve-agents

Periodically review the specialist agent definitions and propose
improvements based on what was learned in `docs/learning/`.

## Sequence

1. **Read recent lessons**:

   ```bash
   ls -t docs/learning/ | head -10
   cat docs/learning/lessons_learned.md
   cat docs/learning/failure_patterns.md
   cat docs/learning/agent_improvements.md
   ```

2. **Read the audit reports** to see what specialists missed:

   ```bash
   ls -t reports/repo_audit_*.md | head -5
   ls -t reports/coordination_*.md | head -5
   ```

3. **Compare**: did any failure pattern recur AFTER the responsible
   specialist already had a check for it? If yes, the check needs
   refinement.

4. **Draft updates** to `.claude/agents/<specialist>.md`:
   - New mandatory checks
   - New forbidden tasks
   - Refined output format
   - Updated tolerance thresholds

5. **Open a PR** (small, ONE specialist at a time):

   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b agents/improve-<specialist>-<date>
   # edit the agent file
   git add .claude/agents/<specialist>.md docs/learning/agent_improvements.md
   git commit -m "agents: refine <specialist> based on <pattern>"
   git push -u origin agents/improve-<specialist>-<date>
   ```

## Rules

- One specialist per PR. Never bulk-update agents.
- Updates must be backed by evidence (citation in `docs/learning/`).
- Forbidden tasks list grows MORE strict over time, not looser.
- Allowed-files list shrinks, not grows (specialists become more
  scoped, not broader).
- The agent's "Critical rules (duplicated)" section stays as-is or
  becomes stricter.

## Forbidden

- ❌ Don't add a NEW specialist agent in this command — that's a
  separate, dedicated PR.
- ❌ Don't bulk-update multiple agent files in one commit.
- ❌ Don't relax safety rules without explicit user approval.
- ❌ Don't merge without specialist coordination review (the
  agent-coordinator should review the PR).

## Output

Print:
- Files changed
- Lessons referenced
- PR URL
- Specialists potentially affected by the update (cascading review
  needed?)
