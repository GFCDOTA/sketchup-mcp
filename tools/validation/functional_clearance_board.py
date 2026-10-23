"""functional_clearance_board.py — evidencia visual da F1C para revisao externa (FP-054). So DESENHA o que o relatorio mediu.

    PT_TO_M=0.0259 python -m tools.validation.functional_clearance_board docs/reports/fp054/f1c/functional_clearance.json \
        artifacts/review/fp054/f1c

Por comodo (cozinha, Banho 01, Banho 02, lavabo) um overlay com: pecas (cor por tipo), interface (face de uso / face de
trabalho / entrada do box — linha grossa) e o trecho usavel, zona de uso, portal(is), regiao alcancavel na largura medida,
gargalo (ponto + segmento + largura), limiar (min/alvo/pref) e veredito de cada regra. A board junta os 4 + a legenda.
Coordenadas do plano (polegadas), y para cima como no SketchUp. Nenhuma geometria e recalculada aqui alem do contexto do comodo.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MP  # noqa: E402

ROOMS = (("r004", "kitchen_overlay.png", "COZINHA (r004)"), ("r005", "bathroom_01_overlay.png", "BANHO 01 (r005)"),
         ("r006", "bathroom_02_overlay.png", "BANHO 02 (r006)"), ("r007", "lavatory_overlay.png", "LAVABO (r007)"))
COLOR = {"toilet": "#c62828", "lavatory": "#1565c0", "shower": "#2e7d32", "kitchen_counter": "#ef6c00"}
MODULE_TYPE = {"Vaso": "toilet", "Bancada": "lavatory", "Box": "shower", "countertop": "kitchen_counter"}
VCOLOR = {"INVALID": "#b71c1c", "VALID_BELOW_TARGET": "#e65100", "VALID": "#2e7d32", "PREFERRED": "#1b5e20",
          "BLOCKED_MISSING_INPUT": "#6a1b9a", "NOT_APPLICABLE": "#757575"}
M2IN = 39.3700787402


def _ctx(con, boxes, rid):
    from tools.validation import circulation_gate as cg
    from tools.validation.functional_clearance import _room_context
    cell, portals, _dropped, rb = _room_context(con, boxes, rid)
    pieces = [(b, cg._footprint(b)) for b in rb if b.get("module") in MODULE_TYPE and (b.get("z0_in") or 0) / M2IN < 1.2]
    return cell, portals, [(b, g) for b, g in cg._blockers(rb)] + pieces    # pecas registradas sempre aparecem


def _draw(ax, rid, title, rows, ctx, legend=True):
    cell, portals, blockers = ctx
    ax.add_patch(MP(list(cell.exterior.coords), closed=True, fc="#fbf8f1", ec="#212121", lw=2.2, zorder=0))
    for b, g in blockers:
        t = MODULE_TYPE.get(b.get("module"))
        for gg in getattr(g, "geoms", [g]):
            ax.add_patch(MP(list(gg.exterior.coords), fc=COLOR.get(t, "#9e9e9e"), alpha=0.55 if t else 0.35, ec="#424242",
                            lw=0.3, zorder=2))
    room_rows = [r for r in rows if r["room_id"] == rid]
    texts = []
    for r in room_rows:
        w = r.get("witness") or {}
        t = r["object_type"]
        if r["constraint"].endswith("reach_path"):
            for poly in w.get("reachable_region") or []:
                ax.add_patch(MP(poly, fc="#4fc3f7", alpha=0.18, ec="#0288d1", lw=0.8, ls=":", zorder=1))
            if w.get("use_zone"):
                ax.add_patch(MP(w["use_zone"], fc="none", ec=COLOR[t], lw=1.6, ls="--", hatch="//", zorder=4))
            g = w.get("bottleneck")
            if g:
                (x0, y0), (x1, y1) = g["segment"]
                ax.plot([x0, x1], [y0, y1], color="#d50000", lw=2.5, zorder=6)
                ax.plot(*g["point"], marker="X", color="#d50000", ms=13, mec="white", zorder=7)
                lbl = (f"gargalo {g['width_m']:.2f} m" + (" (na entrada)" if g.get("at") == "portal" else "")
                       if g.get("width_m") else "desconectado")
                ax.annotate(lbl, g["point"], textcoords="offset points", xytext=(6, -12), fontsize=8, color="#d50000",
                            weight="bold", zorder=8)
        if w.get("free_shape"):
            ax.add_patch(MP(w["free_shape"], fc=COLOR[t], alpha=0.10, ec=COLOR[t], lw=1.0, zorder=3))
        if w.get("segment"):
            (x0, y0), (x1, y1) = w["segment"]
            ax.plot([x0, x1], [y0, y1], color="#000000", lw=5, solid_capstyle="butt", zorder=5)
            ax.plot([x0, x1], [y0, y1], color=COLOR[t], lw=3, solid_capstyle="butt", zorder=5)
            if w.get("usable_segment"):
                (u0, v0), (u1, v1) = w["usable_segment"]
                ax.plot([u0, u1], [v0, v1], color="#ffd600", lw=1.6, zorder=6)
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            n = w.get("normal") or [0, 0]
            ax.annotate("", xy=(mx + n[0] * 8, my + n[1] * 8), xytext=(mx, my),
                        arrowprops={"arrowstyle": "->", "color": COLOR[t], "lw": 1.6}, zorder=6)
        thr = [r.get(k, {}).get("value") for k in ("reference_minimum", "project_target", "preferred")]
        meas = "—" if r["measured"] is None else f"{r['measured']:.2f}"
        texts.append((r["verdict"], f"{r['object_id']:<10} {r['constraint'].split('.', 1)[1]:<22} {meas:>5} m  "
                                    f"[{thr[0]}/{thr[1]}/{thr[2]}]  {r['verdict']}"
                                    + (f"  ({r['interface_basis']})" if r.get("interface_basis") else "")))
    for p in portals:
        ax.plot(p.x, p.y, marker="*", color="#ffab00", mec="#212121", ms=20, zorder=9)
    x0, y0, x1, y1 = cell.bounds
    pad = 6
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=13, weight="bold")
    return texts


def _legend_rows(ax, texts):
    ax.axis("off")
    for i, (verdict, line) in enumerate(texts):
        ax.text(0.0, 1 - i * 0.075, line, family="monospace", fontsize=8.5, color=VCOLOR[verdict], va="top", transform=ax.transAxes)


def _key(ax):
    ax.axis("off")
    items = [("linha grossa colorida", "interface: face de uso / face de trabalho / ENTRADA do box"),
             ("linha amarela", "trecho usavel da interface (o que da para o espaco livre)"),
             ("seta", "normal da interface (para onde a pessoa fica)"),
             ("retangulo tracejado hachurado", "zona de uso (0,30 m junto a interface) — destino do alcance"),
             ("area azul pontilhada", "regiao alcancavel a partir do portal, na largura medida"),
             ("X vermelho + segmento", "gargalo: onde a passagem se rompe com +2 cm"),
             ("estrela", "portal do comodo"),
             ("area translucida colorida", "folga livre medida na frente da interface"),
             ("[a/b/c]", "minimo de referencia / alvo do projeto (PENDING_FELIPE) / preferido, em m")]
    for i, (k, v) in enumerate(items):
        ax.text(0.0, 1 - i * 0.1, f"{k}: {v}", fontsize=9, va="top", transform=ax.transAxes)


def build(report_path: Path, out_dir: Path) -> list[Path]:
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    report = json.loads(report_path.read_text("utf-8"))
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, panels = [], []
    for rid, fname, title in ROOMS:
        ctx = _ctx(con, boxes, rid)
        fig = plt.figure(figsize=(13, 9))
        ax = fig.add_axes([0.02, 0.30, 0.96, 0.64])
        texts = _draw(ax, rid, title, report["rows"], ctx)
        _legend_rows(fig.add_axes([0.03, 0.02, 0.94, 0.25]), texts)
        fig.savefig(out_dir / fname, dpi=110)
        plt.close(fig)
        written.append(out_dir / fname)
        panels.append((rid, title, ctx, texts))
    fig = plt.figure(figsize=(26, 19))
    fig.suptitle("FP-054 F1C — folga funcional e alcance com interfaces SEMÂNTICAS (REPORT_ONLY, planta_74) — "
                 + " · ".join(f"{k} {v}" for k, v in report["summary"].items()), fontsize=15, weight="bold")
    pos = [[0.01, 0.53, 0.32, 0.42], [0.34, 0.53, 0.32, 0.42], [0.01, 0.06, 0.32, 0.42], [0.34, 0.06, 0.32, 0.42]]
    for (rid, title, ctx, _t), p in zip(panels, pos):
        _draw(fig.add_axes(p), rid, title, report["rows"], ctx)
    lax = fig.add_axes([0.68, 0.30, 0.31, 0.64])
    all_texts = [t for *_x, texts in panels for t in texts]
    lax.axis("off")
    for i, (verdict, line) in enumerate(all_texts):
        lax.text(0.0, 1 - i * 0.042, line, family="monospace", fontsize=8, color=VCOLOR[verdict], va="top",
                 transform=lax.transAxes)
    _key(fig.add_axes([0.68, 0.04, 0.31, 0.24]))
    fig.savefig(out_dir / "functional_review_board.png", dpi=90)
    plt.close(fig)
    written.append(out_dir / "functional_review_board.png")
    return written


if __name__ == "__main__":
    for p in build(Path(sys.argv[1]), Path(sys.argv[2])):
        print(p)
