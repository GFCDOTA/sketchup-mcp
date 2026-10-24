"""FP-057 P1: descoberta de tarefas elegiveis e grafo de dependencias — sinteticos + casos A-E sobre um retrato REAL do backlog."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.validation import backlog_discovery as bd
from tools.validation import dependency_graph as dg

SNAP = Path(__file__).resolve().parent / "data/backlog/backlog_snapshot_2026-10-24.json"
CRIT = "## Critérios de aceite\n- [ ] algo\n"


def issue(n, *args, deps=(), state="OPEN", body_extra="", reason="COMPLETED", crit=CRIT):
    """`issue(7, "titulo", ["label", ...], deps=(1,))`: str = titulo, lista = labels (qualquer ordem)."""
    title = next((a for a in args if isinstance(a, str)), "t")
    labels = next((a for a in args if isinstance(a, (list, tuple))), ())
    d = ("**Dependências:** " + ", ".join("#%d" % x for x in deps) + "\n\n") if deps else ""
    return {"number": n, "title": title, "state": state, "stateReason": reason if state == "CLOSED" else None,
            "labels": [{"name": x} for x in labels], "body": d + crit + body_extra}


def graph(*issues, statuses=None):
    return dg.build(list(issues), statuses)


def codes(g):
    return {(f.code, f.issue) for f in dg.analyze(g)}


# ----------------------------------------------------------------------------------------------------------- grafo
def test_missing_self_and_resolved_dependencies_are_reported():
    g = graph(issue(1, deps=(1, 99, 3)), issue(3, state="CLOSED"))
    assert {("DEP_SELF", 1), ("DEP_MISSING", 1), ("DEP_RESOLVED", 1)} <= codes(g)


def test_cycle_between_tasks_is_detected_once_and_epic_in_the_middle_is_not_a_cycle():
    g = graph(issue(1, deps=(2,)), issue(2, deps=(3,)), issue(3, deps=(1,)))
    cyc = [f for f in dg.analyze(g) if f.code == "DEP_CYCLE"]
    assert len(cyc) == 1 and {"#1", "#2", "#3"} <= set(cyc[0].detail.replace(" -> ", " ").split())
    e = graph(issue(1, deps=(2,)), issue(2, ["tipo:epic"], deps=(1,)))
    assert not [f for f in dg.analyze(e) if f.code == "DEP_CYCLE"]


def test_an_open_parent_epic_does_not_block_its_children():
    g = graph(issue(1, ["tipo:epic"]), issue(2, deps=(1,)))
    assert g.open_hard_deps(2) == [] and bd.next_task(bd.evaluate(g)).node.number == 2


def test_blocked_by_dependency_that_only_points_to_an_epic_or_is_resolved_is_flagged():
    only_epic = graph(issue(1, ["tipo:epic"]), issue(2, ["blocked", "bloqueio:dependency"], deps=(1,)))
    assert ("DEP_EPIC_BLOCKER", 2) in codes(only_epic)
    stale = graph(issue(1, state="CLOSED"), issue(2, ["blocked", "bloqueio:dependency"], deps=(1,)))
    assert ("BLOCK_STALE", 2) in codes(stale)
    real = graph(issue(1), issue(2, ["blocked", "bloqueio:dependency"], deps=(1,)))
    assert not {c for c, n in codes(real) if c in ("BLOCK_STALE", "DEP_EPIC_BLOCKER")}


def test_misclassified_blocks_are_flagged():
    wrong = graph(issue(1, "DECISÃO X", ["blocked", "bloqueio:technical"]))
    assert ("BLOCK_MISCLASSIFIED", 1) in codes(wrong)
    human_with_tech_dep = graph(issue(1, "FP-056 P3 — algo", ["blocked", "bloqueio:human-decision", "aprovação-humana-pendente"], deps=(2,)), issue(2))
    assert ("BLOCK_MISCLASSIFIED", 1) in codes(human_with_tech_dep)


def test_parallel_groups_never_put_a_task_with_its_own_dependency_together():
    g = graph(issue(1), issue(2, deps=(1,)), issue(3), issue(4, deps=(2,)))
    groups = dg.parallel_groups(g, [1, 2, 3, 4])
    for grp in groups:
        assert not ({1, 2} <= set(grp) or {2, 4} <= set(grp) or {1, 4} <= set(grp))
    assert any({1, 3} <= set(grp) for grp in groups)


# ------------------------------------------------------------------------------------------------- elegibilidade
def reasons(verdicts, n):
    return next(v.reasons for v in verdicts if v.node.number == n)


def test_eligibility_reasons_are_recorded_for_every_rule():
    g = graph(issue(1), issue(2, crit="sem criterios"), issue(3, deps=(1,)), issue(4, ["blocked", "bloqueio:human-decision"]),
              issue(5, ["blocked", "bloqueio:external"]), issue(6, ["blocked", "bloqueio:environment"]),
              issue(7, ["blocked", "bloqueio:evidence"]), issue(8, ["tipo:epic"]), issue(9),
              statuses={9: "GPT Review"})
    v = bd.evaluate(g, prs=[{"number": 50, "body": "Refs #1"}], claims={})
    assert reasons(v, 1)[0].startswith("ACTIVE_PR: #50")
    assert "NO_ACCEPTANCE_CRITERIA" in reasons(v, 2)
    assert reasons(v, 3)[0].startswith("DEP_OPEN")
    for n, tag in ((4, "HUMAN_DECISION"), (5, "EXTERNAL"), (6, "ENVIRONMENT"), (7, "EVIDENCE"), (8, "EPIC"), (9, "PENDING_REVIEW")):
        assert any(r.startswith(tag) for r in reasons(v, n)), (n, reasons(v, n))


def test_claim_and_component_conflict_make_a_task_ineligible_without_hiding_the_reason():
    a = issue(1, ["spec:FP-056", "fase:P3"])
    b = issue(2, ["spec:FP-056", "fase:P3"])
    g = graph(a, b)
    v = bd.evaluate(g, claims={1: {"agent": "exec-A", "components": ["FP-056|P3"]}})
    assert reasons(v, 1)[0].startswith("CLAIMED: outra execucao ativa (exec-A)")
    assert reasons(v, 2)[0].startswith("COMPONENT_CONFLICT")


def test_stale_dependency_block_reopens_and_technical_block_resumes_but_human_does_not():
    g = graph(issue(1, state="CLOSED"), issue(2, ["blocked", "bloqueio:dependency"], deps=(1,)), issue(3, ["blocked", "bloqueio:technical"]))
    v = {x.node.number: x for x in bd.evaluate(g)}
    assert v[2].eligible and v[2].action == "unblock" and v[3].eligible and v[3].action == "resume"


def test_criterion_only_the_owner_can_close_makes_the_task_ineligible_but_a_mixed_one_is_not():
    owner = issue(1, crit="## Critérios de aceite\n- [x] L2 real\n- [ ] Veredito visual do Felipe\n")
    mixed = issue(2, crit="## Critérios de aceite\n- [ ] teste vermelho\n- [ ] Veredito visual do Felipe\n")
    v = bd.evaluate(graph(owner, mixed))
    assert reasons(v, 1)[0].startswith("HUMAN_VERDICT") and not reasons(v, 2)


def test_priority_follows_the_spec_order_then_critical_path_then_number():
    integ = issue(10, "Gravação em artifacts/ sem gate", ["prio:P0", "spec:FP-055", "tipo:bug"])
    falsepass = issue(11, "Gate dá PASS vazio sem portal", ["prio:P1", "tipo:bug"])
    blocker = issue(12, "algo que destrava", ["prio:P2", "tipo:task"])
    d1, d2 = issue(13, deps=(12,)), issue(14, deps=(12,))
    debt = issue(15, "limpeza", ["tipo:technical-debt"])
    order = [x.node.number for x in bd.evaluate(graph(debt, d1, d2, blocker, falsepass, integ)) if x.eligible]
    assert order[:3] == [10, 11, 12] and order.index(15) > order.index(12)


# ----------------------------------------------------------- casos A-E sobre o retrato real do backlog (2026-10-24)
@pytest.fixture(scope="module")
def real():
    data = json.loads(SNAP.read_text("utf-8"))
    g = dg.build(data["issues"])
    return g, bd.evaluate(g)


def test_real_graph_has_no_missing_reference_no_cycle_and_no_epic_used_as_a_block(real):
    g, _ = real
    bad = [f for f in dg.analyze(g) if f.code in ("DEP_MISSING", "DEP_CYCLE", "DEP_SELF", "DEP_EPIC_BLOCKER", "BLOCK_MISCLASSIFIED")]
    assert bad == [], [str(f) for f in bad]


def test_case_A_untraceable_strokes_decision_stays_blocked_and_independent_work_is_still_selected(real):
    g, v = real
    assert any(r.startswith("HUMAN_DECISION") for r in reasons(v, 484))
    nxt = bd.next_task(v)
    assert nxt is not None and nxt.node.number != 484


def test_case_B_bathroom_measurement_tasks_are_executable_but_their_decision_is_not(real):
    _, v = real
    el = {x.node.number for x in v if x.eligible}
    assert {501, 502} <= el                                       # medicoes ainda executaveis
    assert any(r.startswith("EVIDENCE") for r in reasons(v, 446)) and 446 not in el


def test_case_C_external_credential_is_detected_and_does_not_stop_the_rest(real):
    _, v = real
    assert any(r.startswith("EXTERNAL") for r in reasons(v, 508))
    assert len([x for x in v if x.eligible]) >= 10


def test_case_D_after_a_merge_the_dependents_are_reevaluated_and_another_issue_is_selected(real):
    data = json.loads(SNAP.read_text("utf-8"))
    for i in data["issues"]:
        if i["number"] == 501:                                    # simula: a verificacao do solver foi concluida e fechada
            i["state"], i["stateReason"] = "CLOSED", "COMPLETED"
    g = dg.build(data["issues"])
    v = bd.evaluate(g)
    assert ("DEP_RESOLVED", 446) in {(f.code, f.issue) for f in dg.analyze(g)}
    nxt = bd.next_task(v)
    assert nxt is not None and nxt.node.number != 501


def test_case_E_issue_waiting_for_independent_review_is_skipped_not_approved():
    data = json.loads(SNAP.read_text("utf-8"))
    g = dg.build(data["issues"], {502: "GPT Review"})
    v = bd.evaluate(g)
    assert any(r.startswith("PENDING_REVIEW") for r in reasons(v, 502))
    assert bd.next_task(v) is not None and bd.next_task(v).node.number != 502
