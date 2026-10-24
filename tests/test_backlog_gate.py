"""backlog_gate: o Project nao pode declarar conclusao ou prova sem evidencia rastreavel."""
from __future__ import annotations

from tools.validation.backlog_gate import check

EVID = {"body": "**Evidência** commit 4ad1f33; pytest 22 passed"}


def issue(state="OPEN", labels=(), comments=(), reason="COMPLETED"):
    return {"state": state, "stateReason": reason, "labels": [{"name": n} for n in labels], "comments": list(comments)}


def item(status="Backlog", prova="NOT_TESTED", human="Não", deps=""):
    return {"status": status, "estado da prova": prova, "aprovação humana pendente": human, "dependências": deps}


def codes(issues, items, exc=None):
    return {f.code for f in check(issues, items, exc)}


def test_done_by_inference_is_flagged_on_every_axis():
    got = codes({380: issue()}, {380: item("Done")})
    assert {"DONE_NOT_CLOSED", "DONE_WITHOUT_PROOF", "DONE_WITHOUT_EVIDENCE"} <= got


def test_closed_issue_with_evidence_and_proof_is_clean():
    i = issue("CLOSED", ["prova:UNIT_PASS"], [EVID])
    assert codes({1: i}, {1: item("Done", "UNIT_PASS")}) == set()


def test_commit_comment_without_evidence_marker_is_not_evidence():
    i = issue("CLOSED", ["prova:UNIT_PASS"], [{"body": "fixed in 4ad1f33"}])
    assert "DONE_WITHOUT_EVIDENCE" in codes({1: i}, {1: item("Done", "UNIT_PASS")})


def test_evidence_marker_without_commit_or_test_is_not_evidence():
    i = issue("CLOSED", ["prova:UNIT_PASS"], [{"body": "**Evidência** parece ok"}])
    assert "DONE_WITHOUT_EVIDENCE" in codes({1: i}, {1: item("Done", "UNIT_PASS")})


def test_closed_issue_not_in_done_is_flagged():
    i = issue("CLOSED", ["prova:UNIT_PASS"], [EVID])
    assert "CLOSED_NOT_DONE" in codes({1: i}, {1: item("Backlog", "UNIT_PASS")})


def test_closed_as_not_planned_does_not_need_done():
    i = issue("CLOSED", reason="NOT_PLANNED")
    assert codes({1: i}, {1: item("Backlog")}) == set()


def test_proof_state_above_not_tested_requires_evidence():
    got = codes({1: issue(labels=["prova:SKETCHUP_PASS"])}, {1: item("GPT Review", "SKETCHUP_PASS")})
    assert got == {"PROOF_WITHOUT_EVIDENCE"}


def test_label_and_field_must_agree_on_proof():
    got = codes({1: issue(labels=["prova:NOT_TESTED"])}, {1: item("Backlog", "UNIT_PASS")})
    assert "PROOF_LABEL_MISMATCH" in got


def test_blocked_status_and_label_must_agree():
    assert "BLOCKED_LABEL_MISMATCH" in codes({1: issue()}, {1: item("Blocked", "BLOCKED")})
    assert "BLOCKED_LABEL_MISMATCH" in codes({1: issue(labels=["blocked"])}, {1: item("Backlog")})
    assert not codes({1: issue(labels=["blocked", "prova:BLOCKED"])}, {1: item("Blocked", "BLOCKED")})


def test_done_with_open_dependency_or_pending_human_is_flagged():
    i = issue("CLOSED", ["prova:UNIT_PASS"], [EVID])
    got = codes({1: i, 2: issue()}, {1: item("Done", "UNIT_PASS", "Sim", "#2"), 2: item()})
    assert {"DEPENDENCY_OPEN", "DONE_HUMAN_PENDING"} <= got
    assert "DEPENDENCY_UNKNOWN" in codes({1: i}, {1: item("Done", "UNIT_PASS", deps="#999")})


def test_open_issue_outside_project_is_flagged():
    assert codes({1: issue()}, {}) == {"NOT_IN_PROJECT"}


def test_documented_exception_silences_only_that_code():
    got = codes({1: issue()}, {1: item("Blocked", "BLOCKED")}, {"1": {"BLOCKED_LABEL_MISMATCH": "motivo"}})
    assert got == set()
    got = codes({1: issue()}, {1: item("Done")}, {"1": {"DONE_NOT_CLOSED": "motivo"}})
    assert "DONE_WITHOUT_EVIDENCE" in got


def test_without_project_closed_issue_still_needs_evidence():
    assert "DONE_WITHOUT_EVIDENCE" in codes({1: issue("CLOSED")}, None)
    assert codes({1: issue("CLOSED", comments=[EVID])}, None) == set()


def test_open_parent_epic_does_not_block_a_done_child():
    i = issue("CLOSED", ["prova:UNIT_PASS"], [EVID])
    epic = issue(labels=["tipo:epic"])
    assert codes({1: i, 2: epic}, {1: item("Done", "UNIT_PASS", deps="#2"), 2: item()}) == set()


POLICY = {"effective_from": "2026-10-25T00:00:00Z", "labels": ["prio:P0", "gpt-review-required"],
          "reviewers": ["revisor-gpt"], "executor_logins": ["fmodesto30"]}
HEAD = "a" * 40


def lookup(n):
    return {"exists": True, "headRefOid": HEAD, "headDate": "2026-10-26", "refs": [1]} if n == 5 else None


def review_comment(author="revisor-gpt", sha=HEAD[:12], verdict="APPROVED"):
    body = "\n".join([f"GPT-REVIEW: {verdict}", "PR: #5", f"SHA: {sha}", f"Reviewer: {author}", "Date: 2026-10-27", "Evidence: li o diff e rodei os testes"])
    return {"body": body, "author": {"login": author}, "createdAt": "2026-10-27T10:00:00Z"}


def closed_issue(labels, closed_at, comments=()):
    i = issue("CLOSED", labels, [EVID, *comments])
    i["closedAt"] = closed_at
    return i


def gate(issues, items, policy=POLICY, pr_lookup=lookup):
    import datetime as dt

    from tools.validation.backlog_gate import check as chk
    return {f.code for f in chk(issues, items, None, policy, pr_lookup, dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc))}


def test_independent_review_is_required_for_p0_closed_after_the_policy_date_and_a_bare_marker_is_not_enough():
    late = {1: closed_issue(["prio:P0", "prova:UNIT_PASS"], "2026-10-26T10:00:00Z")}
    assert "DONE_WITHOUT_GPT_REVIEW" in gate(late, {1: item("Done", "UNIT_PASS")})
    forged = {1: closed_issue(["prio:P0", "prova:UNIT_PASS"], "2026-10-26T10:00:00Z",
                              [{"body": "GPT-REVIEW: APPROVED — sem ressalvas", "author": {"login": "fmodesto30"}}])}
    assert "DONE_WITHOUT_GPT_REVIEW" in gate(forged, {1: item("Done", "UNIT_PASS")})
    ok = {1: closed_issue(["prio:P0", "prova:UNIT_PASS"], "2026-10-26T10:00:00Z", [review_comment()])}
    assert "DONE_WITHOUT_GPT_REVIEW" not in gate(ok, {1: item("Done", "UNIT_PASS")})


def test_closures_before_the_policy_date_and_non_p0_are_exempt():
    early = {1: closed_issue(["prio:P0", "prova:UNIT_PASS"], "2026-10-24T10:00:00Z")}
    assert "DONE_WITHOUT_GPT_REVIEW" not in gate(early, {1: item("Done", "UNIT_PASS")})
    p1 = {1: closed_issue(["prio:P1", "prova:UNIT_PASS"], "2026-10-26T10:00:00Z")}
    assert "DONE_WITHOUT_GPT_REVIEW" not in gate(p1, {1: item("Done", "UNIT_PASS")})
    flagged = {1: closed_issue(["prio:P1", "gpt-review-required", "prova:UNIT_PASS"], "2026-10-26T10:00:00Z")}
    assert "DONE_WITHOUT_GPT_REVIEW" in gate(flagged, {1: item("Done", "UNIT_PASS")})
