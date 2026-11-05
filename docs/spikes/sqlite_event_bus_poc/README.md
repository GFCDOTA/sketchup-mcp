# SQLite event-bus PoC — isolated experiment

Small proof of concept for FP-059. **Not wired to SketchUp, GitHub events, Claude Code or Codex CLI.**
All source lives under `docs/spikes/sqlite_event_bus_poc/`. No runtime integrations, permissions or scheduled tasks are modified.

## Run (Python standard library only)

```bash
cd docs/spikes/sqlite_event_bus_poc
python demo.py
python -m unittest discover -v
```

Expected demo:
```text
IMPLEMENT DONE {"artifact": "hello-world"}
REVIEW DONE {"verdict": "APPROVE"}
```

## What it tests

- Durable SQLite event queue with unique event-key deduplication.
- Transactional `BEGIN IMMEDIATE` claim: two competing consumers cannot claim the same event concurrently.
- Lease expiration and recovery after a worker disappears; an old owner cannot acknowledge a reclaimed job.
- Retry and terminal DLQ after three failures.
- Two *real subprocess invocations* with JSON via stdin/stdout: an implementation simulator and a review simulator.
- Restart persistence by reopening the database.

## What it deliberately does **not** prove

- Launching genuine `claude -p` or `codex exec`, authentication, GitHub PR publication or a persistent Windows service.
- Fencing a long-running subprocess at the OS level, robust heartbeat, exactly-once external side effects, migrations or production security.
- End-to-end autonomous coding/review, branch protections or agent independence.

## Next experiment

Replace `agent.py` with adapters that launch authenticated CLIs in isolated, read-only/scope-limited worktrees; keep the reliable publisher separate. Add heartbeat/cancellation, identity and SHA revalidation, safe replay, GitHub reconciliation and independent reviews **before** connecting to FP-057. Do not enable continuous execution from this PoC.

## Real-CLI lab (FP-059 follow-up): `event_store.py` + `workers.py`

Proves the flow **SQLite → real Claude Code CLI → `slugify.py` → SQLite → real Codex CLI → JSON review → SQLite → real Claude CLI (fix)** with three independent worker processes that share nothing but the SQLite file and the job workspace.

| File | Role |
|---|---|
| `event_store.py` | Events with id, type, payload, status, attempt/max_attempts, created/updated/available timestamps, UNIQUE idempotency key, lease owner/token/until; transition log; subprocess audit (PID, exit code, timeout). Claims are fenced by a lease token; `complete()` publishes follow-ups in the same transaction. |
| `agents_cli.py` | Launches the real CLIs. Claude: `-p --permission-mode dontAsk --tools Read,Write,Edit`, no user settings/hooks/MCP. Codex: `exec --sandbox read-only --ephemeral --output-schema`. Strips paid-API keys and GitHub tokens from the child env; refuses bypass flags. |
| `workers.py` | `claude` (IMPLEMENT_REQUESTED), `codex` (REVIEW_REQUESTED), `coordinator` (REVIEW_CHANGES_REQUESTED → next round, max 3, else JOB_FAILED). Harness-owned acceptance tests live outside the agent workspace. Stale versions (sha256 mismatch) are SUPERSEDED, never applied. |
| `run_real_e2e.py` | Opt-in E2E. Scenario A: Claude writes from scratch. Scenario B: a labeled, deliberately defective v0 is reviewed first, so the correction loop is exercised by the real agents. |
| `live_resilience.py` | Opt-in: Claude/Codex not logged in, Claude timeout → retry → DLQ, worker killed mid-run → restart recovers. |
| `test_event_store.py` | Deterministic tests (no LLM): dedup, atomic claim (2 OS processes), killed process + recovery, fencing, retry/DLQ, no re-run of DONE, stale review rejection, review-JSON validation. |

```bash
python -m unittest discover -v                                   # no LLM calls
python run_real_e2e.py --run-live --lab-dir <dir outside any git checkout>
python live_resilience.py --run-live --lab-dir <same>
```

Evidence of the recorded run: `evidence/2026-11-05_real_cli/REPORT.md`.

Still **not** proven: OS-level fencing of a running CLI after lease loss (the result is refused, but the process is not killed), exactly-once external side effects, GitHub reconciliation, continuous/scheduled operation. Do not wire this to FP-057 or SketchUp automation.
