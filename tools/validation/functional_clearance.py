"""functional_clearance.py — FP-054 F1B: folga funcional e ALCANCE por peca, em modo REPORT_ONLY.

Responde "o que e valido?" (F1), nunca "qual layout e melhor?" (F2): NAO move peca, NAO ranqueia, NAO escolhe layout.
Limiares e proveniencia vem de `core/functional_constraints.py`; aqui so mede e da o veredito.

Por peca registrada (vaso, lavatorio, box, bancada da cozinha):
  1. face de uso pelo CONTRATO do tipo (`opposite_single_backing_wall` / `single_free_side`), sobre o retangulo minimo da
     pegada — ambiguo (canto, entre paredes, solta) => BLOCKED_MISSING_INPUT, nunca palpite;
  2. folga na face: maior profundidade d de um retangulo [face, d] (ou disco de diametro d na abertura do box) livre de
     parede e de movel que bloqueia (mesma regra de bloqueio do `circulation_gate`);
  3. ALCANCE: maior largura w de passagem que liga um portal do comodo a zona de uso (faixa de USE_ZONE_DEPTH_M junto a face)
     — conectividade real no espaco livre erodido por w/2, nao "tem espaco perto". Comodo de portal unico e AVALIADO (essa era
     a lacuna da F1); sem portal => BLOCKED_MISSING_INPUT.

Saida: `FunctionalEvaluation` por (peca, regra) com medida, niveis, proveniencia, veredito, motivo e geometria testemunha.

    PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1b   # dry-run da planta_74

REPORT_ONLY: layout existente com INVALID nao quebra o CI; o CI reprova so registro/schema/proveniencia/unidade invalidos e
saida nao deterministica. Complexidade por peca: O(B + K*G), B caixas do comodo, K passos de bissecao (~7) e G custo de uma
erosao do espaco livre (cacheada por (poligono, largura) no `circulation_gate`).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from core.functional_constraints import (
    FUNCTIONAL_CONSTRAINTS,
    OBJECT_TYPES,
    FunctionalEvaluation,
    constraints_for,
    registry_errors,
)

M2IN = 39.3700787402
MODE = "REPORT_ONLY"
USE_ZONE_DEPTH_M = 0.30        # HEURISTIC: faixa onde a pessoa fica para usar a peca (testemunha do alcance, nao limiar)
BACKING_TOL_IN = 6.0           # HEURISTIC: lado da peca a <= 6 in (~15 cm, backsplash/revestimento) da borda conta como encostado
PORTAL_SNAP_M = 0.30           # mesma tolerancia do `circulation_gate._region_of`
SEARCH_MAX_M = 2.0


def _rect_sides(poly: Polygon) -> list[LineString]:
    r = poly.minimum_rotated_rectangle
    pts = list(r.exterior.coords)[:4]
    return [LineString([pts[i], pts[(i + 1) % 4]]) for i in range(4)]


def _outward(side: LineString, poly: Polygon) -> tuple[float, float]:
    (x0, y0), (x1, y1) = side.coords
    nx, ny = (y1 - y0), -(x1 - x0)
    n = math.hypot(nx, ny) or 1.0
    nx, ny = nx / n, ny / n
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if poly.contains(Point(mx + nx * 0.5, my + ny * 0.5)):
        nx, ny = -nx, -ny
    return nx, ny


def resolve_use_face(fp: Polygon, cell: Polygon, contract: str):
    """(lado, normal para fora, motivo). lado None => face nao resolvida pelo contrato (motivo diz por que)."""
    sides = _rect_sides(fp)
    inner = cell.buffer(-BACKING_TOL_IN)
    backed = [not inner.contains(s.interpolate(0.5, normalized=True)) for s in sides]   # perto da borda OU fora dela
    if contract == "opposite_longest_backing_side":
        idx = [i for i, b in enumerate(backed) if b]
        if not idx:
            return None, None, "USE_FACE_UNRESOLVED: nenhum lado encostado"
        longest = max(sides[i].length for i in idx)
        top = [i for i in idx if sides[i].length >= longest - 1.0]
        if len(top) != 1 or backed[(top[0] + 2) % 4]:
            return None, None, "USE_FACE_UNRESOLVED: lados encostados de mesmo comprimento ou opostos"
        face = sides[(top[0] + 2) % 4]
        return face, _outward(face, fp), None
    if contract == "opposite_single_backing_wall":
        if sum(backed) != 1:
            return None, None, f"USE_FACE_UNRESOLVED: {sum(backed)} lados encostados (contrato pede exatamente 1)"
        face = sides[(backed.index(True) + 2) % 4]
    elif contract == "single_free_side":
        free = [i for i, b in enumerate(backed) if not b]
        if len(free) != 1:
            return None, None, f"USE_FACE_UNRESOLVED: {len(free)} lados livres (contrato pede exatamente 1)"
        face = sides[free[0]]
    else:
        return None, None, f"USE_FACE_CONTRACT_UNKNOWN: {contract}"
    return face, _outward(face, fp), None


def _front_rect(face: LineString, n, depth_in: float, inset_in: float = 0.5) -> Polygon:
    (x0, y0), (x1, y1) = face.coords
    ux, uy = (x1 - x0), (y1 - y0)
    L = math.hypot(ux, uy) or 1.0
    ux, uy = ux / L, uy / L
    a = (x0 + ux * inset_in, y0 + uy * inset_in)
    b = (x1 - ux * inset_in, y1 - uy * inset_in)
    return Polygon([a, b, (b[0] + n[0] * depth_in, b[1] + n[1] * depth_in), (a[0] + n[0] * depth_in, a[1] + n[1] * depth_in)])


def _opening_disk(face: LineString, n, diameter_in: float) -> Polygon:
    m = face.interpolate(0.5, normalized=True)
    r = diameter_in / 2
    return Point(m.x + n[0] * (r + 0.01), m.y + n[1] * (r + 0.01)).buffer(r, quad_segs=32)


def _bisect(fits, lo=0.0, hi=SEARCH_MAX_M, tol=0.005) -> float:
    if not fits(tol):
        return 0.0
    if fits(hi):
        return hi
    lo = tol
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    return round(lo, 3)


def measure_front(face, n, free: Polygon, metric: str) -> float:
    room = free.buffer(1e-6)
    shape = (lambda d: _opening_disk(face, n, d * M2IN)) if metric == "opening_disk_diameter" else \
        (lambda d: _front_rect(face, n, d * M2IN))
    return _bisect(lambda d: room.contains(shape(d)))


def measure_reach(free: Polygon, portals: list[Point], zone: Polygon) -> tuple[float, dict]:
    """Maior largura (m) de passagem que liga algum portal a zona de uso (0.0 = desconectado ate 0,30 m)."""
    from tools.validation.circulation_gate import _eroded_regions
    wkb = free.wkb

    def reaches(w):
        regions = _eroded_regions(wkb, w)
        for p in portals:
            near = [r for r in regions if r.distance(p) <= PORTAL_SNAP_M * M2IN]
            if any(r.intersects(zone) for r in near):
                return True
        return False
    lo = 0.30
    if not reaches(lo):
        return 0.0, {"connected_at_m": None}
    w = _bisect(lambda x: reaches(x), lo=lo, hi=1.50, tol=0.01) if not reaches(1.50) else 1.50
    return max(w, lo), {"connected_at_m": lo}


def _room_context(con, boxes, room_id):
    from core.scale import PT_TO_IN
    from tools.spatial_model import build_spatial_model
    from tools.validation import circulation_gate as cg
    sm = build_spatial_model(con, room_id)
    cell = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in sm["_geom"]["cell"].exterior.coords])
    portals, dropped = cg._portal_points(sm, cell)
    inside = [b for b in boxes if b.get("corners") and cg._footprint(b).intersection(cell).area > 1.0]
    return cell, portals, dropped, inside


def _free_without(cell, room_boxes, module):
    from tools.validation import circulation_gate as cg
    blockers = cg._blockers([b for b in room_boxes if b.get("module") != module])
    occ = unary_union([g for _, g in blockers]) if blockers else None
    return cell.difference(occ.buffer(0.5)) if occ is not None else cell


def _coords(geom, nd=2):
    return [[round(x, nd), round(y, nd)] for x, y in geom.exterior.coords] if geom is not None and not geom.is_empty else []


def evaluate_room(con, boxes, room_id, room_type, room_name) -> list[FunctionalEvaluation]:
    cell, portals, dropped, room_boxes = _room_context(con, boxes, room_id)
    out: list[FunctionalEvaluation] = []
    for otype, spec in sorted(OBJECT_TYPES.items()):
        modules = sorted(m for t, m in spec["modules"] if t == room_type)
        if not modules:
            continue
        for module in modules:
            parts = [b for b in room_boxes if b.get("module") == module and (b.get("z0_in") or 0) / M2IN < 1.2]
            cons = constraints_for(otype)
            if not parts:
                out += [FunctionalEvaluation(room_id, module, otype, c.id, "NOT_APPLICABLE", "OBJECT_ABSENT") for c in cons]
                continue
            from tools.validation.circulation_gate import _footprint
            fp = unary_union([_footprint(b) for b in parts]).intersection(cell)    # peca que atravessa a parede: so o que esta no comodo
            face, n, why = resolve_use_face(fp, cell, spec["use_face_contract"])
            if face is None:
                out += [FunctionalEvaluation(room_id, module, otype, c.id, "BLOCKED_MISSING_INPUT", "USE_FACE_UNRESOLVED",
                                             missing_input=("use_face",), witness={"why": why,
                                                                                   "footprint": _coords(fp.minimum_rotated_rectangle)})
                        for c in cons]
                continue
            free = _free_without(cell, room_boxes, module)
            face_w = {"use_face": [[round(x, 2), round(y, 2)] for x, y in face.coords],
                      "normal": [round(n[0], 4), round(n[1], 4)], "contract": spec["use_face_contract"]}
            for c in cons:
                if c.metric == "reach_path_width":
                    if dropped or not portals:
                        missing = "portal" if not portals else "portal_inner_point"
                        out.append(FunctionalEvaluation(room_id, module, otype, c.id, "BLOCKED_MISSING_INPUT",
                                                        "NO_PORTAL" if not portals else "PORTAL_WITHOUT_INNER_POINT",
                                                        missing_input=(missing,), witness=face_w))
                        continue
                    zone = _front_rect(face, n, USE_ZONE_DEPTH_M * M2IN)
                    w, extra = measure_reach(free, portals, zone)
                    reason = "PATH_DISCONNECTED" if w == 0.0 else "MEASURED_PATH_WIDTH"
                    out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(w), reason, w, "m",
                                                    witness={**face_w, "use_zone": _coords(zone), "portals": len(portals),
                                                             **extra}))
                else:
                    d = measure_front(face, n, free, c.metric)
                    shape = _opening_disk(face, n, max(d, 0.01) * M2IN) if c.metric == "opening_disk_diameter" \
                        else _front_rect(face, n, max(d, 0.01) * M2IN)
                    out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(d),
                                                    "MEASURED_" + c.metric.upper(), d, "m",
                                                    witness={**face_w, "free_shape": _coords(shape)}))
    return out


def evaluate(con, boxes) -> dict:
    from tools.room_type import classify_rooms
    evals = []
    for r in classify_rooms(con):
        evals += evaluate_room(con, boxes, r["id"], r["room_type"], r.get("name"))
    rows = [e.to_dict(FUNCTIONAL_CONSTRAINTS.get(e.constraint_id)) for e in evals]
    rows.sort(key=lambda r: (r["room_id"], r["object_id"], r["constraint"]))
    summary = {v: 0 for v in ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE")}
    for r in rows:
        summary[r["verdict"]] += 1
    return {"schema_version": "functional_clearance_report.v1", "mode": MODE, "evaluations": len(rows), "summary": summary,
            "heuristics": {"USE_ZONE_DEPTH_M": USE_ZONE_DEPTH_M, "BACKING_TOL_IN": BACKING_TOL_IN,
                           "PORTAL_SNAP_M": PORTAL_SNAP_M, "provenance": "HEURISTIC"},
            "registry_errors": registry_errors(), "rows": rows}


def _markdown(report: dict) -> str:
    lines = ["# FP-054 F1B — folga funcional e alcance por peça (REPORT_ONLY)", "",
             "> Gerado por `PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1b`. "
             "Retrato datado: regenere, não edite. Nenhum layout foi alterado.", "",
             "Resumo: " + " · ".join(f"{k} {v}" for k, v in report["summary"].items()) + f" — {report['evaluations']} avaliações", "",
             "| Cômodo | Peça | Regra | Medido (m) | Mínimo ref. | Alvo projeto | Preferido | Veredito | Proveniência (mín/alvo/pref) | Falta |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["rows"]:
        lv = [r.get(k) or {} for k in ("reference_minimum", "project_target", "preferred")]
        lines.append(f"| {r['room_id']} | {r['object_id']} | {r['constraint']} | {'' if r['measured'] is None else r['measured']} | "
                     + " | ".join(str(x.get("value", "")) for x in lv)
                     + f" | **{r['verdict']}** | {' / '.join(x.get('provenance', '') for x in lv)} | {', '.join(r['missing_input'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)
    import contextlib
    import io

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    report = evaluate(con, boxes)
    if args.report:
        args.report.mkdir(parents=True, exist_ok=True)
        (args.report / "functional_clearance.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                                               encoding="utf-8", newline="\n")
        (args.report / "functional_clearance.md").write_text(_markdown(report), encoding="utf-8", newline="\n")
    sys.stdout.write(json.dumps({k: report[k] for k in ("mode", "evaluations", "summary", "registry_errors")},
                                ensure_ascii=False) + "\n")
    return 1 if report["registry_errors"] else 0          # REPORT_ONLY: so registro invalido reprova


if __name__ == "__main__":
    raise SystemExit(main())
