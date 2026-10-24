"""FP-057 P4: revisao independente nao falsificavel, caminhos criticos exigem revisao, protecao verificada, falha de coleta nao libera."""
from __future__ import annotations

import datetime as dt

import pytest

from tools.validation import backlog_gate as bg
from tools.validation import pr_policy_gate as pg
from tools.validation import protection_check as pc
from tools.validation import review_verification as rv

NOW = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
HEAD = "b" * 40
POLICY = {"reviewers": ["revisor-gpt"], "executor_logins": ["fmodesto30"]}


def facts(head=HEAD, refs=(7,), date="2026-10-26", exists=True):
    return lambda n: {"exists": exists, "headRefOid": head, "headDate": date, "refs": list(refs)} if n == 5 else None


def comment(login="revisor-gpt", verdict="APPROVED", pr="#5", sha=HEAD[:10], reviewer=None, date="2026-10-27",
            evidence="li o diff e rodei os testes", created="2026-10-27T10:00:00Z"):
    lines = [f"GPT-REVIEW: {verdict}", f"PR: {pr}", f"SHA: {sha}", f"Reviewer: {reviewer or login}", f"Date: {date}"]
    if evidence:
        lines.append(f"Evidence: {evidence}")
    return {"body": "\n".join(lines), "author": {"login": login}, "createdAt": created}


def verify(c, policy=POLICY, pr_facts=None):
    return rv.verify(c, 7, policy, pr_facts or facts(), NOW)


def test_a_complete_review_by_an_authorized_distinct_reviewer_on_the_head_sha_is_approved():
    r = verify(comment())
    assert r.status == "APPROVED" and r.pr == 5 and r.reasons == []


def test_a_bare_marker_or_a_comment_without_the_marker_is_not_a_review_nor_an_approval():
    assert rv.verify({"body": "ok, parece bom", "author": {"login": "revisor-gpt"}}, 7, POLICY, facts(), NOW) is None
    bare = {"body": "GPT-REVIEW: APPROVED", "author": {"login": "fmodesto30"}, "createdAt": "2026-10-27T10:00:00Z"}
    r = rv.verify(bare, 7, POLICY, facts(), NOW)
    assert r.status == "INVALID" and any("executor" in x for x in r.reasons) and any("sem PR" in x for x in r.reasons)


def test_the_executor_cannot_approve_its_own_work_even_with_a_perfect_block():
    r = verify(comment(login="fmodesto30"))
    assert r.status == "INVALID" and any("executor" in x for x in r.reasons) and any("nao e revisor autorizado" in x for x in r.reasons)


def test_without_any_authorized_reviewer_configured_nothing_can_be_approved_fail_closed():
    r = verify(comment(), policy={"reviewers": [], "executor_logins": ["fmodesto30"]})
    assert r.status == "INVALID" and any("nenhum revisor autorizado" in x for x in r.reasons)


def test_reviewer_field_must_match_the_comment_author():
    assert any("Reviewer nao bate" in x for x in verify(comment(reviewer="outra-pessoa")).reasons)


def test_a_new_commit_after_the_review_invalidates_the_approval_as_stale():
    r = verify(comment(sha="c" * 10))
    assert r.status == "STALE" and "HEAD atual" in r.reasons[0]
    issue = {"number": 7, "comments": [comment(sha="c" * 10)]}
    ok, why = rv.has_valid_approval(issue, POLICY, facts(), NOW)
    assert not ok and "STALE" in why[0]


def test_pr_that_does_not_cite_the_issue_or_is_unverifiable_or_missing_evidence_or_with_bad_date_is_invalid():
    assert any("nao cita a Issue" in x for x in verify(comment(), pr_facts=facts(refs=(99,))).reasons)
    assert any("nao verificavel" in x for x in verify(comment(pr="#6")).reasons)
    assert any("inexistente" in x for x in verify(comment(), pr_facts=facts(exists=False)).reasons)
    assert any("sem Evidence" in x for x in verify(comment(evidence="")).reasons)
    assert any("fora de" in x for x in verify(comment(date="2026-10-20")).reasons)          # antes do commit revisado
    assert any("fora de" in x for x in verify(comment(date="2027-01-01")).reasons)          # no futuro
    assert any("Date ausente ou invalida" in x for x in verify(comment(date="ontem")).reasons)


def test_the_latest_review_prevails_changes_requested_cancels_an_earlier_approval_and_vice_versa():
    appr = comment(created="2026-10-27T10:00:00Z")
    chg = comment(verdict="CHANGES_REQUESTED", created="2026-10-28T10:00:00Z", date="2026-10-28")
    again = comment(created="2026-10-29T10:00:00Z", date="2026-10-29")
    assert rv.has_valid_approval({"number": 7, "comments": [appr]}, POLICY, facts(), NOW)[0]
    ok, why = rv.has_valid_approval({"number": 7, "comments": [appr, chg]}, POLICY, facts(), NOW)
    assert not ok and "CHANGES_REQUESTED" in why[0]
    assert rv.has_valid_approval({"number": 7, "comments": [appr, chg, again]}, POLICY, facts(), NOW)[0]
    assert rv.has_valid_approval({"number": 7, "comments": []}, POLICY, facts(), NOW) == (False, ["nenhuma revisao independente registrada"])


def test_backlog_gate_rejects_a_forged_marker_and_accepts_the_verified_review():
    pol = {**POLICY, "effective_from": "2026-10-25T00:00:00Z", "labels": ["gpt-review-required"]}
    base = {"state": "CLOSED", "stateReason": "COMPLETED", "closedAt": "2026-10-28T00:00:00Z",
            "labels": [{"name": "gpt-review-required"}, {"name": "prova:UNIT_PASS"}]}
    evid = {"body": "**Evidência** commit abcdef0; pytest passed", "author": {"login": "fmodesto30"}}
    item = {"status": "Done", "estado da prova": "UNIT_PASS", "aprovação humana pendente": "Não", "dependências": ""}
    forged = {1: {**base, "comments": [evid, {"body": "GPT-REVIEW: APPROVED", "author": {"login": "fmodesto30"}}]}}
    good = {1: {**base, "comments": [evid, comment()]}}
    codes = lambda iss: {f.code for f in bg.check(iss, {1: item}, None, pol, facts(refs=(1,)), NOW)}    # noqa: E731
    assert "DONE_WITHOUT_GPT_REVIEW" in codes(forged)
    assert "DONE_WITHOUT_GPT_REVIEW" not in codes(good)                    # PR #5 cita a Issue #1, SHA = HEAD, revisor autorizado


def test_missing_pr_facts_collected_from_github_never_release_a_review_gated_done():
    pol = {**POLICY, "effective_from": "2026-10-25T00:00:00Z", "labels": ["gpt-review-required"]}
    iss = {1: {"state": "CLOSED", "stateReason": "COMPLETED", "closedAt": "2026-10-28T00:00:00Z",
               "labels": [{"name": "gpt-review-required"}], "comments": [comment()]}}
    got = {f.code for f in bg.check(iss, None, None, pol, lambda n: None, NOW)}
    assert "DONE_WITHOUT_GPT_REVIEW" in got                                 # fato indisponivel => nao verificada


def test_a_failing_evidence_collection_stops_the_gate_instead_of_passing(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gh: rate limit / sem rede")
    monkeypatch.setattr(bg, "_gh", boom)
    with pytest.raises(RuntimeError, match="rate limit"):
        bg.main(["--no-project"])


# ------------------------------------------------------------------------------------------ politica de PR
CRIT = ["core/pipeline_contracts.py", "tools/rooms/shared/spatial_solver/", ".github/workflows/"]


def pr(files, labels=(), crit=CRIT):
    issues = {5: {"state": "OPEN", "labels": [{"name": x} for x in labels]}}
    return {f.code for f in pg.check("Refs #5\nSKP-proof: N/A\nTests: N/A — teste", files, issues, crit)}


def test_pr_touching_a_critical_path_needs_the_review_label_on_the_cited_issue():
    assert "PR_CRITICAL_WITHOUT_REVIEW_LABEL" in pr(["core/pipeline_contracts.py"])
    assert "PR_CRITICAL_WITHOUT_REVIEW_LABEL" in pr(["tools/rooms/shared/spatial_solver/engine.py"])
    assert "PR_CRITICAL_WITHOUT_REVIEW_LABEL" in pr([".github/workflows/ci.yml"])
    assert "PR_CRITICAL_WITHOUT_REVIEW_LABEL" not in pr(["core/pipeline_contracts.py"], ["gpt-review-required"])
    assert "PR_CRITICAL_WITHOUT_REVIEW_LABEL" not in pr(["docs/readme.md"])


def test_invalid_pr_is_blocked_and_a_valid_one_passes_the_objective_gates():
    bad = {f.code for f in pg.check("sem nada", ["tools/validation/x.py"], {})}
    assert {"PR_NO_ISSUE_LINK", "PR_NO_SKP_PROOF_DECLARATION", "PR_CODE_WITHOUT_TESTS"} <= bad
    good = pg.check("Refs #5\nSKP-proof: N/A\nReason: ci-only\nJustification: so governanca.", ["docs/x.md"],
                    {5: {"state": "OPEN", "labels": []}}, CRIT)
    assert good == []


# ------------------------------------------------------------------------------------- protecao de branch
FULL = {"required_status_checks": {"contexts": list(pc.REQUIRED_CONTEXTS)}, "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}


def test_protection_check_passes_only_with_every_context_admin_enforcement_and_no_force_push():
    assert pc.evaluate(FULL) == ("PASS", [])
    miss = {**FULL, "required_status_checks": {"contexts": list(pc.REQUIRED_CONTEXTS)[:-1]}}
    status, why = pc.evaluate(miss)
    assert status == "FAIL" and "qg: geometry, program and integration" in why[0]
    assert pc.evaluate({**FULL, "enforce_admins": {"enabled": False}})[0] == "FAIL"
    assert pc.evaluate({**FULL, "allow_force_pushes": {"enabled": True}})[0] == "FAIL"
    assert pc.evaluate({**FULL, "allow_deletions": {"enabled": True}})[0] == "FAIL"
    assert pc.evaluate(None)[0] == "NOT_VERIFIED"                          # sem dado: nunca PASS
