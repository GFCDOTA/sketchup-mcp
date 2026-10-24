"""Quality Guardian (P1): gates de Issues, SPECs, PR e geometria/programa — mutacoes provam que reprovam o que devem."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.validation import issue_integrity_gate as ig
from tools.validation import pr_policy_gate as pg
from tools.validation import spec_integrity_gate as sg

OK_BODY = "**Dependências:** #2\n\n## Critérios de aceite\n- [ ] algo\n\n## Alternativas\n- a\n\n## Recomendação\n- a"


def iss(labels=(), body=OK_BODY, state="OPEN"):
    return {"state": state, "labels": [{"name": n} for n in labels], "body": body}


def codes(issues, specs=("FP-056_x.md",), exc=None):
    return {f.code for f in ig.check(issues, set(specs), exc)}


def test_open_issue_without_acceptance_criteria_is_flagged_but_an_epic_is_not():
    assert "ACCEPTANCE_MISSING" in codes({1: iss(body="sem criterios")})
    assert "ACCEPTANCE_MISSING" in codes({1: iss(body="## Critérios de aceite\nsem itens")})
    assert "ACCEPTANCE_MISSING" not in codes({1: iss(["tipo:epic"], body="so contexto")})


def test_blocked_needs_exactly_one_cause_and_a_stale_cause_is_flagged():
    assert "BLOCK_REASON_MISSING" in codes({1: iss(["blocked"])})
    assert "BLOCK_REASON_MISSING" in codes({1: iss(["blocked", "bloqueio:technical", "bloqueio:evidence"])})
    assert "BLOCK_REASON_WITHOUT_BLOCK" in codes({1: iss(["bloqueio:technical"])})
    assert "BLOCK_REASON_WITHOUT_BLOCK" in codes({1: iss(["blocked", "bloqueio:technical"], state="CLOSED")})


def test_an_epic_is_never_a_human_decision_nor_blocked():
    assert "BLOCK_EPIC" in codes({1: iss(["tipo:epic", "blocked", "bloqueio:human-decision", ig.HUMAN_FLAG])})
    assert "BLOCK_EPIC" in codes({1: iss(["tipo:epic", ig.HUMAN_FLAG])})


def test_human_decision_needs_the_flag_alternatives_and_a_recommendation():
    good = iss(["blocked", "bloqueio:human-decision", ig.HUMAN_FLAG])
    assert codes({1: good}) == set()
    assert "BLOCK_HUMAN_FLAG_MISMATCH" in codes({1: iss(["blocked", "bloqueio:human-decision"])})
    assert "BLOCK_HUMAN_FLAG_MISMATCH" in codes({1: iss(["blocked", "bloqueio:technical", ig.HUMAN_FLAG])})
    bare = iss(["blocked", "bloqueio:human-decision", ig.HUMAN_FLAG], body="## Critérios de aceite\n- [ ] x")
    assert "BLOCK_HUMAN_NO_ALTERNATIVES" in codes({1: bare})


def test_dependency_block_must_have_an_open_non_epic_dependency():
    dep = ["blocked", "bloqueio:dependency"]
    assert codes({1: iss(dep), 2: iss(["blocked", "bloqueio:human-decision", ig.HUMAN_FLAG])}) == set()
    assert "BLOCK_DEPENDENCY_STALE" in codes({1: iss(dep), 2: iss(state="CLOSED")})
    assert "BLOCK_DEPENDENCY_STALE" in codes({1: iss(dep), 2: iss(["tipo:epic"])})
    assert "BLOCK_DEPENDENCY_STALE" in codes({1: iss(dep, body="## Critérios de aceite\n- [ ] x")})


def test_unknown_spec_label_and_documented_exception():
    assert "SPEC_LABEL_UNKNOWN" in codes({1: iss(["spec:FP-999"])})
    assert "SPEC_LABEL_UNKNOWN" not in codes({1: iss(["spec:FP-056/FP-043"])})
    assert "SPEC_LABEL_UNKNOWN" not in codes({1: iss(["spec:FP-999"])}, exc={"1": {"SPEC_LABEL_UNKNOWN": "motivo"}})


def test_spec_cannot_cite_missing_issues_or_paths_nor_declare_done_what_the_backlog_keeps_open(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/ok.md").write_text("x", encoding="utf-8")
    text = ("| P1 | feita | `docs/ok.md` #10 |\n| P2 | feita | `docs/falta.md` #99 |\n| P3 | **feita** | #11 |\n| P4 | em curso | #11 |\n")
    issues = {10: {"state": "CLOSED"}, 11: {"state": "OPEN"}}
    got = {(f.code, f.issue) for f in sg.check({"FP-056.md": text}, issues, tmp_path)}
    assert ("SPEC_ISSUE_MISSING", 99) in got and ("SPEC_PATH_MISSING", 0) in got
    assert ("SPEC_DONE_OPEN_ISSUE", 11) in got and ("SPEC_DONE_OPEN_ISSUE", 10) not in got


def test_real_specs_cite_only_existing_paths():
    root = Path(__file__).resolve().parents[1]
    texts = {n: (root / "docs/specs" / n).read_text("utf-8") for n in sg.SPECS}
    assert not [f for f in sg.check(texts, {}, root) if f.code == "SPEC_PATH_MISSING"]


PR_OK = "Refs #5\n\nSKP-proof: N/A\nReason: ci-only\nJustification: so governanca.\n"


def pr(body, files, issues=None):
    return {f.code for f in pg.check(body, files, issues if issues is not None else {5: {"state": "OPEN", "labels": []}})}


def test_pr_must_link_an_issue_and_must_not_use_a_closing_keyword():
    assert pr(PR_OK, ["docs/x.md"]) == set()
    assert "PR_NO_ISSUE_LINK" in pr("SKP-proof: N/A", ["docs/x.md"])
    assert "PR_NO_ISSUE_LINK" in pr("Refs #404\nSKP-proof: N/A", ["docs/x.md"])
    assert "PR_CLOSING_KEYWORD" in pr("Closes #5\nSKP-proof: N/A", ["docs/x.md"])
    assert "PR_NO_ISSUE_LINK" not in pr("Issue: N/A — doc solta\nSKP-proof: N/A", ["docs/x.md"])


def test_pr_touching_human_decision_issue_must_declare_it_does_not_apply_the_decision():
    issues = {5: {"state": "OPEN", "labels": [{"name": "bloqueio:human-decision"}]}}
    assert "PR_REFS_HUMAN_BLOCKED" in pr(PR_OK, ["docs/x.md"], issues)
    assert "PR_REFS_HUMAN_BLOCKED" not in pr(PR_OK + "Decisão: não aplicada\n", ["docs/x.md"], issues)


def test_skp_affecting_pr_needs_a_final_skp_and_na_does_not_excuse_it():
    assert "PR_NO_SKP_PROOF_DECLARATION" in pr("Refs #5", ["docs/x.md"])
    f = ["tools/sketchup/shell/build_plan_shell_skp.py", "tests/test_x.py"]
    assert "PR_SKP_AFFECTING_WITHOUT_PROOF" in pr(PR_OK, f)
    assert "PR_SKP_AFFECTING_WITHOUT_PROOF" not in pr("Refs #5\nSKP-proof: entregue", f + ["artifacts/review/planta_74/x/final/a.skp"])


def test_code_change_needs_tests_or_an_explicit_justification_and_approval_claims_need_pending_human():
    assert "PR_CODE_WITHOUT_TESTS" in pr(PR_OK, ["tools/validation/x.py"])
    assert "PR_CODE_WITHOUT_TESTS" not in pr(PR_OK, ["tools/validation/x.py", "tests/test_x.py"])
    assert "PR_CODE_WITHOUT_TESTS" not in pr(PR_OK + "Tests: N/A — refactor coberto por X\n", ["tools/validation/x.py"])
    assert "PR_APPROVAL_WITHOUT_PROOF" in pr(PR_OK + "A aparência está aprovada.\n", ["docs/x.md"])
    assert "PR_APPROVAL_WITHOUT_PROOF" not in pr(PR_OK + "A aparência: PENDING_HUMAN.\n", ["docs/x.md"])


@pytest.mark.planta74_scale
def test_geometry_gate_reports_known_pending_without_approving_and_registry_matches_reality():
    from tools.validation import quality_geometry_gate as gg
    res = gg.evaluate()
    assert res["verdict"] == "KNOWN" and not res["new"] and not res["worse"]
    assert res["geometric_approved"] is False and res["functional_approved"] is False
    assert set(res["known_program_gaps"]) == set(res["missing_program"])           # lacuna sem registro reprova
    assert res["persisting_baseline_defects"] == 29 and res["preflight"] == "PASS"


def test_board_sync_moves_issues_to_gpt_review_only_when_the_pr_is_ready_and_green():
    from tools.validation import board_sync as bs
    ok = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
    items = {1: {"status": "In Progress"}, 2: {"status": "Blocked"}, 3: {"status": "Done"}, 4: {"status": "Backlog"}}
    body = "Refs #1\nRefs #2\nRefs #3\nRefs #4\nRefs #99"
    ready = {"body": body, "isDraft": False, "state": "OPEN", "statusCheckRollup": ok}
    assert bs.plan(ready, items) == [(1, "In Progress", "GPT Review"), (4, "Backlog", "GPT Review")]
    assert bs.target_status({**ready, "isDraft": True}) == "In Progress"
    assert bs.target_status({**ready, "statusCheckRollup": ok + [{"status": "IN_PROGRESS", "conclusion": None}]}) == "In Progress"
    assert bs.target_status({**ready, "statusCheckRollup": ok + [{"status": "COMPLETED", "conclusion": "FAILURE"}]}) == "In Progress"
    assert bs.target_status({**ready, "statusCheckRollup": []}) == "In Progress"
    merged = {**ready, "state": "MERGED"}
    assert bs.plan(merged, {1: {"status": "GPT Review"}}) == []          # mergeado: continua em GPT Review (Done so com evidencia)


def test_audit_report_groups_blocked_issues_by_cause_and_renders_facts_only():
    from tools.validation import audit_report as ar
    issues = [
        {"number": 2, "title": "decisao", "state": "OPEN", "labels": [{"name": "blocked"}, {"name": "bloqueio:human-decision"}]},
        {"number": 1, "title": "dep", "state": "OPEN", "labels": [{"name": "blocked"}, {"name": "bloqueio:dependency"}]},
        {"number": 3, "title": "sem causa", "state": "OPEN", "labels": [{"name": "blocked"}]},
        {"number": 4, "title": "fechada", "state": "CLOSED", "labels": [{"name": "blocked"}, {"name": "bloqueio:technical"}]},
    ]
    by = ar.blocked_by_cause(issues)
    assert [i["number"] for i in by["human-decision"]] == [2] and [i["number"] for i in by["dependency"]] == [1]
    assert [i["number"] for i in by["sem causa"]] == [3] and by["technical"] == []
    caps = {"base": {"capabilities": {"a.b": {"INVOKED": True, "CONSUMED": False}}, "watched_executed": {"x": False},
                     "specialists_invoked": 0, "specialists_total": 9, "recipes_consumed": 0, "recipes_total": 19},
            "catalog": {"a.b": ("IMPLEMENTED", "L1_PASS")}}
    md = ar.render({"date": "2026-10-25", "since": "2026-10-18", "commit": "abc1234", "merged": [], "open_prs": [], "blocked": by,
                    "capabilities": caps, "proofs": [{"path": "artifacts/review/x/summary.json", "commit": "deadbeef", "dirty": False,
                                                       "cases_ok": 10, "cases": 11, "pids": [1], "failed": ["perda_de_programa"]}]})
    assert "Decisoes que realmente dependem do proprietario (1)" in md and "#2 decisao" in md
    assert "| `a.b` | IMPLEMENTED | L1_PASS | True | False |" in md and "10/11" in md and "perda_de_programa" in md
    assert "PENDING_HUMAN" in md and "aprova" in md.lower()


def test_real_repo_proofs_are_listed_with_their_failures():
    from tools.validation import audit_report as ar
    rows = ar.proofs()
    p6 = [r for r in rows if r["path"] == "artifacts/review/fp056/p6/summary.json"]
    assert p6 and p6[0]["cases"] == 11 and p6[0]["failed"] == ["no_program_loss_without_a_recorded_decision"]


@pytest.mark.planta74_scale
def test_geometry_gate_tracks_registered_door_sweeps_and_flags_stale_or_unregistered_ones(monkeypatch):
    from tools.validation import known_gaps
    from tools.validation import quality_geometry_gate as gg
    base = known_gaps.load()
    assert gg.evaluate()["known_door_sweep"] == ["h_o003|rug", "h_o004|rug"]
    unreg = {**base, "door_sweep": {"h_o003|rug": base["door_sweep"]["h_o003|rug"]}}
    monkeypatch.setattr(known_gaps, "load", lambda *a, **k: unreg)
    res = gg.evaluate()
    assert res["verdict"] == "FAIL" and any("varredura real da folha sem registro" in r for r in res["reasons"])
    stale = {**base, "door_sweep": {**base["door_sweep"], "h_o999|rug": {"issue": 1, "reason": "x"}}}
    monkeypatch.setattr(known_gaps, "load", lambda *a, **k: stale)
    assert any("door_sweep registrado que nao existe mais" in r for r in gg.evaluate()["reasons"])
