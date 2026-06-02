"""railing_exact_match + parapet_not_railing_fallback gates (soft-barrier seesaw).

Micro-fixture: 1 guardrail (expected railing), 1 peitoril (expected low wall),
1 unsourced barrier (must NOT render). The current global-flag builder renders
all three as solid low walls (BAD); the fixed by-type+source builder renders the
railing as railing, the peitoril as low wall, and skips the unsourced (GOOD).
"""
from __future__ import annotations

from tools.parapet_not_railing_fallback_gate import (
    audit_parapet_not_railing_fallback,
)
from tools.railing_exact_match_gate import audit_railing_exact_match

CONSENSUS = {"soft_barriers": [
    {"id": "g1", "barrier_type": "guardrail", "host_wall_id": "w1"},
    {"id": "p1", "barrier_type": "peitoril", "height_m": 1.1, "host_wall_id": "w2"},
    {"id": "u1"},  # bare polyline, no source
]}


def _report(barriers):
    return {"soft_barrier_groups": {"barriers": barriers}}


BAD = _report([  # global-flag builder: everything a solid low wall
    {"id": "g1", "rendered": True, "render_as": "low_wall", "host_wall_id": "w1"},
    {"id": "p1", "rendered": True, "render_as": "low_wall", "host_wall_id": "w2"},
    {"id": "u1", "rendered": True, "render_as": "low_wall"},
])
GOOD = _report([  # by-type + source builder
    {"id": "g1", "rendered": True, "render_as": "railing", "host_wall_id": "w1"},
    {"id": "p1", "rendered": True, "render_as": "low_wall", "host_wall_id": "w2"},
    {"id": "u1", "rendered": False, "render_as": None, "skip_reason": "unsourced"},
])


# ---- railing_exact_match -------------------------------------------------

def test_railing_gate_fails_on_bad():
    r = audit_railing_exact_match(CONSENSUS, BAD)
    assert r["verdict"] == "FAIL"
    assert any(f["reason"] == "missing_expected_railing" and f["id"] == "g1"
               for f in r["findings"])


def test_railing_gate_passes_on_good():
    assert audit_railing_exact_match(CONSENSUS, GOOD)["verdict"] == "PASS"


def test_extra_unexpected_railing_fails():
    # rendering the peitoril as a railing = extra (it's not a railing type)
    rep = _report([{"id": "p1", "rendered": True, "render_as": "railing",
                    "host_wall_id": "w2"}])
    r = audit_railing_exact_match(CONSENSUS, rep)
    assert r["verdict"] == "FAIL"
    assert any(f["reason"] == "extra_unexpected_railing" for f in r["findings"])


def test_wrong_host_fails():
    rep = _report([{"id": "g1", "rendered": True, "render_as": "railing",
                    "host_wall_id": "WRONG"}])
    assert any(f["reason"] == "railing_on_wrong_host"
               for f in audit_railing_exact_match(CONSENSUS, rep)["findings"])


def test_length_delta_fails():
    con = {"soft_barriers": [{"id": "g1", "barrier_type": "railing",
                              "expected_length_m": 3.0}]}
    rep = _report([{"id": "g1", "rendered": True, "render_as": "railing",
                    "length_m": 3.5}])
    assert any(f["reason"] == "railing_length_delta"
               for f in audit_railing_exact_match(con, rep)["findings"])


# ---- parapet_not_railing_fallback ---------------------------------------

def test_fallback_gate_fails_on_unsourced_rendered():
    r = audit_parapet_not_railing_fallback(CONSENSUS, BAD)
    assert r["verdict"] == "FAIL"
    assert any(f["id"] == "u1" for f in r["findings"])


def test_fallback_gate_passes_when_unsourced_skipped():
    assert audit_parapet_not_railing_fallback(CONSENSUS, GOOD)["verdict"] == "PASS"
