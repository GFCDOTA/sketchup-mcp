# Current State — 2026-05-25 (post #176; orphan-tools PR #177 in flight)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/track-orphan-su-diagnostic-tools` (open PR #177)
- **develop @** `a29c9dc` — PR #176 (`feat(fixture): quadrado uniform
  4-windows — fidelity reference (JSON-only, SKP deferred)`) merged
  2026-05-25T14:53Z
- **main @** `997b830` (PR #174 "Develop") — behind develop, will
  catch up at the next `main` sync.
- **Open PRs:** **#177** — `chore(tools): track orphan SU diagnostic
  tools (build_room_ring + dump_skp_groups)` (this session). CI
  re-running after the PROJECT_STATE.md §9 row was added.
- **Open issues:** **#122** — `planta_74: close
  global_visual_fidelity WARN advisory (post-PR #121)`, advisory
  only.

## This session (2026-05-25, post-#172 follow-up)

1. **Merged PR #176** (`feat(fixture): quadrado uniform 4-windows`) at
   `a29c9dcc` — squash, branch deleted. JSON + 12 invariant tests
   only; SKP build deferred per `CLAUDE.md` §23 artifact policy.
2. **Opened PR #177** (`chore(tools): track orphan SU diagnostic
   tools`): brings 4 long-orphan files (`tools/build_room_ring_skp.
   {py,rb}` + `tools/dump_skp_groups.{py,rb}`, +727 LOC) into
   `git ls-files`. They were already cited as live tooling in
   `CONTRIBUTING.md` (Live debugging), `docs/learning/
   failure_patterns.md` FP-014, and `docs/adr/
   ADR-003-plan-shell-exporter.md` §1, but had been sitting
   untracked. Initial push failed the `G-REPO-HEALTH` E006 gate;
   fixed by adding a §9 update-log row in `docs/PROJECT_STATE.md`.
   `repo_health_gate --mode check` is now ERROR=0 / WARN=48 / INFO=11
   (warnings are the project-wide W002 `Status:` header backlog, not
   PR-introduced).

## Most recent develop merges (last 5)

| PR  | Title                                                                                                | SHA       | Merged                |
|-----|------------------------------------------------------------------------------------------------------|-----------|-----------------------|
| #176| feat(fixture): quadrado uniform 4-windows — fidelity reference (JSON-only, SKP deferred)             | `a29c9dc` | 2026-05-25 14:53 UTC  |
| #175| feat(repo): artifact policy — promote quadrado canonical .skp + codify human_review/agent_inputs    | `ca4fef7` | 2026-05-25 02:13 UTC  |
| #173| chore(handoff): record post-#172 baseline — Slice 6b shipped, polygon-override loop closed          | `7245763` | 2026-05-25 01:31 UTC  |
| #172| feat(cockpit): Slice 6b — room_polygon_override producer rule + chip handler + text-area UX         | `2c61387` | 2026-05-25 01:28 UTC  |
| #171| feat(tools): restore soft-barrier and room polygon diagnostics                                       | `63f8df3` | 2026-05-24 23:44 UTC  |

## Pipeline state for planta_74 (unchanged from 2026-05-13)

The 4-axis verdict in
`fixtures/planta_74/fidelity_4axis_report.json` remains:

```
wall_fidelity            PASS  h_o005 cut_into_wall via h_w000
soft_barrier_fidelity    PASS  0 cells need a soft_barrier
semantic_room_fidelity   PASS  SALA labels preserved
global_visual_fidelity   WARN  operator-waived (issue #122)
verdict_top_level        WARN  (advisory only)
```

Visual-fidelity-gate policy (`CLAUDE.md` §10, 2026-05-14) requires the
7-artifact evidence pack for any `verdict_top_level: PASS`; until that
pack lands, planta_74 keeps the WARN with the documented advisory
waiver.

## Slice 6 polygon-override chain (ADR-002 §4)

| Slice | Status      | PR / Commit               | Notes                                                                 |
|-------|-------------|---------------------------|-----------------------------------------------------------------------|
| 6a    | MERGED      | #124 `f01a9ae`            | data plane (schema + apply + fidelity metadata)                       |
| 6b    | MERGED      | #172 `2c61387`            | producer rule + cockpit chip handler + text-area UX                   |
| 6c    | NOT STARTED | —                         | F0 `manual_polygon_room_count` + Pre-SKP pane. Deferred per #173.     |
| 6d    | DEFERRED    | —                         | graphical polygon edit UX — waits for Phase 3 (FastAPI + SPA)         |
| 6e    | DEFERRED    | —                         | `amended_consensus.json` for SKP exporter                             |

## Top of next-session queue (post #177 merge)

1. 🟢 **P2 — Smoke harness for the 4 newly-tracked SU tools**
   (env-detect SU 2026; skip cleanly in CI; same pattern as
   `scripts/smoke/smoke_skp_export.py`). Closes the "no tests yet"
   carve-out in PR #177.
2. 🟡 **P1 — Slice 6c** — F0 `manual_polygon_room_count` + Pre-SKP
   pane line. ~15 tests / ~80 LOC. LOW risk. Touchpoints in
   ADR-002 §4. **Do not start without explicit trigger** per #173.
3. 🟡 **P1 — Cycle 6 (Stage 1.6)** — wire autorun inspector into
   `gate_f`. SU runtime; focused session.
4. 🟢 **P2 — Cycle 7** — promote `--inspect-strict` default in CI
   (after Cycle 6).
5. ↘ **Issue #122** — visual-confirm advisory for planta_74; bundle
   into next planta_74 cycle, don't make it standalone.
6. 🔴 **P2 — REAL multi-PDF corpus** — needs Felipe to provide 3+
   real planta PDFs.

## Tooling notes

- **gh CLI** at `C:\Program Files\GitHub CLI\gh.exe`; not on Bash
  PATH. Always invoke via absolute path +
  `--repo GFCDOTA/sketchup-mcp`. Auth keyring
  (`fmodesto30`, scope `repo`). See
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.
- **Python on this machine:** the MS-Store `python.exe` stub
  points at a missing `Python312` install. Use
  `E:\Claude\sketchup-mcp\.venv\Scripts\python.exe` (repo venv,
  works) — or `py -3` once a real interpreter is reinstalled.
  Confirmed during this session by running `repo_health_gate`
  locally against PR #177.
- **Squash-merge is the established pattern** on this repo
  (see #170–#176 all squashed).
- `--delete-branch` deletes the remote branch on merge; the local
  feature branch must be deleted manually
  (`git branch -D <name>` after `git pull --ff-only`).
