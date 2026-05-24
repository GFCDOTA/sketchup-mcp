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

## LL-015 — SU runner mode protocol (interactive default; opt-in headless)

**Date:** 2026-05-23
**Context:** During the quadrado window POC, helper Python
launchers (`_run_add_window.py`, `_render_view.py`,
`_inspect_skp.py`, `_reframe.py`) all called `proc.terminate()`
after a done marker appeared. This silently killed any SU instance
the user had open in parallel for manual inspection, causing the
"abre o SU e fecha rápido" complaint that I initially mis-diagnosed
as a SKP bug. FP-023 documents the anti-pattern; this LL codifies
the positive rule.

**Rule:** every SU runner (Python launcher, harness, helper) MUST
declare a runtime mode and behave accordingly:

| Mode | Termination behaviour |
|---|---|
| `headless` / `ci` | MAY terminate only `proc.pid` (the child the runner itself spawned). NEVER `taskkill /IM SketchUp.exe`. |
| `interactive` / `debug` | MUST NOT terminate. Print done marker + lifecycle log + leave SU running. |
| `attach` / `manual` | NEVER touch any SU process — runner only reads files/markers. |

**Safe default is `interactive`.** A runner that does not declare
its mode and finds none in `RUN_MODE` env or `--mode` CLI must
behave as `interactive` (NO termination). This protects the human
session by default.

**Marker semantics:** `_<name>_done.txt` means "artifact ready, my
script finished". It is NOT a signal to kill SU. Termination is a
separate decision driven by mode.

**Implementation contract** for every `_run_*.py`,
`*launcher*.py`, or tool that calls `Popen` on `SketchUp.exe`:

1. Accept mode via `RUN_MODE` env var OR `--mode {headless,interactive,attach}` CLI OR `--no-terminate` shorthand.
2. Default to `interactive` when nothing is declared.
3. Print at launch: `[su-runner] mode=<X>; terminate_on_done=<bool>`.
4. Document destructiveness in docstring + `--help`.
5. In `headless`: terminate only `proc.pid`, never `taskkill /IM`.
6. In `attach`: don't call `Popen` at all — just read markers.

**Pattern:**
```python
import os, argparse, subprocess

def parse_mode():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["headless", "interactive", "attach"], default=None)
    p.add_argument("--no-terminate", action="store_true")
    args, _ = p.parse_known_args()
    if args.no_terminate or args.mode == "interactive":
        return "interactive"
    if args.mode:
        return args.mode
    return os.environ.get("RUN_MODE", "interactive")

mode = parse_mode()
terminate_on_done = (mode == "headless")
print(f"[su-runner] mode={mode}; terminate_on_done={terminate_on_done}")

if mode != "attach":
    proc = subprocess.Popen([SU, target_skp])
    # ... poll done marker ...
    if terminate_on_done:
        proc.terminate()
        print(f"[su-runner] terminated own child PID {proc.pid}")
    else:
        print(f"[su-runner] artifact ready; SU left running ({proc.pid})")
```

**Reference helper**: `tools/su_runner_safety.py` exports
`parse_mode()`, `should_terminate(mode) -> bool`,
`is_attach(mode) -> bool`, and `log_mode(mode)`. Covered by 35
unit tests in `tests/test_su_runner_safety.py`.

**See also:** FP-023 (the anti-pattern this rule prevents);
LL-009 (bootstrap .skp pattern — same launcher ergonomics).

## LL-016 — Window openings are wall-hosted partial-height apertures (3D post-extrude carve, never 2D full-height)

**Date:** 2026-05-24.
**Context:** Reviewing the quadrado canonical fixture render after
the wall-shell continuity fix landed, the user pointed out that the
window still rendered as a vertical shaft with sill/glass/lintel
infill — semantically a door-like void, not a window. Same bug
present in planta_74 (4 windows). FP-024 documents the anti-pattern;
this LL codifies the positive rule.

**Rule:**

> **Window openings must be wall-hosted partial-height apertures.
> They must preserve wall mass below the sill (peitoril / parapet)
> AND above the head (verga / lintel). They must NEVER be modelled
> as door-like full-height voids unless explicitly classified as
> a door kind.**

This is the architectural contract of a window. The exporter must
encode it structurally — in the topology of the produced SKP — not
cosmetically (via material colours or render tricks).

**Distinguishing kinds:**

| `kind_v5` (normalised) | Full-height void? | Wall mass below sill? | Wall mass above head? |
|---|---|---|---|
| `interior_door` | yes | no (door reaches floor) | no (lintel is part of door frame) |
| `interior_passage` | yes | no | no |
| `glazed_balcony` (porta-vidro) | yes (intentional) | no | no |
| `window` | **NO** | **YES** (peitoril) | **YES** (verga) |

`{interior_door, interior_passage, glazed_balcony}` are routed
through the 2D pre-extrude carve path in
`tools/build_plan_shell_skp.py` and rendered with leaf / marker /
glass-pane fills inside the full-height void.

`{window}` is routed through the 3D post-extrude carve path in
`tools/build_plan_shell_skp.rb build_window_aperture_3d`. The wall
is extruded as a solid; the aperture is cut **only** at
z ∈ [`WINDOW_SILL_IN`, `WINDOW_HEAD_IN`]; the glass face sits at
mid-thickness inside that aperture. Wall mass elsewhere on that
wall stays as wall.

**Implementation contract:**

1. **Python phase** must populate
   `_shell_polygon.json`'s top-level `window_apertures` list with
   `{id, wall_id, kind_v5, center, opening_width_pts,
   host_wall_orientation, host_wall_thickness_pts}` per window.
   Windows must **never** be added to the 2D `carve_rects` union.

2. **Ruby phase** must, for each `window_apertures` entry:
   - Find the host wall lateral face (vertical, perpendicular to
     wall axis, spanning [0, WALL_HEIGHT_IN]).
   - Read its fixed coord from `face.bounds` — never hardcode
     (LL-014).
   - Add a coplanar rectangle at `[cx ± w/2, fixed_coord,
     [WINDOW_SILL_IN, WINDOW_HEAD_IN]]`. SU auto-splits the host
     face.
   - `pushpull(-real_thickness_in)` to drive the aperture face
     through the wall.
   - Emit `WindowGlass_Group_<id>` as a separate top-level group
     at mid-thickness.
   - **MUST NOT emit** `Window_Group_<id>_sill` or
     `Window_Group_<id>_lintel` — those are FP-024 signatures.

3. **Geometry report** must show:
   - `PlanShell_Group.bbox_m.z = [0, WALL_HEIGHT_M]` (~2.70 m).
   - `WindowGlass_Group_<id>.bbox_m.z = [WINDOW_SILL_M, WINDOW_HEAD_M]`
     (~[0.9, 2.1]).

**Validation gates** (locking the rule against regression):

- `tests/test_window_aperture_contract.py` (15 tests) — Python
  contract. Asserts `is_window_aperture()` classification,
  `FULL_HEIGHT_CARVE_KINDS ∩ WINDOW_APERTURE_KINDS = ∅`, windows
  produce `openings_carved = 0` + `window_apertures_3d ≥ 1`, doors
  the inverse. Includes a planta_74 fixture regression test
  (4 windows, all must route to 3D path).

- `tests/test_window_aperture_geometry.py` (9 tests) — SKP /
  geometry-report invariants. Skips cleanly when no SKP artifact
  is present (CI-portable); fails loudly when present and
  miscarved. Asserts wall height preserved, glass at sill-to-head
  only, no legacy `_sill` / `_lintel` group names.

**Cross-references:** ADR-007 (the architectural decision);
FP-024 (the anti-pattern this LL prevents); ADR-003 (the broader
plan-shell exporter); LL-014 (read coords from the actual model);
`docs/specs/quadrado_demo_spec.md` §6.4 (the in-place edit pattern
adopted by `build_window_aperture_3d`).

## LL-018 — Terminal-first GitHub auth: if `git push` works, the cached token can create PRs

**Date:** 2026-05-24.

**Context:** A Claude session pushed a feature branch successfully
(via Git Credential Manager on Windows), then called `gh pr create`,
got "not authenticated," and **escalated immediately to "use the
browser or give me a PAT"** instead of trying to reuse the credential
the `git push` had just used. The PR was opened via the browser
automation tool — a heavy, manual-feeling path that the user
correctly flagged as unnecessary.

**Diagnosis:** `gh` was not authenticated, BUT the Git Credential
Manager on Windows had a valid GitHub OAuth token cached from prior
HTTPS pushes. That same token can:

- Be extracted via `git credential fill`.
- Be exported as `GH_TOKEN` to make `gh` work non-interactively.
- Or be used directly with the GitHub REST API via `curl`.

None of these require user input. None require a PAT. None require
the browser.

**Rule:** Before requesting any manual action for GitHub
(opening / merging / commenting on PRs, listing checks, calling
the API), walk the recovery ladder in
[`docs/protocols/terminal_first_github_auth.md`](../protocols/terminal_first_github_auth.md):

1. `gh auth status` — try `gh` first.
2. `git ls-remote origin` — confirm Git can reach GitHub.
3. `git credential fill` — pull the cached token (NEVER log it).
4. `GH_TOKEN=… gh pr create …` — temporary env var, unset after.
5. `curl https://api.github.com/…` — REST API fallback.
6. Only NOW request manual action, with the diagnostic trail.

The full procedure (including token-hygiene safety rules) lives in
the protocol document above. CLAUDE.md §21 is the short pointer.

**Why this matters operationally:** every "use the browser" / "give
me a PAT" request is a 30-60 second context switch for the user.
Multiply by every PR / merge / status check in a session and it
becomes the dominant friction. The terminal-first ladder eliminates
~95% of those interruptions.

**Token-hygiene non-negotiables** (extracted from the protocol):

- Token never appears in stdout / stderr / logs.
- Token never appears in PR body / commit message / committed file.
- Token only lives in a local shell var or `GH_TOKEN` env.
- Token is unset / cleared at end of cycle.
- Evidence about token use is masked as `ghs_***`, never the real
  value.

**Cross-references:** `docs/protocols/terminal_first_github_auth.md`
(canonical procedure); CLAUDE.md §21 (the rule); LL-012 (fix
tooling access before falling back to manual — same operational
philosophy, applied to PATH-lookup); CLAUDE.md §0 (git flow:
PRs against `develop`).

## LL-019 — Multi-agent coordination: never assume sole authorship of the remote

**Date:** 2026-05-24.
**Context:** During a multi-phase triage session, the operating
agent observed multiple out-of-band mutations to the same repo:

- **PR #158** (`chore(repo): repository health gate + canonical
  hygiene governance`) was opened by a parallel agent between
  Phase A and Phase B, and **merged out-of-band** (squash
  `3e1a290`) at 15:29:40Z while the operating agent was mid-way
  through its Phase D inspection of the same PR.
- **`origin/dashboard/architecture-sre-radar`** and
  **`origin/dashboard/project-roadmap`** were deleted on the remote
  between Phase B and Phase C, surfaced as `[deleted] (none) -> …`
  in the operating agent's next `git fetch --prune`. The operating
  agent did not issue any branch-delete in that window.
- **`origin/develop` HEAD advanced** under the operating agent as
  other agents merged PRs; the agent's prior `gh pr view` cache
  was stale within seconds.
- The shared working tree was **switched between branches** by
  parallel agents (`chore/repo-health-allow-specs-dir` opened
  PR #159, and `chore/repo-cleanup-w1-fresh` appeared with 2
  commits ahead of develop) — the agent's
  `git branch --show-current` and `git status -sb` returned
  inconsistent values within the same turn because another agent
  was actively performing checkouts in the shared working tree.

The operating agent had no bug — it was assuming that the state
captured by its last `gh` or `git` call was still true at the
moment it wanted to act. In a multi-agent environment, **that
assumption is false on a sub-second timescale**.

**Rule:** in multi-agent mode, **never assume sole authorship of
remote state**. Before any GitHub mutation (merge / close / delete
branch / push / API write):

1. **`git fetch --all --prune`** immediately, to surface remote
   deletes (`[deleted] (none) -> origin/<name>`) and new commits
   on the refs you care about.
2. **`gh pr view <n>` immediately** before any per-PR action —
   never reuse the value from a previous turn or even an earlier
   shell command in the same turn.
3. **`git rev-parse origin/develop`** immediately before basing,
   rebasing, or merging.
4. **Diff your snapshot** (the JSON / branch list captured at the
   start of the phase) against current state, and **report any
   out-of-band change in the same response** that performs the
   mutation. Audit trail beats apparent cleanliness.
5. **Use an isolated `git worktree`** when working in a directory
   another agent may also be using. The cost is a few seconds
   (`git worktree add -b <new-branch> <path> origin/develop`);
   the benefit is that branch switches and stash operations don't
   collide with the other agent's working state. Cleanup via
   `git worktree remove <path>` when done.
6. **Don't trust reports older than 30–60 seconds** for destructive
   actions. Re-query.
7. **If state changed mid-operation**, stop and re-classify before
   continuing — the assumption that motivated the action may no
   longer hold.

**Concrete failures this rule prevents:**

- Merging a PR that was already merged by another agent (idempotent
  but wastes a turn and pollutes the audit trail).
- Re-deleting a branch that another agent already deleted (harmless
  but confusing).
- Rebasing onto an `origin/develop` that has already advanced past
  the agent's last fetch (results in unnecessary conflicts or
  attempts to re-do work).
- Committing into a working tree that another agent just switched
  to a different branch — your changes land on the wrong branch
  or get stashed inconsistently.

**Coordination surface — public vs private:**

- **`.ai_bridge/HANDOFF.md`** is the **visible (tracked) coordination
  file** between agents. Use it to record "last known good state"
  and "what I just did" entries so other agents can read them.
- **`.ai_triage/`**, **scratch dirs**, and other gitignored
  locations are **agent-local only** — invisible to peers. Useful
  for working notes; do NOT rely on them for coordination.
- **Commit messages and PR titles** are **public coordination
  signals** — write them so a peer agent can route around your
  work (avoid ambiguous titles like `fix bug`; prefer
  `fix(openings): X` so another agent's grep can match).
- **Branch names** signal intent and ownership — use the canonical
  prefixes (`feature/`, `fix/`, `chore/`, `docs/`) so other agents
  can predict scope from name alone.

**See also:** `docs/AGENT_COORDINATION.md` (the
canonical procedure with copy-paste snippets); CLAUDE.md §22 (the
rule, condensed); LL-018 (terminal-first GitHub auth — same
operational philosophy applied to credentials, not state);
LL-012 (fix tooling access before falling back to manual).
