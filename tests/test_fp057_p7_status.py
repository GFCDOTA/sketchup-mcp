"""FP-057 P7: o relatorio de status vem de fatos e declara os limites da automacao."""
from __future__ import annotations

from tools.validation import autonomous_status as au
from tools.validation import execution_state as es

ACC = "## Critérios de aceite\n- [ ] x\n"


def iss(n, labels=(), body=ACC):
    return {"number": n, "title": f"t{n}", "state": "OPEN", "stateReason": "COMPLETED", "body": body,
            "labels": [{"name": x} for x in ("tipo:task", "prio:P2", *labels)]}


def text(policy=None, runner=False, token=False):
    issues = [iss(1), iss(2, ["blocked", "bloqueio:external"]), iss(3, ["gpt-review-required"])]
    return au.render(issues, [{"number": 9, "body": "Refs #1"}], {3: "GPT Review"}, es.default_state(), policy or {}, runner, token, "2026-10-24")


def test_report_counts_blockers_reviews_and_open_prs_from_facts():
    t = text()
    assert "AUTONOMOUS ENGINEERING STATUS — 2026-10-24" in t
    assert "BLOCKED: 1" in t and "IN_PROGRESS: 1" in t and "external=1" in t
    assert "GPT Review): #3" in t and "PRs abertos: #9" in t


def test_report_never_claims_a_runner_a_token_or_a_reviewer_that_does_not_exist():
    t = text()
    assert "NÃO configurado" in t and "AUSENTE" in t and "NENHUM configurado" in t and "PENDING_HUMAN" in t
    ok = text({"reviewers": ["revisor"]}, runner=True, token=True)
    assert "revisor" in ok and "configurado — a execução" not in ok and "presente" in ok
