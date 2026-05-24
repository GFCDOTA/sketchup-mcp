# Terminal-First GitHub Auth & PR Workflow

> **Permanent operational protocol** for GitHub auth on this repo.
> Canonical reference; do not duplicate this content elsewhere — link here.
> Last updated: 2026-05-24.

---

## Why this protocol exists

A Claude session opened a PR via the browser after `gh pr create`
returned "not authenticated" — without first checking whether the
existing **Git Credential Manager** already had a valid GitHub OAuth
token cached. The session pushed the branch successfully (`git push`
worked = credential manager has a valid token), but then immediately
escalated to "give me a PAT or use the browser" instead of using that
same cached token for the GitHub API.

That escalation is **operational error**. It pushes manual work onto
the user when none is necessary, and it teaches future agents that
"gh not authenticated → ask the human." The right loop is:
**if Git Credential Manager has a token that talks to GitHub, that
token can also create PRs.**

This document is the canonical recovery ladder. Future agents must
walk it before requesting any manual action.

---

## Decision ladder (walk in order)

### Rung 1 — Try `gh` normally

```bash
gh auth status
gh pr status
gh pr list --state open --limit 5
```

If `gh auth status` returns `Logged in to github.com`, just use `gh`.

### Rung 2 — Verify `git push` / `git fetch` work

If `gh` is not authenticated, check whether Git itself can talk to
GitHub on this machine:

```bash
git remote -v
git ls-remote origin HEAD
```

If `git ls-remote origin` succeeds without prompting, the Git
Credential Manager has a valid cached token. Continue to Rung 3.

If it prompts or fails, escalate to Rung 6.

### Rung 3 — Extract the cached credential

```bash
printf "protocol=https\nhost=github.com\n\n" | git credential fill
```

Output is multi-line `key=value`. Extract `password=` into a variable
**without echoing**:

```bash
# Bash / Git Bash
TOKEN=$(printf "protocol=https\nhost=github.com\n\n" \
  | git credential fill \
  | awk -F= '/^password=/{print $2; exit}')
```

```powershell
# PowerShell
$lines = "protocol=https`nhost=github.com`n`n" | git credential fill
$TOKEN = ($lines | Where-Object { $_ -like 'password=*' } |
          ForEach-Object { $_.Substring(9) })[0]
```

**Critical safety rules** when handling the token:

1. NEVER print the token to stdout / stderr / logs.
2. NEVER paste it into a PR body, commit message, or chat message.
3. NEVER write it to a `.md` file or any tracked artifact.
4. Mask any reference to it as `ghs_***` or `<redacted>`.
5. Unset / clear the variable after use.
6. If a tool prints it (e.g. verbose `gh`), suppress that output.

### Rung 4 — Use `GH_TOKEN` temporary env var for `gh`

```bash
# Bash
GH_TOKEN="$TOKEN" gh pr create \
  --base develop \
  --title "..." \
  --body-file pr_body.md
unset TOKEN
```

```powershell
# PowerShell
$env:GH_TOKEN = $TOKEN
gh pr create --base develop --title "..." --body-file pr_body.md
Remove-Item Env:\GH_TOKEN
$TOKEN = $null
```

`--body-file` is preferred over `--body` because:
- It avoids escaping issues with markdown, backticks, special chars.
- It avoids the body appearing in shell history.
- The file can be deleted after the PR is created.

### Rung 5 — GitHub REST API via `curl` (fallback if `gh` unavailable)

If `gh` itself is missing from the environment (rare; see LL-012):

```bash
# Create payload to a temp file (no token in here)
cat > /tmp/pr_payload.json <<'EOF'
{
  "title": "...",
  "body": "...",
  "head": "feature/<branch>",
  "base": "develop"
}
EOF

# Call API; token only on the curl command line (never logged)
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/<owner>/<repo>/pulls \
  -d @/tmp/pr_payload.json \
  | jq '.html_url'

rm /tmp/pr_payload.json
unset TOKEN
```

For merging:

```bash
curl -sS -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/<owner>/<repo>/pulls/<n>/merge \
  -d '{"merge_method":"squash"}'
```

### Rung 6 — Only NOW request manual action

If all of the above failed, report to the user with this structure:

```
GitHub auth recovery failed. Tried:
  1. gh auth status     → <error>
  2. git ls-remote      → <error>
  3. git credential fill → <error>
  4. GH_TOKEN + gh      → <error>
  5. curl + REST API    → <error>

Manual step needed:
  <smallest specific action the user must take>
```

Never short-circuit this ladder. The user's time is more expensive
than the agent's diagnostic loop.

---

## Token-hygiene checklist (must hold for every cycle)

- [ ] Token is never echoed, printed, or logged.
- [ ] Token only lives in a local shell variable or `GH_TOKEN` env.
- [ ] Token is unset/cleared at the end of the cycle.
- [ ] No token appears in chat messages, PR bodies, commit messages,
      or any committed file.
- [ ] Tool output that would leak the token is suppressed
      (e.g. `2>/dev/null` on verbose gh).
- [ ] When evidence about token use is needed, mask as `ghs_***`.

Acceptable evidence format (no real token):

```text
token source: Git Credential Manager
scope: repo (inferred from gh auth flow)
mode: GH_TOKEN env (cleared after use)
status: unset
```

---

## When to use which rung

| Scenario | Start at rung |
|---|---|
| Opening a PR | 1 (always try `gh` first) |
| Reading PR comments | 1 |
| Merging a PR | 1 |
| Checking CI status | 1 |
| `gh` says "not authenticated" but you JUST pushed | 3 (cred fill) |
| `gh` is missing from PATH | 5 (REST API) |
| `git push` itself fails with 401 | 6 (manual — credential genuinely expired) |
| User explicitly says "use the browser" | browser tool |

---

## Cross-references

- `CLAUDE.md` §21 — short summary of the rule (this doc is the long form).
- `docs/learning/lessons_learned.md` LL-018 — the operational lesson
  that motivated this protocol.
- `CLAUDE.md` §0 — git flow (PRs always against `develop`).
- `CLAUDE.md` §4 — PR standard (required PR body sections).
