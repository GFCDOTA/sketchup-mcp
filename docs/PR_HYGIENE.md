# PR_HYGIENE — startup, exit, and GitHub workflow rules

> **Status:** Canonical
> **Type:** Operational protocol for opening, working on, and closing
> any cycle / PR.
> **Updated:** 2026-05-24
> **Companion docs:** [`REPO_HYGIENE.md`](REPO_HYGIENE.md) (file
> policy), [`GATES.md`](GATES.md) (validation gates),
> [`HANDOFF.md`](HANDOFF.md) (onboarding),
> [`../CLAUDE.md`](../CLAUDE.md) §0 (git flow), §14 (autonomous
> continuation), §15 (hygiene protocol), §17 (twelve-question stop
> gate).

This document tells you exactly what to do **before** you start
work, **during** the cycle, and **before** you stop. It is the
operational counterpart to `REPO_HYGIENE.md` (which classifies files)
and `GATES.md` (which lists validation gates).

If you only have time to read one section, read §1 (startup) and §3
(exit). They are the load-bearing checklists.

---

## 1. Startup checklist — every new session, on every machine

Run these commands in this order. Skipping any step has caused a
real incident on this repo at least once.

```bash
git status                                   # must be clean OR you must know why
git remote -v                                # confirm origin = GFCDOTA/sketchup-mcp
git fetch --all --prune                      # also drops deleted remote branches
git checkout develop
git pull --ff-only origin develop            # never merge into develop; ff or stop
git status                                   # confirm clean + develop @ origin HEAD
gh pr list --state open --repo GFCDOTA/sketchup-mcp
```

**Interpretation:**

- `git status` not clean → STOP. Read the existing changes. They may
  be unfinished work from a previous session or from a parallel
  agent. Do NOT clobber them. Either commit them on a branch or
  `git stash` with a clear message.
- `gh pr list --state open` shows you what's already in flight.
  Picking up an existing PR or branching off it is often the right
  next move; opening a parallel PR is rarely the right move (see
  §4 — "Avoid PR sprawl").
- `git pull --ff-only` fails if `develop` diverged → never force-
  push to fix it. Reset to `origin/develop` (your local was the
  diverged copy) and pick up changes from there.

Then read in order: [`../CLAUDE.md`](../CLAUDE.md),
[`PROJECT_STATE.md`](PROJECT_STATE.md),
[`ANTI_FORGETTING.md`](ANTI_FORGETTING.md),
[`GATES.md`](GATES.md), the top entry of
[`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md), and
[`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md).

---

## 2. During the cycle

### 2.1 Branch and commit discipline

- Branch from `develop`, never from `main`. Naming: `feature/`,
  `fix/`, `chore/`, `docs/`, `perf/`, `refactor/`, `test/`,
  `agents/`, `tooling/`, `validate/`, `hotfix/`. See
  [`../CLAUDE.md`](../CLAUDE.md) §0.
- One PR = one idea. If the diff grows past ~500 LOC and is not
  pure docs, split.
- One commit = one concept. Never mix refactor + functional fix +
  perf optimisation in the same commit (see CLAUDE.md §1 hard rule).
- Use conventional commit prefixes (`feat:`, `fix:`, `chore:`,
  `test:`, `docs:`, `refactor:`).
- Co-author your commits with the assisting agent
  (`Co-Authored-By: ...`).

### 2.2 Run the cheap gates while you work

You do NOT need to wait for CI. The same gates run locally:

```bash
python scripts/project_state_check.py             # < 2 s
python tools/repo_health_gate.py --mode audit     # < 3 s, always exit 0
ruff check <paths-you-touched>                    # < 2 s
pytest <tests-you-touched> -v                     # depends
```

If you intend to ship a non-trivial change, also run:

```bash
python tools/repo_health_gate.py --mode check --base origin/develop
```

This mirrors CI; it FAILS on any ERROR-class finding. Fix the
underlying issue before pushing.

### 2.3 When you discover an unrelated issue

Do NOT bundle it into the current PR. Note it in
[`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md) or
[`learning/failure_patterns.md`](learning/failure_patterns.md) (as
`FP-NNN`) and keep moving. Mixing cleanup with algorithm changes is
banned (`CLAUDE.md` §15, `REPO_HYGIENE.md` §6).

### 2.4 Don't sneak generated outputs into the index

Every artefact that lands in git must satisfy `REPO_HYGIENE.md` §4
(canonical) or live under one of the gitignored paths (`runs/`,
`out/`, `review/`, `__pycache__/`, etc). The repo health gate
detector E002 (`generated-in-wrong-path`) catches violations.

### 2.5 If a structural change lands, update the state docs

The detector E006 (`project-state-stale`) fires when a PR touches
`tools/`, `tests/`, `fixtures/`, `ground_truth/`, `docs/specs/`,
`docs/adr/`, `.github/workflows/`, `scripts/`, or `patches/` but
does NOT update at least one of:

- [`PROJECT_STATE.md`](PROJECT_STATE.md)
- [`HANDOFF.md`](HANDOFF.md)
- [`REPO_HYGIENE.md`](REPO_HYGIENE.md)
- [`GATES.md`](GATES.md)
- [`ANTI_FORGETTING.md`](ANTI_FORGETTING.md)

If your change is structural, refresh the relevant section + add a
line to that doc's `## Update log` table in the same commit.

### 2.6 New `.md` MUST carry a `Status:` header

Detector E004 (`new-md-no-status`) fails the gate. Add one of:

```markdown
> **Status:** Canonical
> **Status:** Active
> **Status:** Generated (do not edit). Produced by <script>.
> **Status:** Archived. Superseded by <path>.
> **Status:** Delete candidate — pending audit cycle <N>
```

See [`REPO_HYGIENE.md`](REPO_HYGIENE.md) §2 for the full policy.

---

## 3. Exit checklist — before you stop a cycle

Run these in order. The output of the gates BELONGS in the cycle's
exit report.

```bash
git status                                            # confirm clean
gh pr list --state open --repo GFCDOTA/sketchup-mcp   # snapshot of open PRs
python scripts/project_state_check.py                 # G-PROJECT-STATE
python tools/repo_health_gate.py --mode check --base origin/develop  # G-REPO-HEALTH
```

Both gates MUST be green. If they aren't, you are not done.

Then report (in the PR body or the exit message):

- **PRs open before this cycle:** N
- **Actions taken on existing PRs:** (merged / closed / commented /
  rebased / dependent on this PR)
- **PRs open after this cycle:** M
- **Reason for any PR that remains open:** (waiting on CI, requires
  human review, depends on PR #X, blocked on real data, etc.)

Update [`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) with a
fresh top entry, overwrite
[`../.ai_bridge/CURRENT_STATE.md`](../.ai_bridge/CURRENT_STATE.md),
refresh [`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md).

A cycle is NOT complete until both gates are green AND the three
`.ai_bridge/` files are refreshed. See
[`../CLAUDE.md`](../CLAUDE.md) §17 twelve-question stop gate.

---

## 4. Avoid PR sprawl

A high PR count is a symptom of governance failure. Before opening a
new PR:

1. **`gh pr list --state open` first.** If a PR already exists for
   the file / area / topic, prefer adding a commit to that branch
   (if you own it) or commenting on it.
2. **One concept = one PR = one branch.** Never stack on top of an
   unmerged feature branch unless you're explicitly opening a
   "dependent on PR #N" follow-up.
3. **Close stale PRs honestly.** If a PR has been open for >7 days
   with no progress, either rebase + push, or close with a comment
   explaining why and a pointer to the replacement branch.
4. **Squash on merge.** Established pattern on this repo (#114,
   #116, #118, #120, #121, #134, #135, #153 all squashed).
5. **Delete merged feature branches** (local + remote) per
   [`../CLAUDE.md`](../CLAUDE.md) §0.

The repo health gate currently does NOT flag PR sprawl directly,
but the `.ai_triage/` ad-hoc audit (when run via the gh CLI) does.
See §5.4 below for the manual triage routine.

---

## 5. Terminal-first GitHub workflow

> **Rule (short form, copy-paste-able):** Terminal-first always. If
> Git can push/fetch, try credential-helper + temporary `GH_TOKEN` +
> `gh`/`curl` before asking for browser, PAT, or manual PR actions.
> Never print, commit, or log tokens.

The full escalation ladder — try each step before falling back to
the next. The browser is the **last** resort, not the first.

### 5.1 Step 1: confirm `gh` is authenticated

```bash
gh auth status                # exits 0 if authenticated
```

If `gh` reports authenticated → use it directly for the rest of the
session.

### 5.2 Step 2: confirm git can talk to GitHub

```bash
git ls-remote origin > /dev/null   # exits 0 if push/fetch credentials work
```

If this succeeds and `gh auth status` failed, that means git has a
credential helper (typically Git Credential Manager on Windows /
osxkeychain on macOS / libsecret on Linux) but `gh` has not picked
up the token.

### 5.3 Step 3: borrow the credential and run `gh` with `GH_TOKEN`

```bash
# Extract the GitHub token from the local credential helper (NEVER
# printed to stdout, NEVER copied into a file).
GH_TOKEN_TMP=$(printf 'protocol=https\nhost=github.com\n\n' | \
               git credential fill | awk -F= '/^password=/{print $2}')

# Run gh with the token in the env ONLY for this command.
GH_TOKEN="$GH_TOKEN_TMP" gh pr list --repo GFCDOTA/sketchup-mcp

# Wipe the token immediately.
unset GH_TOKEN_TMP
```

PowerShell equivalent:

```powershell
$cred = ("protocol=https`nhost=github.com`n`n" | git credential fill)
$tok  = ($cred | Select-String -Pattern '^password=' | ForEach-Object {
                 ($_ -split '=',2)[1] })
$env:GH_TOKEN = $tok
gh pr list --repo GFCDOTA/sketchup-mcp
Remove-Item Env:\GH_TOKEN
```

### 5.4 Step 4: if `gh` is broken/unavailable, use `curl` against the REST API

```bash
GH_TOKEN_TMP=$(printf 'protocol=https\nhost=github.com\n\n' | \
               git credential fill | awk -F= '/^password=/{print $2}')

curl -sS -H "Authorization: Bearer $GH_TOKEN_TMP" \
     -H "Accept: application/vnd.github+json" \
     https://api.github.com/repos/GFCDOTA/sketchup-mcp/pulls?state=open

unset GH_TOKEN_TMP
```

### 5.5 Step 5: only THEN ask the user to act manually

If steps 1–4 fail, the credential helper is genuinely empty or
revoked. Only then is it appropriate to ask the user for a
browser-based action or a fresh PAT.

### 5.6 Rules that MUST hold across every step

- **Never** `echo $GH_TOKEN`, `cat ~/.gh_token`, or write the token
  to a file.
- **Never** commit a token. If a token ever ends up in a commit,
  rotate it immediately and force-push the fix in a new branch.
- **Never** include a token in a `--debug` log, error message, or
  exception backtrace.
- **Always** scope `GH_TOKEN` to a single command (`GH_TOKEN=... gh
  ...`) or `unset` it right after use.
- **Never** persist `GH_TOKEN` in shell history. Use a leading space
  before the command if your shell respects `HISTCONTROL=ignorespace`.
- **gh CLI absolute path on Windows:**
  `C:\Program Files\GitHub CLI\gh.exe`. Always pass `--repo
  GFCDOTA/sketchup-mcp` so the command works regardless of cwd.

### 5.7 Common one-liners

```bash
# Open a PR from the current branch into develop
gh pr create --base develop --title "<title>" --body "<body>" \
             --repo GFCDOTA/sketchup-mcp

# Squash-merge a green PR
gh pr merge --squash --delete-branch --repo GFCDOTA/sketchup-mcp <PR#>

# Inspect CI for a PR
gh pr checks --repo GFCDOTA/sketchup-mcp <PR#>

# Reproduce CI's repo-health gate locally
python tools/repo_health_gate.py --mode check --base origin/develop
```

### 5.8 If you must use a PAT, scope it correctly

- Required scopes for this repo: `repo` (full).
- Optional: `read:org` only if listing org membership.
- Token TTL: 7 days for routine work; never longer than 90 days for
  any token used in automation.
- Storage: ONLY in the OS credential manager (Git Credential
  Manager on Windows, Keychain on macOS, libsecret on Linux). Never
  in `~/.gh_token`, never in `.env`, never in a file in the repo.

---

## 6. PR body template

Every PR body must follow this template (also documented in
[`../CLAUDE.md`](../CLAUDE.md) §4):

```markdown
## Summary
1-3 bullets, what this PR is.

## What changed
List of files + brief reason.

## What did NOT change
Confirm scope: no algorithm / no schema / no thresholds / no Ruby/SU
/ no fixtures / whatever applies.

## Validation
Commands run + expected output. Include:
  - pytest output (counts)
  - ruff result
  - `python scripts/project_state_check.py` exit + summary
  - `python tools/repo_health_gate.py --mode check --base origin/develop`
    exit + ERROR/WARN counts
  - smoke / bench output if relevant

## Risks
What could go wrong.

## Rollback
Exact git revert / git push --delete commands.

## Next steps
Optional: what should follow this PR.
```

For a PR that updates this file or any of the other governance docs,
also include:

```markdown
## Governance impact
Which canonical doc + which section changed and why.
```

---

## 7. Quick reference card

```text
START
  git status; git fetch --all --prune; git checkout develop
  git pull --ff-only origin develop; git status; gh pr list

WORK
  branch from develop; one concept per PR; one concept per commit
  conventional commit prefixes; co-author the agent
  cheap gates as you go:
    python scripts/project_state_check.py
    python tools/repo_health_gate.py --mode audit
    ruff check <paths>; pytest <tests>

EXIT
  git status; gh pr list --state open
  python scripts/project_state_check.py        # MUST exit 0
  python tools/repo_health_gate.py --mode check --base origin/develop  # MUST exit 0
  refresh .ai_bridge/CURRENT_STATE.md
  prepend entry to .ai_bridge/HANDOFF.md
  refresh .ai_bridge/TODO_NEXT.md
  report PRs open before / actions / PRs open after / reason

GITHUB
  gh auth status -> git ls-remote -> GH_TOKEN from credential helper
  -> gh / curl -> human/browser (LAST RESORT)
  never print, commit, or log tokens
```

---

## 8. Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial canonical PR hygiene + terminal-first GitHub workflow doc. Consolidates the startup/exit checklists + the 5-step credential escalation ladder + the PR-sprawl rules. Pulls together the rules that previously lived inside individual session memories. |
