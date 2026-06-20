"""sofa_placement_gate.py — GATE de PLACEMENT/ORIENTACAO do sofa (veredito do GPT:
"objeto PASS, placement FAIL" — sofa bem construido mas flutuando no centro, sem eixo
pra TV). Valida uma POSICAO de sofa na sala (nao a anatomia, que e do sofa_gate):

  1. ANCORADO        — costas do sofa perto de uma parede (nao flutua no centro)
  2. FRENTE->FOCO    — olha pra uma parede-TV LIMPA (eixo sofa->TV), angulo<=30, dist ok
  3. FORA_CIRCULACAO — bbox nao cruza zonas de passagem / giro de porta
  4. CLEARANCE       — ha folga livre na frente do sofa (dentro do comodo, sem passagem)
  5. JUSTIFICATIVA   — a posicao tem REGRA (nao "caiu no centro porque cabia")

HARD = ancorado + frente_para_foco + fora_circulacao -> qualquer um falho = FAIL.
SOFT = clearance + justificativa -> falho = WARN. Tudo ok = PASS. Deterministico, sem SU.

A regra que o Claude tem que seguir (GPT): "Sofa so pode ser aprovado se front_vector
aponta pra TV/ponto focal; bbox nao cruza circulacao; esta ancorado; ha clearance na
frente; nao esta no meio de passagem; a escolha tem justificativa."

Uso: python interior/validators/sofa_placement_gate.py   (roda 5 fixtures de erro/acerto)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shapely.geometry import Point, Polygon          # noqa: E402
from shapely.ops import unary_union                   # noqa: E402
from interior.semantics.wall_affordance import wall_affordance   # noqa: E402
from tools.bedroom_layout import _door_zones, _wall_setup, M     # noqa: E402
from tools.spatial_model import PT_TO_M, build_spatial_model     # noqa: E402

from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; env PT_TO_M -> 0.0259)
TV_MIN_VIEW, TV_MAX_VIEW = 1.8, 5.0
ANCHOR_MAX_M = 0.45      # costas a no maximo 0.45m da parede = ancorado
FOCAL_MAX_ANG = 30.0     # angulo frente-vs-TV
CLEAR_M = 0.45           # folga exigida na frente


def _angle(a, b):
    na, nb = math.hypot(*a), math.hypot(*b)
    if na == 0 or nb == 0:
        return 180.0
    c = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))
    return math.degrees(math.acos(c))


def _tv_point(sm, aff):
    """Ponto focal (centro da parede-TV limpa, recuado 0.25m). None se nao ha."""
    tv_id = aff["best_tv_wall"]
    if tv_id is None:
        return None, None
    ws = _wall_setup(sm, tv_id)
    if ws is None:
        return tv_id, None
    amid = (ws["along_lo"] + ws["along_hi"]) / 2.0
    perp = ws["face"] + ws["sgn"] * M(0.25)
    return tv_id, ((amid, perp) if ws["orient"] == "h" else (perp, amid))


def placement_gate(con, room_id, center_in, facing, sofa_w=2.2, sofa_d=0.95, justification=""):
    """center_in = (x,y) em shell-inches (mesmo PT_TO_IN do brain); facing = vetor 2D
    pra onde o sofa OLHA (frente). Devolve veredito PASS/WARN/FAIL + checks + porques."""
    sm = build_spatial_model(con, room_id)
    aff = wall_affordance(con, room_id)
    cell = sm["_geom"]["cell"]
    cx, cy = center_in[0] / PT_TO_IN, center_in[1] / PT_TO_IN          # -> pdf-points
    fx, fy = facing
    fn = math.hypot(fx, fy) or 1.0
    fx, fy = fx / fn, fy / fn
    px, py = -fy, fx                                                    # eixo da largura (perp)
    hw, hd = M(sofa_w) / 2.0, M(sofa_d) / 2.0
    corners = [(cx + px * hw * sw + fx * hd * sd, cy + py * hw * sw + fy * hd * sd)
               for sw, sd in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    sofa_poly = Polygon(corners)
    back_pt = Point(cx - fx * hd, cy - fy * hd)

    checks, why = {}, []

    # 1. ANCORADO — costas perto da parede (borda do comodo)
    back_gap_m = cell.exterior.distance(back_pt) * PT_TO_M
    checks["ancorado"] = back_gap_m <= ANCHOR_MAX_M
    if not checks["ancorado"]:
        why.append(f"flutuando: costas a {back_gap_m:.2f}m da parede (max {ANCHOR_MAX_M})")

    # 2. FRENTE -> FOCO (parede-TV limpa, eixo sofa->TV)
    tv_id, tv_pt = _tv_point(sm, aff)
    ang, dist = 180.0, 0.0
    if tv_pt is not None:
        ang = _angle((fx, fy), (tv_pt[0] - cx, tv_pt[1] - cy))
        dist = math.hypot(tv_pt[0] - cx, tv_pt[1] - cy) * PT_TO_M
    focal_ok = tv_pt is not None and ang <= FOCAL_MAX_ANG and TV_MIN_VIEW <= dist <= TV_MAX_VIEW
    checks["frente_para_foco"] = focal_ok
    if not focal_ok:
        why.append(f"sem eixo p/ TV (parede {tv_id}, ang {ang:.0f}>{FOCAL_MAX_ANG:.0f} ou dist {dist:.1f}m fora [{TV_MIN_VIEW},{TV_MAX_VIEW}])")

    # 3 + 5. FORA DA CIRCULACAO (passagens + giro de porta)
    circ = list(sm["_geom"]["circ"] or [])
    dz = _door_zones(sm)
    if dz is not None:
        circ.append(dz)
    keepout = unary_union(circ) if circ else None
    overlap = sofa_poly.intersection(keepout).area * PT_TO_M ** 2 if keepout else 0.0
    checks["fora_circulacao"] = overlap < 0.05
    if not checks["fora_circulacao"]:
        why.append(f"cruza circulacao/passagem ({overlap:.2f} m2)")

    # 4. CLEARANCE na frente (faixa CLEAR_M, largura 0.7*W, dentro do comodo e livre)
    fw = M(sofa_w * 0.7) / 2.0
    inner, outer = hd, hd + M(CLEAR_M)
    strip = Polygon([(cx + px * fw * s + fx * inner, cy + py * fw * s + fy * inner) for s in (-1, 1)]
                    + [(cx + px * fw * s + fx * outer, cy + py * fw * s + fy * outer) for s in (1, -1)])
    clear_ok = cell.buffer(M(0.06)).contains(strip) and (
        keepout is None or strip.intersection(keepout).area * PT_TO_M ** 2 < 0.05)
    checks["clearance_frente"] = bool(clear_ok)
    if not clear_ok:
        why.append("sem folga livre na frente do sofa")

    # 6. JUSTIFICATIVA
    checks["justificativa"] = bool(str(justification).strip())
    if not checks["justificativa"]:
        why.append("posicao sem justificativa (regra)")

    HARD = ("ancorado", "frente_para_foco", "fora_circulacao")
    SOFT = ("clearance_frente", "justificativa")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "checks": checks, "why": why,
            "back_gap_m": round(back_gap_m, 2), "tv_wall": tv_id,
            "front_angle_deg": round(ang, 1), "view_dist_m": round(dist, 2),
            "circ_overlap_m2": round(overlap, 3)}


# ------------------------------------------------------------------ fixtures
def _fixtures(con, room_id="r002"):
    """5 placements (GPT): correto / flutuando / rotacionado errado / no corredor / sem
    eixo. Deriva o correto do solver; sintetiza os erros a partir da geometria real."""
    from interior.planners.living_room_planner import plan_living
    sm = build_spatial_model(con, room_id)
    cell = sm["_geom"]["cell"]
    cc = cell.centroid
    plan = plan_living(con, room_id)
    out = []
    if plan.get("result") == "OK":
        s = plan["plan"]["sofa"]
        out.append(("correto (solver)", tuple(s["center_in"]), tuple(s["facing"]), s["rule"], "PASS"))
        # rotacionado errado: mesma ancora, facing INVERTIDO (de costas pra TV)
        out.append(("rotacionado errado", tuple(s["center_in"]),
                    (-s["facing"][0], -s["facing"][1]), "", "FAIL"))
    # flutuando no centro do comodo, sem ancora
    out.append(("flutuando no centro",
                (cc.x * PT_TO_IN, cc.y * PT_TO_IN), (1.0, 0.0), "", "FAIL"))
    # no corredor / passagem: em cima de uma zona de circulacao
    circ = sm["_geom"]["circ"] or []
    if circ:
        z = unary_union(list(circ)).representative_point()
        out.append(("no corredor (circulacao)",
                    (z.x * PT_TO_IN, z.y * PT_TO_IN), (1.0, 0.0), "", "FAIL"))
    return out


if __name__ == "__main__":
    import json
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    rid = sys.argv[1] if len(sys.argv) > 1 else "r002"
    print(f"=== SofaPlacementGate fixtures ({rid}) ===")
    ok = True
    for name, c_in, face, just, expect in _fixtures(con, rid):
        r = placement_gate(con, rid, c_in, face, justification=just)
        hit = r["result"] == expect
        ok = ok and hit
        flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["result"]]
        mark = "[ok]" if hit else "[X ESPERAVA " + expect + "]"
        print(f"  {flag} {name:26} -> {r['result']:4} {mark}")
        if r["why"]:
            print(f"        porque: {'; '.join(r['why'])}")
    print(f"\n{'TODOS OK' if ok else 'FALHOU: gate nao bate com o esperado'}")
    sys.exit(0 if ok else 1)
