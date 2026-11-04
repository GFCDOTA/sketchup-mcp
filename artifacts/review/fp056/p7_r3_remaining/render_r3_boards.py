"""Pranchas para validacao HUMANA das alternativas R3 medidas em `measure_r3_remaining.py` (#502 / #495).

Para cada par: planta vista de cima com o PDF por baixo, uma coluna por alternativa (atual + cada alternativa), as duas pecas
do par preenchidas (azul / laranja) e a SOBREPOSICAO em planta em vermelho. Mesmas mutacoes do script de medicao (importadas),
mesmas caixas do `collect_boxes`. Nada e aplicado. Aparencia: PENDING_HUMAN.

Uso (da raiz do repo):
  PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_r3_remaining/render_r3_boards.py
"""
import copy
import importlib.util
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from core.project_sources import plant_pdf_path  # noqa: E402
from core.scale import PT_TO_IN  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
_spec = importlib.util.spec_from_file_location("measure_r3", HERE / "measure_r3_remaining.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
RESULTS = {(r["alternative"], r["target"]): r
           for r in json.loads((HERE / "r3_remaining_alternatives.json").read_text("utf-8"))["results"]}


def poly(b):
    cs = b.get("corners") or [[b["x0"], b["y0"]], [b["x1"], b["y0"]], [b["x1"], b["y1"]], [b["x0"], b["y1"]]]
    return Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in cs]).buffer(0)


def union(bs):
    return unary_union([poly(b) for b in bs]) if bs else Polygon()


def fill(ax, g, **kw):
    for p in getattr(g, "geoms", [g]):
        if not p.is_empty:
            ax.fill(*p.exterior.xy, **kw)


CASES = [
    {"title": "COZINHA — backsplash (azul) x vidro do cooktop e cuba (laranja)", "room": M.KITCHEN, "target": M.T_COOK,
     "a": M.bsp, "b": lambda bs: M.cook(bs) + M.sink(bs),
     "alts": [("atual", M.nothing), ("(a) deslocar cooktop+cuba", M.k_shift),
              ("(b) backsplash acima do vidro/borda", M.k_raise),
              ("(c) recortar vidro/cuba pela face do backsplash", M.k_notch)]},
    {"title": "BANHO 01 — tapete (laranja) x vaso (azul)", "room": M.B1, "target": M.T_RUG, "a": M.vaso, "b": M.rug,
     "alts": [("atual", M.nothing), ("(a) encolher o tapete ate a borda do vaso", M.r_cut),
              ("(b) tirar o tapete", M.r_remove)]},
    {"title": "BANHO 02 — papeleira (laranja) x bancada/gabinete (azul)", "room": M.B2, "target": M.T_PAPER,
     "a": M.counter, "b": M.paper,
     "alts": [("atual", M.nothing), ("(a) papeleira acima do tampo", M.p_raise),
              ("(b) deslocar ao longo da parede +0,-60 cm", M.p_slide(0, -60)), ("(c) tirar a papeleira", M.p_remove)]},
]


def main():
    pdf = pdfium.PdfDocument(str(plant_pdf_path("planta_74", ROOT)))[0]
    pw, ph = pdf.get_size()
    img = pdf.render(scale=4).to_pil().convert("L")
    rooms = {str(r.get("name") or r["id"]): Polygon(r["polygon_pts"]) for r in M.con["rooms"] if r.get("polygon_pts")}
    for case in CASES:
        room = rooms[case["room"]]
        x0, y0, x1, y1 = room.buffer(12).bounds
        alts = case["alts"]
        fig, axes = plt.subplots(1, len(alts), figsize=(5.2 * len(alts), 6.4))
        for ax, (name, fn) in zip(axes, alts):
            bs = copy.deepcopy(M.BOXES)
            note = fn(bs)
            ax.imshow(img, cmap="gray", extent=(0, pw, 0, ph), origin="upper", interpolation="lanczos", alpha=0.55)
            ax.plot(*room.exterior.xy, color="#444", lw=0.8)
            for b in M.sel(bs, case["room"], lambda _b: True):
                ax.plot(*poly(b).exterior.xy, color="#888", lw=0.4)
            ga, gb = union(case["a"](bs)), union(case["b"](bs))
            fill(ax, ga, facecolor="#1f77b4", alpha=0.45, edgecolor="#1f77b4", lw=0.8)
            fill(ax, gb, facecolor="#ff7f0e", alpha=0.45, edgecolor="#ff7f0e", lw=0.8)
            fill(ax, ga.intersection(gb), facecolor="#d62728", alpha=0.95, edgecolor="#d62728", lw=1.2)
            r = RESULTS.get((name, case["target"])) or next(
                (v for (n, t), v in RESULTS.items() if t == case["target"] and n.startswith(name[:4])), {})
            ok = r.get("target_resolved")
            verdict = ("RESOLVE" if ok and not r.get("worse_defects") else "NAO RESOLVE" if not ok else "RESOLVE mas PIORA outro")
            if "z0" in note:
                verdict += " (so muda a ALTURA: o vermelho em planta fica)"
            if name == "atual":
                verdict = f"ATUAL: {r.get('target_measure_m', 0) * 100:.1f} cm de interpenetracao"
            ax.set_title(f"{name}\n{verdict} | pre-voo {r.get('preflight_apartment', '?')}\n{note[:70]}", fontsize=8)
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
        fig.suptitle(case["title"] + "  — vermelho = sobreposicao em planta (gemeo L1; nada aplicado; aparencia PENDING_HUMAN)",
                     fontsize=10)
        fig.tight_layout()
        out = HERE / f"board_{case['target'].split('|')[0]}.png"
        fig.savefig(out, dpi=110)
        plt.close(fig)
        print(out)


if __name__ == "__main__":
    main()
