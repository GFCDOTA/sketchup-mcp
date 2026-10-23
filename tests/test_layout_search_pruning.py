"""Otimizacoes exatas da busca de posicao (2026-10-23): a versao nova do `_table_set` (servico) devolve EXATAMENTE o que a
versao antiga devolvia. A referencia abaixo e a implementacao anterior, literal; as zonas cobrem sem obstaculo, com
obstaculos, com circulacao e o caso em que nada cabe."""
from __future__ import annotations

import pytest
from shapely.geometry import Point, Polygon
from shapely.geometry import box as _shp_box

from tools.rooms.service import layout as svc


def _table_set_reference(zone, placed, circ):
    """Copia literal do `_table_set` anterior a otimizacao (busca O(grade x obstaculos) com buffers no laco)."""
    inner = zone.buffer(-0.06)
    x0, y0, x1, y1 = zone.bounds
    best = None
    cx0, cy0 = (x0 + x1) / 2, (y0 + y1) / 2
    for diam in (0.90, 0.80, 0.70, 0.60):
        table_ok = []
        gx = x0
        while gx <= x1:
            gy = y0
            while gy <= y1:
                table = Point(gx, gy).buffer(diam / 2, quad_segs=8)
                gy += 0.05
                if not inner.contains(table):
                    continue
                if any(table.intersects(p.buffer(pm)) for p, pm in placed):
                    continue
                if circ is not None and table.intersection(circ).area > svc._DOOR_TOL_M2:
                    continue
                table_ok.append((gx, gy - 0.05, table))
            gx += 0.05
        for tx, ty, table in table_ok:
            chairs = []
            for dx, dy in ((0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)):
                cc = (tx + dx * (diam / 2 + 0.28), ty + dy * (diam / 2 + 0.28))
                ch = _shp_box(cc[0] - 0.22, cc[1] - 0.22, cc[0] + 0.22, cc[1] + 0.22)
                pulled = ch.buffer(0.16)
                if not zone.buffer(-0.02).contains(pulled):
                    continue
                if circ is not None and ch.intersection(circ).area > svc._DOOR_TOL_M2:
                    continue
                if any(pulled.intersects(p.buffer(0.03)) for p in [q for q, _ in placed] + [x[0] for x in chairs]):
                    continue
                chairs.append((ch, cc, (-dx, -dy)))
            if len(chairs) < 2:
                continue
            score = (-len(chairs), (tx - cx0) ** 2 + (ty - cy0) ** 2)
            if best is None or score < best[0]:
                best = (score, diam, (tx, ty), table, chairs)
        if best is not None:
            break
    if best is None:
        return None
    _score, diam, center, table, chairs = best
    return diam, center, table.wkb, [(c.wkb, cc, face) for c, cc, face in chairs]


def _normalize(result):
    out, _note = result
    if not out:
        return None
    table, chairs = out[0], out[1:]
    return table[8], table[3], table[2].wkb, [(c[2].wkb, c[3], c[4]) for c in chairs]


L_SHAPE = Polygon([(0, 0), (4.0, 0), (4.0, 1.6), (1.8, 1.6), (1.8, 3.4), (0, 3.4)])
CASES = {
    "retangulo_livre": (_shp_box(0, 0, 3.2, 2.6), [], None),
    "com_obstaculos": (_shp_box(0, 0, 3.6, 3.0), [(_shp_box(0.0, 0.0, 0.9, 0.6), 0.30), (_shp_box(2.6, 2.2, 3.6, 3.0), 0.20)], None),
    "com_circulacao": (_shp_box(0, 0, 3.6, 3.0), [(_shp_box(0.0, 0.0, 0.9, 0.6), 0.30)], _shp_box(1.4, 0.0, 2.2, 3.0)),
    "em_L": (L_SHAPE, [(_shp_box(3.0, 0.0, 4.0, 0.7), 0.25)], _shp_box(0.0, 2.6, 1.8, 3.4)),
    "nada_cabe": (_shp_box(0, 0, 1.0, 1.0), [], None),
    "desce_para_0_80": (_shp_box(0, 0, 1.6, 1.6), [], None),
    "desce_para_0_60": (_shp_box(0, 0, 2.0, 1.2), [], None),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_optimized_table_search_returns_exactly_what_the_old_search_returned(name):
    zone, placed, circ = CASES[name]
    assert _normalize(svc._table_set(zone, placed, circ)) == _table_set_reference(zone, placed, circ)


# ---- busca da mesa de jantar da sala: ancora com mais folga de corredor primeiro (aprovada pelo Felipe com antes/depois)

def _portal(w_furnished, tier, w_empty=None):
    return {"w_furnished_m": w_furnished, "tier": tier, "w_empty_m": w_empty}


def test_corridor_slack_is_the_tightest_portal_against_its_own_requirement():
    from tools.validation import circulation_gate as cg
    result = {"checks": {"corredor_principal": {"portais": [
        {"w_furnished_m": None},                                            # ancora: nao medida
        _portal(0.95, "principal"), _portal(0.81, "secundaria"), _portal(0.70, "shell_estreito", w_empty=0.76)]}}}
    tol = cg.GEOMETRY_TOLERANCE_M
    expected = min(0.95 - cg.PRIMARY_TARGET_M, 0.81 - cg.SECONDARY_TARGET_M, 0.70 - (0.76 - tol))
    assert cg.corridor_slack_m(result) == pytest.approx(round(expected, 4))
    assert cg.corridor_slack_m({"checks": {"corredor_principal": {"portais": [{"w_furnished_m": None}]}}}) is None
    assert cg.corridor_slack_m({}) is None


@pytest.mark.planta74_scale
def test_dining_search_stays_cheap_and_still_passes_the_gate():
    """Trava de desempenho deterministica (conta chamadas, nao mede relogio): antes da ordenacao por folga eram 95."""
    import json
    from pathlib import Path

    from tools.furnish_apartment import living_room_boxes
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
    _boxes, out = living_room_boxes(con, "r002")
    mesa = next(d for d in out["placement_decisions"] if d["candidate_id"] == "mesa_de_jantar")
    assert mesa["optimizer"] == "dining_grid_search_v3_slack_ordered_refine" and mesa["gate_result"] == "PASS"
    assert mesa["n_candidates_tried"] <= 40, mesa


# ---- GateSession: sala + mobilia fixa calculadas 1x por busca; veredito e saida identicos ao gate completo

@pytest.mark.planta74_scale
def test_gate_session_and_decision_mode_match_the_full_gate_in_every_room():
    import copy
    import json
    from pathlib import Path

    from tools.orchestration.furnish_apartment import collect_boxes
    from tools.validation import circulation_gate as cg
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json").read_text("utf-8"))
    boxes, _summary = collect_boxes(con)
    checked = 0
    for room in con["rooms"]:
        try:
            full = cg.gate(con, copy.deepcopy(boxes), room["id"])
        except KeyError:                                   # comodo sem celula resolvida
            continue
        half = len(boxes) // 2
        session = cg.GateSession(con, copy.deepcopy(boxes[:half]), room["id"]).check(copy.deepcopy(boxes[half:]))
        assert json.dumps(session, sort_keys=True, default=str) == json.dumps(full, sort_keys=True, default=str), room["id"]
        decided = cg.gate(con, copy.deepcopy(boxes), room["id"], decide_only=True)
        assert decided["result"] == full["result"], room["id"]
        if full["result"] == "PASS":
            assert decided["checks"] == full["checks"]      # no PASS o modo decisao calculou tudo
        checked += 1
    assert checked >= 5


def test_gate_session_is_lazy_and_never_annotates_before_the_first_check():
    from tools.validation import circulation_gate as cg
    base = [{"kind": "sofa", "x0": 0, "y0": 0, "x1": 10, "y1": 10}]
    cg.GateSession({"rooms": []}, base, "r000")              # nada calculado: nem o modelo espacial e montado
    assert "interaction_policy" not in base[0] and "geometry_intent" not in base[0]
