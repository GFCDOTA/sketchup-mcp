"""Live resilience checks against the REAL CLIs (opt-in, --run-live).

R1 Claude with an empty config dir (not logged in) -> must NOT count as success.
R2 Codex with an empty CODEX_HOME (not logged in)  -> must NOT count as success.
R3 Claude killed by timeout                         -> retry, then DLQ + JOB_FAILED.
R4 Worker process killed while Claude is running    -> event survives, a restarted
   worker reclaims it after lease expiry and completes it.

python live_resilience.py --run-live --lab-dir <dir outside the checkout>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from event_store import EventStore
from run_real_e2e import SEEDED_V0, SEEDED_V0_TESTS, code_provenance
from workers import Ctx, JobPaths, handle_implement, handle_review, sha256_file

HERE = Path(__file__).resolve().parent


def pid_alive(pid: int) -> bool:
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def summary(store, job):
    return {"events": [(e["id"], e["event_type"], e["status"], e["attempt"]) for e in store.events(job)],
            "terminal": store.job_terminal(job)}


def r1_claude_auth(run_dir, store):
    empty = run_dir / "empty_claude_config"
    empty.mkdir()
    store.publish("IMPLEMENT_REQUESTED", "r1:implement", "r1-claude-auth", {"round": 1}, max_attempts=1)
    ev = store.claim("IMPLEMENT_REQUESTED", "r1-worker", 60)
    handle_implement(store, ev, Ctx(run_dir, 60, 120, {"CLAUDE_CONFIG_DIR": str(empty)}))
    s = summary(store, "r1-claude-auth")
    run = [r for r in store.runs() if r["event_id"] == ev["id"]][-1]
    ok = (s["terminal"] == "JOB_FAILED" and store.get(ev["id"])["status"] == "DLQ"
          and not any(t == "IMPLEMENT_COMPLETED" for _, t, _, _ in s["events"]))
    return {"pass": ok, "exit_code": run["exit_code"], "pid": run["pid"], "error": store.get(ev["id"])["error"][:300], **s}


def r2_codex_auth(run_dir, store):
    empty = run_dir / "empty_codex_home"
    empty.mkdir()
    p = JobPaths(run_dir, "r2-codex-auth")
    p.artifact.write_text(SEEDED_V0, encoding="utf-8")
    (p.workspace / "test_slugify.py").write_text(SEEDED_V0_TESTS, encoding="utf-8")
    store.publish("REVIEW_REQUESTED", "r2:review", "r2-codex-auth",
                  {"round": 0, "artifact_sha256": sha256_file(p.artifact)}, max_attempts=1)
    ev = store.claim("REVIEW_REQUESTED", "r2-worker", 60)
    handle_review(store, ev, Ctx(run_dir, 60, 120, {"CODEX_HOME": str(empty)}))
    s = summary(store, "r2-codex-auth")
    run = [r for r in store.runs() if r["event_id"] == ev["id"]][-1]
    ok = (s["terminal"] == "JOB_FAILED" and store.get(ev["id"])["status"] == "DLQ"
          and not any(t.startswith("REVIEW_APPROVED") or t == "REVIEW_CHANGES_REQUESTED" for _, t, _, _ in s["events"]))
    return {"pass": ok, "exit_code": run["exit_code"], "pid": run["pid"], "error": store.get(ev["id"])["error"][:300], **s}


def r3_claude_timeout(run_dir, store):
    store.publish("IMPLEMENT_REQUESTED", "r3:implement", "r3-claude-timeout", {"round": 1}, max_attempts=2)
    states = []
    for _ in range(2):
        ev = None
        for _ in range(10):  # wait out the retry backoff
            ev = store.claim("IMPLEMENT_REQUESTED", "r3-worker", 60)
            if ev:
                break
            time.sleep(0.5)
        handle_implement(store, ev, Ctx(run_dir, 60, 3))
        states.append(store.get(ev["id"])["status"])
    runs = [r for r in store.runs() if r["event_id"] == ev["id"]]
    ok = states == ["PENDING", "DLQ"] and all(r["timed_out"] == 1 for r in runs) and store.job_terminal("r3-claude-timeout") == "JOB_FAILED"
    return {"pass": ok, "states_after_each_attempt": states, "runs": [(r["pid"], r["exit_code"], r["timed_out"]) for r in runs],
            **summary(store, "r3-claude-timeout")}


def r4_kill_and_recover(run_dir, store):
    job = "r4-kill-recover"
    eid, _ = store.publish("IMPLEMENT_REQUESTED", "r4:implement", job, {"round": 1})
    common = [sys.executable, str(HERE / "workers.py"), "--role", "claude", "--run-dir", str(run_dir),
              "--lease", "20", "--timeout", "600"]
    log1 = open(run_dir / "evidence" / "r4_worker1.log", "w", encoding="utf-8")
    w1 = subprocess.Popen(common + ["--max-events", "1"], cwd=HERE, stdout=log1, stderr=subprocess.STDOUT)
    claude_pid = None
    for _ in range(120):
        runs = [r for r in store.runs() if r["event_id"] == eid]
        if runs:
            claude_pid = runs[0]["pid"]
            break
        time.sleep(0.5)
    time.sleep(5)  # let Claude actually start working
    subprocess.run(["taskkill", "/PID", str(w1.pid), "/T", "/F"], capture_output=True)
    w1.wait()
    log1.close()
    time.sleep(1)
    after_kill = store.get(eid)
    killed = {"worker_pid": w1.pid, "claude_pid": claude_pid, "worker_alive": pid_alive(w1.pid),
              "claude_alive": pid_alive(claude_pid) if claude_pid else None,
              "event_status_after_kill": after_kill["status"], "lease_owner": after_kill["lease_owner"]}
    time.sleep(max(0.0, after_kill["lease_until"] - time.time()) + 1)
    log2 = open(run_dir / "evidence" / "r4_worker2.log", "w", encoding="utf-8")
    w2 = subprocess.Popen(common + ["--max-events", "1"], cwd=HERE, stdout=log2, stderr=subprocess.STDOUT)
    w2.wait(timeout=900)
    log2.close()
    final = store.get(eid)
    runs = [r for r in store.runs() if r["event_id"] == eid]
    ok = (after_kill["status"] == "RUNNING" and not killed["worker_alive"] and not killed["claude_alive"]
          and final["status"] == "DONE" and final["attempt"] == 2
          and any(e["event_type"] == "REVIEW_REQUESTED" for e in store.events(job)))
    return {"pass": ok, "killed": killed, "restarted_worker_pid": w2.pid, "final_status": final["status"],
            "final_attempt": final["attempt"], "final_lease_owner": final["lease_owner"],
            "runs": [(r["pid"], r["exit_code"], r["outcome"]) for r in runs], **summary(store, job)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-live", action="store_true")
    ap.add_argument("--lab-dir", required=True)
    ap.add_argument("--only", default="R1,R2,R3,R4")
    a = ap.parse_args()
    if not a.run_live:
        print("No CLIs executed; pass --run-live explicitly")
        return 0
    lab = Path(a.lab_dir).resolve()
    if any((d / ".git").exists() for d in (lab, *lab.parents)):
        print("FAIL: lab dir must be outside any git checkout", file=sys.stderr)
        return 2
    run_dir = lab / datetime.now(timezone.utc).strftime("resilience_%Y%m%dT%H%M%SZ")
    (run_dir / "evidence").mkdir(parents=True)
    store = EventStore(run_dir / "queue.sqlite")
    fns = {"R1": r1_claude_auth, "R2": r2_codex_auth, "R3": r3_claude_timeout, "R4": r4_kill_and_recover}
    results = {}
    for key in a.only.split(","):
        print(f"--- {key}", flush=True)
        try:
            results[key] = fns[key](run_dir, store)
        except Exception as e:  # noqa: BLE001
            results[key] = {"pass": False, "exception": repr(e)}
        print(json.dumps(results[key], indent=1), flush=True)
    results["_code"] = {"pass": True, **code_provenance()}
    (run_dir / "evidence" / "resilience.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    (run_dir / "evidence" / "events.json").write_text(json.dumps(store.events(), indent=1), encoding="utf-8")
    (run_dir / "evidence" / "subprocess_runs.json").write_text(json.dumps(store.runs(), indent=1), encoding="utf-8")
    verdict = "PASS" if all(r["pass"] for r in results.values()) else "FAIL"
    print("evidence:", run_dir / "evidence")
    print("LIVE_RESILIENCE:", verdict)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
