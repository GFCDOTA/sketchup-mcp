# AGENT_COORDINATION — Multi-Agent Coordination Protocol

> **Status:** Canonical (2026-05-24).
> **Type:** Permanent operational protocol for sessions where multiple
> Claude (or human) agents may be acting on the same repo concurrently.
> **Companion docs:** [`../CLAUDE.md`](../CLAUDE.md) §22 (short rule),
> [`HANDOFF.md`](HANDOFF.md) (canonical onboarding),
> [`REPO_HYGIENE.md`](REPO_HYGIENE.md) (file policy),
> [`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) (the public coordination channel).
> Canonical reference; do not duplicate this content elsewhere — link here.

---

## 0. Root rule — read this first

**Multiple autonomous agents MUST NEVER share the same physical
working directory.** This is not a guideline; it is the architectural
precondition for everything else in this protocol.

The default isolation mechanism is `git worktree add` — one worktree
per agent / per session. Worktrees share the same `.git/objects`
(no disk waste) but have independent index, HEAD, and working tree
(no race conditions on `git checkout`, `git add`, `git commit`).

```bash
# canonical worktree layout for sketchup-mcp
D:\Claude\worktrees\sketchup-agent-a
D:\Claude\worktrees\sketchup-agent-b
D:\Claude\worktrees\sketchup-claude-main
# ... one per agent / session
```

**Lock files (`.coord/active_branch.txt`, advisory marker files in
`.ai_bridge/`, etc.) are advisory only.** They are useful as
human-readable signals about who is doing what, but they do NOT
prevent two agents from racing on the same `.git/index`. The
architectural isolation (worktrees) is the primary safety mechanism;
lock files are at most a courtesy layer on top.

If you find yourself about to act in a working directory another
agent may also be using, **stop and create a worktree first** —
even for a "quick" edit.

---

## Why this protocol exists

A Claude session observed multiple out-of-band mutations to
`GFCDOTA/sketchup-mcp` during a triage cycle:

- A peer agent opened **PR #158** and merged it (squash `3e1a290`) at
  15:29:40Z while the operating agent was inspecting that same PR.
- Two `dashboard/*` branches were deleted on the remote between
  the agent's Phase B and Phase C fetches.
- `origin/develop` HEAD advanced between consecutive `gh pr view`
  calls in the same turn.
- The shared working tree was checked out to a different branch by
  a peer agent between the operating agent's `git branch
  --show-current` and `git status -sb` invocations — within the
  same command sequence.

The operating agent's failure mode was not malicious or buggy: it
was assuming that the state captured by its last `gh` or `git`
call still held when it wanted to act. **In a multi-agent
environment, that assumption is false on a sub-second timescale.**

This protocol is the canonical recovery ladder. Every agent must
walk it before any GitHub mutation or shared-working-tree
operation.

---

## Definitions

- **Mutation:** any write that affects shared state — `git push`,
  `gh pr merge`, `gh pr close`, `gh pr comment`, branch delete,
  REST API POST/PUT/PATCH/DELETE, file write in shared working tree,
  branch checkout in shared working tree.
- **Snapshot:** the agent's last captured view of remote/working
  state, e.g. a `gh pr list` JSON or a `git branch -r` text dump
  saved on disk.
- **Out-of-band change:** any state change between two of the
  operating agent's calls that the agent did not cause.

---

## Mandatory checklist before every mutation

Walk in order. If any step surfaces an out-of-band change,
**stop**, document, re-classify the planned action.

### 1. Refresh local view of remote refs
```bash
git fetch --all --prune
```
Outputs to scan for:
- `- [deleted]         (none)     -> origin/<name>` — peer deleted a branch
- `<old>..<new>  develop -> origin/develop` — peer advanced develop
- `<old>..<new>  <some-branch> -> origin/<some-branch>` — peer pushed to a branch you may be tracking

### 2. Confirm `origin/develop` HEAD before basing / rebasing / merging
```bash
git rev-parse origin/develop
git log origin/develop --oneline -3
```
If the HEAD is different from what your snapshot recorded, the
plan that depended on the older HEAD may be invalid (e.g. a rebase
target no longer applies, a "ready to merge" PR has new conflicts).

### 3. Re-query per-PR state immediately before per-PR action
```bash
gh pr view <N> --json number,state,mergeStateStatus,statusCheckRollup,headRefName,baseRefName
```
**Do not reuse** the value from a previous turn, or even from an
earlier shell command in the same turn if the action is
destructive.

For batch reasoning, capture a fresh full list:
```bash
gh pr list --state open --limit 100 --json number,headRefName,baseRefName,mergeStateStatus,statusCheckRollup \
  > .ai_triage/open_prs_now.json
```

### 4. Diff snapshot vs current state
If you have a prior snapshot:
```bash
python -c "
import json
before = {p['number']: p for p in json.load(open('.ai_triage/open_prs_after_phase_X.json'))}
after  = {p['number']: p for p in json.load(open('.ai_triage/open_prs_now.json'))}
print('new PRs:',     sorted(set(after) - set(before)))
print('closed PRs:',  sorted(set(before) - set(after)))
print('state changed:', sorted(n for n in (set(before) & set(after))
                               if before[n].get('mergeStateStatus') != after[n].get('mergeStateStatus')))
"
```
**Report any difference in the same response as the planned
action.** Audit trail beats apparent cleanliness.

### 5. Always use an isolated `git worktree`
Per §0, worktree-per-agent is the **default**, not an opt-in. Every
agent starts a session by claiming its own worktree:

```bash
# from the canonical clone (D:\Claude\microservices\plan-extract-v2):
git fetch --prune origin
git worktree add D:\Claude\worktrees\sketchup-<agent-id> \
                  -b chore/<scoped-name> origin/develop
cd D:\Claude\worktrees\sketchup-<agent-id>
# do work here; the canonical clone is never touched
```

When the session ends and the branch is merged or abandoned:
```bash
cd D:\Claude\microservices\plan-extract-v2
git worktree remove D:\Claude\worktrees\sketchup-<agent-id>
```

Cost: ~2 seconds. Benefit: branch switches, stashes, uncommitted
edits, and `git index` writes never collide with a peer agent in
the same repo. Replaces the entire class of "the working tree
changed between my two git calls" incidents.

### 6. Stale-snapshot rule
**Do not trust a snapshot older than 30–60 seconds** for
destructive actions. If your snapshot was captured earlier in the
session and you're about to merge / close / delete, re-query.

### 7. Mid-operation state change
If during a multi-step operation (e.g. merge → CI poll → next
merge) you observe an unexpected state change between steps:

1. **Stop the operation.**
2. **Capture the new state** in a snapshot file.
3. **Re-classify the planned action** against the new state.
4. **Record the out-of-band event** in `.ai_bridge/HANDOFF.md` if
   another agent should know about it.
5. **Resume only if the action still makes sense.**

---

## Mandatory checklist before every commit

Even with a per-agent worktree, run these before every `git commit`:

1. **Confirm current branch.** `git branch --show-current` must
   match the branch you intend to commit to. If `main` or `develop`,
   STOP — direct commits there are blocked by both this protocol
   and `pre_bash_guard.py`.
2. **Confirm HEAD SHA.** `git rev-parse HEAD` must match the SHA
   your last operation expected.
3. **Inspect the staged diff.** `git diff --stat HEAD` (or
   `git diff --cached --stat` for index-only). Every modified path
   should be one you intentionally touched this session.
4. **Confirm no unexpected file changes.** If a file you did NOT
   touch appears modified, that is an out-of-band change — apply
   the §7 mid-operation recovery before continuing.

These four checks take under 5 seconds and catch the most common
"I just committed a peer agent's WIP" failure mode.

---

## Mandatory checklist after every commit

1. **Verify the commit landed where you expected.**
   `git log --oneline -1` shows the new SHA + message + branch.
   Compare against your intent.
2. **Push ASAP.** `git push -u origin <branch>` (or `git push` if
   the upstream is already set). Do NOT accumulate multiple local
   commits before pushing — every commit you hold locally is at
   risk of being lost if another agent rewrites or deletes the
   branch.
3. **Record the SHA in `.ai_bridge/HANDOFF.md`.** Append a one-line
   entry: branch + SHA + one-sentence summary. This is the public
   signal peer agents need to route around your work.

If the push is rejected (non-fast-forward, hook failure), do NOT
add `--force` reflexively. Investigate, re-base if appropriate,
re-push. Force-push on a shared branch is forbidden (§"Forbidden
actions").

---

## Concurrency incident — when to stop and report

A **concurrency incident** is any of:

- The branch you were working on suddenly belongs to a peer agent.
- HEAD moved between two of your calls without your intervention.
- Files you did not touch appear modified in `git status`.
- A PR you were preparing was opened or merged by a peer first.
- The working tree path you were operating in is checked out to a
  different branch from the one your previous tool call observed.

When any of these happens:

1. **Stop immediately.** Do NOT attempt to "patch over" or "merge
   in" the peer's work in your current session.
2. **Capture the new state.** `git status`, `git log --oneline -5`,
   `git branch --show-current`, `git rev-parse HEAD`,
   `gh pr list --state open --base develop`.
3. **Report to the user in the same response** that detected the
   incident. Include: branch expected vs branch observed, SHA
   expected vs SHA observed, files modified unexpectedly, last
   tool call you executed.
4. **Wait for instruction** before any new mutation. If the user
   says "continue", create a NEW worktree from `origin/develop` and
   restart the work cleanly — do not try to salvage the polluted
   working tree.

Better to lose a few minutes of work than to overwrite a peer
agent's commits or push a Frankenstein branch.

---

## Coordination surface — what's visible, what's not

| Channel | Visibility | Use for |
|---|---|---|
| `.ai_bridge/HANDOFF.md` | **tracked, visible to all agents** | "last known good state", "I just did X" notes, branch ownership claims |
| `.ai_bridge/CURRENT_STATE.md` | tracked, visible | running state of the active project |
| `.ai_bridge/TODO_NEXT.md` | tracked, visible | next work items |
| Commit messages, PR titles, PR bodies | **public, visible** | scope signaling, conflict avoidance |
| Branch names with canonical prefixes (`feature/`, `fix/`, `chore/`, `docs/`, `perf/`, `refactor/`, `test/`) | **public, visible** | scope + ownership prediction |
| `.ai_triage/` | gitignored, **agent-local only** | working notes; do NOT use for coordination |
| scratch dirs, `_*.md`, `.tmp_*` | gitignored, **agent-local only** | same — never put coordination signals here |
| Slack / chat / human channels | out-of-band | escalation, decisions humans must make |

**Rule:** any coordination signal a peer agent needs to act on
**must be in a tracked file or visible on GitHub**. Notes that
only exist in `.ai_triage/` or your own conversation context are
invisible to peers.

---

## Forbidden actions even under multi-agent pressure

Even when racing a peer, do NOT:

- `git push --force` to `main` / `develop` / any branch a peer may
  have based their work on.
- Delete a branch that has an open PR pointing at it.
- Close a PR without a comment explaining why.
- Touch `main` directly (peer agents rely on the develop→main flow).
- Commit credentials, tokens, or secrets discovered while reading
  peer work.
- Edit files you don't own in a peer agent's branch (use your own
  worktree).
- Bypass `pre_bash_guard.py` or any other safety hook.

---

## When to escalate to a human

- Two agents have made conflicting changes to the same file on the
  same logical scope and a rebase would lose work.
- An agent observes a peer doing something that violates §1 of
  `CLAUDE.md` (hard safety rules) — report, do not undo.
- A PR was merged that the operating agent had been asked to review
  and the user's intent for review was specifically pre-merge.
- A peer agent's commit signs a different identity and the
  operating agent cannot verify provenance.

Report with: the snapshot file paths, the observed change, the
suspected peer (if known by commit author / PR creator), and the
proposed next action.

---

## Cross-references

- [`learning/lessons_learned.md`](learning/lessons_learned.md) LL-019 —
  the lesson and incident timeline that motivated this protocol.
- [`../CLAUDE.md`](../CLAUDE.md) §22 — short summary of the rule
  (this doc is the long form).
- [`../CLAUDE.md`](../CLAUDE.md) §0 — git flow (PRs always against `develop`).
- [`../CLAUDE.md`](../CLAUDE.md) §4 — PR standard.
- [`REPO_HYGIENE.md`](REPO_HYGIENE.md) §3 — don't-delete-blindly
  protocol (worktree isolation makes the protocol cheaper to honour
  because a peer's WIP can't sneak into your diff).
- [`protocols/terminal_first_github_auth.md`](protocols/terminal_first_github_auth.md) —
  companion protocol; covers HOW to call GitHub safely after this
  protocol determines WHAT is safe to call.
- [`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) — the public
  coordination channel.

---

## Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Renamed from `docs/protocols/multi_agent_coordination.md` to canonical top-level `docs/AGENT_COORDINATION.md`. Added §0 root rule (worktree-per-agent is the default, lock files are advisory only) + explicit pre-commit / post-commit / concurrency-incident checklists. Strengthened §5 from "use worktree when sharing a dir" to "always use worktree". |
| 2026-05-24 | (earlier this day) | Initial protocol drafted under `docs/protocols/multi_agent_coordination.md` after the PR #158 mid-merge incident. |
