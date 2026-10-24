"""FP-057 P5: reconciliacao Issues x PRs x Project — transicoes por fato, sem cartao duplicado, cota e token tratados."""
from __future__ import annotations

import datetime as dt

from tools.validation import backlog_reconcile as br

NOW = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
POLICY = {"effective_from": "2026-10-25T00:00:00Z", "labels": ["gpt-review-required"], "reviewers": [], "executor_logins": ["fmodesto30"]}
EVID = {"body": "**Evidência** commit abcdef0; pytest passed", "createdAt": "2026-10-26T10:00:00Z"}
ACCEPT = "## Critérios de aceite\n- [ ] faz a coisa\n"


def issue(n, labels=(), body=ACCEPT, state="OPEN", comments=(), reason="COMPLETED", deps=""):
    b = (f"**Dependências:** {deps}\n" if deps else "") + body
    return {"number": n, "title": f"t{n}", "state": state, "stateReason": reason, "body": b, "comments": list(comments),
            "labels": [{"name": x} for x in ("tipo:task", *labels)]}


def card(n, status):
    return {"number": n, "status": status}


def run(issues, cards, prs=(), claims=None, lookup=None):
    return br.plan(issues, cards, list(prs), POLICY, lookup or (lambda _n: None), claims, NOW)


def moves(res):
    return {m.issue: (m.frm, m.to) for m in res[0]}


def test_eligible_backlog_item_becomes_ready_and_one_with_open_dependency_does_not():
    res = run([issue(1), issue(2, deps="#1")], [card(1, "Backlog"), card(2, "Backlog")])
    assert moves(res) == {1: ("Backlog", "Ready")}


def test_dependency_closure_with_evidence_unlocks_the_dependent():
    res = run([issue(1, state="CLOSED", comments=[EVID]), issue(2, deps="#1")], [card(1, "In Progress"), card(2, "Backlog")])
    assert moves(res) == {1: ("In Progress", "Done"), 2: ("Backlog", "Ready")}


def test_open_pr_citing_the_issue_moves_it_to_in_progress():
    pr = {"number": 9, "body": "Refs #1", "isDraft": True, "checks": "pending"}
    assert moves(run([issue(1)], [card(1, "Ready")], [pr])) == {1: ("Ready", "In Progress")}


def test_green_ready_pr_goes_to_gpt_review_only_when_the_issue_requires_it():
    pr = {"number": 9, "body": "Refs #1", "isDraft": False, "checks": "pass"}
    assert moves(run([issue(1, ["gpt-review-required"])], [card(1, "In Progress")], [pr])) == {1: ("In Progress", "GPT Review")}
    assert moves(run([issue(1)], [card(1, "Ready")], [pr])) == {1: ("Ready", "In Progress")}


def test_proven_blocker_moves_to_blocked_and_a_stale_dependency_block_returns_to_ready():
    res = run([issue(1, ["blocked", "bloqueio:external"])], [card(1, "Ready")])
    assert moves(res) == {1: ("Ready", "Blocked")}
    stale = run([issue(2, ["blocked", "bloqueio:dependency"], deps="#1"), issue(1, state="CLOSED", comments=[EVID])],
                [card(2, "Blocked"), card(1, "Done")])
    assert moves(stale) == {2: ("Blocked", "Ready")}


def test_done_requires_closed_issue_with_evidence_never_by_inference():
    res = run([issue(1, state="CLOSED"), issue(2, state="CLOSED", comments=[EVID])], [card(1, "In Progress"), card(2, "In Progress")])
    assert moves(res) == {2: ("In Progress", "Done")}
    assert [a.code for a in res[1]] == ["CLOSED_WITHOUT_EVIDENCE"]


def test_done_card_on_open_issue_or_without_evidence_is_an_anomaly_and_open_one_is_pulled_back():
    res = run([issue(1), issue(2, state="CLOSED")], [card(1, "Done"), card(2, "Done")])
    codes = {a.code for a in res[1]}
    assert codes == {"DONE_NOT_CLOSED", "DONE_WITHOUT_EVIDENCE"}
    assert moves(res) == {1: ("Done", "In Progress")}


def test_closed_issue_that_requires_independent_review_stays_in_gpt_review_without_a_verified_approval():
    i = issue(1, ["gpt-review-required"], state="CLOSED", comments=[EVID])
    i["closedAt"] = "2026-10-26T10:00:00Z"
    assert moves(run([i], [card(1, "In Progress")])) == {1: ("In Progress", "GPT Review")}
    assert moves(run([i], [card(1, "GPT Review")])) == {}                       # ja esta no lugar certo; nunca vira Done


def test_closed_not_planned_and_epics_are_left_alone():
    ep = issue(3)
    ep["labels"] = [{"name": "tipo:epic"}]
    assert moves(run([issue(1, state="CLOSED", reason="NOT_PLANNED"), ep], [card(1, "Backlog"), card(3, "Backlog")])) == {}


def test_duplicate_cards_are_reported_and_the_first_status_is_used():
    res = run([issue(1)], [card(1, "Ready"), card(1, "Backlog")])
    assert [a.code for a in res[1]] == ["DUPLICATE_CARD"] and moves(res) == {}


def test_plan_is_idempotent_once_applied():
    cards = [card(1, "Backlog")]
    first = run([issue(1)], cards)
    assert moves(first) == {1: ("Backlog", "Ready")}
    assert run([issue(1)], [card(1, "Ready")])[0] == []


def test_apply_skips_a_card_changed_concurrently_and_applies_the_rest():
    ms = [br.Move(1, "Backlog", "Ready", "x"), br.Move(2, "Backlog", "Ready", "x")]
    done = []
    out = br.apply(ms, {1: "In Progress", 2: "Backlog"}, lambda n, s: done.append((n, s)), 5000, "2026-11-01T01:00:00Z")
    assert done == [(2, "Ready")] and out["skipped"] == [(1, "CONCURRENT_CHANGE")] and not out["deferred"]


def test_apply_defers_without_writing_when_the_graphql_budget_is_low_and_records_the_retry_time():
    called = []
    out = br.apply([br.Move(1, "Backlog", "Ready", "x")], {1: "Backlog"}, lambda n, s: called.append(n), 405, "2026-11-01T01:00:00Z")
    assert called == [] and out["deferred"] and out["retry_after"] == "2026-11-01T01:00:00Z" and out["applied"] == []


def test_automation_state_is_partial_without_token_and_deferred_on_low_quota():
    assert br.automation_state(False, 5000) == "PARTIAL"
    assert br.automation_state(True, 100) == "DEFERRED"
    assert br.automation_state(True, 5000) == "COMPLETE"
    assert br.automation_state(True, None) == "UNKNOWN"


def test_closure_before_the_policy_date_is_not_pulled_back_to_gpt_review():
    i = issue(1, ["gpt-review-required"], state="CLOSED", comments=[EVID])
    i["closedAt"] = "2026-10-20T10:00:00Z"
    assert moves(run([i], [card(1, "Done")])) == {}


def test_one_card_that_errors_is_recorded_and_does_not_abort_the_others():
    ms = [br.Move(1, "Backlog", "Ready", "x"), br.Move(2, "Backlog", "Ready", "x")]
    done = []

    def set_status(n, s):
        if n == 1:
            raise KeyError(1)
        done.append(n)
    out = br.apply(ms, {1: "Backlog", 2: "Backlog"}, set_status, 5000, "2026-11-01T01:00:00Z")
    assert done == [2] and out["skipped"][0][0] == 1 and out["skipped"][0][1].startswith("ERROR KeyError")
