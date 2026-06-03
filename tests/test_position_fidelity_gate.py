"""Micro-fixture do position_fidelity_gate (Felipe 2026-06-02).

Prova isolada (sem build SU): 1 caso CORRETO passa, 3 RUINS falham —
janela deslocada, porta no host errado, gradil curto/recuado. So depois
disso o gate vai pra planta_74 real.
"""
from __future__ import annotations

import copy

from tools.position_fidelity_gate import compare


def _base():
    # escala implicita = 0.01 m/pt (derivada das portas no report)
    consensus = {
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "m000", "orientation": "h", "start": [0, 100], "end": [100, 100]},
            {"id": "m001", "orientation": "v", "start": [100, 0], "end": [100, 100]},
            {"id": "m002", "orientation": "v", "start": [0, 0], "end": [0, 100]},
        ],
        "openings": [
            {"id": "d0", "center": [50, 100], "opening_width_pts": 30,
             "wall_id": "m000", "kind_v5": "interior_door"},
            {"id": "w0", "center": [100, 50], "opening_width_pts": 25,
             "wall_id": "m001", "kind_v5": "window"},
        ],
        "soft_barriers": [
            {"id": "sb_noise"},  # sem fonte -> deve ser skip (sem grupo no report)
            {"id": "h_sb000", "barrier_type": "peitoril",
             "geometry_origin": "human_annotation", "render_as": "grade",
             "orientation": "h", "polyline_pts": [[0, 0], [100, 0]],
             "human_annotation": {"bbox_pts": [0, 0, 100, 5]}},
        ],
    }
    report = {"groups_diagnostic": [
        {"name": "DoorLeaf_Group_d0", "bbox_m": {"min": [0.35, 0.99, 0], "max": [0.65, 1.01, 2.1]}},
        {"name": "WindowGlass_Group_w0", "bbox_m": {"min": [0.99, 0.375, 0.9], "max": [1.01, 0.625, 2.1]}},
        {"name": "SoftBarrier_Group_1", "bbox_m": {"min": [0, -0.02, 0], "max": [1.0, 0.02, 1.1]}},
    ]}
    return consensus, report


def _fails(findings):
    return [f for f in findings if f["verdict"] == "FAIL"]


def test_caso_correto_passa():
    con, rep = _base()
    assert _fails(compare(con, rep)) == []  # nada falha no caso certo


def test_janela_deslocada_falha():
    con, rep = _base()
    # desloca o grupo da janela 0.5m em x
    for g in rep["groups_diagnostic"]:
        if g["name"] == "WindowGlass_Group_w0":
            g["bbox_m"]["min"][0] += 0.5
            g["bbox_m"]["max"][0] += 0.5
    fails = _fails(compare(con, rep))
    assert any(f["element"] == "w0" and f["reason"] == "center_offset" for f in fails)


def test_porta_no_host_errado_falha():
    con, rep = _base()
    # d0 diz wall_id=m000 (horizontal y=100), mas centro esta na parede vertical
    con["openings"][0]["center"] = [100, 50]
    for g in rep["groups_diagnostic"]:
        if g["name"] == "DoorLeaf_Group_d0":  # report bate com o centro errado (isola o host)
            g["bbox_m"]["min"] = [0.85, 0.49, 0]
            g["bbox_m"]["max"] = [1.15, 0.51, 2.1]
    fails = _fails(compare(con, rep))
    assert any(f["element"] == "d0" and f["reason"] == "wrong_host_wall" for f in fails)


def test_gradil_curto_e_recuado_falha():
    con, rep = _base()
    # bbox maior (y 0..50) + polyline no centro e curto (x 20..60)
    for b in con["soft_barriers"]:
        if b["id"] == "h_sb000":
            b["human_annotation"]["bbox_pts"] = [0, 0, 100, 50]
            b["polyline_pts"] = [[20, 25], [60, 25]]
    fails = _fails(compare(con, rep))
    reasons = {f["reason"] for f in fails if f["element"] == "h_sb000"}
    assert "railing_offset_from_host" in reasons  # recuado pro centro
    assert "coverage_short" in reasons            # nao cobre a largura
    assert any(r.startswith("terminal_gap") for r in reasons)  # endpoints soltos


def test_extra_sem_fonte_falha():
    con, rep = _base()
    # aparece um grupo pro sb_noise (index 0) que NAO tem fonte -> over-generation
    rep["groups_diagnostic"].append(
        {"name": "SoftBarrier_Group_0", "bbox_m": {"min": [0, 0, 0], "max": [1, 0.02, 1.1]}})
    fails = _fails(compare(con, rep))
    assert any(f["element"] == "sb_noise" and f["reason"] == "extra_without_source" for f in fails)
