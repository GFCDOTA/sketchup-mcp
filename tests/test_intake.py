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


# -- 5a revisao do Codex (#641): entrada de prontidao BLOCKED ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("state", ["BLOCKED", "blocked", "Blocked"])
def test_an_audited_blocked_readiness_entry_refuses_the_issue(state):
    res = plan([issue(1)], readiness={1: {"state": state}})
    assert res.candidate is None and "BLOCKED" in res.skipped[0]


def test_an_issue_with_no_readiness_entry_is_still_accepted():
    assert plan([issue(1)], readiness={}).candidate.node.number == 1
    assert plan([issue(1)], readiness=None).candidate.node.number == 1


@pytest.mark.parametrize("entry", [{"state": "READY", "needs_sketchup": False}, {"state": "READY"}, {}])
def test_a_non_blocked_readiness_entry_does_not_refuse(entry):
    assert plan([issue(1)], readiness={1: entry}).candidate.node.number == 1


def test_a_blocked_entry_for_another_issue_does_not_affect_this_one():
    res = plan([issue(1), issue(2)], readiness={2: {"state": "BLOCKED"}})
    assert res.candidate.node.number == 1 and any(s.startswith("#2:") and "BLOCKED" in s for s in res.skipped)


# -- 6a revisao do Codex (#641): Project consultado, dependencia ausente, lista truncada --------------------------------------------------------------
def test_with_the_project_consulted_an_issue_missing_from_it_or_without_status_is_not_ready():
    assert plan([issue(1)], statuses={}).candidate is None and "nao tem status" in plan([issue(1)], statuses={}).skipped[0]
    assert plan([issue(1)], statuses={2: "Ready"}).candidate is None
    assert plan([issue(1)], statuses={1: None}).candidate is None
    assert plan([issue(1)], statuses={1: "Ready"}).candidate.node.number == 1
    assert plan([issue(1)], statuses=None).candidate.node.number == 1                  # Project nao consultado: vale o comportamento anterior


def test_a_dependency_that_is_not_among_the_loaded_issues_refuses_the_candidate():
    res = plan([issue(1, deps=(9,))])
    assert res.candidate is None and "#9" in res.skipped[0] and "nao carregada" in res.skipped[0]
    assert plan([issue(1, deps=(2,)), issue(2, state="CLOSED")]).candidate.node.number == 1               # dependencia carregada e concluida: segue


def test_a_possibly_truncated_issue_or_pr_list_publishes_nothing(cli, monkeypatch, capsys):
    from tools.validation import backlog_discovery as bd
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([issue(1)], None, [{"number": n, "body": "", "headRefName": "x"} for n in range(bd.LOAD_LIMIT)]))
    assert intake.main(["publish", "--apply"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["candidate"] is None and "truncada" in out["error"] and (not cli.exists() or EventStore(cli).events() == [])


# -- 7a revisao do Codex (#641): dependencia reflexiva; trava do estado ate a publicacao ----------------------------------------------------------------
def test_a_self_dependency_refuses_the_candidate_and_publishes_nothing(cli, monkeypatch, capsys):
    from tools.validation import backlog_discovery as bd
    res = plan([issue(1, deps=(1,))])
    assert res.candidate is None and "depende dela mesma" in res.skipped[0]
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([issue(1, deps=(1,))], None, []))
    assert intake.main(["publish", "--apply"]) == 1
    assert json.loads(capsys.readouterr().out)["candidate"] is None and (not cli.exists() or EventStore(cli).events() == [])


def test_the_execution_state_lock_is_held_from_reading_the_claims_until_the_request_is_written(cli, monkeypatch):
    held = []
    real_publish = intake.publish

    def publish_while_checking_the_lock(store, verdict, issues):
        try:
            with es.locked(es.state_path(), wait_s=0.2):                                 # outro processo tentando reivindicar nesta janela
                held.append(False)
        except TimeoutError:
            held.append(True)
        return real_publish(store, verdict, issues)
    monkeypatch.setattr(intake, "publish", publish_while_checking_the_lock)
    assert intake.main(["publish", "--apply"]) == 0
    assert held == [True]


# -- 8a revisao do Codex (#641): todo claim ativo e externo ao intake, inclusive o de `claude` -------------------------------------------------------
@pytest.mark.parametrize("holder", ["claude", "codex", "intake", "outro-agente"])
def test_an_issue_with_an_active_claim_is_never_a_candidate_whoever_holds_it(holder):
    state = es.default_state()
    es.claim(state, 1, holder, "feat/x", "a" * 40, ["comp-a"])
    res = plan([issue(1)], state=state)
    assert res.candidate is None


@pytest.mark.parametrize("holder", ["claude", "codex"])
def test_an_active_claim_on_another_issue_does_not_block_an_unrelated_candidate(holder):
    state = es.default_state()
    es.claim(state, 2, holder, "feat/x", "a" * 40, ["comp-a"])
    res = plan([issue(1), issue(2)], state=state)
    assert res.candidate is not None and res.candidate.node.number == 1


def test_the_intake_agent_is_no_name_at_all_so_no_claim_is_ever_its_own():
    assert intake.INTAKE_AGENT is None


@pytest.mark.parametrize("holder", ["intake", "claude", "None", ""])
def test_an_active_claim_on_another_issue_of_the_same_component_blocks_the_candidate_whatever_the_agent_name(holder):
    state = es.default_state()
    es.claim(state, 9, holder, "feat/x", "a" * 40, ["FP-060|-"])                                      # outra Issue, MESMO componente que a candidata
    assert plan([issue(1)], state=state).candidate is None
    other = es.default_state()
    es.claim(other, 9, holder, "feat/x", "a" * 40, ["FP-043|P1"])                                     # componente diferente: nao bloqueia
    assert plan([issue(1)], state=other).candidate.node.number == 1


# -- 9a revisao do Codex (#641): o status do Project vale para a identidade COMPLETA do item ------------------------------------------------------------
REPO_NAME = "GFCDOTA/sketchup-mcp"


def prow(number, status, type_="Issue", repo=REPO_NAME):
    return {"status": status, "content": {"number": number, "type": type_, "repository": repo}}


def test_only_issues_of_this_repository_count_for_the_project_status():
    from tools.validation import backlog_discovery as bd
    rows = [prow(1, "Ready", repo="outro/repo"), prow(1, "Ready", type_="PullRequest"), prow(2, "Ready"), prow(3, "In progress", repo="https://github.com/GFCDOTA/sketchup-mcp")]
    assert bd.project_statuses(rows, REPO_NAME) == {2: "Ready", 3: "In progress"}


def test_two_items_with_the_same_number_are_an_ambiguous_identity_never_ready():
    from tools.validation import backlog_discovery as bd
    out = bd.project_statuses([prow(5, "Ready"), prow(5, "Ready")], REPO_NAME)
    assert out == {5: bd.AMBIGUOUS_STATUS}
    assert plan([issue(5)], statuses=out).candidate is None


def test_a_ready_item_of_another_repository_with_the_same_number_does_not_authorize_this_issue(cli, monkeypatch, capsys):
    from tools.validation import backlog_discovery as bd
    mapped = bd.project_statuses([prow(1, "Ready", repo="outro/repo")], REPO_NAME)                  # a Issue #1 DESTE repo nao esta no Project
    assert mapped == {}
    monkeypatch.setattr(bd, "load", lambda statuses=False: ([issue(1)], mapped, []))
    assert intake.main(["publish", "--apply", "--project"]) == 1
    assert json.loads(capsys.readouterr().out)["candidate"] is None and (not cli.exists() or EventStore(cli).events() == [])



# -- 8a revisao do Codex (#641): vinculos de fechamento do GitHub; revalidacao sob a trava -------------------------------------------------------------
@pytest.mark.parametrize("body", ["Closes #1", "fixes #1", "Resolves: #1", "Refs #1", "Relates to #1", "Fixed #3, #1", "closes #1 and #2"])
def test_an_open_pr_linked_by_any_github_keyword_blocks_a_new_request(body):
    res = plan([issue(1)], prs=[{"number": 50, "body": body, "headRefName": "x"}])
    assert res.candidate is None and all("PR #50" in x for x in res.skipped)                          # `Refs`/`Relates to` o agendador ja descarta antes


def test_a_pr_that_only_mentions_the_number_without_a_link_keyword_does_not_block():
    assert plan([issue(1)], prs=[{"number": 50, "body": "ver tambem #1 na discussao", "headRefName": "x"}]).candidate.node.number == 1


def test_a_pr_opened_between_the_first_read_and_the_lock_is_seen_by_the_revalidation_and_nothing_is_published(cli, monkeypatch, capsys):
    from tools.validation import backlog_discovery as bd
    reads = iter([([issue(1)], None, []), ([issue(1)], None, [{"number": 77, "body": "Closes #1", "headRefName": "feat/x"}])])
    monkeypatch.setattr(bd, "load", lambda statuses=False: next(reads))
    assert intake.main(["publish", "--apply"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["published"] is None and "revalidacao" in out["note"] and any("PR #77" in s for s in out["revalidated_skipped"])
    assert not cli.exists() or EventStore(cli).events() == []
