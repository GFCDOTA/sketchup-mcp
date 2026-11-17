"""Leitura do backlog (`tools/validation/backlog_discovery.py`) usada pelo intake do FP-060: status do Project por identidade completa (Issue deste repositorio)
e `load` pelo `gh` com limites explicitos (o padrao de 30 do `gh` omitiria PRs/Issues em silencio)."""
from __future__ import annotations

import json

from tests.test_intake import REPO_NAME, issue, plan, prow


def test_only_issues_of_this_repository_count_for_the_project_status():
    from tools.validation import backlog_discovery as bd
    rows = [prow(1, "Ready", repo="outro/repo"), prow(1, "Ready", type_="PullRequest"), prow(2, "Ready"), prow(3, "In progress", repo="https://github.com/GFCDOTA/sketchup-mcp")]
    assert bd.project_statuses(rows, REPO_NAME) == {2: "Ready", 3: "In progress"}


def test_two_items_with_the_same_number_are_an_ambiguous_identity_never_ready():
    from tools.validation import backlog_discovery as bd
    out = bd.project_statuses([prow(5, "Ready"), prow(5, "Ready")], REPO_NAME)
    assert out == {5: bd.AMBIGUOUS_STATUS}
    assert plan([issue(5)], statuses=out).candidate is None


def test_backlog_load_reads_issues_prs_and_the_project_through_gh_with_explicit_limits(monkeypatch):
    from tools.validation import backlog_discovery as bd
    from tools.validation import backlog_gate as bg
    calls = []
    rows = {"items": [{"content": {"number": 1, "type": "Issue", "repository": "https://github.com/" + bg.REPO}, "status": "Ready"}]}

    def fake_gh(*argv):
        calls.append(argv)
        if argv[:2] == ("issue", "list"):
            return json.dumps([issue(1)])
        if argv[:2] == ("pr", "list"):
            return json.dumps([{"number": 9, "body": "Closes #1", "headRefName": "x"}])
        if argv[:2] == ("project", "item-list"):
            return json.dumps(rows)
        raise AssertionError(argv)
    monkeypatch.setattr(bg, "_gh", fake_gh)
    issues, statuses, prs = bd.load(statuses=True)
    assert [i["number"] for i in issues] == [1] and prs[0]["number"] == 9 and statuses == {1: "Ready"}
    assert all(str(bd.LOAD_LIMIT) in a for a in calls if a[:2] in (("issue", "list"), ("pr", "list")))      # nunca o limite padrao de 30 do gh
    assert "--state" in calls[1] and "open" in calls[1]
    _i, st, _p = bd.load(statuses=False)
    assert st is None and not any(a[:2] == ("project", "item-list") for a in calls[3:])                  # sem --project, o Project nao e consultado
