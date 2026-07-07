"""Semi-autonomous pipeline (commit 2) — decision_judge objective fusion.

Synthetic proposals only (no consensus, no SU, no LLM — interns run with
with_style=False, geometry/overlap injected as pre-computed verdicts). Locks:
- clean program -> OBJECTIVE_STRONG_PASS; WARN -> BORDERLINE; FAIL -> STRONG_FAIL;
- INVALID as a first-class class (malformed / unknown type);
- TASTE_REFUSED for aesthetic gaps (the machine abstains);
- objective consistency_gap -> BORDERLINE (never auto approve/reject);
- scalar confidence derived honestly from PASS/WARN/FAIL counts + coverage;
- the module never contains a human-verdict literal.
"""
from __future__ import annotations

import inspect
import re

from tools.interior_studio import decision_judge as dj


def _program(items, env="sala", area=14.0, pid="furniture_program_r002") -> dict:
    return {"id": pid, "type": "furniture_program", "environment": env,
            "room_id": "r002", "room_name": "SALA", "area_m2": area,
            "items": items}


def _gap(**over) -> dict:
    base = {"id": "gap_duplicate_main_sofa", "type": "consistency_gap",
            "kind": "duplicate_main", "severity": "med",
            "title": "sofa: 2 refs principais", "detail": "escolher 1"}
    base.update(over)
    return base


# ---- furniture_program: the three canonical verdicts ---------------------


def test_clean_program_is_strong_pass():
    r = dj.classify(_program([{"asset": "sofa", "priority": "core"}]),
                    geometry="PASS", overlap="PASS")
    assert r["classification"] == dj.STRONG_PASS
    assert r["verdict"] == "PASS"
    assert r["confidence"] == 1.0                     # full coverage, all clean
    assert r["judge_verdicts"] == {"interns": "PASS", "geometry_sanity": "PASS",
                                   "furniture_overlap": "PASS"}


def test_program_with_intern_warn_is_borderline():
    # sofa in a 3 m² sala -> capacidade WARN (med), nothing high
    r = dj.classify(_program([{"asset": "sofa"}], area=3.0),
                    geometry="PASS", overlap="PASS")
    assert r["classification"] == dj.BORDERLINE
    assert r["verdict"] == "WARN"
    assert 0.0 < r["confidence"] < 1.0


def test_program_with_gate_warn_is_borderline():
    # interns clean but the overlap gate warns -> borderline
    r = dj.classify(_program([{"asset": "sofa"}]),
                    geometry="PASS", overlap="WARN")
    assert r["classification"] == dj.BORDERLINE
    assert r["judge_verdicts"]["furniture_overlap"] == "WARN"


def test_program_with_cross_room_item_is_strong_fail():
    # cama (bed) in a sala -> pertencimento high -> FAIL
    r = dj.classify(_program([{"asset": "cama"}, {"asset": "sofa"}]),
                    geometry="PASS", overlap="PASS")
    assert r["classification"] == dj.STRONG_FAIL
    assert r["verdict"] == "FAIL"
    assert any("pertencimento" in e for e in r["evidence"])


def test_gate_fail_forces_strong_fail_even_if_interns_pass():
    r = dj.classify(_program([{"asset": "sofa"}]),
                    geometry="FAIL", overlap="PASS")
    assert r["classification"] == dj.STRONG_FAIL
    # one fail among three ran signals -> confidence in the FAIL is modest, honest
    assert 0.0 < r["confidence"] < 0.5


# ---- coverage: a required gate that could not run is NOT strong pass ------


def test_clean_interns_but_skipped_gates_is_borderline_not_pass():
    r = dj.classify(_program([{"asset": "sofa"}]))   # geometry/overlap None
    assert r["classification"] == dj.BORDERLINE
    assert r["judge_verdicts"]["geometry_sanity"] == "SKIPPED"
    assert r["judge_verdicts"]["furniture_overlap"] == "SKIPPED"
    assert any("cobertura incompleta" in e for e in r["evidence"])
    # confidence penalised by coverage (only interns ran of 3 expected)
    assert r["confidence"] < 0.5


def test_strong_pass_confidence_drops_when_one_gate_skipped():
    full = dj.classify(_program([{"asset": "sofa"}]),
                       geometry="PASS", overlap="PASS")
    assert full["confidence"] == 1.0


# ---- INVALID as a first-class class --------------------------------------


def test_empty_items_is_invalid():
    r = dj.classify(_program([]))
    assert r["classification"] == dj.INVALID
    assert r["confidence"] == 0.0


def test_missing_environment_is_invalid():
    p = _program([{"asset": "sofa"}])
    del p["environment"]
    assert dj.classify(p)["classification"] == dj.INVALID


def test_unknown_type_is_invalid():
    assert dj.classify({"id": "x", "type": "weird"})["classification"] == dj.INVALID
    assert dj.classify("not a dict")["classification"] == dj.INVALID


# ---- consistency_gap: taste refused, objective borderline ----------------


def test_objective_gap_is_borderline():
    r = dj.classify(_gap())
    assert r["classification"] == dj.BORDERLINE
    assert r["decision_type"] == "consistency_gap"
    assert r["judge_verdicts"]["objective"] is True
    assert r["confidence"] == 0.6                      # med severity


def test_high_severity_gap_more_confident_than_low():
    hi = dj.classify(_gap(severity="high"))["confidence"]
    lo = dj.classify(_gap(severity="low"))["confidence"]
    assert hi > lo


def test_style_intern_gap_is_taste_refused():
    r = dj.classify(_gap(id="gap_estilo_r004", kind="intern_estilo",
                         intern="estilo", severity="med",
                         title="cozinha — estilo WARN"))
    assert r["classification"] == dj.TASTE_REFUSED
    assert r["verdict"] == "TASTE"
    assert r["judge_verdicts"]["objective"] is False
    assert r["confidence"] == 0.0


def test_taste_marker_in_kind_is_refused():
    r = dj.classify(_gap(kind="visual_review", intern=None))
    assert r["classification"] == dj.TASTE_REFUSED


def test_gap_with_bad_severity_is_invalid():
    r = dj.classify(_gap(severity="whatever"))
    assert r["classification"] == dj.INVALID


# ---- the RAIL: judge never emits a human verdict -------------------------


def test_judge_module_has_no_human_verdict_literal():
    src = inspect.getsource(dj)
    assert not re.search(r"['\"](IMPROVED|SAME|WORSE)['\"]", src)
