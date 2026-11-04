"""#446 / FP-056 R6 — pranchas para VALIDAR OLHANDO o arco de giro da porta do box do BANHO 01 (abertura 0,70 m).

Desenha, sobre o PDF da planta, o BANHO 01 visto de cima para dois candidatos do solver (o MELHOR da ordem e o ORIGINAL):
box, vaso, bancada, porta do comodo com o giro, tapete e toalheiro, e a folha da porta do box aberta nos 4 casos medidos
(modelo A = folha declarada de 0,70 m; modelo B = vao usavel de 0,6165 m; dobradica do lado da parede e do lado do vidro fixo),
com a area varrida pela folha e a INTERSECAO em vermelho. O titulo de cada quadro traz o angulo maximo de abertura.

Nao refaz o solver nem a medicao: le `runs/fp056_r6_box_swing/box_swing_r005_opening070.json` (gerado por
`measure_box_swing.py`; rode com `--reuse-solve` se ja houver o cache) e reconstroi a geometria com as MESMAS funcoes
(`apply_candidate`, `evaluate_layout`, `door_swings_pt`/`door_sweeps_pt`, `_synthetic_door` do script de medicao).
Nada e aplicado (o monkeypatch do PR 559 e desfeito no fim).

Uso (da raiz do repo):
  PT_TO_M=0.0259 PYTHONPATH=. PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
      artifacts/review/fp056/p7_446_box_swing/render_box_swing.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MEASURE_JSON = ROOT / "runs" / "fp056_r6_box_swing" / "box_swing_r005_opening070.json"
CANDIDATES = (("r005:Vaso:-0.16", "MELHOR proposta do solver (Vaso deslizado -0,16 m)", "box_swing_r005_best.png"),
              ("ORIGINAL", "layout ORIGINAL do builder (nada se move)", "box_swing_r005_original.png"))
LEAVES = (("A_declarada:lado_parede", "A: folha 0,70 m (declarada) - dobradica do lado da PAREDE"),
          ("A_declarada:lado_vidro_fixo", "A: folha 0,70 m (declarada) - dobradica do lado do VIDRO FIXO"),
          ("B_vao_usavel:lado_parede", "B: folha 0,6165 m (vao livre real) - dobradica do lado da PAREDE"),
          ("B_vao_usavel:lado_vidro_fixo", "B: folha 0,6165 m (vao livre real) - dobradica do lado do VIDRO FIXO"))
BLOCKER_PT = {"kb_tapete": "tapete", "kb_toalheiro": "toalheiro", "kb_parede_pedra": "revestimento de pedra",
              "PAREDE": "parede"}


def _measure_module():
    spec = importlib.util.spec_from_file_location("measure_box_swing", HERE / "measure_box_swing.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _blocker(name):
    if not name:
        return "nada"
    for k, v in BLOCKER_PT.items():
        if k in name:
            return v
    return name.split("|")[-1].split("#")[0]


def main() -> int:
    if os.environ.get("PT_TO_M") != "0.0259":
        print("PT_TO_M=0.0259 e obrigatorio (escala da planta_74)", file=sys.stderr)
        return 2
    if not MEASURE_JSON.exists():
        print(f"falta {MEASURE_JSON}: rode measure_box_swing.py (com --reuse-solve se houver cache)", file=sys.stderr)
        return 2
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pypdfium2 as pdfium
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from shapely.ops import unary_union

    import tools.rooms.bathroom.layout as bl
    from core.project_sources import plant_pdf_path
    from core.scale import PT_TO_IN, PT_TO_M
    from tools.furnish_apartment import collect_boxes
    from tools.room_type import classify_rooms
    from tools.rooms.shared.clearance import (
        box_footprint_pt,
        door_sweeps_pt,
        door_swings_pt,
        wall_mass_pt,
    )
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.rooms.shared.spatial_solver import solver as sv
    from tools.rooms.shared.spatial_solver.candidates import apply_candidate, enumerate_candidates
    from tools.rooms.shared.spatial_solver.engine import evaluate_layout
    from tools.rooms.shared.spatial_solver.problem import build_problem, room_policy
    from tools.spatial_model import build_spatial_model
    from tools.validation.functional_clearance import collect_interfaces

    ms = _measure_module()
    data = json.loads(MEASURE_JSON.read_text("utf-8"))
    per_cand = {c["candidate_id"]: c for c in data["per_candidate"]}
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    rid = ms.ROOM_ID

    pdf = pdfium.PdfDocument(str(plant_pdf_path("planta_74", ROOT)))
    page = pdf[0]
    W, H = page.get_size()
    scale = 6.0
    pdf_img = page.render(scale=scale).to_pil().convert("L")

    orig = bl._box_front

    def variant(opening_m):                     # mesmo monkeypatch de probe_door_opening.py:12-17 (PR 559)
        def f(b, door_c):
            horiz, a0, a1, front, back, sin, fixw, leaf_lo = orig(b, door_c)
            return horiz, a0, a1, front, back, sin, bl.M(opening_m + 0.05), leaf_lo
        return f

    outputs = []
    bl._box_front = variant(ms.OPENING_M)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            boxes, _ = collect_boxes(con)
            ifaces = collect_interfaces(con, boxes)
        r = {x["id"]: x for x in classify_rooms(con)}[rid]
        room_type, room_name = r["room_type"], str(r["name"])
        problem = build_problem(con, boxes, rid, room_type, ifaces, policy=room_policy(room_type))
        cands = {c.candidate_id: c for c in enumerate_candidates(problem)}
        local = sv.neighborhood(con, boxes, rid)
        cell = build_spatial_model(con, rid)["_geom"]["cell"]
        walls = wall_mass_pt(con)
        room_swings = {k: v for k, v in door_swings_pt(con).items() if v.intersects(cell)}
        x0, y0, x1, y1 = cell.buffer(14).bounds
        for k in room_swings:
            bx = room_swings[k].bounds
            x0, y0, x1, y1 = min(x0, bx[0] - 4), min(y0, bx[1] - 4), max(x1, bx[2] + 4), max(y1, bx[3] + 4)
        crop = pdf_img.crop((int(x0 * scale), int((H - y1) * scale), int(x1 * scale), int((H - y0) * scale)))

        for cid, cdesc, fname in CANDIDATES:
            rec = per_cand[cid]
            b2, i2 = apply_candidate(problem, local, ifaces, cands[cid], room_name)
            ev = evaluate_layout(con, b2, rid, room_type, i2, room_name)
            row = next(x for x in ev.rows if x["object_id"] == "Box" and x["constraint"] == "shower.entry_width")
            box_if = i2[(rid, "Box")]
            normal = box_if.normal
            segs = {"A_declarada": [(x / PT_TO_IN, y / PT_TO_IN) for x, y in box_if.segment_in],
                    "B_vao_usavel": [(x / PT_TO_IN, y / PT_TO_IN) for x, y in row["witness"]["usable_segment"]]}

            def fps(pred, _b2=b2):
                return [box_footprint_pt(b, PT_TO_IN) for b in _b2 if b.get("room") == room_name and b.get("corners")
                        and pred(b)]
            box_fp = unary_union(fps(lambda b: b.get("module") == "Box" and b.get("kind") in ("kb_piso_box", "box_vidro")))
            vaso = unary_union(fps(lambda b: b.get("module") == "Vaso"))
            banc = unary_union(fps(lambda b: b.get("module") == "Bancada" and b.get("kind") in ("gabinete", "bancada_banho")))
            tapete = unary_union(fps(lambda b: b.get("kind") == "kb_tapete"))
            toalh = unary_union(fps(lambda b: b.get("kind") == "kb_toalheiro"))
            pedra = unary_union(fps(lambda b: b.get("kind") == "kb_parede_pedra"))
            blockers = {"tapete": tapete, "toalheiro": toalh, "revestimento": pedra, "parede": walls, "vaso": vaso,
                        "bancada": banc}

            fig, axes = plt.subplots(2, 2, figsize=(15, 17), dpi=110)
            fig.suptitle(f"BANHO 01 - porta de ABRIR no box (abertura 0,70 m, PR 559) - {cdesc}\n"
                         "Vista de cima sobre o PDF. Amarelo = area que a folha do box varre ao abrir 90 graus para fora; "
                         "VERMELHO = onde a folha bate.", fontsize=13, fontweight="bold")
            for ax, (lk, ltitle) in zip(axes.flat, LEAVES):
                model, lab = lk.split(":")
                seg = segs[model]
                k = 0 if ms_end(seg, cell) == lab else 1
                syn = ms._synthetic_door(seg, normal, k, "box_leaf")
                sweep = door_sweeps_pt(syn, leaf_thickness_m=ms.GLASS_T_M)["box_leaf"]
                leaf_rec = rec["leaves"][lk]
                angs = leaf_rec["door_open_angle_by_obstacle_set"]
                a_all = angs["todas_as_pecas+parede"]
                a_noenx = angs["sem_enxoval(tapete,toalheiro,...)"]
                ax.imshow(crop, cmap="gray", extent=(x0, x1, y0, y1), origin="upper", alpha=0.55, zorder=0)

                def draw(g, fc, ec, lw=1.2, z=2, alpha=0.9, hatch=None, _ax=ax):
                    for p in getattr(g, "geoms", [g]):
                        if p.is_empty or p.geom_type != "Polygon":
                            continue
                        xs, ys = p.exterior.xy
                        _ax.fill(xs, ys, facecolor=fc, edgecolor=ec, linewidth=lw, alpha=alpha, zorder=z, hatch=hatch)
                draw(walls.intersection(cell.buffer(20)), "#8a8a8a", "#555555", z=1, alpha=0.55)
                xs, ys = cell.exterior.xy
                ax.plot(xs, ys, color="#333333", lw=0.8, ls=":", zorder=2)
                draw(box_fp, "#bfe3f2", "#2b7fa8", z=2, alpha=0.75)
                draw(banc, "#d9c3a0", "#7a5a2e", z=3)
                draw(vaso, "#f4f4f4", "#222222", z=3)
                draw(pedra, "#6b5f55", "#3b332c", z=3)
                draw(tapete, "#f2a65a", "#b35c00", z=3, alpha=0.8)
                draw(toalh, "#9b59b6", "#5b2c6f", lw=2.0, z=6)
                for d, sw in room_swings.items():
                    draw(sw, "#c8f0c8", "#2e8b57", z=2, alpha=0.5, hatch="//")
                    ax.text(*sw.centroid.coords[0], f"giro da porta\ndo comodo ({d})", ha="center", va="center",
                            fontsize=8, color="#1f5f3a", zorder=7)
                draw(sweep.buffer(0.05).buffer(-0.05),"#fff3a0", "none", lw=0, z=4, alpha=0.75)
                bad = []
                for name, g in blockers.items():
                    inter = sweep.intersection(g)
                    if not inter.is_empty and inter.area * PT_TO_M ** 2 * 1e4 >= 0.05:
                        draw(inter.buffer(0.05).buffer(-0.05),"#e00000", "none", lw=0, z=8, alpha=0.95)
                        bad.append(f"{name} {inter.area * PT_TO_M ** 2 * 1e4:.1f} cm2")
                # folha: fechada (tracejada), aberta ate onde consegue (grossa) e o arco de 90 graus
                hinge = seg[k]
                other = seg[1 - k]
                L = math.dist(hinge, other)
                ux, uy = (other[0] - hinge[0]) / L, (other[1] - hinge[1]) / L
                cs = 1 if (ux * normal[1] - uy * normal[0]) > 0 else -1
                nx, ny = -uy * cs, ux * cs

                def tip(deg, _h=hinge, _L=L, _u=(ux, uy), _n=(nx, ny)):
                    t = math.radians(deg)
                    return (_h[0] + _L * (_u[0] * math.cos(t) + _n[0] * math.sin(t)),
                            _h[1] + _L * (_u[1] * math.cos(t) + _n[1] * math.sin(t)))
                arc = [tip(d) for d in range(0, 91)]
                ax.plot([p[0] for p in arc], [p[1] for p in arc], color="#c9a400", lw=1.2, ls="--", zorder=5)
                ax.plot([hinge[0], other[0]], [hinge[1], other[1]], color="#1565c0", lw=2.2, ls="--", zorder=7)
                tmax = tip(a_all["max_open_deg"])
                ax.plot([hinge[0], tmax[0]], [hinge[1], tmax[1]], color="#0d47a1", lw=4.0, zorder=9,
                        solid_capstyle="butt")
                ax.plot(*hinge, marker="o", ms=9, mfc="#0d47a1", mec="white", zorder=10)
                ax.annotate("dobradica", hinge, textcoords="offset points", xytext=(-10, -16), fontsize=8,
                            color="#0d47a1", zorder=10, ha="center")
                ok90 = a_all["ok"]
                head = ("abre 90 graus" if ok90 else
                        f"ABRE SO {a_all['max_open_deg']:.0f} graus (bate em: {_blocker(a_all['blocked_by'])})")
                extra = ("" if ok90 else
                         f"\nsem tapete/toalheiro: {'abre 90 graus' if a_noenx['ok'] else 'abre %.0f graus (bate em: %s)' % (a_noenx['max_open_deg'], _blocker(a_noenx['blocked_by']))}")
                ax.set_title(f"{ltitle}\n{head}{extra}", fontsize=10.5, color="#b00000" if not ok90 else "#1b5e20")
                gaps = leaf_rec["min_gap_to_cm"]
                ax.text(0.01, 0.01, (f"folha {leaf_rec['leaf_len_m']:.3f} m; folga ao vaso {gaps.get('Vaso', '?')} cm, "
                                     f"a bancada {gaps.get('Bancada', '?')} cm\nbatidas: " + ("; ".join(bad) or "nenhuma")),
                        transform=ax.transAxes, fontsize=8.5, va="bottom", zorder=11,
                        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#999999"})
                ax.set_xlim(x0, x1)
                ax.set_ylim(y0, y1)
                ax.set_aspect("equal")
                ax.set_xticks([])
                ax.set_yticks([])
            handles = [Patch(fc="#bfe3f2", ec="#2b7fa8", label="box (chuveiro)"),
                       Patch(fc="#f4f4f4", ec="#222222", label="vaso (posicao deste candidato)"),
                       Patch(fc="#d9c3a0", ec="#7a5a2e", label="bancada / gabinete"),
                       Patch(fc="#f2a65a", ec="#b35c00", label="tapete (enxoval do builder)"),
                       Patch(fc="#9b59b6", ec="#5b2c6f", label="toalheiro na parede (h 1,10 m)"),
                       Patch(fc="#6b5f55", ec="#3b332c", label="revestimento de pedra (2 cm)"),
                       Patch(fc="#8a8a8a", ec="#555555", label="parede"),
                       Patch(fc="#c8f0c8", ec="#2e8b57", hatch="//", label="giro da porta do comodo"),
                       Patch(fc="#fff3a0", ec="#c9a400", label="area varrida pela folha do box (0 a 90 graus)"),
                       Patch(fc="#e00000", ec="#8b0000", label="INTERSECAO: a folha bate aqui"),
                       Line2D([], [], color="#1565c0", lw=2.2, ls="--", label="folha fechada"),
                       Line2D([], [], color="#0d47a1", lw=4.0, label="folha no angulo maximo que consegue abrir")]
            fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=10, frameon=True)
            fig.text(0.5, 0.075, "Medicao L1 (sem SketchUp), nada aplicado. Dados: measure_box_swing.py / "
                     "box_swing_r005_opening070_summary.json. Veredito visual: PENDING_HUMAN.",
                     ha="center", fontsize=9, color="#444444")
            fig.tight_layout(rect=(0, 0.1, 1, 0.95))
            out = HERE / fname
            fig.savefig(out)
            plt.close(fig)
            outputs.append(out)
    finally:
        bl._box_front = orig
    for o in outputs:
        print(f"-> {o}")
    return 0


def ms_end(seg, cell) -> str:
    """Mesmo criterio do script de medicao: ponta 0 e 'lado_parede' se estiver mais perto da borda do comodo."""
    from shapely.geometry import Point
    d = [Point(p).distance(cell.exterior) for p in seg]
    return "lado_parede" if d[0] <= d[1] else "lado_vidro_fixo"


if __name__ == "__main__":
    sys.exit(main())
