#!/usr/bin/env python3
"""Position-fidelity gate — MVP controlado (Felipe 2026-06-02).

Compara POSICAO/TAMANHO/HOST dos elementos JA CONHECIDOS (com provenance no
consensus) contra o que o build observou (geometry_report do SKP). NAO infere
elemento novo por IA. NAO usa visual-oracle como criterio. Determinístico.

Expected  = consensus canonico (openings, walls, soft_barriers com fonte).
Observed  = geometry_report.groups_diagnostic (bbox_m por grupo nomeado pelo id).

Falha (FAIL) para:
  - elemento esperado AUSENTE (carved no consensus, sem grupo no build);
  - soft_barrier observado EXTRA sem fonte (over-generation);
  - centro deslocado > tol;
  - largura/comprimento diferente > tol;
  - host wall errado (centro da abertura longe do wall_id declarado);
  - grade/peitoril deslocado do segmento host (offset frontal);
  - gap TERMINAL em grade que deveria fechar (endpoint solto, longe de parede).

Veredito verde = "checks codificados passaram", NAO "modelo fiel".
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from tools.gate_util import pt_seg_dist

TOL = {
    "center_m": 0.10,        # centro de abertura
    "size_m": 0.10,          # largura/comprimento
    "host_offset_m": 0.05,   # offset do host segment (grade/peitoril)
    "terminal_gap_m": 0.05,  # gap terminal (fechamento)
    "host_wall_m": 0.15,     # centro de abertura vs linha do wall_id host
}


def _has_source(b: dict) -> bool:
    return bool(b.get("barrier_type")) and b.get("geometry_origin") == "human_annotation"


def _is_grade(b: dict) -> bool:
    return _has_source(b) and (
        b.get("render_as") == "grade" or b.get("barrier_type") in ("guardrail", "railing")
    )


def _groups_by_id(report: dict) -> dict:
    """name 'DoorLeaf_Group_h_o000' -> indexa por sufixo id e por nome cheio."""
    out = {}
    for g in report.get("groups_diagnostic", []):
        out[g.get("name", "")] = g
    return out


def _bbox_center_m(g: dict):
    mn = g["bbox_m"]["min"]
    mx = g["bbox_m"]["max"]
    return ((mn[0] + mx[0]) / 2.0, (mn[1] + mx[1]) / 2.0)


def _bbox_span_m(g: dict):
    mn = g["bbox_m"]["min"]
    mx = g["bbox_m"]["max"]
    return (mx[0] - mn[0], mx[1] - mn[1])


def derive_scale(consensus: dict, groups: dict) -> float:
    """pt->m calibrado pelos PROPRIOS dados: largura observada (m) de cada porta /
    largura no consensus (pt). Robusto a qualquer PT_TO_M usado no build. Fallback:
    0.19 / wall_thickness_pts."""
    ratios = []
    for op in consensus.get("openings", []):
        oid = op.get("id")
        wpt = op.get("opening_width_pts", 0)
        if not oid or wpt <= 0:
            continue
        # SO janela/glazed: porta tem swing -> bbox inflada -> contamina a escala
        g = next((gg for n, gg in groups.items() if ("WindowGlass" in n or "GlazedBalcony" in n) and n.endswith(oid)), None)
        if not g:
            continue
        sx, sy = _bbox_span_m(g)
        wm = max(sx, sy)  # a maior dimensao do bbox ~ a largura do vao
        if wm > 0:
            ratios.append(wm / wpt)
    if ratios:
        ratios.sort()
        return ratios[len(ratios) // 2]  # mediana
    wt = float(consensus.get("wall_thickness_pts", 5.4) or 5.4)
    return 0.19 / wt


def _pt_dist_to_seg_m(px, py, ax, ay, bx, by, s) -> float:
    """distancia ponto->segmento, em metros (entradas em pts, s=pt_to_m)."""
    return pt_seg_dist(px, py, ax, ay, bx, by) * s


def compare(consensus: dict, report: dict, tol: dict = None) -> list:
    tol = tol or TOL
    groups = _groups_by_id(report)
    s = derive_scale(consensus, groups)
    walls = consensus.get("walls", [])
    walls_by_id = {w.get("id"): w for w in walls}
    findings = []

    def add(element, kind, verdict, reason, expected=None, observed=None, delta_m=None):
        findings.append({"element": element, "kind": kind, "verdict": verdict,
                         "reason": reason, "expected": expected, "observed": observed,
                         "delta_m": (round(delta_m, 3) if delta_m is not None else None)})

    # ---- aberturas carved (portas / janelas / glazed balcony) ----
    CARVED = ("interior_door", "door_arc", "door", "window", "glazed_balcony", "interior_passage")
    for op in consensus.get("openings", []):
        oid = op.get("id")
        kind = op.get("kind_v5") or op.get("kind") or ""
        if kind not in CARVED:
            continue
        g = next((gg for n, gg in groups.items()
                  if n.endswith(oid) and ("DoorLeaf" in n or "WindowGlass" in n or "GlazedBalcony" in n)), None)
        if g is None:
            if kind in ("interior_passage",):  # passagem pode nao virar grupo
                continue
            add(oid, kind, "FAIL", "expected_absent",
                expected="grupo renderizado", observed="ausente")
            continue
        is_door = kind in ("interior_door", "door_arc", "door")
        # centro: porta tem swing -> bbox-center desloca ~largura; tol maior.
        # (o host_check abaixo, consensus-interno, pega deslocamento real de porta)
        ecx, ecy = op["center"][0] * s, op["center"][1] * s
        ocx, ocy = _bbox_center_m(g)
        dc = math.hypot(ocx - ecx, ocy - ecy)
        ctol = 0.80 if is_door else tol["center_m"]
        if dc > ctol:
            add(oid, kind, "FAIL", "center_offset", expected=[round(ecx, 2), round(ecy, 2)],
                observed=[round(ocx, 2), round(ocy, 2)], delta_m=dc)
        # largura: pula porta (bbox inclui o swing)
        if not is_door:
            ew = op.get("opening_width_pts", 0) * s
            sx, sy = _bbox_span_m(g)
            ow = max(sx, sy)
            if ew > 0 and abs(ow - ew) > tol["size_m"]:
                add(oid, kind, "FAIL", "width_mismatch", expected=round(ew, 2),
                    observed=round(ow, 2), delta_m=abs(ow - ew))
        # host wall: centro deve cair na linha do wall_id declarado
        w = walls_by_id.get(op.get("wall_id"))
        if w:
            d_host = _pt_dist_to_seg_m(op["center"][0], op["center"][1],
                                       w["start"][0], w["start"][1], w["end"][0], w["end"][1], s)
            if d_host > tol["host_wall_m"]:
                add(oid, kind, "FAIL", "wrong_host_wall", expected=op.get("wall_id"),
                    observed="centro fora da linha do host", delta_m=d_host)

    # ---- soft_barriers com fonte (grade/peitoril) ----
    for i, b in enumerate(consensus.get("soft_barriers", [])):
        gname = f"SoftBarrier_Group_{i}"
        g = groups.get(gname)
        if not _has_source(b):
            if g is not None:  # observado EXTRA sem fonte = over-generation
                add(b.get("id"), "soft_barrier", "FAIL", "extra_without_source",
                    expected="skip (sem fonte)", observed=gname)
            continue
        if g is None:
            add(b.get("id"), "soft_barrier", "FAIL", "expected_absent",
                expected=gname, observed="ausente")
            continue
        bb = (b.get("human_annotation") or {}).get("bbox_pts")
        pl = b.get("polyline_pts") or []
        if bb and len(pl) >= 2:
            x0, y0, x1, y1 = bb
            horiz = b.get("orientation", "h") == "h"
            # FRONT-RUN = segmento mais longo (a corrida frontal); os demais sao
            # retornos de FECHAMENTO. alignment/coverage so no front-run (suporta L).
            fa, fb = max(((pl[i], pl[i + 1]) for i in range(len(pl) - 1)),
                         key=lambda ab: math.hypot(ab[1][0] - ab[0][0], ab[1][1] - ab[0][1]))
            if horiz:
                pos = (fa[1] + fb[1]) / 2.0
                off = min(abs(pos - y0), abs(pos - y1)) * s
                lo, hi = min(fa[0], fb[0]), max(fa[0], fb[0])
                miss = (abs(lo - x0) + abs(x1 - hi)) * s
                expect_len = abs(x1 - x0) * s
            else:
                pos = (fa[0] + fb[0]) / 2.0
                off = min(abs(pos - x0), abs(pos - x1)) * s
                lo, hi = min(fa[1], fb[1]), max(fa[1], fb[1])
                miss = (abs(lo - y0) + abs(y1 - hi)) * s
                expect_len = abs(y1 - y0) * s
            if off > tol["host_offset_m"]:
                add(b.get("id"), "grade", "FAIL", "railing_offset_from_host",
                    expected="colado na borda", observed="recuado", delta_m=off)
            if miss > tol["size_m"]:
                add(b.get("id"), "grade", "FAIL", "coverage_short",
                    expected=round(expect_len, 2), observed="encurtado", delta_m=miss)
            # fechamento: cada endpoint do polyline deve estar perto de uma parede
            for (ex, ey), side in ((pl[0], "start"), (pl[-1], "end")):
                dmin = min((_pt_dist_to_seg_m(ex, ey, w["start"][0], w["start"][1],
                                              w["end"][0], w["end"][1], s) for w in walls), default=9.9)
                if dmin > tol["terminal_gap_m"]:
                    add(b.get("id"), "grade", "FAIL", f"terminal_gap_{side}",
                        expected="fecha em parede/pilar", observed="endpoint solto", delta_m=dmin)

    return findings


def run(consensus_path: str, report_path: str, tol: dict = None) -> int:
    con = json.loads(Path(consensus_path).read_text("utf-8"))
    rep = json.loads(Path(report_path).read_text("utf-8"))
    findings = compare(con, rep, tol)
    fails = [f for f in findings if f["verdict"] == "FAIL"]
    print(f"position_fidelity_gate: {len(fails)} FAIL de {len(findings)} achados")
    for f in findings:
        d = f"{f['delta_m']}m" if f["delta_m"] is not None else "-"
        print(f"  [{f['verdict']}] {f['element']} ({f['kind']}) {f['reason']} "
              f"| exp={f['expected']} obs={f['observed']} delta={d}")
    print("OVERALL:", "RED" if fails else "GREEN (checks codificados passaram, != fiel)")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    sys.exit(run(a.consensus, a.report))
