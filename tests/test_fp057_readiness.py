"""FP-057: o scheduler nao declara elegivel o que nao tem proximo passo executavel, e mostra o que impede CONCLUIR."""
from __future__ import annotations

import json
from pathlib import Path

from tools.validation import backlog_discovery as bd
from tools.validation import dependency_graph as dg
from tools.validation import task_readiness as tr

ROOT = Path(__file__).resolve().parents[1]
ACC = "## Critérios de aceite\n- [ ] x\n"
AUDITED = (429, 416, 436, 453, 457, 463, 460, 462, 473, 476)       # 501 fechou com evidencia (PRs 547/559): sai do registro


def issue(n, labels=(), kind="task", state="OPEN"):
    return {"number": n, "title": f"t{n}", "state": state, "stateReason": "COMPLETED", "body": ACC,
            "labels": [{"name": x} for x in (f"tipo:{kind}", "prio:P2", *labels)]}


def verdicts(nums, readiness, **kw):
    return {v.node.number: v for v in bd.evaluate(dg.build([issue(n, **kw) for n in nums]), [], {}, readiness)}


def entry(**kw):
    base = {"audited_at": "2026-10-25", "state": "READY", "next_step": "faz", "offline": True, "needs_sketchup": False}
    return {**base, **kw}


def test_ready_entry_exposes_the_next_step_and_what_blocks_completion():
    r = {1: entry(completion_blockers=[{"cause": "REVIEW", "ref": "#524", "detail": "caminho critico"}])}
    v = verdicts([1], r)[1]
    assert v.eligible and v.next_step == "faz" and v.offline is True and v.completion_blockers[0]["cause"] == "REVIEW"
    assert "para concluir: REVIEW #524" in str(v) and "proximo passo (offline)" in str(v)


def test_blocked_entry_makes_the_issue_ineligible_with_cause_ref_and_detail():
    r = {1: {"audited_at": "2026-10-25", "state": "BLOCKED", "cause": "HUMAN_DECISION", "ref": "#446", "detail": "decide o dono"}}
    v = verdicts([1], r)[1]
    assert not v.eligible and "HUMAN_DECISION: decide o dono (#446)" in v.reasons[0]


def test_without_a_registry_at_all_behaviour_is_unchanged():
    assert verdicts([1, 2], None)[1].eligible and verdicts([1, 2], None)[2].next_step is None


def test_eligible_issue_without_an_audited_next_step_is_not_eligible_when_a_registry_is_in_use():
    # defeito observado em 2026-10-25: #430 e #457 saiam ELEGIVEL sem nenhum proximo passo (o executor concluia "nada a fazer")
    v = verdicts([1, 2], {1: entry()})
    assert v[1].eligible and v[1].next_step == "faz"
    assert not v[2].eligible and v[2].reasons[0].startswith("NO_NEXT_STEP") and v[2].next_step is None
    assert bd.classify(v[2]) == "BLOCKED"


def test_every_eligible_verdict_carries_a_concrete_next_step_whenever_the_registry_is_loaded():
    reg = tr.load()
    nums = sorted({*reg, 900, 901, 902})
    for v in verdicts(nums, reg).values():
        assert not v.eligible or (v.next_step and isinstance(v.offline, bool) and isinstance(v.needs_sketchup, bool))


def test_real_registry_covers_the_audited_issues_and_every_entry_is_actionable_or_traced():
    reg = tr.load()
    assert set(AUDITED) <= set(reg)
    for n in AUDITED:
        e = reg[n]
        if e["state"] == "READY":
            assert len(e["next_step"]) > 40 and isinstance(e["offline"], bool) and isinstance(e["needs_sketchup"], bool)
            assert not (e["offline"] and e["needs_sketchup"])
        else:
            assert e["state"] == "BLOCKED" and e["cause"] in tr.CAUSES and e["ref"] and e["detail"]
    v = verdicts(AUDITED, reg)
    assert all(v[n].eligible and v[n].next_step for n in AUDITED if reg[n]["state"] == "READY")
    assert all(not v[n].eligible and reg[n]["cause"] in v[n].reasons[0] for n in AUDITED if reg[n]["state"] == "BLOCKED")


def test_catalog_and_workflow_adjacent_issues_declare_review_as_completion_blocker():
    reg = tr.load()
    for n in (429, 460, 453):
        # READY: o bloqueio de conclusao e declarado em completion_blockers; BLOCKED: e a propria causa (a #453 acabou a medicao segura)
        blockers = reg[n]["completion_blockers"] if reg[n]["state"] == "READY" else [{"cause": reg[n]["cause"], "ref": reg[n]["ref"]}]
        assert any(b["cause"] == "REVIEW" and b["ref"] == "#524" for b in blockers), n
    assert any(b["cause"] == "ENVIRONMENT" for b in reg[460]["completion_blockers"])      # L2 exige SketchUp real
    assert reg[473]["cause"] == "EVIDENCE" and reg[476]["cause"] == "EVIDENCE"                # sem reference_target aprovado


def test_every_file_ref_in_the_real_registry_exists_and_issue_refs_are_well_formed():
    for n, e in tr.load().items():
        for b in e.get("completion_blockers", []) + ([e] if e["state"] == "BLOCKED" else []):
            assert b["cause"] in tr.CAUSES and b["detail"]
            ref = b["ref"]
            if ref.startswith("#"):
                assert ref[1:].isdigit(), (n, ref)
            else:
                assert (ROOT / ref.split("#")[0]).exists(), (n, ref)


def codes(reg, issues):
    return {c for c, _n, _d in tr.validate(reg, issues, ROOT)}


def test_validate_rejects_untraceable_or_stale_entries():
    open_ = {1: {"state": "OPEN"}, 524: {"state": "OPEN"}}
    assert codes({2: entry()}, open_) == {"READINESS_UNKNOWN_ISSUE"}
    assert codes({1: entry()}, {1: {"state": "CLOSED"}}) == {"READINESS_STALE"}
    assert "READINESS_READY_WITHOUT_NEXT_STEP" in codes({1: entry(next_step="")}, open_)
    assert "READINESS_READY_FLAGS" in codes({1: entry(offline=True, needs_sketchup=True)}, open_)
    bad = entry(completion_blockers=[{"cause": "PREGUICA", "ref": "#999", "detail": "x"}])
    assert {"READINESS_BAD_CAUSE", "READINESS_BAD_REF"} <= codes({1: bad}, open_)
    nofile = entry(completion_blockers=[{"cause": "EVIDENCE", "ref": "docs/nao/existe.md", "detail": "x"}])
    assert "READINESS_BAD_REF" in codes({1: nofile}, open_)
    assert "READINESS_NO_DATE" in codes({1: entry(audited_at="")}, open_)
    assert codes({1: entry(completion_blockers=[{"cause": "REVIEW", "ref": "#524", "detail": "ok"}])}, open_) == set()


def test_summary_counts_ready_blocked_pending_review_and_environment_separately():
    nodes = [issue(1), issue(2, ["blocked", "bloqueio:human-decision", "aprovação-humana-pendente"]),
             issue(3, ["blocked", "bloqueio:environment"]), issue(4), issue(5, kind="epic")]
    statuses = {4: "GPT Review"}
    vs = bd.evaluate(dg.build(nodes, statuses), [], {})
    s = bd.summarize(vs)
    assert s == {"READY": [1], "BLOCKED": [2], "PENDING_REVIEW": [4], "ENVIRONMENT": [3], "IN_PROGRESS": [], "EPIC": [5]}


def test_registry_json_is_valid_and_versioned():
    data = json.loads((ROOT / "docs/governance/task_readiness.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "task_readiness.v1" and data["tasks"]


def test_within_a_rank_tasks_that_can_finish_end_to_end_come_before_those_that_only_start():
    r = {1: entry(completion_blockers=[{"cause": "REVIEW", "ref": "#524", "detail": "x"}]), 2: entry()}
    vs = bd.evaluate(dg.build([issue(1), issue(2)]), [], {}, r)
    assert [v.node.number for v in vs if v.eligible] == [2, 1]
