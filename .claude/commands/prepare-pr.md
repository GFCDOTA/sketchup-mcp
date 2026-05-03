---
description: Compose a compliant PR body for the current branch following the standard template.
---

# /prepare-pr

Generate the standard PR body for the current branch.

## Sequence

1. **Verify current branch is not main/develop**:

   ```bash
   git branch --show-current
   ```

   If on `main` or `develop`: bail with error.

2. **Check working tree is clean**:

   ```bash
   git status -s
   ```

   If dirty: ask the user to commit/stash first.

3. **Compute diff stats vs develop**:

   ```bash
   git fetch origin develop
   git diff origin/develop...HEAD --stat
   git log origin/develop..HEAD --oneline
   ```

4. **Detect scope**:
   - Files touched matched against the specialist routing table in
     `.claude/agents/agent-coordinator.md`
   - PRs touching `tools/*.rb` or `tools/skp_from_consensus.py` →
     route to sketchup-specialist
   - PRs touching `extract/`, `classify/`, `topology/`, `model/`,
     `roi/`, `ingest/` → route to geometry-specialist
   - Etc.

5. **Compose the PR body** following the standard template:

   ```markdown
   ## Summary
   <1-3 bullets — what this PR does>

   ## What changed
   <list of files + brief reason for each>

   ## What did NOT change
   <explicit confirmation of scope>
   - no algorithm change
   - no schema change
   - no Ruby/SketchUp change
   - no threshold change
   <or whichever apply>

   ## Validation
   ```bash
   <commands run + expected output>
   ```

   ## Risks
   <what could go wrong, and what we did to mitigate>

   ## Rollback
   ```bash
   git revert <commit-hash>
   # or
   git push origin --delete <branch>
   ```

   ## Next steps
   <optional follow-up PRs>

   ## Specialist agents to invoke
   <list from step 4>

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```

6. **Open the PR** (if `gh` is authenticated):

   ```bash
   gh pr create --base develop --head <branch> \
     --title "<prefix>: <title>" \
     --body "$(cat <<'EOF'
   <generated body>
   EOF
   )"
   ```

   If `gh` not authenticated: print URL
   `https://github.com/GFCDOTA/sketchup-mcp/pull/new/<branch>`.

## Rules

- Always against `develop` (never `main`).
- Title prefix matches branch prefix (`feature:`, `fix:`, `chore:`,
  `docs:`, `perf:`, `refactor:`, `test:`, `agents:`, `tooling:`).
- Title under 70 chars; details go in the body.
- Never use `--no-verify` or `--no-gpg-sign`.
- If specialist agents flagged a regression, the PR body must
  acknowledge it explicitly (do not hide).

## Output

Print the PR URL or the manual-create URL. Done.
