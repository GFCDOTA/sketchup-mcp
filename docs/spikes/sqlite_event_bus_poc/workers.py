"""Queue consumers. Each role runs as its own OS process and talks to the
others ONLY through the SQLite event store and files in the job workspace.

  claude      consumes IMPLEMENT_REQUESTED      -> real `claude -p`
  codex       consumes REVIEW_REQUESTED         -> real `codex exec --sandbox read-only`
  coordinator consumes REVIEW_CHANGES_REQUESTED -> next IMPLEMENT_REQUESTED or JOB_FAILED (no LLM)

Usage: python workers.py --role claude --run-dir <lab run dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from agents_cli import (
    child_env,
    claude_argv,
    codex_argv,
    parse_claude_json,
    redact,
    resolve_bins,
    run_cli,
)
from event_store import EventStore, LeaseLost

MAX_ROUNDS = 3
ARTIFACT = "slugify.py"

REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdict", "artifact_sha256", "inspected", "code_excerpt", "requirements", "tests_assessment",
                 "issues", "summary"],
    "properties": {
        "verdict": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES"]},
        "artifact_sha256": {"type": "string"},
        "inspected": {"type": "boolean"},
        "code_excerpt": {"type": "string"},
        "requirements": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "met", "evidence"],
            "properties": {"id": {"type": "string", "enum": ["lowercase", "strip_ends", "collapse_spaces", "example"]},
                           "met": {"type": "boolean"}, "evidence": {"type": "string"}}}},
        "tests_assessment": {"type": "object", "additionalProperties": False, "required": ["adequate", "notes"],
                             "properties": {"adequate": {"type": "boolean"}, "notes": {"type": "string"}}},
        "issues": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["severity", "description", "suggested_fix"],
            "properties": {"severity": {"type": "string", "enum": ["blocker", "major", "minor"]},
                           "description": {"type": "string"}, "suggested_fix": {"type": "string"}}}},
        "summary": {"type": "string"},
    },
}

# Harness-owned acceptance tests. Live OUTSIDE the agent workspace so the
# implementer cannot edit them to make itself pass.
ACCEPTANCE_TESTS = '''import unittest
from slugify import slugify

class Acceptance(unittest.TestCase):
    def test_example_from_spec(self):
        self.assertEqual(slugify(" Hello World "), "hello-world")
    def test_lowercases(self):
        self.assertEqual(slugify("ABC"), "abc")
    def test_strips_ends(self):
        self.assertEqual(slugify("   abc   "), "abc")
    def test_collapses_space_runs(self):
        self.assertEqual(slugify("a    b  c"), "a-b-c")
    def test_empty(self):
        self.assertEqual(slugify(""), "")

if __name__ == "__main__":
    unittest.main()
'''

SPEC = ("Create `slugify.py` defining `slugify(text: str) -> str` that: (1) converts the text to lowercase; "
        "(2) removes whitespace at both ends; (3) replaces each run of consecutive spaces with a single hyphen. "
        "Example: slugify(\" Hello World \") == \"hello-world\". Python standard library only.")


# --- helpers ---------------------------------------------------------------
def sha256_file(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def tree_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)).replace("\\", "/"): sha256_file(p)
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


class JobPaths:
    def __init__(self, run_dir: Path, job_id: str):
        self.root = run_dir / "jobs" / job_id
        self.workspace = self.root / "workspace"
        self.acceptance = self.root / "acceptance"
        self.codex = self.root / "codex"
        self.logs = run_dir / "evidence" / "logs"
        for d in (self.workspace, self.acceptance, self.codex, self.logs):
            d.mkdir(parents=True, exist_ok=True)
        (self.acceptance / "test_acceptance_slugify.py").write_text(ACCEPTANCE_TESTS, encoding="utf-8")
        (self.codex / "review_schema.json").write_text(json.dumps(REVIEW_SCHEMA, indent=1), encoding="utf-8")

    @property
    def artifact(self) -> Path:
        return self.workspace / ARTIFACT


def run_tests(paths: JobPaths) -> dict:
    """Run the implementer's own tests AND the harness acceptance tests."""
    py = sys.executable
    res = {}
    own = subprocess.run([py, "-m", "unittest", "discover", "-s", str(paths.workspace), "-p", "test_*.py", "-v"],
                         cwd=paths.workspace, capture_output=True, text=True, timeout=120)
    acc = subprocess.run([py, "-m", "unittest", "test_acceptance_slugify", "-v"], cwd=paths.acceptance,
                         capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PYTHONPATH": str(paths.workspace), "PYTHONDONTWRITEBYTECODE": "1"})
    for name, r in (("agent_tests", own), ("acceptance_tests", acc)):
        tail = r.stderr.strip().splitlines()
        res[name] = {"exit_code": r.returncode, "summary": " | ".join(tail[-3:]), "output": r.stderr[-3000:]}
    res["agent_tests"]["ran_zero"] = "Ran 0 tests" in own.stderr
    res["passed"] = own.returncode == 0 and acc.returncode == 0 and not res["agent_tests"]["ran_zero"]
    return res


class Heartbeat:
    """Renews the lease while a long CLI run is in progress. If the lease is
    lost (another worker reclaimed it), the result is later refused by the
    fenced complete()/fail()."""
    def __init__(self, store, ev, lease):
        self.store, self.ev, self.lease = store, ev, lease
        self.stop = threading.Event()
        self.lost = False
        self.t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop.wait(max(1.0, self.lease / 3)):
            if not self.store.renew(self.ev, self.lease):
                self.lost = True
                return

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.t.join(timeout=5)


def launch(store, ev, agent, argv, stdin_text, cwd, timeout, paths: JobPaths, extra_env=None):
    stem = paths.logs / f"e{ev['id']:03d}_a{ev['attempt']}_{agent}"
    holder = {}

    def started(pid):
        holder["run_id"] = store.run_started(ev["id"], agent, [redact(a) for a in argv], cwd, pid,
                                             f"{stem}.stdout.txt", f"{stem}.stderr.txt")
        print(f"[{agent}] event {ev['id']} attempt {ev['attempt']}: spawned pid={pid}", flush=True)

    (stem.with_suffix(".prompt.txt")).write_text(stdin_text, encoding="utf-8")
    run = run_cli(argv, stdin_text, cwd, timeout, f"{stem}.stdout.txt", f"{stem}.stderr.txt", on_start=started,
                  env=child_env({"PYTHONDONTWRITEBYTECODE": "1", **(extra_env or {})}))
    print(f"[{agent}] event {ev['id']}: pid={run.pid} exit={run.exit_code} timed_out={run.timed_out} "
          f"{run.duration_s}s", flush=True)
    return run, holder["run_id"], stem


# --- handlers --------------------------------------------------------------
def implement_prompt(ev) -> str:
    p = ev["payload"]
    lines = [
        "You are the IMPLEMENTATION agent working in an isolated lab directory (your current working directory).",
        SPEC,
        "Also create `test_slugify.py` with unittest tests that cover each requirement and sensible edge cases.",
        "Only create or edit `slugify.py` and `test_slugify.py` in the current directory. Do not touch any other "
        "path. No git, no network, no package installs.",
    ]
    if p.get("feedback"):
        lines += ["", f"This is correction round {p['round']}. An independent reviewer examined the CURRENT "
                  f"version of slugify.py (sha256 {p['reviewed_sha256']}) and requested changes. Read the current "
                  "files first, then fix every blocker/major issue below (minor ones too if cheap):",
                  json.dumps(p["feedback"], indent=1)]
    if ev.get("error"):
        lines += ["", "Your previous attempt on this same request was rejected by the harness with this error "
                  "(fix it):", ev["error"][-1500:]]
    lines += ["", "When finished, reply with a one-line summary of what you changed."]
    return "\n".join(lines)


def handle_implement(store, ev, ctx):
    paths = JobPaths(ctx.run_dir, ev["job_id"])
    before = sha256_file(paths.artifact)
    with Heartbeat(store, ev, ctx.lease) as hb:
        run, run_id, stem = launch(store, ev, "claude", claude_argv(ctx.bins), implement_prompt(ev),
                                   paths.workspace, ctx.timeout, paths, ctx.extra_env)
    outcome, err = "ok", None
    try:
        if run.timed_out:
            raise RuntimeError(f"claude timed out after {ctx.timeout}s (killed)")
        if run.exit_code != 0:
            try:  # surface the CLI's own message (e.g. "Not logged in") instead of a JSON tail
                d = json.loads(run.stdout)
                detail = f"is_error={d.get('is_error')} subtype={d.get('subtype')} result={str(d.get('result'))[:300]}"
            except ValueError:
                detail = f"stdout: {run.stdout[-300:]}"
            raise RuntimeError(f"claude exit {run.exit_code}; {detail}; stderr: {run.stderr[-300:]}")
        meta = parse_claude_json(run.stdout)
        if not paths.artifact.exists():
            raise RuntimeError("claude finished but slugify.py was not produced")
        after = sha256_file(paths.artifact)
        if ev["payload"].get("feedback") and after == before:
            raise RuntimeError("correction requested but slugify.py is byte-identical to the reviewed version")
        tests = run_tests(paths)
        (stem.with_suffix(".tests.json")).write_text(json.dumps(tests, indent=1), encoding="utf-8")
        if not tests["passed"]:
            raise RuntimeError("tests failed: agent_tests=" + tests["agent_tests"]["summary"] +
                               " ; acceptance=" + tests["acceptance_tests"]["summary"] + "\n" +
                               tests["acceptance_tests"]["output"][-800:])
    except Exception as e:  # noqa: BLE001 - every failure becomes a persisted retry/DLQ
        outcome, err = "failed", str(e)
    store.run_finished(run_id, run.exit_code, run.timed_out, outcome if not err else f"failed: {err[:200]}")
    if hb.lost:
        print(f"[claude] event {ev['id']}: lease lost during run; result discarded", flush=True)
        return
    try:
        if err:
            print(f"[claude] event {ev['id']} -> {store.fail(ev, err)}: {err[:200]}", flush=True)
            return
        rnd = ev["payload"]["round"]
        result = {"artifact": ARTIFACT, "artifact_sha256": after, "previous_sha256": before, "tests": {
            k: {"exit_code": tests[k]["exit_code"], "summary": tests[k]["summary"]} for k in ("agent_tests", "acceptance_tests")},
            "claude": {"session_id": meta.get("session_id"), "num_turns": meta.get("num_turns"),
                       "models": sorted((meta.get("modelUsage") or {}).keys()),
                       "permission_denials": meta.get("permission_denials"), "result": str(meta.get("result"))[:500]}}
        store.complete(ev, result, follow_ups=[
            {"event_type": "IMPLEMENT_COMPLETED", "idempotency_key": f"{ev['job_id']}:r{rnd}:implement_completed",
             "payload": {"round": rnd, "artifact_sha256": after, "implement_event_id": ev["id"]}},
            {"event_type": "REVIEW_REQUESTED", "idempotency_key": f"{ev['job_id']}:r{rnd}:review:{after[:16]}",
             "payload": {"round": rnd, "artifact_sha256": after}},
        ])
        print(f"[claude] event {ev['id']} DONE sha={after[:12]} -> REVIEW_REQUESTED", flush=True)
    except LeaseLost as e:
        print(f"[claude] {e}", flush=True)


def review_prompt(ev, sha, files: dict[str, str], harness_tests: dict) -> str:
    """The exact persisted file contents are embedded (bound to the sha):
    Codex's sandboxed shell on Windows intermittently fails to spawn
    processes, so reading must not depend on it. Tests are executed by the
    harness (Codex cannot run python.exe in its read-only sandbox here) and
    their real output is handed over for analysis."""
    blocks = []
    for name, text in files.items():
        blocks += [f"----- BEGIN {name} -----", text.rstrip("\n"), f"----- END {name} -----"]
    test_report = json.dumps({k: {"exit_code": v["exit_code"], "output": v["output"][-1500:]}
                              for k, v in harness_tests.items() if isinstance(v, dict) and "exit_code" in v}, indent=1)
    return "\n".join([
        "You are an independent CODE REVIEWER. You are in a read-only sandbox: do NOT modify, create or delete any file.",
        "The files under review are in the current directory and their exact contents are reproduced below "
        "(authoritative for this sha256). You may additionally inspect them with read-only commands.",
        *blocks,
        "Real test output, executed by the harness on this exact version (agent_tests = the implementer's "
        "test_slugify.py; acceptance_tests = independent harness tests):",
        test_report,
        "Requirements under review: " + SPEC,
        f"The version under review has sha256 {sha}. Echo it exactly in artifact_sha256.",
        "Set inspected=true only if you actually read the code above; put in code_excerpt one line copied verbatim "
        "from slugify.py that is central to your verdict.",
        "Evaluate each requirement id: lowercase, strip_ends, collapse_spaces, example — with concrete evidence.",
        "Assess whether the tests actually exercise the requirements.",
        "Report only REAL defects against the stated requirements or broken/inadequate tests as blocker/major. "
        "Style preferences or behavior the spec does not ask for are at most minor and must not block approval.",
        "verdict = APPROVE only if every requirement is met and there is no blocker/major issue; otherwise REQUEST_CHANGES.",
        "Return JSON matching the provided output schema.",
    ])


def validate_review(review: dict, sha: str, source: str) -> None:
    """Reject anything that is not a real, consistent review of THIS version.
    A reviewer that could not inspect the code produces an invalid review
    (-> retry/DLQ), never a verdict."""
    if review.get("verdict") not in ("APPROVE", "REQUEST_CHANGES"):
        raise ValueError("invalid verdict")
    if review.get("inspected") is not True:
        raise ValueError("reviewer reports it did not inspect the code; not a valid review")
    excerpt = (review.get("code_excerpt") or "").strip()
    if not excerpt or excerpt not in source:
        raise ValueError(f"code_excerpt {excerpt[:80]!r} is not a verbatim line of the reviewed slugify.py")
    if review.get("artifact_sha256") != sha:
        raise ValueError(f"review refers to sha {review.get('artifact_sha256')!r}, expected {sha}")
    ids = sorted(r["id"] for r in review["requirements"])
    if ids != sorted(["lowercase", "strip_ends", "collapse_spaces", "example"]):
        raise ValueError(f"requirements must cover each id exactly once, got {ids}")
    blocking = [i for i in review["issues"] if i["severity"] in ("blocker", "major")]
    unmet = [r["id"] for r in review["requirements"] if not r["met"]]
    if review["verdict"] == "APPROVE" and (blocking or unmet):
        raise ValueError(f"inconsistent review: APPROVE with unmet={unmet} blocking={len(blocking)}")
    if review["verdict"] == "REQUEST_CHANGES" and not review["issues"]:
        raise ValueError("inconsistent review: REQUEST_CHANGES without issues")


def handle_review(store, ev, ctx):
    paths = JobPaths(ctx.run_dir, ev["job_id"])
    sha = ev["payload"]["artifact_sha256"]
    current = sha256_file(paths.artifact)
    if current != sha:
        store.supersede(ev, f"stale review request: requested {sha[:12]}, workspace now {str(current)[:12]}")
        print(f"[codex] event {ev['id']} SUPERSEDED (stale version)", flush=True)
        return
    source = paths.artifact.read_text(encoding="utf-8")
    files = {ARTIFACT: source}
    tests_file = paths.workspace / "test_slugify.py"
    if tests_file.exists():
        files["test_slugify.py"] = tests_file.read_text(encoding="utf-8")
    harness_tests = run_tests(paths)
    snap_before = tree_digest(paths.workspace)
    out = paths.codex / f"review_e{ev['id']:03d}_a{ev['attempt']}.json"
    out.unlink(missing_ok=True)
    with Heartbeat(store, ev, ctx.lease) as hb:
        run, run_id, _ = launch(store, ev, "codex", codex_argv(ctx.bins, paths.workspace, paths.codex / "review_schema.json", out),
                                review_prompt(ev, sha, files, harness_tests), paths.workspace, ctx.timeout, paths,
                                ctx.extra_env)
    err, review = None, None
    try:
        if run.timed_out:
            raise RuntimeError(f"codex timed out after {ctx.timeout}s (killed)")
        if run.exit_code != 0:
            raise RuntimeError(f"codex exit {run.exit_code}; stderr: {run.stderr[-400:]}")
        if tree_digest(paths.workspace) != snap_before:
            raise RuntimeError("codex modified the workspace despite read-only review")
        if not out.exists() or not out.read_text(encoding="utf-8").strip():
            raise RuntimeError("codex produced no final message")
        review = json.loads(out.read_text(encoding="utf-8"))
        validate_review(review, sha, source)
    except Exception as e:  # noqa: BLE001
        err = str(e)
    store.run_finished(run_id, run.exit_code, run.timed_out, "ok" if not err else f"failed: {err[:200]}")
    if hb.lost:
        print(f"[codex] event {ev['id']}: lease lost; result discarded", flush=True)
        return
    try:
        if err:
            print(f"[codex] event {ev['id']} -> {store.fail(ev, err)}: {err[:200]}", flush=True)
            return
        if sha256_file(paths.artifact) != sha:  # artifact changed while Codex was reading
            store.supersede(ev, "artifact changed during review; verdict discarded")
            return
        rnd = ev["payload"]["round"]
        kind = "REVIEW_APPROVED" if review["verdict"] == "APPROVE" else "REVIEW_CHANGES_REQUESTED"
        store.complete(ev, review, follow_ups=[{
            "event_type": kind, "idempotency_key": f"{ev['job_id']}:r{rnd}:{kind.lower()}:{sha[:16]}",
            "payload": {"round": rnd, "artifact_sha256": sha, "review": review, "review_event_id": ev["id"]}}])
        print(f"[codex] event {ev['id']} DONE verdict={review['verdict']} -> {kind}", flush=True)
    except LeaseLost as e:
        print(f"[codex] {e}", flush=True)


def handle_changes(store, ev, ctx):
    """Coordinator: turns a change request into the next implementation round."""
    paths = JobPaths(ctx.run_dir, ev["job_id"])
    p = ev["payload"]
    if sha256_file(paths.artifact) != p["artifact_sha256"]:
        store.supersede(ev, "stale change request: it reviews an older artifact version")
        print(f"[coordinator] event {ev['id']} SUPERSEDED (stale review)", flush=True)
        return
    rnd = p["round"]
    if rnd >= MAX_ROUNDS:
        store.complete(ev, {"decision": "round limit reached"}, follow_ups=[{
            "event_type": "JOB_FAILED", "idempotency_key": f"{ev['job_id']}:job_failed:round_limit",
            "payload": {"reason": f"review still requests changes after {rnd} implementation rounds"}}])
        print(f"[coordinator] event {ev['id']} -> JOB_FAILED (round limit)", flush=True)
        return
    issues = p["review"]["issues"]
    store.complete(ev, {"decision": f"request correction round {rnd + 1}"}, follow_ups=[{
        "event_type": "IMPLEMENT_REQUESTED", "idempotency_key": f"{ev['job_id']}:r{rnd + 1}:implement",
        "payload": {"round": rnd + 1, "reviewed_sha256": p["artifact_sha256"], "feedback": issues,
                    "review_summary": p["review"]["summary"]}}])
    print(f"[coordinator] event {ev['id']} -> IMPLEMENT_REQUESTED round {rnd + 1}", flush=True)


ROLES = {"claude": ("IMPLEMENT_REQUESTED", handle_implement),
         "codex": ("REVIEW_REQUESTED", handle_review),
         "coordinator": ("REVIEW_CHANGES_REQUESTED", handle_changes)}


class Ctx:
    def __init__(self, run_dir, lease, timeout, extra_env=None):
        self.run_dir, self.lease, self.timeout = Path(run_dir).resolve(), lease, timeout
        self.bins = resolve_bins()
        self.extra_env = extra_env or {}


def active_events(store) -> int:
    return sum(e["status"] in ("PENDING", "RUNNING") for e in store.events())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=sorted(ROLES), required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--lease", type=float, default=60)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--max-wall", type=float, default=3600)
    ap.add_argument("--max-events", type=int, default=0, help="exit after N handled events (0 = unlimited)")
    ap.add_argument("--exit-when-idle", action="store_true", help="exit when no PENDING/RUNNING events remain")
    a = ap.parse_args(argv)
    ctx = Ctx(a.run_dir, a.lease, a.timeout)
    store = EventStore(ctx.run_dir / "queue.sqlite")
    event_type, handler = ROLES[a.role]
    owner = f"{a.role}-worker-pid{os.getpid()}"
    print(f"[{a.role}] worker up pid={os.getpid()} owner={owner}", flush=True)
    handled, t0 = 0, time.monotonic()
    while time.monotonic() - t0 < a.max_wall:
        ev = store.claim(event_type, owner, a.lease)
        if ev:
            handler(store, ev, ctx)
            handled += 1
            if a.max_events and handled >= a.max_events:
                break
            continue
        if a.exit_when_idle and active_events(store) == 0:
            break
        time.sleep(a.poll)
    print(f"[{a.role}] worker exit, handled={handled}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
