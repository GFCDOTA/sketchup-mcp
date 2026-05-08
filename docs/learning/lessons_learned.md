# Lessons Learned

> Operational lessons from real sessions. Each lesson is a positive
> rule. Add a new entry every time we discover "this should always
> happen this way." Anti-patterns go to `failure_patterns.md`.

## LL-012 — Fix tooling access before falling back to manual

**Date:** 2026-05-08
**Context:** Mid-session, opened the Cycle 12 cockpit PR via the
"compare URL → user pastes manually in browser" workflow because
`gh: command not found` in the Bash that Claude Code runs in. Felipe
correctly pushed back: doing it manually means the next PR hits the
same wall. The fix is to find the tool, not work around it.

**Diagnosis:** `gh.exe` was installed at `C:\Program Files\GitHub CLI\`
and authenticated via keyring (account `fmodesto30`, scope `repo`),
but Git Bash didn't have that directory on its PATH.

**Rule:** When a CLI is "missing" from the environment, the first
move is `where`/`Get-ChildItem` to the standard install paths
(`C:\Program Files\<Tool>\`, `%LOCALAPPDATA%\Programs\<tool>\`,
`scoop\shims\`). If the binary exists, invoke via absolute path
(`"/c/Program Files/GitHub CLI/gh.exe"`) and pass cwd-independent
flags (`--repo <owner>/<name>`). Document the path so the next
session doesn't repeat the diagnostic. **Don't fall back to manual
workflow because the binary lookup failed.**

**Automation:** cross-project memory file
`~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`;
referenced from `MEMORY.md` so every Claude session sees it before
attempting a PR action.

**Generalization:** the pattern applies to any external CLI on
Windows + Git Bash where PATH inheritance into the harness shell is
unreliable — `python.exe`, `node.exe`, `docker.exe`, etc. Probe
before assuming.



## LL-001 — SketchUp is the last gate, never the first

**Date:** 2026-05-03
**Context:** During autonomous loops, SketchUp was being launched
on every change to `consume_consensus.rb` or to the consensus, even
when the consensus was identical to a previous run.
**Rule:** Validate JSON + render PNG previews + compute consensus
hash BEFORE launching SU. Cache by hash. Honor `--force-skp` to
bypass.
**Automation:** `scripts/smoke/smoke_skp_export.py` enforces gate
order A→H. See `docs/validation/sketchup_smoke_workflow.md` for the
gate contract, CLI options, and typical invocations.

## LL-002 — Always reproduce CI failure locally in a fresh venv

**Date:** 2026-05-03
**Context:** A PR passed pytest in the dev's Windows venv but failed
in ubuntu CI because `Pillow` was a phantom transitive dep on Windows
and not in `pyproject.toml`. Two CI iterations were burned before
reproducing locally caught it in one shot.
**Rule:** When a PR touches deps, CI workflow, or anything that
crosses platform boundaries, simulate the CI environment locally
first:
```bash
python -m venv /tmp/ci_test_venv
/tmp/ci_test_venv/bin/python -m pip install -e ".[dev]"
/tmp/ci_test_venv/bin/python -m pytest [+ same --deselect set as CI]
```
**Automation:** Could become a make target or a `/validate-ci-locally`
slash command.

## LL-003 — Develop-first git flow

**Date:** 2026-05-03
**Context:** Direct PRs against `main` made it hard to batch-validate
multiple features before promoting to release. A merge to main
sometimes broke CI which then broke other in-flight PRs.
**Rule:** All PRs go to `develop`. Only `develop → main` PRs touch
main. Documented in `docs/git_workflow.md` and `CLAUDE.md` §0.

## LL-004 — Ruff rules: select, never autofix repo-wide

**Date:** 2026-05-03
**Context:** A previous attempt at `ruff --fix .` would have changed
~93 fixable violations across many files at once, mixing import
sort, unused removals, and style. Hard to review and risky.
**Rule:** Configure ruff with conservative selects (E, F, I), keep
ruff in CI as `continue-on-error: true` until baseline is cleaned in
**dedicated, scoped PRs**. Never mass-autoformat.

## LL-005 — Backup textually before mass branch cleanup

**Date:** 2026-05-03
**Context:** Cleaning up branches that aren't pushed/merged risks
losing 80+ commits silently. When deleting `feat/svg-ingest` was
considered, a worktree had uncommitted work.
**Rule:** Before any branch cleanup, write a textual backup with
each branch name + last SHA + last commit subject + unique commit
count vs main. Save outside the repo (e.g.
`D:/Claude/scratch/<repo>-branch-cleanup-backup.txt`). Allows
recovery via `git fetch origin <sha>` later.

## LL-006 — Claude Code constitution lives in CLAUDE.md, not in chat

**Date:** 2026-05-03
**Context:** Sending a giant prompt every session works but is
fragile — context compaction can lose the rules mid-session.
**Rule:** Persistent rules go to `CLAUDE.md` and `.claude/agents/`.
Subagents include their critical rules in their own files (not just
referencing CLAUDE.md), so they survive compaction.

## LL-007 — Specialist agents are read-only by default

**Date:** 2026-05-03
**Context:** Giving an agent both "find the issue" and "fix it"
permissions creates a path for silent damage. Reviewers can't tell
what the agent decided vs what the human approved.
**Rule:** Specialists (geometry, openings, sketchup, performance,
validator) write reports under `reports/` and comment on PRs. They
do NOT modify code. Only `docs-maintainer` (narrowly) and
`ci-guardian` (via PR draft only) edit shared files.

## LL-008 — Always provide a `--skip-skp` and `--force-skp` pair

**Date:** 2026-05-03
**Context:** During development of the smoke harness, having only
"always run SketchUp" or "always skip" made testing painful.
**Rule:** Any tool that can launch SketchUp must accept both
`--skip-skp` (run cheap gates only) and `--force-skp` (override the
hash-based cache). The default behavior is "smart skip" (cache by
content hash).

## LL-009 — Bootstrap .skp template solves SU2026 Welcome dialog

**Date:** 2026-05-03
**Context:** SU2026 trial showed a Welcome dialog when launched
without a positional `.skp`, blocking the autorun plugin from ever
firing. Saw multiple "exited prematurely (code=0/1)" failures.
**Rule:** When launching SU 2026 via `tools.skp_from_consensus`,
always pass a positional `.skp`. The launcher already does this:
it picks the most recent `.skp` in the output dir; if none, copy a
template like
`C:\Program Files\SketchUp\SketchUp 2026\SketchUp\resources\en-US\Templates\Temp01a - Simple.skp`
to the output dir as `_bootstrap.skp`.

## LL-010 — Multi-specialist parallel audit produces higher-quality synthesis (2026-05-XX)

**Date:** 2026-05-04
**Context:** During the 2026-05-04 panorama generation, eight specialist analyses ran in parallel (instead of one single-pass review). Each surfaced different gaps: the validator GT leak (validator-specialist), CI Ruby syntax blindness (ci-guardian), 17 root-of-repo orphan scripts (repo-auditor), schema drift between raster and vector openings (geometry-specialist), DL-006 status drift (docs-maintainer).
**Lesson:** For non-trivial repo audits, prefer N parallel specialist passes over a single sequential review. The synthesis surfaces issues no single pass would have caught.
**Caveat:** Only applies to AUDIT/REVIEW work where each specialist has a distinct lens. For execution/coding tasks, parallel agents on overlapping code paths cause merge conflicts — keep them disjoint.

## LL-011 — Empirical evidence overrides initial parametric choice (Cycle 8b, 2026-05-08)

**Date:** 2026-05-08
**Context:** Cycle 8b promote-concave-hull-default decision. User authorized `ratio = 0.30` based on architectural intuition + LLM (`planta-assistant`) recommendation. First implementation run revealed `ratio=0.30` cuts INTO valid rooms (A.S. 10.39 → 1.35 m², COZINHA 11.34 → 5.23 m², TERRACO TECNICO 5.77 → 0.69 m²). Three rooms failed GT ranges. Re-ran with `ratio=0.50`: 10/11 rooms in range, only TERRACO TECNICO marginally below floor (1.61 vs 2.0).
**Lesson:** When a parametric decision is initially made on theoretical reasoning (LLM "more correct" + user "biggest fix"), **execute the smallest reproducible run and let empirical numbers override**. The protocol path was honored: I asked the LLM, applied the answer, INVESTIGATED the resulting failures (not "maquiar"), found the root cause (algorithm aggression), tested the alternative (`ratio=0.50`), and chose the option with better empirical evidence. Recorded the override in `.ai_bridge/GPT_RESPONSES.md` so the audit trail is intact.
**Caveat:** This loop only works if the gate (in this case, fidelity engine + GT ranges) is honest. Had I been allowed to "maquiar" the GT ranges to match `ratio=0.30`'s output, the empirical signal would have been silenced. CLAUDE.md §1 + the operational protocol's RED rule against "alterar baseline para fazer passar" are what made the override visible.
**See also:** `FP-012` (the bug being fixed); `feedback_autonomia_operacional_protocolo.md` (the GREEN/YELLOW/RED loop that authorized the override).
