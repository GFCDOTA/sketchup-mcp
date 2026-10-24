"""#440: o baseline de defeitos nunca e editado para aceitar defeito novo ou pior; so encolhe por correcao."""
from __future__ import annotations

from tools.validation import defect_baseline as db
from tools.validation import pr_policy_gate as pg

OLD = [{"key": "r0|CONTAINMENT|A", "measure": 0.05}, {"key": "r0|DOOR|P1", "measure": 30.0}]
BODY = "Refs #5\nSKP-proof: N/A\nTests: N/A — teste"
ISS = {5: {"state": "OPEN", "labels": []}}


def codes(new, files=(pg.BASELINE_PATH,)):
    return {f.code for f in pg.check(BODY, list(files), ISS, (), (OLD, new))}


def test_removing_or_reducing_a_defect_is_a_legitimate_correction():
    assert db.weakened(OLD, OLD[:1]) == []
    assert db.weakened(OLD, [{"key": "r0|CONTAINMENT|A", "measure": 0.01}, OLD[1]]) == []


def test_new_defect_or_worse_measure_in_the_registry_is_flagged():
    assert db.weakened(OLD, [*OLD, {"key": "r1|OBJECTS|B", "measure": 0.01}]) == ["r1|OBJECTS|B: defeito novo no registro"]
    worse = [{"key": "r0|CONTAINMENT|A", "measure": 0.2}, OLD[1]]
    assert "pior" in db.weakened(OLD, worse)[0]


def test_pr_that_edits_the_registry_to_accept_a_defect_fails_the_policy_gate():
    assert "PR_BASELINE_WEAKENED" in codes([*OLD, {"key": "r1|OBJECTS|B", "measure": 0.01}])
    assert "PR_BASELINE_WEAKENED" not in codes(OLD[:1])
    assert "PR_BASELINE_WEAKENED" not in codes([*OLD, {"key": "x", "measure": 9}], files=("docs/x.md",))
