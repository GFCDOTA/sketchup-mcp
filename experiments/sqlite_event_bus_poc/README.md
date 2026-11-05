# SQLite event-bus PoC — isolated experiment

Small proof of concept for FP-059. **Not wired to SketchUp, GitHub events, Claude Code or Codex CLI.**
All source lives under `experiments/sqlite_event_bus_poc/`. No runtime integrations, permissions or scheduled tasks are modified.

## Run (Python standard library only)

```bash
cd experiments/sqlite_event_bus_poc
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
