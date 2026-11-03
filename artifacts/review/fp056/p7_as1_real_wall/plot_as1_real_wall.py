"""Planta (vista de topo) da A.S. para as variantes de `as1_real_wall_alternatives.json` (refaz so o planejador da A.S.).

Uso (da raiz do repo):  PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_as1_real_wall/plot_as1_real_wall.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import probe_as1_real_wall as p  # noqa: E402
from shapely.affinity import scale as _scale  # noqa: E402

from tools.rooms.shared.clearance import soft_barrier_masses_pt  # noqa: E402

COLORS = {"churrasqueira": "#b5523b", "coifa": "#222222", "bancada_gourmet": "#8a6a4f", "cuba_gourmet": "#9aa0a6",
          "banqueta": "#555555", "prateleira_servico": "#c9a227", "jardineira": "#5a7d4f"}


def _draw(ax, con, wall_m, variant, title):
    p.STATE["variant"] = variant
    boxes, _out = p.sl.build_boxes(con, p.RID)
    for g in getattr(wall_m, "geoms", [wall_m]):
        ax.fill(*g.exterior.xy, color="#444", lw=0)
    for _i, m, _t in soft_barrier_masses_pt(con):
        mm = _scale(m, p.PT_TO_M, p.PT_TO_M, origin=(0, 0))
        ax.fill(*mm.exterior.xy, color="#7aa6c2", lw=0)
    for o in con["openings"]:
        if o.get("wall_id") == "m004":
            cx, cy = (c * p.PT_TO_M for c in o["center"])
            hw = o["opening_width_pts"] * p.PT_TO_M / 2
            ax.plot([cx - hw, cx + hw], [cy, cy], color="#2e86de", lw=3)
            ax.text(cx, cy + 0.12, f"{o['id']} ({o.get('kind_v5')})", ha="center", fontsize=6, color="#2e86de")
    for b in boxes:
        xs = [c[0] * 0.0254 for c in b["corners"]] + [b["corners"][0][0] * 0.0254]
        ys = [c[1] * 0.0254 for c in b["corners"]] + [b["corners"][0][1] * 0.0254]
        k = b.get("kind")
        if k in ("coifa", "prateleira_servico", "varal_teto"):
            ax.plot(xs, ys, color=COLORS.get(k, "#888"), lw=1.2, ls="--")
        else:
            ax.fill(xs, ys, color=COLORS.get(k, "#bbbbbb"), alpha=0.85, lw=0.4, ec="k")
    ax.set_xlim(1.2, 7.0)
    ax.set_ylim(15.6, 10.2)   # y do PDF cresce para baixo: mesma orientacao da planta
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=7)
    ax.tick_params(labelsize=6)


def main() -> int:
    doc = json.loads((HERE / "as1_real_wall_alternatives.json").read_text("utf-8"))
    con = json.loads(p.PLANTA_74_CONSENSUS.read_text("utf-8"))
    p.STATE["wall_m"] = p._wall_m(con)
    wall_m = p.STATE["wall_m"]
    by_id = {r["variant"]["id"]: r for r in doc["rows"]}
    picks = ["atual", "p7_085"] + [x["on"] for x in doc["prateleira_to_wall"] if x["on"] != "atual"]
    picks = [i for i in picks if i in by_id][:5]
    fig, axes = plt.subplots(1, len(picks) + 1, figsize=(3.2 * (len(picks) + 1), 4.2), dpi=150)
    for ax, i in zip(axes, picks):
        r = by_id[i]
        ch = r["screen"]["pieces"].get("churrasqueira")
        gap = "omitida" if not ch else f"{ch['gap_m'] * 100:.1f} cm de {ch['nearest_wall']}"
        _draw(ax, con, wall_m, None if i == "atual" else r["variant"], f"{i}\nchurrasqueira: {gap}")
    p.STATE["variant"] = None
    # painel final: as faces reais testadas, as zonas de circulacao do spatial_model e o contorno sem fonte sb002
    ax = axes[-1]
    _draw(ax, con, wall_m, None, "faces testadas (vermelho), circulação (hachurado),\ncontorno sem fonte sb002 (pontilhado)")
    for c in doc["spatial_model_r001"]["circulation_zones_bounds_m"]:
        ax.add_patch(plt.Rectangle((c[0], c[1]), c[2] - c[0], c[3] - c[1], fill=False, hatch="///", ec="#e67e22", lw=0.6))
    for wid in p.WALL_IDS:
        w = next(x for x in con["walls"] if x["id"] == wid)
        xs, ys = [w["start"][0] * p.PT_TO_M, w["end"][0] * p.PT_TO_M], [w["start"][1] * p.PT_TO_M, w["end"][1] * p.PT_TO_M]
        ax.plot(xs, ys, color="red", lw=1.5)
        ax.text(sum(xs) / 2, sum(ys) / 2, wid, color="red", fontsize=7)
    sb = next(s for s in con["soft_barriers"] if s["id"] == "sb002")
    ax.plot([q[0] * p.PT_TO_M for q in sb["polyline_pts"]], [q[1] * p.PT_TO_M for q in sb["polyline_pts"]], ":", color="k", lw=0.8)
    fig.suptitle("A.S./terraço — gêmeo em caixas (L1), parede = cinza, barreira = azul, coifa/prateleira = tracejado",
                 fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "as1_real_wall_plan.png")
    print("ok", picks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
