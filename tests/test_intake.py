"""FP-060 MT-11 (#637), estagio 1: Issue pronta e AUTORIZADA vira `IMPLEMENT_REQUESTED`. Nada aqui executa um agente: o evento so e gravado."""
from __future__ import annotations

import json

import pytest

from tools.orchestration import intake
from tools.orchestration.event_store import EventStore
from tools.validation import execution_state as es

CRIT = "## Critérios de aceite\n- [ ] algo\n"


def issue(n, labels=("intake", "fp060"), deps=(), state="OPEN", title="t", body_extra=""):
    names = {"intake": intake.AUTH_LABEL, "fp060": "spec:FP-060", "geo": "spec:FP-043"}
    d = ("**Dependências:** " + ", ".join("#%d" % x for x in deps) + "\n\n") if deps else ""
    return {"number": n, "title": title, "state": state, "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "labels": [{"name": names.get(x, x)} for x in labels], "body": d + body_extra + CRIT}


def plan(issues, prs=(), statuses=None, readiness=None, state=None):
    return intake.plan(list(issues), list(prs), state or es.default_state(), statuses, readiness)


# ------------------------------------------------------------------------------------------------------------ barreira
def test_an_authorized_orchestration_issue_is_the_candidate():
    res = plan([issue(1)])
    assert res.candidate.node.number == 1 and res.skipped == []


def test_ready_alone_is_not_enough_the_human_label_is_required():
    res = plan([issue(1, labels=("fp060",))])
    assert res.candidate is None and "executor-intake" in res.skipped[0] and res.skipped[0].startswith("#1:")


def test_a_geometry_or_furniture_spec_never_enters_even_with_the_label():
    res = plan([issue(1, labels=("intake", "geo"))])
    assert res.candidate is None and "fora de" in res.skipped[0]


def test_an_issue_without_any_spec_never_enters():
    res = plan([issue(1, labels=("intake",))])
    assert res.candidate is None and "None" in res.skipped[0]


def test_the_readiness_audit_saying_it_needs_sketchup_refuses_even_an_authorized_issue():
    ready = {1: {"state": "READY", "next_step": "x", "offline": False, "needs_sketchup": True}}
    res = plan([issue(1)], readiness=ready)
    assert res.candidate is None and "SketchUp" in res.skipped[0]


def test_no_readiness_registry_entry_is_required_for_an_authorized_issue():
    assert plan([issue(1)], readiness={}).candidate.node.number == 1


@pytest.mark.parametrize("status,ok", [("Ready", True), ("In Progress", False), ("GPT Review", False), ("Backlog", False), ("Blocked", False)])
def test_when_the_project_is_known_only_ready_cards_enter(status, ok):
    res = plan([issue(1)], statuses={1: status})
    assert (res.candidate is not None) is ok


def test_the_first_authorized_issue_wins_over_an_unauthorized_one_that_ranks_before_it():
    res = plan([issue(1, labels=("fp060",)), issue(2)])
    assert res.candidate.node.number == 2 and any(s.startswith("#1:") for s in res.skipped)


# ------------------------------------------------------------- o que o agendador ja recusa nunca chega a ser candidato
@pytest.mark.parametrize("case", ["closed", "open_dep", "blocked", "human_decision", "active_pr", "claimed_by_other"])
def test_ineligible_issues_by_the_scheduler_are_never_candidates(case):
    issues, prs, state = [issue(1)], [], es.default_state()
    if case == "closed":
        issues = [issue(1, state="CLOSED")]
    elif case == "open_dep":
        issues = [issue(2), issue(1, deps=(2,), labels=("intake", "fp060"))]
        issues[0]["labels"] = [{"name": "spec:FP-060"}]                                       # a dependencia nao e autorizada
    elif case == "blocked":
        issues = [issue(1, labels=("intake", "fp060", "blocked", "bloqueio:dependency"))]
    elif case == "human_decision":
        issues = [issue(1, labels=("intake", "fp060", "aprovação-humana-pendente"))]
    elif case == "active_pr":
        prs = [{"number": 9, "body": "Refs #1", "headRefName": "feat/x"}]
    elif case == "claimed_by_other":
        es.claim(state, 1, "outro-agente", "feat/y", "abc", ["FP-060|P3"])
    assert plan(issues, prs, state=state).candidate is None


# ------------------------------------------------------------------------------------------------------------ o evento
def test_the_request_key_is_stable_for_the_same_spec_and_changes_when_the_issue_is_edited():
    a, b = issue(1, body_extra="v1\n"), issue(1, body_extra="v2\n")
    ka = intake.publish_args(plan([a]).candidate, [a])["idempotency_key"]
    ka2 = intake.publish_args(plan([a]).candidate, [a])["idempotency_key"]
    kb = intake.publish_args(plan([b]).candidate, [b])["idempotency_key"]
    assert ka == ka2 and ka != kb and ka.startswith("implement:issue:1:")


def test_publishing_twice_creates_one_event_and_the_payload_carries_only_references(tmp_path):
    store = EventStore(tmp_path / "s.db")
    issues = [issue(1, title="Titulo da tarefa")]
    cand = plan(issues).candidate

    first = intake.publish(store, cand, issues)
    second = intake.publish(store, cand, issues)

    assert first[1] is True and second == (first[0], False)
    ev = store.events()[0]
    assert ev["event_type"] == "IMPLEMENT_REQUESTED" and ev["job_id"] == "issue:1" and ev["aggregate_type"] == "issue" and ev["status"] == "PENDING"
    assert set(json.loads(ev["payload"])) == {"issue", "title", "spec_hash", "spec", "fase"}      # nunca o corpo da Issue


def test_the_executor_correction_claim_never_picks_up_an_implement_request(tmp_path):
    store = EventStore(tmp_path / "s.db")
    issues = [issue(1)]
    intake.publish(store, plan(issues).candidate, issues)
    assert store.claim(("CORRECTION_REQUESTED",), "executor", 60) is None                          # hoje ninguem consome o pedido


# ------------------------------------------------------------------------------------------------------------------- CLI
@pytest.fixture()
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setenv("EVENT_STORE_DB_PATH", str(tmp_path / "store.db"))
    from tools.orchestration import store_factory
    from tools.validation import backlog_discovery as bd
    store_factory.reset_store()
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([issue(1)], None, []))
    monkeypatch.setattr(bd, "load_readiness", lambda: {})
    yield tmp_path / "store.db"
    store_factory.reset_store()


def test_publish_without_apply_plans_and_writes_nothing(cli, capsys):
    assert intake.main(["publish"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidate"]["issue"] == 1 and out["published"] is None and "sem --apply" in out["note"]
    assert not cli.exists() or EventStore(cli).events() == []


def test_publish_with_apply_records_the_event_once(cli, capsys):
    assert intake.main(["publish", "--apply"]) == 0
    assert intake.main(["publish", "--apply"]) == 0
    first, second = (json.loads(x) for x in capsys.readouterr().out.replace("}\n{", "}\n@@{").split("\n@@"))
    assert first["published"]["created"] is True and second["published"]["created"] is False
    assert len(EventStore(cli).events()) == 1


def test_plan_exits_1_when_there_is_no_candidate(cli, monkeypatch, capsys):
    from tools.validation import backlog_discovery as bd
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([issue(1, labels=("fp060",))], None, []))
    assert intake.main(["plan"]) == 1
    assert json.loads(capsys.readouterr().out)["candidate"] is None
