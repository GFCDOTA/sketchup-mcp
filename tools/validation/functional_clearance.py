"""functional_clearance.py — FP-054 F1B/F1C: folga funcional e ALCANCE por peca.

Responde "o que e valido?" (F1), nunca "qual layout e melhor?" (F2): NAO move peca, NAO ranqueia, NAO escolhe layout.
Limiares, fontes e proveniencia vem de `core/functional_constraints.py`; aqui so mede e da o veredito.

Por peca registrada (vaso, lavatorio, box, bancada da cozinha):
  1. INTERFACE (F1C): face de uso / face de trabalho / entrada do box vem de semantica EXPLICITA — o builder do banheiro
     (`functional_interfaces` no resultado do brain) e a ancora hidraulica do PDF na cozinha. Conferida contra a pegada
     (segmento sobre a borda da peca). Sem semantica: em REPORT_ONLY usa o contrato geometrico da F1B, marcado
     `HEURISTIC_GEOMETRY`; em SOLVER => BLOCKED_MISSING_INPUT (o solver nunca usa face inferida como hard).
  2. folga na interface: maior profundidade d de um retangulo [interface, d] livre de parede e de movel que bloqueia;
     no box, tambem a largura livre do vao de entrada (`entry_clear_width`).
  3. ALCANCE: maior largura w de passagem que liga um portal a zona de uso (faixa de USE_ZONE_DEPTH_M junto a interface) —
     conectividade real no espaco livre erodido por w/2. Testemunha: regiao alcancavel na largura medida e o GARGALO
     (ponto onde a conexao se rompe com w + 2 cm).

    PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1c [--compare <f1b.json>]

REPORT_ONLY: layout existente com INVALID nao quebra o CI; o CI reprova so registro/fonte/proveniencia/unidade invalidos e saida
nao deterministica. Complexidade por peca: O(B + K*G), B caixas do comodo, K passos de bissecao (~7), G uma erosao (cacheada).
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
    MODES,
    OBJECT_TYPES,
    FunctionalEvaluation,
    FunctionalInterface,
    constraints_for,
    registry_errors,
)
from tools.rooms.shared.spatial_solver.geometry import (  # noqa: F401 — re-exportados (API da F1B/F1C)
    M2IN,
    PORTAL_SNAP_M,
    SEARCH_MAX_M,
    _bisect,
    _coords,
    _free_without,
    _front_rect,
    _gap_witness,
    _multi_coords,
    _reach_components,
    measure_entry_width,
    measure_front,
    measure_reach,
    usable_face,
)

USE_ZONE_DEPTH_M = 0.30        # HEURISTIC: faixa onde a pessoa fica para usar a peca (testemunha do alcance, nao limiar)
BACKING_TOL_IN = 6.0           # HEURISTIC (so fallback): lado a <= 6 in (~15 cm) da borda conta como encostado
INTERFACE_ON_FOOTPRINT_TOL_IN = 1.0


# ------------------------------------------------------------------------------------------- interface: fallback
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
    """FALLBACK GEOMETRICO (F1B): (lado, normal para fora, motivo). Lado None => nao resolvido. Resultado e HEURISTIC_GEOMETRY."""
    sides = _rect_sides(fp)
    inner = cell.buffer(-BACKING_TOL_IN)
    backed = [not inner.contains(s.interpolate(0.5, normalized=True)) for s in sides]
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


# ------------------------------------------------------------------------------------------------ geometria


# --------------------------------------------------------------------------------------------- contexto + interface
def _room_context(con, boxes, room_id):
    from core.scale import PT_TO_IN
    from tools.spatial_model import build_spatial_model
    from tools.validation import circulation_gate as cg
    sm = build_spatial_model(con, room_id)
    cell = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in sm["_geom"]["cell"].exterior.coords])
    portals, dropped = cg._portal_points(sm, cell)
    inside = [b for b in boxes if b.get("corners") and cg._footprint(b).intersection(cell).area > 1.0]
    return cell, portals, dropped, inside


def collect_interfaces(con: dict, boxes: list[dict]) -> dict[tuple[str, str], FunctionalInterface]:
    """Interfaces SEMANTICAS por (comodo, modulo): brain do banheiro (`functional_interfaces`) e ancora da cozinha."""
    from tools.room_type import classify_rooms
    from tools.rooms.bathroom.layout import build_boxes as bath_boxes
    from tools.rooms.kitchen.functional_interfaces import functional_interfaces as kitchen_ifaces
    out: dict[tuple[str, str], FunctionalInterface] = {}
    for r in classify_rooms(con):
        if r["room_type"] == "BATHROOM":
            _b, meta = bath_boxes(con, r["id"])
            raw = (meta or {}).get("functional_interfaces") or []
        elif r["room_type"] == "KITCHEN":
            raw = kitchen_ifaces(con, r["id"], [b for b in boxes if b.get("room") == str(r.get("name") or r["id"])])
        else:
            continue
        for d in raw:
            iface = FunctionalInterface.from_builder(r["id"], d)
            out[(r["id"], iface.module)] = iface
    return out


def _resolve_interface(iface, fp, cell, spec, mode):
    """(face LineString, normal, base, nota, faltando). face None => BLOCKED com `faltando`."""
    if iface is not None:
        face = LineString(iface.segment_in)
        if fp.boundary.distance(face.interpolate(0.5, normalized=True)) > INTERFACE_ON_FOOTPRINT_TOL_IN:
            return None, None, iface.basis, "INTERFACE_GEOMETRY_MISMATCH: interface fora da borda da peca", ("interface_geometry",)
        return face, iface.normal, iface.basis, iface.note, ()
    if mode == "SOLVER":
        return None, None, None, "SEMANTIC_INTERFACE_MISSING: solver nao aceita face inferida", (f"semantic_{spec['interface']}",)
    face, n, why = resolve_use_face(fp, cell, spec["fallback_contract"])
    if face is None:
        return None, None, "HEURISTIC_GEOMETRY", why, ("use_face",)
    note = "fallback geometrico F1B" + ("; abertura do box = meio do lado livre (NAO e a porta)" if spec["interface"] ==
                                       "shower_entry" else "")
    return face, n, "HEURISTIC_GEOMETRY", note, ()


def evaluate_room(con, boxes, room_id, room_type, room_name, interfaces=None, mode="REPORT_ONLY") -> list[FunctionalEvaluation]:
    if mode not in MODES:
        raise ValueError(f"modo desconhecido: {mode!r}")
    from tools.validation.circulation_gate import _footprint
    interfaces = interfaces or {}
    cell, portals, dropped, room_boxes = _room_context(con, boxes, room_id)
    out: list[FunctionalEvaluation] = []
    for otype, spec in sorted(OBJECT_TYPES.items()):
        for module in sorted(m for t, m in spec["modules"] if t == room_type):
            parts = [b for b in room_boxes if b.get("module") == module and (b.get("z0_in") or 0) / M2IN < 1.2]
            cons = constraints_for(otype)
            if not parts:
                out += [FunctionalEvaluation(room_id, module, otype, c.id, "NOT_APPLICABLE", "OBJECT_ABSENT") for c in cons]
                continue
            fp = unary_union([_footprint(b) for b in parts]).intersection(cell)
            face, n, basis, note, missing = _resolve_interface(interfaces.get((room_id, module)), fp, cell, spec, mode)
            if face is None:
                out += [FunctionalEvaluation(room_id, module, otype, c.id, "BLOCKED_MISSING_INPUT",
                                             note.split(":")[0], missing_input=missing,
                                             witness={"why": note, "footprint": _coords(fp.minimum_rotated_rectangle)},
                                             interface_basis=basis) for c in cons]
                continue
            free = _free_without(cell, room_boxes, module)
            usable = usable_face(face, n, free)
            fw = {"interface": spec["interface"], "segment": [[round(x, 2), round(y, 2)] for x, y in face.coords],
                  "usable_segment": [[round(x, 2), round(y, 2)] for x, y in usable.coords] if usable is not None else None,
                  "normal": [round(n[0], 4), round(n[1], 4)], "note": note,
                  "footprint": _coords(fp.minimum_rotated_rectangle)}
            for c in cons:
                if c.metric == "reach_path_width":
                    if dropped or not portals:
                        miss = "portal" if not portals else "portal_inner_point"
                        out.append(FunctionalEvaluation(room_id, module, otype, c.id, "BLOCKED_MISSING_INPUT",
                                                        "NO_PORTAL" if not portals else "PORTAL_WITHOUT_INNER_POINT",
                                                        missing_input=(miss,), witness=fw, interface_basis=basis))
                        continue
                    if usable is None:                    # interface toda contra obstaculo/parede: zona de uso inexistente
                        out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(0.0), "INTERFACE_OBSTRUCTED",
                                                        0.0, "m", witness=fw, interface_basis=basis))
                        continue
                    zone = _front_rect(usable, n, USE_ZONE_DEPTH_M * M2IN)
                    w, extra = measure_reach(free, portals, zone)
                    out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(w),
                                                    "PATH_DISCONNECTED" if w == 0.0 else "MEASURED_PATH_WIDTH", w, "m",
                                                    witness={**fw, "use_zone": _coords(zone),
                                                             "portals": [[round(p.x, 2), round(p.y, 2)] for p in portals],
                                                             **extra}, interface_basis=basis))
                elif c.metric == "entry_clear_width":
                    if basis == "HEURISTIC_GEOMETRY":
                        out.append(FunctionalEvaluation(room_id, module, otype, c.id, "BLOCKED_MISSING_INPUT",
                                                        "ENTRY_SEGMENT_UNDECLARED", missing_input=("entry_segment",),
                                                        witness=fw, interface_basis=basis))
                        continue
                    wv = measure_entry_width(face, n, free)
                    out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(wv), "MEASURED_ENTRY_WIDTH",
                                                    wv, "m", witness=fw, interface_basis=basis))
                else:
                    if usable is None:
                        out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(0.0), "INTERFACE_OBSTRUCTED",
                                                        0.0, "m", witness=fw, interface_basis=basis))
                        continue
                    d = measure_front(usable, n, free)
                    out.append(FunctionalEvaluation(room_id, module, otype, c.id, c.classify(d), "MEASURED_FRONT_DEPTH",
                                                    d, "m", witness={**fw, "free_shape": _coords(_front_rect(usable, n, max(d, 0.01) * M2IN))},
                                                    interface_basis=basis))
    return out


def evaluate(con, boxes, interfaces=None, mode="REPORT_ONLY") -> dict:
    from tools.room_type import classify_rooms
    evals = []
    for r in classify_rooms(con):
        evals += evaluate_room(con, boxes, r["id"], r["room_type"], r.get("name"), interfaces, mode)
    rows = [e.to_dict(FUNCTIONAL_CONSTRAINTS.get(e.constraint_id)) for e in evals]
    rows.sort(key=lambda r: (r["room_id"], r["object_id"], r["constraint"]))
    summary = {v: 0 for v in ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE")}
    for r in rows:
        summary[r["verdict"]] += 1
    bases: dict[str, int] = {}
    for r in rows:
        if r["interface_basis"]:
            bases[r["interface_basis"]] = bases.get(r["interface_basis"], 0) + 1
    return {"schema_version": "functional_clearance_report.v2", "mode": mode, "evaluations": len(rows), "summary": summary,
            "interface_bases": dict(sorted(bases.items())),
            "heuristics": {"USE_ZONE_DEPTH_M": USE_ZONE_DEPTH_M, "BACKING_TOL_IN (so fallback)": BACKING_TOL_IN,
                           "PORTAL_SNAP_M": PORTAL_SNAP_M, "provenance": "HEURISTIC"},
            "registry_errors": registry_errors(), "rows": rows}


# ------------------------------------------------------------------------------------------- comparacao F1B x F1C
F1B_TO_F1C = {"shower.opening_clearance": "shower.entry_front_clearance"}


def compare(f1b: dict, f1c: dict) -> list[dict]:
    """Uma linha por resultado da F1B (e as regras novas da F1C), com a divergencia explicada."""
    new = {(r["room_id"], r["object_id"], r["constraint"]): r for r in f1c["rows"]}
    seen, out = set(), []
    for old in f1b["rows"]:
        key = (old["room_id"], old["object_id"], F1B_TO_F1C.get(old["constraint"], old["constraint"]))
        cur = new.get(key)
        seen.add(key)
        out.append(_diff(old, cur, renamed=old["constraint"] in F1B_TO_F1C))
    for key, cur in sorted(new.items()):
        if key not in seen:
            out.append(_diff(None, cur))
    return out


def _seg(r):
    w = (r or {}).get("witness") or {}
    return w.get("segment") or w.get("use_face")


def _diff(old, cur, renamed=False):
    row = {"room_id": (cur or old)["room_id"], "object_id": (cur or old)["object_id"],
           "f1b_constraint": old and old["constraint"], "f1c_constraint": cur and cur["constraint"],
           "f1b_verdict": old and old["verdict"], "f1c_verdict": cur and cur["verdict"],
           "f1b_measured": old and old["measured"], "f1c_measured": cur and cur["measured"],
           "f1c_interface_basis": cur and cur["interface_basis"]}
    why = []
    if old is None:
        why.append("REGRA_NOVA_F1C (sem equivalente na F1B)")
    elif cur is None:
        why.append("REGRA_REMOVIDA")
    else:
        if renamed:
            why.append("METRICA_REDEFINIDA: disco de 0,60 m (citacao NBR nao conferida) -> profundidade livre na frente da "
                       "ENTRADA declarada (fonte tier D conferida)")
        so, sn = _seg(old), _seg(cur)
        if so and sn:
            moved = min(max(math.dist(so[0], sn[0]), math.dist(so[1], sn[1])),
                        max(math.dist(so[0], sn[1]), math.dist(so[1], sn[0])))
            if moved > 6.0:
                why.append(f"INTERFACE_MUDOU: semantica difere da face heuristica em ate {moved / M2IN:.2f} m")
            elif moved > 0.05:
                why.append(f"MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere {moved / M2IN * 100:.1f} cm do lado "
                           "heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha")
        if cur.get("reason_code") == "INTERFACE_OBSTRUCTED":
            why.append("INTERFACE_OBSTRUIDA: a entrada declarada da para parede/obstaculo (nada livre na frente)")
        if old.get("reference_minimum", {}).get("provenance") != cur.get("reference_minimum", {}).get("provenance"):
            why.append(f"PROVENIENCIA: {old.get('reference_minimum', {}).get('provenance')} -> "
                       f"{cur.get('reference_minimum', {}).get('provenance')}")
    row["divergent"] = bool(old is None or cur is None or old["verdict"] != cur["verdict"]
                            or (old["measured"] is not None and cur["measured"] is not None
                                and abs(old["measured"] - cur["measured"]) > 0.011))
    row["explanation"] = "; ".join(why) or "IGUAL (mesma interface, mesma medida)"
    return row


def _markdown(report: dict, comparison: list[dict] | None) -> str:
    lines = ["# FP-054 F1C — folga funcional e alcance com interfaces semânticas (REPORT_ONLY)", "",
             "> Gerado por `PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1c "
             "--compare docs/reports/fp054/f1b/functional_clearance.json`. Retrato datado: regenere, não edite. Nenhum layout foi "
             "alterado.", "",
             "Resumo: " + " · ".join(f"{k} {v}" for k, v in report["summary"].items()) + f" — {report['evaluations']} avaliações; "
             "base da interface: " + ", ".join(f"{k} {v}" for k, v in report["interface_bases"].items()), "",
             "| Cômodo | Peça | Regra | Medido (m) | Mín. ref. | Alvo | Pref. | Veredito | Base da interface | Proveniência (mín/alvo/pref) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["rows"]:
        lv = [r.get(k) or {} for k in ("reference_minimum", "project_target", "preferred")]
        lines.append(f"| {r['room_id']} | {r['object_id']} | {r['constraint']} | {'' if r['measured'] is None else r['measured']} | "
                     + " | ".join(str(x.get("value", "")) for x in lv)
                     + f" | **{r['verdict']}** | {r['interface_basis'] or ''} | {' / '.join(x.get('provenance', '') for x in lv)} |")
    if comparison is not None:
        lines += ["", "## F1B heurística × F1C semântica", "",
                  "| Cômodo | Peça | Regra F1B → F1C | F1B | F1C | Medida F1B → F1C (m) | Diverge | Explicação |",
                  "|---|---|---|---|---|---|---|---|"]
        for c in comparison:
            lines.append(f"| {c['room_id']} | {c['object_id']} | {c['f1b_constraint'] or '—'} → {c['f1c_constraint'] or '—'} | "
                         f"{c['f1b_verdict'] or '—'} | {c['f1c_verdict'] or '—'} | {c['f1b_measured']} → {c['f1c_measured']} | "
                         f"{'**sim**' if c['divergent'] else 'não'} | {c['explanation']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path)
    ap.add_argument("--compare", type=Path, help="relatorio F1B (heuristico) para comparar")
    ap.add_argument("--mode", choices=MODES, default="REPORT_ONLY")
    args = ap.parse_args(argv)
    import contextlib
    import io

    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
        ifaces = collect_interfaces(con, boxes)
    report = evaluate(con, boxes, ifaces, args.mode)
    comparison = compare(json.loads(args.compare.read_text("utf-8")), report) if args.compare else None
    if args.report:
        args.report.mkdir(parents=True, exist_ok=True)
        (args.report / "functional_clearance.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                                               encoding="utf-8", newline="\n")
        if comparison is not None:
            (args.report / "f1b_vs_f1c.json").write_text(json.dumps(comparison, indent=1, ensure_ascii=False) + "\n",
                                                         encoding="utf-8", newline="\n")
        (args.report / "functional_clearance.md").write_text(_markdown(report, comparison), encoding="utf-8", newline="\n")
    sys.stdout.write(json.dumps({k: report[k] for k in ("mode", "evaluations", "summary", "interface_bases", "registry_errors")},
                                ensure_ascii=False) + "\n")
    return 1 if report["registry_errors"] else 0          # REPORT_ONLY: so registro invalido reprova


if __name__ == "__main__":
    raise SystemExit(main())
