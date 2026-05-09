# `.ai_bridge/` — persistent agent communication

Coordination files for cross-session work between Claude / ChatGPT /
other agents. **Tracked in git so context survives across machines,
branches, and sessions.**

## Files

| File | Lifecycle | Read at session start? |
|---|---|---|
| `PROJECT_CONTEXT.md` | stable | **yes** |
| `CURRENT_STATE.md` | per-session | **yes** |
| `HANDOFF.md` | per-session, **updated at end of every long session** | **yes** |
| `TODO_NEXT.md` | continuous, ROI-ordered | **yes** |
| `GPT_REQUESTS.md` | append-only log | when GPT needed |
| `GPT_RESPONSES.md` | append-only log | when GPT needed |
| `DECISIONS.md` | append-only ADR-lite | as needed |
| `LESSONS.md` | append-only learning log | as needed |
| `QUESTIONS_FOR_NEXT_AGENT.md` | only when blocked | as needed |

## Session start protocol (CLAUDE.md §17)

1. Read `CLAUDE.md`
2. Read `.ai_bridge/PROJECT_CONTEXT.md`
3. Read `.ai_bridge/CURRENT_STATE.md`
4. Read `.ai_bridge/HANDOFF.md`
5. Read `.ai_bridge/TODO_NEXT.md`
6. `git status` + branch
7. Continue from highest-ROI item; ask human only on real blocker

## Session end protocol

Update `HANDOFF.md` with status / branch+commit / files changed /
validation / open problems / next best actions / risks / GPT notes.

## Safety rules

- **No** credentials, tokens, passwords, cookies, private paths.
- **No** giant logs — summarize.
- **No** doc duplication — link.
- Compact every 3-5 PRs or weekly. Promote permanent rules →
  `CLAUDE.md`, decisions → `docs/adr/`, ops snapshots →
  `docs/ops/`, learnings → `docs/learning/`.

## Why this exists

Sessions end. Context is lost. Without persistent coordination,
each new session re-investigates state from scratch and may
re-litigate decisions. `.ai_bridge/` is the cheapest fix:
plain markdown, version-controlled, agent-readable.

It does NOT replace tests, metrics, or validation — it complements
them by giving agents continuity.
