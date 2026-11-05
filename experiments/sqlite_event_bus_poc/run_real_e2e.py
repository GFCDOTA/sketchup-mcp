"""Real E2E: SQLite -> Claude CLI -> slugify.py -> SQLite -> Codex CLI -> JSON review -> SQLite -> Claude (if needed).

Opt-in only (--run-live). Spawns three independent worker processes
(claude, codex, coordinator) that share nothing but the SQLite file and the
job workspace. No mocks: if either CLI is missing or not logged in, the run
FAILS.

Scenarios
  A  fresh      : IMPLEMENT_REQUESTED round 1 -> Claude writes slugify.py from scratch.
  B  seeded-bug : a human-written, deliberately defective slugify.py v0 is put in the
                  workspace and REVIEW_REQUESTED round 0 is published. The defect is a
                  labeled fixture; detecting it and fixing it is left to the real agents.

python run_real_e2e.py --run-live --lab-dir <dir outside the main checkout>
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agents_cli import resolve_bins
from event_store import EventStore
from workers import JobPaths, run_tests, sha256_file

HERE = Path(__file__).resolve().parent

SEEDED_V0 = '''def slugify(text):
    # SEEDED DEFECT (lab fixture): no strip, no collapse of space runs.
    return text.lower().replace(" ", "-")
'''
SEEDED_V0_TESTS = '''import unittest
from slugify import slugify

class T(unittest.TestCase):
    def test_lower(self):
        self.assertEqual(slugify("Hello"), "hello")

if __name__ == "__main__":
    unittest.main()
'''


def code_provenance() -> dict:
    """Commit the harness ran from, and whether the PoC dir was dirty."""
    def git(*a):
        r = subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--", "."))}


def cli_versions(bins) -> dict:
    out = {}
    for name, argv in bins.items():
        r = subprocess.run([*argv, "--version"], capture_output=True, text=True, timeout=60)
        out[name] = {"argv0": argv[-1], "version": (r.stdout or r.stderr).strip(), "exit_code": r.returncode}
    return out


def seed(store: EventStore, run_dir: Path, scenarios: str) -> list[str]:
    jobs = []
    if "A" in scenarios:
        JobPaths(run_dir, "jobA-fresh")
        eid, created = store.publish("IMPLEMENT_REQUESTED", "jobA-fresh:r1:implement", "jobA-fresh", {"round": 1})
        dup, created2 = store.publish("IMPLEMENT_REQUESTED", "jobA-fresh:r1:implement", "jobA-fresh",
                                      {"round": 1, "note": "DUPLICATE delivery must be ignored"})
        assert eid == dup and created and not created2, "duplicate publish created a second job"
        jobs.append("jobA-fresh")
    if "B" in scenarios:
        p = JobPaths(run_dir, "jobB-seeded-defect")
        p.artifact.write_text(SEEDED_V0, encoding="utf-8")
        (p.workspace / "test_slugify.py").write_text(SEEDED_V0_TESTS, encoding="utf-8")
        store.publish("REVIEW_REQUESTED", f"jobB-seeded-defect:r0:review:{sha256_file(p.artifact)[:16]}",
                      "jobB-seeded-defect", {"round": 0, "artifact_sha256": sha256_file(p.artifact), "seeded": True})
        jobs.append("jobB-seeded-defect")
    return jobs


def spawn_workers(run_dir: Path, args) -> dict:
    procs = {}
    for role in ("claude", "codex", "coordinator"):
        log = open(run_dir / "evidence" / f"worker_{role}.log", "w", encoding="utf-8")
        procs[role] = (subprocess.Popen(
            [sys.executable, str(HERE / "workers.py"), "--role", role, "--run-dir", str(run_dir),
             "--lease", str(args.lease), "--timeout", str(args.timeout), "--exit-when-idle",
             "--max-wall", str(args.max_wall)],
            cwd=HERE, stdout=log, stderr=subprocess.STDOUT), log)
    return procs


def evaluate(store: EventStore, run_dir: Path, jobs: list[str]) -> dict:
    runs = store.runs()
    by_agent = {a: [r for r in runs if r["agent"] == a] for a in ("claude", "codex")}
    checks = {
        "claude_cli_really_ran_ok": any(r["exit_code"] == 0 and r["outcome"] == "ok" for r in by_agent["claude"]),
        "codex_cli_really_ran_ok": any(r["exit_code"] == 0 and r["outcome"] == "ok" for r in by_agent["codex"]),
        "no_unfinished_events": all(e["status"] not in ("PENDING", "RUNNING") for e in store.events()),
        "every_accepted_review_inspected_code": all(
            json.loads(e["result"]).get("inspected") is True
            for e in store.events() if e["event_type"] == "REVIEW_REQUESTED" and e["status"] == "DONE"),
    }
    per_job = {}
    for job in jobs:
        evs = store.events(job)
        paths = JobPaths(run_dir, job)
        approved = [e for e in evs if e["event_type"] == "REVIEW_APPROVED"]
        final_sha = sha256_file(paths.artifact)
        tests = run_tests(paths) if paths.artifact.exists() else {"passed": False}
        rounds = max([json.loads(e["payload"]).get("round", 0) for e in evs if e["event_type"] == "IMPLEMENT_REQUESTED"] or [0])
        per_job[job] = {
            "terminal": store.job_terminal(job),
            "approved_sha_matches_final_artifact": bool(approved) and json.loads(approved[0]["payload"])["artifact_sha256"] == final_sha,
            "final_tests_pass": tests["passed"],
            "implementation_rounds": rounds,
            "changes_requested": sum(e["event_type"] == "REVIEW_CHANGES_REQUESTED" for e in evs),
            "dlq": sum(e["status"] == "DLQ" for e in evs),
            "final_sha256": final_sha,
        }
    checks["all_jobs_approved"] = all(j["terminal"] == "REVIEW_APPROVED" and j["approved_sha_matches_final_artifact"]
                                      and j["final_tests_pass"] for j in per_job.values())
    if "jobB-seeded-defect" in per_job:
        b = per_job["jobB-seeded-defect"]
        checks["correction_loop_exercised"] = b["changes_requested"] >= 1 and b["implementation_rounds"] >= 1
    return {"checks": checks, "jobs": per_job, "verdict": "PASS" if all(checks.values()) else "FAIL"}


def dump(store: EventStore, run_dir: Path, meta: dict, result: dict, jobs: list[str]) -> Path:
    ev_dir = run_dir / "evidence"
    events = store.events()
    for e in events:
        e["payload"] = json.loads(e["payload"])
        e["result"] = json.loads(e["result"]) if e["result"] else None
    (ev_dir / "events.json").write_text(json.dumps(events, indent=1), encoding="utf-8")
    (ev_dir / "transitions.json").write_text(json.dumps(store.transitions(), indent=1), encoding="utf-8")
    (ev_dir / "subprocess_runs.json").write_text(json.dumps(store.runs(), indent=1), encoding="utf-8")
    (ev_dir / "result.json").write_text(json.dumps({**meta, **result}, indent=1), encoding="utf-8")
    for job in jobs:
        p = JobPaths(run_dir, job)
        dst = ev_dir / "artifacts" / job
        dst.mkdir(parents=True, exist_ok=True)
        for f in p.workspace.glob("*.py"):
            shutil.copy2(f, dst / f.name)
        for f in p.codex.glob("review_e*.json"):
            shutil.copy2(f, dst / f.name)
    return ev_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-live", action="store_true")
    ap.add_argument("--lab-dir", required=True)
    ap.add_argument("--scenarios", default="AB")
    ap.add_argument("--lease", type=float, default=60)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--max-wall", type=float, default=3600)
    args = ap.parse_args()
    bins = resolve_bins()
    if not args.run_live:
        print("No CLIs executed; pass --run-live explicitly")
        return 0
    if set(bins) != {"claude", "codex"}:
        print("FAIL: both real CLIs are required", file=sys.stderr)
        return 2
    lab = Path(args.lab_dir).resolve()
    if any((d / ".git").exists() for d in (lab, *lab.parents)):
        print("FAIL: lab dir must be outside any git checkout", file=sys.stderr)
        return 2
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    run_dir = lab / run_id
    (run_dir / "evidence").mkdir(parents=True)
    store = EventStore(run_dir / "queue.sqlite")
    meta = {"run_id": run_id, "started_utc": datetime.now(timezone.utc).isoformat(), "cli": cli_versions(bins),
            "python": sys.version.split()[0], "lab_dir": str(run_dir), "code": code_provenance()}
    jobs = seed(store, run_dir, args.scenarios)
    procs = spawn_workers(run_dir, args)
    meta["worker_pids"] = {role: p.pid for role, (p, _) in procs.items()}
    print("workers:", meta["worker_pids"], flush=True)
    t0 = time.monotonic()
    while any(p.poll() is None for p, _ in procs.values()) and time.monotonic() - t0 < args.max_wall + 60:
        time.sleep(2)
    for role, (p, log) in procs.items():
        if p.poll() is None:
            p.kill()
        log.close()
        meta.setdefault("worker_exit_codes", {})[role] = p.returncode
    meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
    meta["wall_seconds"] = round(time.monotonic() - t0, 1)
    result = evaluate(store, run_dir, jobs)
    ev_dir = dump(store, run_dir, meta, result, jobs)
    print(json.dumps(result, indent=1))
    print("evidence:", ev_dir)
    print("REAL_CLI_E2E:", result["verdict"])
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
