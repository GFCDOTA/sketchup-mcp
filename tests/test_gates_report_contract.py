"""P3a-01 — gates com `--report` contra o build canônico aprovado (FP-043).

Defeito reproduzido: `run_deterministic_gates --fixture planta_74 --report artifacts/planta_74/geometry_report.json`
reprovava o PRÓPRIO build aprovado em 2026-07-11 por DEFASAGEM DE CONTRATO entre os gates e o builder:

- `railing_exact_match_gate` só esperava grade para `barrier_type` de guarda-corpo; o builder (e o consensus
  curado pelo Felipe) decidem por `render_as` explícito primeiro (`h_sb000` é `peitoril` com `render_as: grade`);
- `position_fidelity_gate` só aceitava `human_annotation` como fonte; o builder aceita também `pdf_vector` e
  `pdf_text_label` (`h_sb001` MURETA H=0,70M, curada em 2026-07-11) e o gate chamava o grupo renderizado de
  "extra sem fonte".

A correção alinha o gate ao contrato do builder; nada do consensus nem do relatório canônico foi alterado e os
casos negativos continuam reprovando (deslocamento, omissão de grade, escala errada, fonte inexistente).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.position_fidelity_gate import compare
from tools.railing_exact_match_gate import audit_railing_exact_match
from tools.run_deterministic_gates import run_all

ROOT = Path(__file__).resolve().parents[1]
CON_PATH = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
REP_PATH = ROOT / "artifacts/planta_74/geometry_report.json"
CON = json.loads(CON_PATH.read_text("utf-8"))
REP = json.loads(REP_PATH.read_text("utf-8"))


def _sb(i, **kw):
    return {"id": f"s{i}", **kw}


def _rep(*barriers):
    return {"soft_barrier_groups": {"barriers": [dict(b) for b in barriers]}}


# ----------------------------------------------------------------- railing_exact_match_gate
def test_render_as_grade_explicito_vence_o_tipo_peitoril():
    con = {"soft_barriers": [_sb(0, barrier_type="peitoril", render_as="grade")]}
    rep = _rep({"id": "s0", "render_as": "railing"})
    assert audit_railing_exact_match(con, rep)["verdict"] == "PASS"


def test_render_as_low_wall_explicito_vence_o_tipo_de_guarda_corpo():
    con = {"soft_barriers": [_sb(0, barrier_type="guardrail", render_as="low_wall")]}
    assert audit_railing_exact_match(con, _rep({"id": "s0", "render_as": "low_wall"}))["verdict"] == "PASS"
    res = audit_railing_exact_match(con, _rep({"id": "s0", "render_as": "railing"}))
    assert res["verdict"] == "FAIL" and res["findings"][0]["reason"] == "extra_unexpected_railing"


def test_grade_autorizada_e_omitida_continua_reprovando():
    con = {"soft_barriers": [_sb(0, barrier_type="peitoril", render_as="grade")]}
    res = audit_railing_exact_match(con, _rep({"id": "s0", "render_as": "low_wall"}))
    assert res["verdict"] == "FAIL" and res["findings"][0]["reason"] == "missing_expected_railing"


def test_grade_sem_autorizacao_continua_reprovando():
    con = {"soft_barriers": [_sb(0, barrier_type="mureta")]}
    res = audit_railing_exact_match(con, _rep({"id": "s0", "render_as": "railing"}))
    assert res["verdict"] == "FAIL" and res["findings"][0]["reason"] == "extra_unexpected_railing"


def test_tipo_de_guarda_corpo_sem_render_as_continua_esperando_grade():
    con = {"soft_barriers": [_sb(0, barrier_type="guardrail")]}
    assert audit_railing_exact_match(con, _rep({"id": "s0", "render_as": "railing"}))["verdict"] == "PASS"
    assert audit_railing_exact_match(con, _rep({"id": "s0", "render_as": "low_wall"}))["verdict"] == "FAIL"


# --------------------------------------------------------------- position_fidelity_gate
def _group(name, bbox):
    return {"name": name, "bbox_m": {"min": bbox[0], "max": bbox[1]}}


def _pos(consensus_barriers, groups):
    con = {"walls": [], "openings": [], "wall_thickness_pts": 5.4, "soft_barriers": consensus_barriers}
    return compare(con, {"groups_diagnostic": groups})


@pytest.mark.parametrize("origin", ["human_annotation", "pdf_vector", "pdf_text_label"])
def test_origens_que_o_builder_aceita_contam_como_fonte(origin):
    b = {"id": "b", "barrier_type": "mureta", "geometry_origin": origin, "polyline_pts": [[0, 0], [10, 0]]}
    findings = _pos([b], [_group("SoftBarrier_Group_0", ([0, 0, 0], [1, 0.2, 0.7]))])
    assert [f for f in findings if f["verdict"] == "FAIL"] == []


def test_barreira_sem_origem_de_fonte_renderizada_continua_extra_sem_fonte():
    b = {"id": "b", "barrier_type": "mureta", "geometry_origin": "svg_segments", "polyline_pts": [[0, 0], [10, 0]]}
    findings = _pos([b], [_group("SoftBarrier_Group_0", ([0, 0, 0], [1, 0.2, 0.7]))])
    assert [f["reason"] for f in findings if f["verdict"] == "FAIL"] == ["extra_without_source"]


def test_barreira_com_fonte_e_sem_grupo_continua_expected_absent():
    b = {"id": "b", "barrier_type": "mureta", "geometry_origin": "pdf_vector", "polyline_pts": [[0, 0], [10, 0]]}
    findings = _pos([b], [])
    assert [f["reason"] for f in findings if f["verdict"] == "FAIL"] == ["expected_absent"]


# --------------------------------------------------- build canônico aprovado + contraprovas
def test_gates_com_report_passam_no_build_canonico_aprovado():
    res = run_all(consensus_path=str(CON_PATH), report_path=str(REP_PATH))
    statuses = {k: g.get("overall", g.get("verdict")) for k, g in res["gates"].items()}
    assert res["overall"] == "PASS", statuses
    assert {"railing_match", "position_fidelity", "scale_anchor"} <= set(statuses)


def _group_named(rep, name):
    return next(g for g in rep["groups_diagnostic"] if g["name"] == name)


def test_abertura_deslocada_no_relatorio_reprova_position_fidelity():
    rep = copy.deepcopy(REP)
    g = _group_named(rep, "DoorLeaf_Group_h_o000")
    for k in ("min", "max"):
        g["bbox_m"][k][0] += 1.5   # porta tem tolerância de 0,80 m (bbox inclui o swing)
    res = run_all(consensus_path=str(CON_PATH), report_path=str(REP_PATH))   # controle: o canônico passa
    assert res["overall"] == "PASS"
    findings = compare(CON, rep)
    assert any(f["verdict"] == "FAIL" and f["element"] == "h_o000" for f in findings)


def test_grade_omitida_no_relatorio_reprova_railing_match():
    rep = copy.deepcopy(REP)
    for b in rep["soft_barrier_groups"]["barriers"]:
        if b["id"] == "h_sb000":
            b["render_as"] = "low_wall"
    res = audit_railing_exact_match(CON, rep)
    assert res["verdict"] == "FAIL" and res["findings"][0]["reason"] == "missing_expected_railing"


def test_grupo_de_grade_ausente_reprova_position_fidelity():
    rep = copy.deepcopy(REP)
    idx = next(i for i, sb in enumerate(CON["soft_barriers"]) if sb["id"] == "h_sb000")
    rep["groups_diagnostic"] = [g for g in rep["groups_diagnostic"] if g["name"] != f"SoftBarrier_Group_{idx}"]
    findings = compare(CON, rep)
    assert any(f["verdict"] == "FAIL" and f["reason"] == "expected_absent" and f["element"] == "h_sb000" for f in findings)


def test_escala_errada_no_relatorio_reprova_o_gate_de_escala_dentro_do_run_all(tmp_path):
    rep = copy.deepcopy(REP)
    sh = _group_named(rep, "PlanShell_Group")
    for k in ("min", "max"):
        sh["bbox_m"][k] = [round(v * 1.36, 4) for v in sh["bbox_m"][k]]
    bad = tmp_path / "geometry_report.json"
    bad.write_text(json.dumps(rep), encoding="utf-8")
    res = run_all(consensus_path=str(CON_PATH), report_path=str(bad))
    assert res["gates"]["scale_anchor"]["overall"] == "FAIL" and res["overall"] == "FAIL"
