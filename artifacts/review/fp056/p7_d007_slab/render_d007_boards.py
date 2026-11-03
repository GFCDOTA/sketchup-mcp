"""Pranchas para validacao HUMANA das alternativas D-007 medidas em `measure_d007.py` (#447).

Planta vista de cima com o PDF por baixo, uma coluna por alternativa (a) laje 0,4t sob a parede (atual), (b) laje sem entrar
sob a parede e (c) regiao utilizavel global. Em cada coluna:
  - laje/`cell` que o planejador recebe, preenchida por comodo (verde);
  - moveis (caixas do `collect_boxes`) por cima, contorno cinza;
  - VERMELHO: modulo que entra na parede ou sai da laje (cheques WALL/CONTAINMENT do gemeo; inclui os R1);
  - MAGENTA: area em que dois moveis se interpenetram (cheque OBJECTS do gemeo);
  - comodo VAZIO hachurado em preto e modulos perdidos listados no rodape; cozinha que aborta a geracao com a faixa "ABORTA".
Mesmas mutacoes (classe `Variant`) e mesmas funcoes da medicao; titulo com caixas, pre-voo e motivo do abort lidos de
`d007_alternatives.json`. Nada e aplicado. Gemeo em caixas = L1. Aparencia: PENDING_HUMAN.

Uso (da raiz do repo):
  PT_TO_M=0.0259 PYTHONPATH=. PYTHONIOENCODING=utf-8 python artifacts/review/fp056/p7_d007_slab/render_d007_boards.py
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
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
_spec = importlib.util.spec_from_file_location("measure_d007", HERE / "measure_d007.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
DATA = json.loads((HERE / "d007_alternatives.json").read_text("utf-8"))["variants"]
ALTS = [("a_atual", "(a) laje entra 0,4t sob a parede (ATUAL)", 0.4, False),
        ("b_under0", "(b) laje sem entrar sob a parede", 0.0, False),
        ("c_usable_global", "(c) regiao utilizavel global", 0.4, True)]
SHORT = {"r000": "SUITE 01", "r001": "A.S.", "r002": "SALA", "r003": "SUITE 02", "r004": "COZINHA", "r005": "BANHO 01",
         "r006": "BANHO 02", "r007": "LAVABO"}


def poly(b):
    cs = b.get("corners") or [[b["x0"], b["y0"]], [b["x1"], b["y0"]], [b["x1"], b["y1"]], [b["x0"], b["y1"]]]
    return Polygon([(x / PT_TO_IN, y / PT_TO_IN) for x, y in cs]).buffer(0)


def fill(ax, g, **kw):
    for p in getattr(g, "geoms", [g]):
        if not p.is_empty and p.geom_type == "Polygon":
            ax.fill(*p.exterior.xy, **kw)


def generate(con, under, usable):
    """Mesma geracao da medicao: se o gate da ancora aborta, gera de novo SO para mostrar (diagnostico)."""
    from tools.furnish_apartment import collect_boxes
    from tools.rooms.kitchen import validation as kval
    from tools.rooms.shared import spatial_model as sm
    from tools.validation import box_geometry as bx
    from tools.validation import defect_baseline as db
    rooms_all = [r["id"] for r in con["rooms"]]
    with M.Variant(under, tuple(rooms_all) if usable else ()):
        floors = sm._consensus_geometry(con)[3]
        cells = {rid: Polygon(e["outer"], holes=e.get("holes") or []) for rid, e in floors.items()}
        aborted = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                boxes, _summary = collect_boxes(con)
        except SystemExit:
            aborted = True
            orig = kval.require_kitchen_anchor
            kval.require_kitchen_anchor = lambda c, r: None
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    boxes, _summary = collect_boxes(con)
            finally:
                kval.require_kitchen_anchor = orig
        names = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
        from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
        reports = bx.validate_boxes(con, copy.deepcopy(boxes), PLANTA_74_CONSENSUS, names)
        from tools.rooms.shared.clearance import wall_mass_pt
        from tools.sketchup.shell.build_plan_shell_skp import compute_room_floors
        walls = wall_mass_pt(con)          # piso efetivo do validador = laje do shell - massa de parede (built_geometry.py:75)
        eff = {names[rid]: Polygon(e["outer"], holes=e.get("holes") or []).difference(walls)
               for rid, e in compute_room_floors(con).items()}
    base = {b["key"] for b in json.loads((ROOT / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))["defects"]}
    bad, pairs = {}, []
    for rid, rep in reports.items():
        for f in rep["findings"]:
            if f.get("check") in ("WALL", "CONTAINMENT") and f.get("module"):
                bad[(names[rid], f["module"])] = db.key(rid, f) in base
            elif f.get("check") == "OBJECTS" and f.get("modules"):
                pairs.append((names[rid], *f["modules"]))
    return {"cells": cells, "boxes": boxes, "aborted": aborted, "bad": bad, "pairs": pairs, "names": names, "eff": eff,
            "walls": walls}


def draw(ax, g, data, img, pw, ph, rooms, title, window=None):
    ax.imshow(img, cmap="gray", extent=(0, pw, 0, ph), origin="upper", interpolation="lanczos", alpha=0.5)
    by_room: dict = {}
    for b in g["boxes"]:
        by_room.setdefault(str(b.get("room")), []).append(b)
    for rid, cell in g["cells"].items():
        fill(ax, cell, facecolor="#2ca02c", alpha=0.18, edgecolor="#2ca02c", lw=0.6)
    for rid, name in g["names"].items():
        n = len(by_room.get(name, []))
        c = rooms[rid].representative_point()
        if n == 0:
            fill(ax, g["cells"].get(rid, rooms[rid]), facecolor="none", edgecolor="black", hatch="xxx", lw=1.2)
            ax.text(c.x, c.y, f"{SHORT[rid]}\nVAZIO", ha="center", va="center", fontsize=8, fontweight="bold",
                    color="white", bbox={"facecolor": "black", "alpha": 0.85, "pad": 2}, clip_on=True)
        else:
            ax.text(c.x, c.y, f"{SHORT[rid]}\n{n} caixas", ha="center", va="center", fontsize=6, color="#114411",
                    bbox={"facecolor": "white", "alpha": 0.6, "pad": 1, "lw": 0}, clip_on=True)
    mods: dict = {}
    for b in g["boxes"]:
        mods.setdefault((str(b.get("room")), str(b.get("module"))), []).append(poly(b))
    for (room, mod), ps in mods.items():
        u = unary_union(ps)
        for p in ps:
            ax.plot(*p.exterior.xy, color="#555", lw=0.25)
        if (room, mod) in g["bad"]:      # contorno vermelho = modulo reprovado; solido = o pedaco fora do piso efetivo/na parede
            for p in getattr(u, "geoms", [u]):
                ax.plot(*p.exterior.xy, color="#d62728", lw=1.4)
            out = u.difference(g["eff"][room]) if room in g["eff"] else u.intersection(g["walls"])
            fill(ax, out.buffer(0.6), facecolor="#d62728", alpha=0.95, edgecolor="#8b0000", lw=0.6)
    for room, a, b in g["pairs"]:
        if (room, a) in mods and (room, b) in mods:
            fill(ax, unary_union(mods[(room, a)]).intersection(unary_union(mods[(room, b)])), facecolor="#e377c2",
                 alpha=0.95, edgecolor="#7f007f", lw=0.8)
    if g["aborted"] and (window is None or rooms["r004"].intersects(Polygon.from_bounds(*window))):
        k = rooms["r004"]
        fill(ax, k, facecolor="none", edgecolor="#ff7f0e", lw=2.5)
        ax.text(k.centroid.x, k.bounds[1] - 4, "ABORTA AQUI\n(ancora da pia)", ha="center", va="top", fontsize=7,
                fontweight="bold", color="white", bbox={"facecolor": "#ff7f0e", "alpha": 0.95, "pad": 2}, clip_on=True)
    tw = data["twin"]
    lost = tw["missing_program_unregistered"]
    head = f"{title}\nGERACAO {'ABORTA (cozinha: ancora da pia)' if data['generation'] == 'ABORTED' else 'OK'}"
    head += f" | {data['n_boxes']} caixas{' (diagnostico)' if data['generation'] == 'ABORTED' else ''}"
    fails = [SHORT[r] for r, v in data["preflight_by_room"].items() if v["status"] in ("FAIL", "BLOCKED_MISSING_INPUT")]
    head += f"\npre-voo {data['preflight']}" + (f" ({', '.join(fails)})" if fails and window is None else "")
    head += ("\n" if window is not None else " | ") + (f"defeitos novos {len(tw['new'])} / piores {len(tw['worse'])}"
                                                       f" | R1 restantes {data['r1_baseline_persisting']}/11")
    ax.set_title(head, fontsize=8)
    if window is None:
        lost_txt = f"PERDIDO ({len(lost)}): " + ", ".join(k.replace("|PROGRAM|", ":") for k in lost) if lost else "nada perdido"
        ax.text(0.01, 0.01, _wrap(lost_txt, 70), transform=ax.transAxes, fontsize=6, va="bottom",
                bbox={"facecolor": "white", "alpha": 0.85, "pad": 2})
    x0, y0, x1, y1 = window or unary_union(list(rooms.values())).buffer(10).bounds
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def _wrap(s, n):
    out, line = [], ""
    for w in s.split(" "):
        if len(line) + len(w) > n:
            out.append(line)
            line = ""
        line += w + " "
    return "\n".join([*out, line])


LEGEND = ("verde = laje/cell que o planejador recebe | contorno cinza = moveis | contorno VERMELHO = movel reprovado (parede/fora da laje, "
          "inclui os R1), vermelho cheio = o pedaco dentro da parede (engrossado p/ ver mm)\n"
          "MAGENTA = movel dentro de outro | hachura preta = comodo VAZIO | laranja = cozinha que aborta")


def main():
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    pdf = pdfium.PdfDocument(str(plant_pdf_path("planta_74", ROOT)))[0]
    pw, ph = pdf.get_size()
    img = pdf.render(scale=4).to_pil().convert("L")
    rooms = {r["id"]: Polygon(r["polygon_pts"]).buffer(0) for r in con["rooms"]}
    gens = {key: generate(copy.deepcopy(con), under, usable) for key, _t, under, usable in ALTS}
    fig, axes = plt.subplots(1, 3, figsize=(21, 7.4))
    for ax, (key, title, _u, _us) in zip(axes, ALTS):
        draw(ax, gens[key], DATA[key], img, pw, ph, rooms, title)
    fig.suptitle("#447 D-007 - planta inteira, as 3 alternativas (gemeo L1, nada aplicado, aparencia PENDING_HUMAN)\n" + LEGEND,
                 fontsize=10)
    fig.tight_layout()
    out = HERE / "board_d007_apartment.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(out)
    fig, axes = plt.subplots(2, 3, figsize=(18, 13))
    for row, rid in enumerate(("r004", "r003")):
        win = rooms[rid].buffer(14).bounds
        for col, (key, title, _u, _us) in enumerate(ALTS):
            draw(axes[row][col], gens[key], DATA[key], img, pw, ph, rooms, f"{SHORT[rid]} - {title}", window=win)
    fig.suptitle("#447 D-007 - zoom COZINHA (linha 1) e SUITE 02 (linha 2)\n" + LEGEND, fontsize=10)
    fig.tight_layout()
    out = HERE / "board_d007_zoom_kitchen_suite02.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
