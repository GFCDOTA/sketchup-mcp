"""FP-060-A01 M1 (#606): laboratorio isolado do closed-loop minimo Claude <-> Codex sobre o EventStore de producao.

Suite deterministica (sem LLM): os CLIs sao substituidos por runners falsos; git, SQLite e o runner de testes sao reais.
A prova com os dois CLIs reais e operacional (`python -m tools.orchestration.closed_loop_lab drive`), nunca esta suite."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from tools.orchestration import closed_loop_lab as lab_mod
from tools.orchestration.closed_loop_lab import CliResult, Lab, LabError
from tools.orchestration.event_store import EventStore

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
    def __init__(self, *actions):
        self.actions, self.calls = list(actions), []

    def __call__(self, argv, cwd, env, stdin, timeout, on_start) -> CliResult:
        pid = 4000 + len(self.calls)
        self.calls.append({"cwd": Path(cwd), "prompt": stdin, "argv": argv})
        on_start(pid)
        return self.actions.pop(0)(Path(cwd), pid)


def verdict(kind: str, findings: list | None = None, excerpt: str | None = None, touch: str | None = None,
            tests: tuple = ("tests/test_lab_slug.py",)):
    def action(repo: Path, out: Path, pid: int) -> CliResult:
        data = (repo / lab_mod.ARTIFACT).read_bytes()
        line = excerpt or next(ln for ln in data.decode("utf-8").splitlines() if "re.sub" in ln or "return" in ln)
        _, sha = lab_mod.git(["rev-parse", "HEAD"], repo)
        out.write_text(json.dumps({
            "pr": lab_mod.LAB_PR, "head_sha": sha, "verdict": kind, "findings": findings or [], "tests_reviewed": list(tests),
            "confidence": "HIGH", "files_reviewed": [{"path": lab_mod.ARTIFACT, "sha256": hashlib.sha256(data).hexdigest(),
                                                      "code_excerpt": line}]}), encoding="utf-8")
        if touch:
            (repo / touch).write_text("alterado pelo revisor", encoding="utf-8")
        return CliResult(pid, 0, "", "", False)
    return action


def cli_failure(rc: int, stderr: str):
    def action(repo: Path, out: Path, pid: int) -> CliResult:
        return CliResult(pid, rc, "", stderr, False)
    return action


class FakeCodex:
    def __init__(self, *actions):
        self.actions, self.calls = list(actions), []

    def __call__(self, argv, cwd, env, stdin, timeout, on_start) -> CliResult:
        pid = 5000 + len(self.calls)
        self.calls.append({"prompt": stdin, "argv": argv})
        on_start(pid)
        repo, out = Path(argv[argv.index("-C") + 1]), Path(argv[argv.index("--output-last-message") + 1])
        return self.actions.pop(0)(repo, out, pid)


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


def test_report_passes_only_when_every_m1_criterion_is_derived_from_the_store(env):
    lab, store = env
    drive(lab, store, FakeClaude(writes(ASCII_FIX), writes(UNICODE_FIX)),
          FakeCodex(verdict("REQUEST_CHANGES", [FINDING]), verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["verdict"] == "PASS" and all(rep["criteria"].values())
    assert rep["final_head"] == rep["approved_head"]
    assert [r["pid"] for r in rep["runs"]] == [4000, 5000, 4001, 5001]


def test_report_fails_m1_when_the_correction_loop_was_not_exercised(env):
    lab, store = env
    drive(lab, store, FakeClaude(writes(UNICODE_FIX)), FakeCodex(verdict("APPROVE")))

    rep = lab_mod.report(lab, store)

    assert rep["criteria"]["workflow_completed"] is True
    assert rep["criteria"]["request_changes_then_correction"] is False
    assert rep["verdict"] == "FAIL"
