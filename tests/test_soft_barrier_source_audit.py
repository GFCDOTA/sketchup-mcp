"""soft_barrier_source_audit — provenance of soft barriers (finding #4)."""
from __future__ import annotations

from tools.soft_barrier_source_audit import audit_soft_barrier_sources


def test_bare_polyline_is_unsourced_warn():
    con = {"soft_barriers": [
        {"id": "sb000", "polyline_pts": [[0, 0], [1, 0]]},          # bare
        {"id": "h_sb000", "barrier_type": "peitoril", "height_m": 1.1},  # sourced
    ]}
    res = audit_soft_barrier_sources(con)
    assert res["verdict"] == "WARN"
    assert res["n_unsourced"] == 1
    assert res["n_sourced"] == 1
    assert res["findings"][0]["id"] == "sb000"


def test_all_sourced_passes():
    con = {"soft_barriers": [
        {"id": "a", "barrier_type": "mureta"},
        {"id": "b", "human_confirmed": True},
        {"id": "c", "pdf_text": "PEITORIL H=1,10M"},
    ]}
    assert audit_soft_barrier_sources(con)["verdict"] == "PASS"


def test_no_soft_barriers_passes():
    assert audit_soft_barrier_sources({})["verdict"] == "PASS"
    assert audit_soft_barrier_sources({"soft_barriers": []})["verdict"] == "PASS"
