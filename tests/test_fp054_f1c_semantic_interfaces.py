"""FP-054 F1C: interfaces funcionais EXPLICITAS, fontes estruturadas (#394) e comparacao F1B x F1C."""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from core.functional_constraints import (
    FUNCTIONAL_CONSTRAINTS,
    S_CATRACA,
    S_PROPOSAL,
    FunctionalInterface,
    SourceRef,
    Threshold,
    registry_errors,
)
from tests.test_fp054_f1b_functional_clearance import M, _eval, _room, _toilet_on_east_wall
from tools.validation import functional_clearance as fc


# ------------------------------------------------------------------------------------------------ fontes
def test_every_threshold_carries_the_structured_source_fields():
    fields = ("source_tier", "source_type", "source_ref", "source_version_or_date", "exact_claim_supported", "applicability",
              "limitations")
    for c in FUNCTIONAL_CONSTRAINTS.values():
        for lvl in (c.reference_minimum, c.project_target, c.preferred):
            for s in lvl.sources:
                assert all(getattr(s, f) for f in fields), (c.id, s.source_ref)
    assert registry_errors() == []


def test_no_secondary_source_is_promoted_to_normative_or_technical():
    for c in FUNCTIONAL_CONSTRAINTS.values():
        for lvl in (c.reference_minimum, c.project_target, c.preferred):
            assert lvl.provenance != "NORMATIVE"
            if lvl.provenance == "TECHNICAL_REFERENCE":
                assert {s.source_tier for s in lvl.sources} & {"A", "B", "C"}


@pytest.mark.parametrize("prov,src,bad", [
    ("NORMATIVE", S_CATRACA, True),                  # blog nunca e norma
    ("TECHNICAL_REFERENCE", S_CATRACA, True),        # tier D nao sustenta referencia tecnica
    ("COMFORT_GUIDE", S_PROPOSAL, True),             # proposta interna nao e guia externo
    ("PROJECT_POLICY", S_CATRACA, True),             # politica do projeto e interna (tier E)
    ("COMFORT_GUIDE", S_CATRACA, False),
])
def test_provenance_must_match_the_source_tier(prov, src, bad):
    assert bool(Threshold(0.9, "m", prov, (src,)).tier_errors()) is bad


def test_source_without_exact_claim_is_refused():
    with pytest.raises(ValueError):
        SourceRef("D", "blog", "https://x", "2026", "", "residencial", "nenhuma")


# --------------------------------------------------------------------------------------------- interfaces
def _iface(b, **over):
    x0, y0, x1, y1 = b
    cy = (y0 + y1) / 2
    fx = x1 - 0.65 * M
    base = dict(room_id="r_syn", module="Vaso", object_type="toilet", interface="use_face",
                segment_in=((fx, cy - 0.18 * M), (fx, cy + 0.18 * M)), normal=(-1.0, 0.0), basis="SEMANTIC_DECLARED",
                source="teste")
    base.update(over)
    return FunctionalInterface(**base)


def _eval_with(con, boxes, ifaces, mode="REPORT_ONLY"):
    rows = [e.to_dict() for e in fc.evaluate_room(con, boxes, "r_syn", "BATHROOM", "SINTETICO",
                                                  {(i.room_id, i.module): i for i in ifaces}, mode)]
    return {r["constraint"]: r for r in rows}


def test_semantic_interface_is_used_and_labelled():
    con, b = _room()
    r = _eval_with(con, [_toilet_on_east_wall(b)], [_iface(b)])
    assert r["toilet.front_clearance"]["interface_basis"] == "SEMANTIC_DECLARED"
    assert r["toilet.front_clearance"]["verdict"] == "PREFERRED"


def test_report_only_fallback_is_labelled_heuristic():
    con, b = _room()
    r = _eval(con, [_toilet_on_east_wall(b)])
    assert r["toilet.front_clearance"]["interface_basis"] == "HEURISTIC_GEOMETRY"


def test_solver_mode_never_accepts_an_inferred_face():
    con, b = _room()
    r = _eval_with(con, [_toilet_on_east_wall(b)], [], mode="SOLVER")
    for k in ("toilet.front_clearance", "toilet.reach_path"):
        assert r[k]["verdict"] == "BLOCKED_MISSING_INPUT"
        assert r[k]["missing_input"] == ["semantic_use_face"]


def test_interface_off_the_piece_is_blocked_not_trusted():
    con, b = _room()
    x0, y0, x1, y1 = b
    far = _iface(b, segment_in=((x0 + 5, y0 + 5), (x0 + 5, y0 + 20)))
    r = _eval_with(con, [_toilet_on_east_wall(b)], [far])
    assert r["toilet.front_clearance"]["verdict"] == "BLOCKED_MISSING_INPUT"
    assert r["toilet.front_clearance"]["missing_input"] == ["interface_geometry"]


def test_interface_contract_validation():
    con, b = _room()
    with pytest.raises(ValueError):
        _iface(b, normal=(1.0, 1.0))
    with pytest.raises(ValueError):
        _iface(b, basis="GUESS")
    with pytest.raises(ValueError):
        _iface(b, interface="door")


def _shower_scene(b, entry):
    x0, y0, x1, y1 = b
    box = {"module": "Box", "kind": "box_vidro", "z0_in": 0.0, "h_in": 80.0,
           "corners": [[x0, y0], [x0 + 0.9 * M, y0], [x0 + 0.9 * M, y0 + 0.9 * M], [x0, y0 + 0.9 * M]]}
    fy = y0 + 0.9 * M
    seg = ((x0 + entry[0] * M, fy), (x0 + entry[1] * M, fy))
    return box, FunctionalInterface("r_syn", "Box", "shower", "shower_entry", seg, (0.0, 1.0), "SEMANTIC_DECLARED", "teste")


def test_entry_width_comes_from_the_declared_entry_segment():
    con, b = _room()
    box, iface = _shower_scene(b, (0.45, 0.90))                          # vao declarado de 0,45 m
    r = _eval_with(con, [box], [iface])
    assert abs(r["shower.entry_width"]["measured"] - 0.45) <= 0.02 and r["shower.entry_width"]["verdict"] == "INVALID"
    box, iface = _shower_scene(b, (0.20, 0.90))                          # 0,70 m
    r = _eval_with(con, [box], [iface])
    assert r["shower.entry_width"]["verdict"] == "VALID"


def test_heuristic_never_invents_the_shower_entry_width():
    con, b = _room()
    x0, y0, x1, y1 = b
    wall_to_wall = {"module": "Box", "kind": "box_vidro", "z0_in": 0.0, "h_in": 80.0,          # 3 paredes: 1 lado livre
                    "corners": [[x0, y0], [x1, y0], [x1, y0 + 0.9 * M], [x0, y0 + 0.9 * M]]}
    r = _eval(con, [wall_to_wall])
    assert r["shower.entry_front_clearance"]["interface_basis"] == "HEURISTIC_GEOMETRY"     # face resolvida pelo fallback
    assert r["shower.entry_width"]["verdict"] == "BLOCKED_MISSING_INPUT"
    assert r["shower.entry_width"]["missing_input"] == ["entry_segment"]


# ---------------------------------------------------------------------------------------------- planta real
@pytest.fixture(scope="module")
def real():
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
        ifaces = fc.collect_interfaces(con, boxes)
    return con, boxes, ifaces


@pytest.mark.planta74_scale
def test_every_registered_piece_of_planta74_has_a_semantic_interface(real):
    con, boxes, ifaces = real
    assert set(ifaces) == {("r004", "countertop"), ("r005", "Vaso"), ("r005", "Bancada"), ("r005", "Box"),
                           ("r006", "Vaso"), ("r006", "Bancada"), ("r006", "Box"), ("r007", "Vaso"), ("r007", "Bancada")}
    assert all(i.semantic for i in ifaces.values())
    assert ifaces[("r004", "countertop")].basis == "SEMANTIC_PDF_ANCHOR"


@pytest.mark.planta74_scale
def test_solver_mode_on_planta74_has_no_heuristic_and_no_blocked(real):
    con, boxes, ifaces = real
    rep = fc.evaluate(con, boxes, ifaces, "SOLVER")
    assert rep["evaluations"] == 23 and rep["summary"]["BLOCKED_MISSING_INPUT"] == 0
    assert "HEURISTIC_GEOMETRY" not in rep["interface_bases"]
    assert rep == fc.evaluate(con, boxes, ifaces, "SOLVER")                   # deterministico


@pytest.mark.planta74_scale
def test_comparison_covers_all_f1b_results_and_explains_every_divergence(real):
    from pathlib import Path
    con, boxes, ifaces = real
    f1b = json.loads(Path("docs/reports/fp054/f1b/functional_clearance.json").read_text("utf-8"))
    rows = fc.compare(f1b, fc.evaluate(con, boxes, ifaces))
    assert len([r for r in rows if r["f1b_constraint"]]) == 20
    for r in rows:
        if r["divergent"]:
            assert r["explanation"] and not r["explanation"].startswith("IGUAL"), r


@pytest.mark.planta74_scale
def test_exporting_interfaces_does_not_change_any_box():
    from tools.validation.room_regression_diff import capture
    with contextlib.redirect_stdout(io.StringIO()):
        s = capture()
    assert s["snapshot_sha256"].startswith("a4fa928927d11a0f") and s["part_count"] == 390   # FP-056 P1 (so a A.S. mudou)
