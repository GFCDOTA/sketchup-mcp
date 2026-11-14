"""FP-060-A01 M1 (#606): laboratorio isolado do closed-loop minimo Claude <-> Codex sobre o EventStore de producao.

Suite deterministica (sem LLM): os CLIs sao substituidos por runners falsos; git, SQLite e o runner de testes sao reais.
A prova com os dois CLIs reais e operacional (`python -m tools.orchestration.closed_loop_lab drive`), nunca esta suite."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from tools.orchestration import closed_loop_lab as lab_mod
from tools.orchestration.closed_loop_lab import CliResult, Lab, LabError
from tools.orchestration.event_store import EventStore, LeaseLost

windows_only = pytest.mark.skipif(os.name != "nt", reason="requires real Windows Job Objects")

ASCII_FIX = '''"""lab_slug."""
import re


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text.strip("-")
'''

UNICODE_FIX = '''"""lab_slug."""
import re


def slugify(text: str) -> str:
    text = re.sub(r"[\\W_]+", "-", text.lower())
    return text.strip("-")
'''

BROKEN = '''"""lab_slug."""


def slugify(text: str) -> str:
    return text
'''

FINDING = {"severity": "HIGH", "file": "lab_slug.py", "line": 6, "reason": "regex ASCII remove letras Unicode (R2)",
           "required_change": "manter todo caractere com str.isalnum()"}


class Crash(BaseException):
    """Simula a morte abrupta do coordenador (nao e Exception: nenhum handler do laboratorio a engole)."""


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _result_line(is_error: bool = False, text: str = "feito") -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": is_error, "result": text,
                       "session_id": "fake", "num_turns": 2, "total_cost_usd": 0.0})


def writes(code: str, extra: dict | None = None, is_error: bool = False, rc: int = 0, before=None):
    def action(cwd: Path, pid: int) -> CliResult:
        if before:
            before()
        (cwd / lab_mod.ARTIFACT).write_text(code, encoding="utf-8", newline="\n")
        for rel, body in (extra or {}).items():
            (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
            (cwd / rel).write_text(body, encoding="utf-8", newline="\n")
        return CliResult(pid, rc, _result_line(is_error), "", False)
    return action


class FakeClaude:
    def __init__(self, *actions, containment="job_object"):
        self.actions, self.calls, self.containment = list(actions), [], containment

    def __call__(self, argv, cwd, env, stdin, timeout, on_start, **_) -> CliResult:
        pid = 4000 + len(self.calls)
        self.calls.append({"cwd": Path(cwd), "prompt": stdin, "argv": argv})
        on_start(pid)
        return self.actions.pop(0)(Path(cwd), pid)._replace(containment=self.containment)


def verdict(kind: str, findings: list | None = None, excerpt: str | None = None, touch: str | None = None,
            tests: tuple = ("tests/test_lab_slug.py",)):
    def action(repo: Path, out: Path, pid: int) -> CliResult:
        reviewed = []
        for rel in (lab_mod.ARTIFACT, lab_mod.REVIEW_TEST_FILE):
            if (repo / rel).is_file():
                data = (repo / rel).read_bytes()
                line = next(ln for ln in data.decode("utf-8").splitlines() if "re.sub" in ln or "return" in ln or "assert" in ln)
                reviewed.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(),
                                 "code_excerpt": excerpt if excerpt and rel == lab_mod.ARTIFACT else line})
        _, sha = lab_mod.git(["rev-parse", "HEAD"], repo)
        out.write_text(json.dumps({
            "pr": lab_mod.LAB_PR, "head_sha": sha, "verdict": kind, "findings": findings or [], "tests_reviewed": list(tests),
            "confidence": "HIGH", "files_reviewed": reviewed}), encoding="utf-8")
        if touch:
            (repo / touch).write_text("alterado pelo revisor", encoding="utf-8")
        return CliResult(pid, 0, "", "", False)
    return action


def cli_failure(rc: int, stderr: str):
    def action(repo: Path, out: Path, pid: int) -> CliResult:
        return CliResult(pid, rc, "", stderr, False)
    return action


class FakeCodex:
    def __init__(self, *actions, containment="job_object"):
        self.actions, self.calls, self.containment = list(actions), [], containment

    def __call__(self, argv, cwd, env, stdin, timeout, on_start, **_) -> CliResult:
        pid = 5000 + len(self.calls)
        self.calls.append({"prompt": stdin, "argv": argv})
        on_start(pid)
        repo, out = Path(argv[argv.index("-C") + 1]), Path(argv[argv.index("--output-last-message") + 1])
        return self.actions.pop(0)(repo, out, pid)._replace(containment=self.containment)


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def env(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "governance" / "event_bridge.json"))
    lab = Lab(tmp_path / "lab")
    lab.root.mkdir()
    store = EventStore(lab.db, clock=clock)
    lab_mod.seed(lab, store)
    return lab, store


def run(lab, store, claude, codex, owner="lab-coordinator:1", **kw):
    return lab_mod.step(lab, store, owner, claude_runner=claude, codex_runner=codex, claude_bin="claude", codex_bin="codex", **kw)


def drive(lab, store, claude, codex, limit=20):
    actions = []
    for i in range(limit):
        res = run(lab, store, claude, codex, owner=f"lab-coordinator:{i}")
        actions.append(res["action"])
        if res["action"] in ("TERMINAL", "IDLE"):
            break
    return actions


def types(store):
    return [e["event_type"] for e in store.events(lab_mod.JOB_ID)]


def commits(lab):
    _, out = lab_mod.git(["rev-list", "--count", "HEAD"], lab.repo)
    return int(out)


def test_seed_publishes_one_implement_request_for_a_failing_artifact(env):
    lab, store = env
    events = store.events(lab_mod.JOB_ID)
    assert [(e["event_type"], e["status"]) for e in events] == [("IMPLEMENT_REQUESTED", "PENDING")]
    assert commits(lab) == 1


def test_duplicate_seed_event_does_not_create_a_second_job(env):
    lab, store = env
    first = store.events(lab_mod.JOB_ID)[0]
    eid, created = store.publish("IMPLEMENT_REQUESTED", first["idempotency_key"], lab_mod.JOB_ID, {"round": 1})
    assert (eid, created) == (first["id"], False)
    assert len(store.events(lab_mod.JOB_ID)) == 1


def test_request_changes_then_correction_then_approve_completes_the_workflow(env):
    lab, store = env
    claude = FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX))
    codex = FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE"))

    actions = drive(lab, store, claude, codex)

    assert actions == ["DELIVERED", "CHANGES_REQUESTED", "CORRECTION_DISPATCHED", "DELIVERED", "APPROVED", "TERMINAL"]
    assert types(store) == ["IMPLEMENT_REQUESTED", "IMPLEMENT_COMPLETED", "REVIEW_REQUESTED", "REVIEW_CHANGES_REQUESTED",
                            "CORRECTION_REQUESTED", "IMPLEMENT_COMPLETED", "REVIEW_REQUESTED", "REVIEW_APPROVED",
                            "WORKFLOW_COMPLETED"]
    assert {e["status"] for e in store.events(lab_mod.JOB_ID)} == {"DONE", "RECORDED"}
    assert (lab.repo / lab_mod.ARTIFACT).read_text(encoding="utf-8") == UNICODE_FIX
    assert commits(lab) == 3
    assert [(r["agent"], r["pid"], r["exit_code"]) for r in store.runs()] == [
        ("claude", 4000, 0), ("codex", 5000, 0), ("claude", 4001, 0), ("codex", 5001, 0)]


def test_correction_prompt_carries_the_reviewer_findings_and_the_spec(env):
    lab, store = env
    claude = FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX))
    drive(lab, store, claude, FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE")))

    assert FINDING["reason"] not in claude.calls[0]["prompt"]
    assert FINDING["reason"] in claude.calls[1]["prompt"]
    assert "isalnum" in claude.calls[1]["prompt"]


def test_correction_may_add_a_regression_test_that_is_run_delivered_and_reviewed(env):
    lab, store = env
    regression = 'from lab_slug import slugify\n\n\ndef test_unicode_letters_are_kept():\n    assert slugify("Café") == "café"\n'
    claude = FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX, extra={lab_mod.REVIEW_TEST_FILE: regression}))
    both = (lab_mod.TEST_FILE, lab_mod.REVIEW_TEST_FILE)
    codex = FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE", tests=both))

    actions = drive(lab, store, claude, codex)

    assert actions[-2:] == ["APPROVED", "TERMINAL"]
    assert (lab.repo / lab_mod.REVIEW_TEST_FILE).read_text(encoding="utf-8") == regression
    review = [e for e in store.events(lab_mod.JOB_ID) if e["event_type"] == "REVIEW_REQUESTED"][-1]
    assert json.loads(review["result"])["evidence"]["selected"] == sorted(both)
    assert lab_mod.REVIEW_TEST_FILE in claude.calls[1]["prompt"]


def test_needs_human_verdict_escalates_once_and_never_approves(env):
    lab, store = env
    codex = FakeCodex(verdict("NEEDS_HUMAN"))
    run(lab, store, FakeClaude(writes(UNICODE_FIX)), codex)

    res = run(lab, store, FakeClaude(), codex)

    assert res["action"] == "ESCALATED" and len(codex.calls) == 1
    assert types(store)[-2:] == ["REVIEW_BLOCKED", "JOB_FAILED"]
    assert run(lab, store, FakeClaude(), codex) == {"action": "TERMINAL", "state": "JOB_FAILED"}


def test_is_error_true_with_exit_zero_is_a_failure_not_a_delivery(env):
    lab, store = env
    res = run(lab, store, FakeClaude(writes(ASCII_FIX, is_error=True)), FakeCodex())

    assert res["action"] == "FAILED"
    assert commits(lab) == 1
    assert types(store) == ["IMPLEMENT_REQUESTED"]
    assert store.events(lab_mod.JOB_ID)[0]["status"] == "PENDING"


def test_change_outside_the_allowed_artifact_is_rejected(env):
    lab, store = env
    hostile = writes(ASCII_FIX, extra={"tests/test_lab_slug.py": "def test_ok():\n    assert True\n"})

    res = run(lab, store, FakeClaude(hostile), FakeCodex())

    assert res["action"] == "FAILED" and "fora do escopo" in res["reason"]
    assert commits(lab) == 1 and types(store) == ["IMPLEMENT_REQUESTED"]


def test_new_file_planted_by_the_agent_is_rejected_before_tests_run(env):
    lab, store = env
    res = run(lab, store, FakeClaude(writes(ASCII_FIX, extra={"conftest.py": "raise SystemExit(0)\n"})), FakeCodex())

    assert res["action"] == "FAILED" and "conftest.py" in res["reason"]
    assert commits(lab) == 1


def test_failing_trusted_tests_block_delivery_and_feed_the_retry(env, clock):
    lab, store = env
    claude = FakeClaude(writes(BROKEN), writes(ASCII_FIX))

    first = run(lab, store, claude, FakeCodex())
    after_first = commits(lab)
    clock.advance(5)
    second = run(lab, store, claude, FakeCodex())

    assert first["action"] == "FAILED" and after_first == 1
    assert second["action"] == "DELIVERED" and commits(lab) == 2
    assert "testes do coordenador" in claude.calls[1]["prompt"]


def test_review_without_literal_inspection_proof_is_blocked_never_approved(env):
    lab, store = env
    codex = FakeCodex(verdict("APPROVE", excerpt="linha que nao existe no arquivo"))
    run(lab, store, FakeClaude(writes(UNICODE_FIX)), codex)

    res = run(lab, store, FakeClaude(), codex)

    assert res["action"] == "REVIEW_BLOCKED" and "code_excerpt" in res["reason"]
    assert "REVIEW_BLOCKED" in types(store)
    assert "REVIEW_APPROVED" not in types(store) and "WORKFLOW_COMPLETED" not in types(store)


def test_approve_without_reviewing_the_executed_tests_is_blocked(env):
    lab, store = env
    codex = FakeCodex(verdict("APPROVE", tests=("tests/test_outro.py",)))
    run(lab, store, FakeClaude(writes(UNICODE_FIX)), codex)

    res = run(lab, store, FakeClaude(), codex)

    assert res["action"] == "REVIEW_BLOCKED" and "tests_reviewed" in res["reason"]


def test_reviewer_that_alters_the_workspace_invalidates_its_own_verdict(env):
    lab, store = env
    codex = FakeCodex(verdict("APPROVE", touch="plantado.txt"))
    run(lab, store, FakeClaude(writes(UNICODE_FIX)), codex)

    res = run(lab, store, FakeClaude(), codex)

    assert res["action"] == "REVIEW_BLOCKED" and "alterou" in res["reason"]
    assert "REVIEW_APPROVED" not in types(store)


def test_reviewer_auth_failure_is_blocked_and_retried_never_success(env):
    lab, store = env
    codex = FakeCodex(cli_failure(1, "Error: not logged in. Run codex login"))
    run(lab, store, FakeClaude(writes(UNICODE_FIX)), codex)

    res = run(lab, store, FakeClaude(), codex)

    review = [e for e in store.events(lab_mod.JOB_ID) if e["event_type"] == "REVIEW_REQUESTED"][0]
    assert res["action"] == "REVIEW_BLOCKED" and "auth" in res["reason"]
    assert review["status"] == "PENDING" and review["attempt"] == 1
    assert store.runs()[-1]["exit_code"] == 1


def test_round_limit_ends_in_job_failed_without_completion(env):
    lab, store = env
    claude = FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX))
    codex = FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("REQUEST_CHANGES", [FINDING]))

    actions = [run(lab, store, claude, codex, max_rounds=2)["action"] for _ in range(7)]

    assert actions[-2:] == ["ROUND_LIMIT", "TERMINAL"]
    assert types(store)[-1] == "JOB_FAILED" and "WORKFLOW_COMPLETED" not in types(store)


def test_pause_flag_blocks_claims_and_cli_launch(env):
    lab, store = env
    lab.pause_flag.write_text("pausado", encoding="utf-8")
    claude = FakeClaude(writes(ASCII_FIX))

    res = run(lab, store, claude, FakeCodex())

    assert res["action"] == "PAUSED" and not claude.calls
    assert store.events(lab_mod.JOB_ID)[0]["status"] == "PENDING"


def test_coordinator_crash_after_claim_is_recovered_by_a_new_owner_after_lease_expiry(env, clock):
    lab, store = env
    claude = FakeClaude(writes(ASCII_FIX))

    def die(ev):
        raise Crash()

    with pytest.raises(Crash):
        run(lab, store, claude, FakeCodex(), owner="lab-coordinator:dead", on_claimed=die)
    assert run(lab, store, claude, FakeCodex(), owner="lab-coordinator:2")["action"] == "IDLE"
    clock.advance(lab_mod.CLAIM_LEASE_S + 1)
    res = run(lab, store, claude, FakeCodex(), owner="lab-coordinator:2")

    assert res["action"] == "DELIVERED" and len(claude.calls) == 1
    assert store.events(lab_mod.JOB_ID)[0]["attempt"] == 2


def test_worker_that_lost_its_lease_cannot_deliver_a_late_result(env, clock):
    lab, store = env
    slow = FakeClaude(writes(ASCII_FIX, before=lambda: clock.advance(lab_mod.RUN_LEASE_S + 1)), writes(ASCII_FIX))

    late = run(lab, store, slow, FakeCodex(), owner="lab-coordinator:slow")
    assert late["action"] == "LEASE_LOST" and commits(lab) == 1
    assert "REVIEW_REQUESTED" not in types(store)

    res = run(lab, store, slow, FakeCodex(), owner="lab-coordinator:new")
    assert res["action"] == "DELIVERED" and commits(lab) == 2


def test_crash_between_delivery_and_ack_is_reconciled_without_a_second_commit(env, clock, monkeypatch):
    lab, store = env
    claude = FakeClaude(writes(ASCII_FIX))
    real, seen = store.complete, []

    def flaky(ev, result, follow_ups=(), outbox_entries=()):
        if not seen:
            seen.append(ev["id"])
            raise Crash()
        return real(ev, result, follow_ups, outbox_entries)

    monkeypatch.setattr(store, "complete", flaky)
    with pytest.raises(Crash):
        run(lab, store, claude, FakeCodex())
    assert commits(lab) == 2 and "REVIEW_REQUESTED" not in types(store)

    clock.advance(lab_mod.RUN_LEASE_S + 1)
    res = run(lab, store, claude, FakeCodex(), owner="lab-coordinator:2")

    assert res["action"] == "DELIVERED" and res["reconciled"] is True
    assert len(claude.calls) == 1 and commits(lab) == 2
    assert types(store).count("REVIEW_REQUESTED") == 1


def test_two_coordinators_racing_launch_a_single_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "governance" / "event_bridge.json"))
    lab = Lab(tmp_path / "lab")
    lab.root.mkdir()
    lab_mod.seed(lab, EventStore(lab.db))
    entered, release, out = threading.Event(), threading.Event(), {}
    claude = FakeClaude(writes(ASCII_FIX, before=lambda: (entered.set(), release.wait(30))))

    t = threading.Thread(target=lambda: out.update(a=run(lab, EventStore(lab.db), claude, FakeCodex(), owner="lab-coordinator:a")))
    t.start()
    assert entered.wait(30)
    out["b"] = run(lab, EventStore(lab.db), claude, FakeCodex(), owner="lab-coordinator:b")
    release.set()
    t.join(60)

    assert out["b"]["action"] == "IDLE" and out["a"]["action"] == "DELIVERED"
    assert len(claude.calls) == 1 and commits(lab) == 2


def test_lab_refuses_a_directory_inside_another_git_repository(tmp_path):
    (tmp_path / ".git").mkdir()
    lab = Lab(tmp_path / "inner" / "lab")
    lab.root.mkdir(parents=True)

    with pytest.raises(LabError, match="repositorio git"):
        lab_mod.seed(lab, EventStore(lab.db))


def killed_cli(lab, store, alive=()):
    """Um CLI cujo coordenador morreu com ele no ar (run sem termino) + a verificacao da arvore feita pelo driver."""
    run_id = store.run_started(1, "claude", ["C:/bin/claude.exe"], lab.repo, 4999, lab.logs / "o.txt", lab.logs / "e.txt")
    lab_mod.record_orphan_check(lab, {"run": run_id, "agent": "claude", "pid": 4999, "grace_s": 2.0, "alive": list(alive)})
    return run_id


def test_report_passes_only_when_every_m1_criterion_is_derived_from_the_store(env):
    lab, store = env
    killed_cli(lab, store)
    drive(lab, store, FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX)),
          FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["verdict"] == "PASS" and all(rep["criteria"].values())
    assert rep["final_head"] == rep["approved_head"]
    assert [r["pid"] for r in rep["runs"]] == [4999, 4000, 5000, 4001, 5001]
    assert [r["containment"] for r in rep["runs"]] == [None, "job_object", "job_object", "job_object", "job_object"]


def test_report_fails_when_no_cli_was_killed_with_its_coordinator(env):
    lab, store = env
    drive(lab, store, FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX)),
          FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["criteria"]["orphan_cli_tree_dead_after_coordinator_kill"] is False and rep["verdict"] == "FAIL"


def test_report_fails_when_an_orphan_cli_tree_is_still_alive(env):
    lab, store = env
    killed_cli(lab, store, alive=[4999, 5123])
    drive(lab, store, FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX)),
          FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["criteria"]["orphan_cli_tree_dead_after_coordinator_kill"] is False and rep["verdict"] == "FAIL"
    assert rep["orphan_checks"][0]["alive"] == [4999, 5123]


def test_report_fails_when_a_finished_cli_ran_outside_a_job_object(env):
    lab, store = env
    killed_cli(lab, store)
    drive(lab, store, FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX), containment="none"),
          FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["criteria"]["finished_cli_runs_job_contained"] is False and rep["verdict"] == "FAIL"


def test_default_runner_is_the_job_object_supervisor_on_windows_only():
    expected = lab_mod.run_supervised if os.name == "nt" else lab_mod.run_observed
    assert lab_mod.default_runner() is expected
    assert lab_mod.default_runner("observed") is lab_mod.run_observed


def _real_env():
    return {"SystemRoot": os.environ["SystemRoot"], "TEMP": os.environ["TEMP"], "TMP": os.environ["TEMP"]}


def _io(tmp_path, prompt):
    stdin, stdout, stderr = tmp_path / "in.txt", tmp_path / "out.txt", tmp_path / "err.txt"
    stdin.write_text(prompt, encoding="utf-8")
    return stdin, stdout, stderr


@windows_only
def test_supervised_runner_returns_real_output_pid_and_job_containment(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "lab:x", {})
    ev = store.claim("IMPLEMENT_REQUESTED", "lab-coordinator:t", 20)
    pids = []
    script = "import sys; sys.stdout.write(sys.stdin.read()[::-1]); sys.stderr.write('aviso'); raise SystemExit(4)"

    res = lab_mod.run_supervised([sys.executable, "-c", script], tmp_path, _real_env(), "abc", 30, pids.append,
                                 lease=(store, ev), io=_io(tmp_path, "abc"))

    assert (res.exit_code, res.stdout, res.stderr, res.timed_out, res.containment) == (4, "cba", "aviso", False, "job_object")
    assert pids == [res.pid] and res.pid > 0
    assert store.renew(ev, 5) is True


@windows_only
def test_supervised_runner_kills_the_cli_tree_and_raises_when_the_lease_is_lost(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "lab:x", {})
    ev = store.claim("IMPLEMENT_REQUESTED", "lab-coordinator:t", 20)
    ready, effect = tmp_path / "ready", tmp_path / "effect"
    child = f"from pathlib import Path; import time; Path({str(ready)!r}).write_text('r'); time.sleep(3); Path({str(effect)!r}).write_text('escapou')"
    root = tmp_path / "root.py"
    root.write_text(f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(60)\n", encoding="utf-8")
    outcome = []

    def work():
        try:
            lab_mod.run_supervised([sys.executable, str(root)], tmp_path, _real_env(), "", 60, lambda pid: None,
                                   lease=(store, ev), io=_io(tmp_path, ""))
            outcome.append("returned")
        except LeaseLost:
            outcome.append("lease_lost")

    t = threading.Thread(target=work)
    t.start()
    deadline = time.monotonic() + 20
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert ready.exists()
    with store._tx() as db:
        db.execute("UPDATE events SET lease_until=0 WHERE id=?", (ev["id"],))
    t.join(30)

    assert outcome == ["lease_lost"]
    time.sleep(3.5)
    assert not effect.exists()


def test_cli_started_hook_sees_agent_event_and_pid_after_the_audit_row_exists(env):
    lab, store = env
    seen = []

    def hook(agent, ev, pid):
        seen.append((agent, ev["event_type"], pid, [r["pid"] for r in store.runs()]))

    run(lab, store, FakeClaude(writes(ASCII_FIX)), FakeCodex(), on_cli_started=hook)

    assert seen == [("claude", "IMPLEMENT_REQUESTED", 4000, [4000])]


def not_logged_in(cwd: Path, pid: int) -> CliResult:
    """Assinatura medida no Claude Code 2.1.158 sem login: exit 1, subtype success, is_error true."""
    return CliResult(pid, 1, _result_line(True, "Not logged in · Please run /login"), "", False)


def exhaust(lab, store, clock, claude, codex, tries=6):
    out = []
    for i in range(tries):
        out.append(run(lab, store, claude, codex, owner=f"lab-coordinator:{i}")["action"])
        clock.advance(2)
    return out


def test_real_claude_not_logged_in_signature_is_classified_as_credential_failure(env):
    lab, store = env
    res = run(lab, store, FakeClaude(not_logged_in), FakeCodex())

    assert res["action"] == "FAILED" and "credencial" in res["reason"]
    assert commits(lab) == 1 and store.runs()[0]["exit_code"] == 1


def test_fault_env_points_only_the_faulted_cli_at_a_lab_owned_config_dir(tmp_path):
    lab = Lab(tmp_path / "lab")
    lab.root.mkdir()
    lab_mod.declare_fault(lab, "claude-auth")

    env_ = lab_mod.fault_env(lab, base={"PATH": "x", "CLAUDE_CONFIG_DIR": "real", "CODEX_HOME": "real"})

    assert Path(env_["CLAUDE_CONFIG_DIR"]).parent.parent == lab.root and Path(env_["CLAUDE_CONFIG_DIR"]).is_dir()
    assert env_["CODEX_HOME"] == "real" and env_["PATH"] == "x"
    assert lab_mod.fault_env(Lab(tmp_path / "sem_falha"), base={"CODEX_HOME": "real"}) == {"CODEX_HOME": "real"}


def test_declared_fault_cannot_change_when_a_lab_is_resumed(tmp_path):
    lab = Lab(tmp_path / "lab")
    lab.root.mkdir()
    lab_mod.declare_fault(lab, "claude-auth")
    lab_mod.declare_fault(lab, "claude-auth")

    with pytest.raises(LabError, match="claude-auth"):
        lab_mod.declare_fault(lab, "codex-auth")


def test_negative_report_passes_when_claude_auth_failure_dead_letters_with_nothing_delivered(env, clock):
    lab, store = env
    lab_mod.declare_fault(lab, "claude-auth")
    claude = FakeClaude(not_logged_in, not_logged_in, not_logged_in)

    actions = exhaust(lab, store, clock, claude, FakeCodex())
    rep = lab_mod.report(lab, store)

    assert actions[:3] == ["FAILED"] * 3 and actions[-1] == "TERMINAL" and len(claude.calls) == 3
    assert rep["mode"] == "negative:claude-auth" and rep["verdict"] == "PASS" and all(rep["criteria"].values())
    assert len(rep["commits"]) == 1 and "credencial" in rep["failure_reasons"][0]
    assert "negative:claude-auth" in lab_mod.render_markdown(rep)


def test_negative_report_for_codex_auth_keeps_the_delivery_and_blocks_every_review(env, clock):
    lab, store = env
    lab_mod.declare_fault(lab, "codex-auth")
    unauthorized = cli_failure(1, "ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header")
    codex = FakeCodex(unauthorized, unauthorized, unauthorized)

    actions = exhaust(lab, store, clock, FakeClaude(writes(UNICODE_FIX)), codex)
    rep = lab_mod.report(lab, store)

    assert actions[:4] == ["DELIVERED", "REVIEW_BLOCKED", "REVIEW_BLOCKED", "REVIEW_BLOCKED"] and actions[-1] == "TERMINAL"
    assert rep["verdict"] == "PASS" and len(rep["commits"]) == 2 and len(rep["blocked_reviews"]) == 3
    assert types(store)[-1] == "JOB_FAILED" and "REVIEW_APPROVED" not in types(store)


def test_negative_report_fails_when_the_faulted_cli_still_completes_work(env):
    lab, store = env
    lab_mod.declare_fault(lab, "claude-auth")
    drive(lab, store, FakeClaude(writes(UNICODE_FIX)), FakeCodex(verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["verdict"] == "FAIL"
    assert rep["criteria"]["faulted_cli_never_completed_an_event"] is False


def test_failure_reason_keeps_the_cause_but_drops_network_identifiers(env):
    lab, store = env
    noisy = ("ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, "
             "url: https://api.openai.com/v1/responses, cf-ray: a58178ef494c82ee-GIG, request id: req_416029f472244cae96c7")
    codex = FakeCodex(cli_failure(1, noisy))
    run(lab, store, FakeClaude(writes(UNICODE_FIX)), codex)

    res = run(lab, store, FakeClaude(), codex)

    stored = json.dumps([res, lab_mod.report(lab, store)])
    assert "401 Unauthorized" in res["reason"]
    assert "cf-ray" not in stored and "a58178ef494c82ee" not in stored and "req_416029f4" not in stored


def test_machine_readable_output_is_pure_ascii_whatever_the_console_encoding(capsys):
    payload = {"action": "FAILED", "reason": "Not logged in · Please run /login — não é sucesso �"}

    lab_mod._emit(payload)

    line = capsys.readouterr().out.strip()
    assert line.isascii() and json.loads(line) == payload


def test_report_shows_a_run_without_recorded_end_as_interrupted(env):
    lab, store = env
    store.run_started(1, "codex", ["C:/bin/codex.exe", "exec"], lab.repo, 777, lab.logs / "o.txt", lab.logs / "e.txt")

    rep = lab_mod.report(lab, store)

    assert rep["interrupted_runs"] == [1]
    assert rep["runs"][0]["finished"] is False and rep["runs"][0]["seconds"] is None
    assert rep["runs"][0]["binary"] == "codex.exe" and rep["lab"] == "lab"
    assert "INTERROMPIDO" in lab_mod.render_markdown(rep)


def test_report_fails_m1_when_the_correction_loop_was_not_exercised(env):
    lab, store = env
    drive(lab, store, FakeClaude(writes(UNICODE_FIX)), FakeCodex(verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["criteria"]["workflow_completed"] is True
    assert rep["criteria"]["request_changes_then_correction"] is False
    assert rep["verdict"] == "FAIL"


# -- driver, CLI e verificacao de orfaos (lacunas apontadas pelo crapper, 2026-11-13) -----------------------------------------
def _ok_preflight():
    return {"ok": True, "claude": {"version": "fake"}, "codex": {"version": "fake"}}


def in_process_steps(lab, claude, codex, seen):
    """Substitui o processo `step` por uma chamada em-processo com CLIs falsos; devolve o que o processo imprimiria."""
    def run_step(argv, env):
        seen.append(list(argv))
        res = lab_mod.step(lab, EventStore(lab.db), f"lab-coordinator:{len(seen)}", claude_runner=claude, codex_runner=codex,
                           claude_bin="claude", codex_bin="codex")
        return 0, json.dumps(res), ""
    return run_step


def scripted_steps(seen, *outputs):
    """Cada chamada devolve a proxima tupla (exit code, stdout, stderr); a ultima se repete."""
    def run_step(argv, env):
        seen.append(list(argv))
        out = outputs[min(len(seen), len(outputs)) - 1]
        return out() if callable(out) else out
    return run_step


PAUSED = (0, json.dumps({"action": "PAUSED"}), "")
IDLE = (0, json.dumps({"action": "IDLE"}), "")


def drive_log(lab):
    return [json.loads(ln) for ln in (lab.root / "DRIVE_LOG.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture()
def fresh_lab(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "governance" / "event_bridge.json"))
    monkeypatch.setattr(lab_mod, "ORPHAN_GRACE_S", 0.0)
    lab = Lab(tmp_path / "lab")
    lab.root.mkdir()
    return lab


def test_drive_seeds_runs_steps_until_terminal_and_writes_log_and_reports(fresh_lab, capsys):
    lab, seen = fresh_lab, []
    claude = FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX))
    codex = FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE"))

    code = lab_mod._drive(lab, 20, None, 5.0, run_step=in_process_steps(lab, claude, codex, seen), preflight_fn=_ok_preflight)

    assert [e["action"] for e in drive_log(lab)] == ["DELIVERED", "CHANGES_REQUESTED", "CORRECTION_DISPATCHED", "DELIVERED",
                                                     "APPROVED", "TERMINAL"]
    assert seen[0][-4:] == ["--lab", str(lab.root), "--runner", "auto"] and "step" in seen[0]
    rep = json.loads((lab.root / "REPORT.json").read_text(encoding="utf-8"))
    assert rep["criteria"]["workflow_completed"] is True and (lab.root / "REPORT.md").exists()
    assert code == 1                                   # nenhum CLI foi morto com o coordenador: o relatorio M1 nao passa
    assert capsys.readouterr().out.isascii()


def test_drive_does_not_die_on_a_reason_outside_the_console_code_page(fresh_lab, capsys):
    lab, seen = fresh_lab, []
    reason = "Not logged in " + chr(0xB7) + " Please run /login " + chr(0xFFFD)        # o caso real de 2026-11-10
    failed = (0, json.dumps({"action": "FAILED", "reason": reason}), "")

    lab_mod._drive(lab, 5, None, 5.0, run_step=scripted_steps(seen, failed, PAUSED), preflight_fn=_ok_preflight)

    out = capsys.readouterr().out
    assert out.isascii() and len(seen) == 2
    assert drive_log(lab)[0]["reason"] == reason


def test_drive_checks_the_tree_after_a_crash_and_spends_each_chaos_switch_once(fresh_lab, monkeypatch):
    lab, seen = fresh_lab, []
    monkeypatch.setattr(lab_mod.ps, "tree_pids", lambda pid, since=None: [], raising=False)
    monkeypatch.setattr(lab_mod.ex, "pid_alive", lambda pid: False)

    def cli_in_the_air():                              # o step morreu com um CLI registrado e sem termino
        EventStore(lab.db).run_started(1, "claude", ["C:/bin/claude.exe"], lab.repo, 4321, lab.logs / "o", lab.logs / "e")
        return lab_mod.CRASH_EXIT, "", ""

    lab_mod._drive(lab, 4, "REVIEW_REQUESTED", 5.0, kill_during="claude", preflight_fn=_ok_preflight,
                   run_step=scripted_steps(seen, cli_in_the_air, (lab_mod.CRASH_EXIT, "", ""), PAUSED))

    assert "--kill-during" in seen[0] and "--crash-on" in seen[0]
    assert "--kill-during" not in seen[1] and "--crash-on" in seen[1]       # 1o crash deixou run sem termino: era o kill
    assert "--kill-during" not in seen[2] and "--crash-on" not in seen[2]   # 2o crash sem run novo: era o crash-on
    log = drive_log(lab)
    assert log[0]["action"] == "CRASHED"
    assert log[0]["orphans"] == [{"run": 1, "agent": "claude", "pid": 4321, "grace_s": 0.0, "alive": []}]
    assert log[1]["orphans"] == []


def test_drive_stops_after_idling_longer_than_the_limit(fresh_lab):
    lab, seen = fresh_lab, []
    clock = [0.0]                                      # relogio falso: so o `sleep` do driver o avanca (2 s por passo ocioso)
    lab_mod._drive(lab, 50, None, 3.0, run_step=scripted_steps(seen, IDLE), preflight_fn=_ok_preflight,
                   sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds), monotonic=lambda: clock[0])
    assert len(seen) == 3 and clock[0] == 4.0


def test_drive_restarts_the_idle_budget_after_a_step_that_did_work(fresh_lab):
    lab, seen = fresh_lab, []
    clock = [0.0]
    worked = (0, json.dumps({"action": "DELIVERED"}), "")
    lab_mod._drive(lab, 50, None, 3.0, preflight_fn=_ok_preflight, monotonic=lambda: clock[0],
                   sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
                   run_step=scripted_steps(seen, IDLE, IDLE, worked, IDLE))
    assert [e["action"] for e in drive_log(lab)] == ["IDLE", "IDLE", "DELIVERED", "IDLE", "IDLE", "IDLE"]


def test_drive_stops_at_a_step_that_neither_crashed_nor_answered(fresh_lab):
    lab, seen = fresh_lab, []
    lab_mod._drive(lab, 50, None, 5.0, run_step=scripted_steps(seen, (1, "Traceback ...", "boom")), preflight_fn=_ok_preflight)
    log = drive_log(lab)
    assert len(seen) == 1 and log[0]["action"] == "STEP_ERROR" and log[0]["stderr"] == "boom"


def test_drive_is_blocked_and_seeds_nothing_when_a_cli_is_missing(fresh_lab, capsys):
    lab, seen = fresh_lab, []
    code = lab_mod._drive(lab, 5, None, 5.0, run_step=scripted_steps(seen, PAUSED),
                          preflight_fn=lambda: {"ok": False, "codex": {"version": "INDISPONIVEL"}})
    assert code == 2 and not seen and not lab.repo.exists()
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["action"] == "BLOCKED"


def test_drive_resumes_a_seeded_lab_without_seeding_again(env):
    lab, store = env
    seen = []
    lab_mod._drive(lab, 5, None, 5.0, run_step=scripted_steps(seen, PAUSED), preflight_fn=_ok_preflight)
    assert len(store.events(lab_mod.JOB_ID)) == 1 and commits(lab) == 1 and len(seen) == 1


def test_check_orphans_records_each_unfinished_run_once(env, monkeypatch):
    lab, store = env
    monkeypatch.setattr(lab_mod.ps, "tree_pids", lambda pid, since=None: [pid, pid + 1], raising=False)
    monkeypatch.setattr(lab_mod.ex, "pid_alive", lambda pid: True)
    run_id = store.run_started(1, "codex", ["C:/bin/codex.exe"], lab.repo, 700, lab.logs / "o", lab.logs / "e")

    first = lab_mod.check_orphans(lab, store, grace_s=0.0)
    second = lab_mod.check_orphans(lab, store, grace_s=0.0)

    assert [(c["run"], c["agent"], c["pid"]) for c in first] == [(run_id, "codex", 700)] and 700 in first[0]["alive"]
    assert second == [] and len(lab_mod.orphan_checks(lab)) == 1


def test_check_orphans_ignores_runs_that_finished(env):
    lab, store = env
    run_id = store.run_started(1, "codex", ["C:/bin/codex.exe"], lab.repo, 700, lab.logs / "o", lab.logs / "e")
    store.run_finished(run_id, 0, False, "exit 0; containment=job_object")
    assert lab_mod.check_orphans(lab, store, grace_s=0.0) == [] and lab_mod.orphan_checks(lab) == []


def _last_json(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_cli_seed_report_and_paused_step_speak_json(fresh_lab, capsys):
    lab = fresh_lab
    assert lab_mod.main(["seed", "--lab", str(lab.root)]) == 0
    assert _last_json(capsys)["action"] == "SEEDED"
    assert lab_mod.main(["report", "--lab", str(lab.root)]) == 0
    assert _last_json(capsys)["verdict"] == "FAIL"
    lab.pause_flag.write_text("pausado", encoding="utf-8")
    assert lab_mod.main(["step", "--lab", str(lab.root)]) == 0
    assert _last_json(capsys) == {"action": "PAUSED"}


def test_cli_drive_forwards_every_switch_to_the_driver(fresh_lab, monkeypatch):
    got = {}
    monkeypatch.setattr(lab_mod, "_drive", lambda *a, **k: got.update(args=a, kwargs=k) or 7)

    code = lab_mod.main(["drive", "--lab", str(fresh_lab.root), "--crash-on", "REVIEW_REQUESTED", "--kill-during", "codex",
                         "--runner", "observed", "--max-steps", "9", "--idle-limit", "3", "--fault", "codex-auth"])

    assert code == 7
    assert got["args"] == (Lab(fresh_lab.root.resolve()), 9, "REVIEW_REQUESTED", 3.0, "codex-auth", "codex", "observed")


def test_cli_refuses_a_lab_inside_a_git_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "governance" / "event_bridge.json"))
    (tmp_path / ".git").mkdir()
    with pytest.raises(LabError, match="repositorio git"):
        lab_mod.main(["seed", "--lab", str(tmp_path / "lab")])


def test_observed_runner_feeds_stdin_reports_the_pid_and_declares_no_containment(tmp_path):
    pids = []
    res = lab_mod.run_observed([sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"], tmp_path,
                               dict(os.environ), "abc", 60, pids.append)
    assert (res.exit_code, res.stdout, res.timed_out, res.containment) == (0, "ABC", False, "none")
    assert pids == [res.pid] and res.pid > 0


def test_observed_runner_kills_and_flags_a_cli_that_exceeds_the_timeout(tmp_path):
    res = lab_mod.run_observed([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, dict(os.environ), "", 1,
                               lambda pid: None)
    assert res.timed_out is True and res.exit_code == -1
