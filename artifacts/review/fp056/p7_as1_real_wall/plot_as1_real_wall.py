"""Prancha para validacao HUMANA das alternativas de `as1_real_wall_alternatives.json` (#442 / #488).

Planta vista de cima com o PDF por baixo (mesmas coordenadas em pontos do consensus), uma coluna por alternativa, cada peca da
A.S. rotulada e o conflito em VERMELHO com a medida escrita (folga ate a parede real ou faixa que fecha a circulacao). As caixas
sao refeitas pelo proprio planejador com as mesmas variacoes do `probe_as1_real_wall.py` (importadas). Nada e aplicado.
Aparencia: PENDING_HUMAN.

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
import pypdfium2 as pdfium  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import nearest_points  # noqa: E402

from core.project_sources import plant_pdf_path  # noqa: E402
from tools.validation import circulation_gate as cg  # noqa: E402

NAMES = {"churrasqueira": "churrasqueira", "coifa": "coifa", "prateleira_servico": "prateleira", "tanque": "tanque",
         "maq_lavar": "lavadora", "maq_secar": "secadora", "armario_servico": "armario", "varal_teto": "varal",
         "bancada_gourmet": "bancada gourmet", "cuba_gourmet": "cuba", "banqueta": "banqueta", "mesa_externa": "mesa",
         "cadeira_externa": "cadeira", "jardineira": "jardineira", "condensadora": "condensadora"}
FILL = {"churrasqueira": "#b5523b", "bancada_gourmet": "#8a6a4f", "cuba_gourmet": "#9aa0a6", "banqueta": "#555555",
        "tanque": "#d9d9d9", "maq_lavar": "#d9d9d9", "armario_servico": "#7f7f7f", "jardineira": "#5a7d4f",
        "condensadora": "#bcbcbc", "mesa_externa": "#8a6a4f"}
HIGH = {"coifa": "#111111", "prateleira_servico": "#c9a227", "varal_teto": "#7f7f7f"}   # acima do piso: so contorno
OMITTED_WATCH = ("bancada_gourmet", "cuba_gourmet", "banqueta", "mesa_externa", "maq_secar")
TO_PT = 1.0 / p.PT_TO_IN


def _poly_pt(b):
    return Polygon([(x * TO_PT, y * TO_PT) for x, y in b["corners"]]).buffer(0)


def _boxes(variant, permissive=False, shelf_to_wall=False):
    p.STATE["variant"] = variant
    orig = cg.GateSession
    if permissive:   # so para a peca entrar e o MESMO gate julgar o arranjo completo (como `circulation_if_placed`)
        class _P(orig):
            def check(self, boxes, decide_only=False):
                return {"result": "PASS", "checks": {}}
        cg.GateSession = _P
    try:
        boxes, out = p.sl.build_boxes(p_con, p.RID)
    finally:
        cg.GateSession = orig
        p.STATE["variant"] = None
    if shelf_to_wall:
        for b in boxes:
            if b["kind"] == "prateleira_servico":
                dx = -_poly_pt(b).distance(p_wall_pt) * p.PT_TO_IN
                b["corners"] = [[x + dx, y] for x, y in b["corners"]]
    return boxes, out


def _gap(ax, b, label):
    """Linha vermelha da peca ate o ponto mais proximo da massa de parede, com a medida."""
    a, w = nearest_points(_poly_pt(b), p_wall_pt)
    d = a.distance(w) * p.PT_TO_M
    if d <= p.EPS_DEPTH:
        ax.annotate(f"{label}: encostada (0,0 cm)", (a.x, a.y), (a.x + 4, a.y - 10), fontsize=6.5, color="#1a7f37",
                    arrowprops={"arrowstyle": "-", "color": "#1a7f37", "lw": 0.8})
        return
    ax.plot([a.x, w.x], [a.y, w.y], color="red", lw=2.2)
    ax.text((a.x + w.x) / 2, (a.y + w.y) / 2 - 2, f"{label}\n{d * 100:.1f} cm ate a parede", color="red", fontsize=6.5,
            ha="center", va="bottom", fontweight="bold", bbox={"fc": "white", "ec": "red", "alpha": 0.85, "pad": 1})


def _draw(ax, boxes, out, title, notes):
    ax.imshow(p_img, cmap="gray", extent=(0, p_pw, 0, p_ph), origin="upper", interpolation="lanczos", alpha=0.6)
    for g in getattr(p_wall_pt, "geoms", [p_wall_pt]):
        ax.plot(*g.exterior.xy, color="#2f6fb0", lw=0.6)
    ax.plot(*p_room.exterior.xy, color="#444", lw=0.6, ls="--")
    for b in boxes:
        k, g = b["kind"], _poly_pt(b)
        if k in HIGH:
            ax.plot(*g.exterior.xy, color=HIGH[k], lw=1.3, ls="--")
        else:
            ax.fill(*g.exterior.xy, color=FILL.get(k, "#cccccc"), alpha=0.8, ec="k", lw=0.5)
        c = g.centroid
        dy = {"coifa": 6, "prateleira_servico": -6, "varal_teto": 6}.get(k, 0)
        ax.text(c.x, c.y + dy, NAMES.get(k, k), fontsize=5.5, ha="center", va="center",
                color="white" if k in ("churrasqueira", "bancada_gourmet", "armario_servico", "banqueta") else "black")
    drop = {k for k, _w in out.get("dropped", [])}
    present = {b["kind"] for b in boxes}
    miss = [NAMES[k] for k in OMITTED_WATCH if k not in present or k in drop]
    ax.text(0.01, 0.01, "OMITIDO: " + (", ".join(miss) if miss else "nada") + ("\n" + notes if notes else ""),
            transform=ax.transAxes, fontsize=6.5, va="bottom", bbox={"fc": "white", "ec": "#888", "alpha": 0.9})
    x0, y0, x1, y1 = p_room.buffer(14).bounds
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ticks = [t for t in range(0, 30) if x0 <= t / p.PT_TO_M <= x1]
    ax.set_xticks([t / p.PT_TO_M for t in ticks], [f"{t} m" for t in ticks], fontsize=6)
    ticks = [t for t in range(0, 30) if y0 <= t / p.PT_TO_M <= y1]
    ax.set_yticks([t / p.PT_TO_M for t in ticks], [f"{t} m" for t in ticks], fontsize=6)
    ax.set_title(title, fontsize=8)


def main() -> int:
    global p_con, p_wall_pt, p_img, p_pw, p_ph, p_room
    doc = json.loads((HERE / "as1_real_wall_alternatives.json").read_text("utf-8"))
    p_con = json.loads(p.PLANTA_74_CONSENSUS.read_text("utf-8"))
    p.STATE["wall_m"] = p._wall_m(p_con)
    p_wall_pt = p.wall_mass_pt(p_con)
    page = pdfium.PdfDocument(str(plant_pdf_path("planta_74", p.ROOT)))[0]
    p_pw, p_ph = page.get_size()
    p_img = page.render(scale=4).to_pil().convert("L")
    p_room = Polygon(next(r for r in p_con["rooms"] if r["id"] == p.RID)["polygon_pts"])
    rows = {r["variant"]["id"]: r for r in doc["rows"]}
    tries = [r for r in doc["rows"] if r.get("circulation_if_placed")]
    best = next((r for r in tries if r["variant"]["widths"][0] == 0.85), tries[0])   # a maior largura que passa no _slide
    fig, axes = plt.subplots(1, 4, figsize=(22, 7.6))

    b, o = _boxes(None)
    _draw(axes[0], b, o, "ATUAL (churrasqueira 1,00 m na 'alvenaria cega' do planejador)\npre-voo PASS | 390 caixas", "")
    for x in b:
        if x["kind"] in ("churrasqueira", "prateleira_servico"):
            _gap(axes[0], x, "churrasqueira + coifa" if x["kind"] == "churrasqueira" else "prateleira")

    r = rows["p7_085"]
    b, o = _boxes(r["variant"])
    coifa = r["gates"]["support_r001"]["Coifa"]
    _draw(axes[1], b, o, f"0,85 m do p7 (mesma constante)\npre-voo PASS | {r['gates']['boxes_total']} caixas | "
          f"gap da coifa PIORA 75,33 -> {coifa * 100:.2f} cm", "apoio da coifa pior que o baseline KNOWN_MODULES")
    for x in b:
        if x["kind"] in ("churrasqueira", "prateleira_servico"):
            _gap(axes[1], x, "churrasqueira + coifa" if x["kind"] == "churrasqueira" else "prateleira")

    b, o = _boxes(best["variant"], permissive=True)
    ci = best["circulation_if_placed"]
    sec = next(q for q in ci["portais"] if q["portal_role"] == "SECONDARY")
    _draw(axes[2], b, o, f"melhor tentativa em m013: {best['variant']['widths'][0]:.2f} m, centro y = "
          f"{best['variant']['along']:.2f} m\ncirculation_gate {ci['result']}: {ci['reason_code']} "
          f"(varanda {sec['w_empty_m']:.1f} -> {sec['w_furnished_m']:.1f} m)",
          "o planejador DESCARTA esta posicao (mostrada so para ver o conflito)")
    ch = next(x for x in b if x["kind"] == "churrasqueira")
    tq = next(x for x in b if x["kind"] == "tanque")
    a, t = nearest_points(_poly_pt(ch), _poly_pt(tq))
    axes[2].fill(*_poly_pt(ch).exterior.xy, color="none", ec="red", lw=2)
    axes[2].plot([a.x, t.x], [a.y, t.y], color="red", lw=2.5)
    axes[2].text((a.x + t.x) / 2, (a.y + t.y) / 2 + 9, f"passagem\n{a.distance(t) * p.PT_TO_M * 100:.1f} cm\n(alvo 80 cm)",
                 color="red", fontsize=6.5, ha="center", fontweight="bold", bbox={"fc": "white", "ec": "red", "pad": 1})
    for c in doc["spatial_model_r001"]["circulation_zones_bounds_m"]:
        q = [v / p.PT_TO_M for v in c]
        axes[2].add_patch(plt.Rectangle((q[0], q[1]), q[2] - q[0], q[3] - q[1], fill=False, hatch="///", ec="#e67e22", lw=0.6))
    _gap(axes[2], ch, "churrasqueira + coifa")

    pr = doc["prateleira_to_wall"][0]
    b, o = _boxes(None, shelf_to_wall=True)
    _draw(axes[3], b, o, f"prateleira corrigida na parede oeste (m012)\npre-voo {pr['preflight']} | gemeo novo/pior "
          f"{len(pr['twin_new'])}/{len(pr['twin_worse'])} | {pr['boxes_total']} caixas", "churrasqueira igual ao atual")
    for x in b:
        if x["kind"] in ("churrasqueira", "prateleira_servico"):
            _gap(axes[3], x, "churrasqueira + coifa" if x["kind"] == "churrasqueira" else "prateleira")

    legend = [Line2D([], [], color="red", lw=2.2, label="folga ate a parede real / passagem que fecha (medida escrita)"),
              Line2D([], [], color="#1a7f37", lw=1, label="encostada na parede real (<= 0,5 mm, EPS_DEPTH)"),
              Line2D([], [], color="#2f6fb0", lw=0.8, label="massa de parede do consensus (wall_mass_pt)"),
              Line2D([], [], color="#111", lw=1.3, ls="--", label="pecas altas: coifa, prateleira (amarelo), varal"),
              Patch(fc="none", ec="#e67e22", hatch="///", label="zona de circulacao (giro de porta / frente da varanda)"),
              Line2D([], [], color="#444", lw=0.6, ls="--", label="poligono do comodo r001")]
    fig.legend(handles=legend, loc="lower center", ncol=6, fontsize=7, frameon=False)
    fig.suptitle("A.S. | TERRACO SOCIAL — #442 / #488: churrasqueira, coifa e prateleira contra parede REAL (PDF por baixo; "
                 "gemeo em caixas L1; nada aplicado; aparencia PENDING_HUMAN)", fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(HERE / "as1_real_wall_plan.png", dpi=110)
    print("ok", best["variant"]["id"])
    return 0


p_con = p_wall_pt = p_img = p_room = None
p_pw = p_ph = 0.0

if __name__ == "__main__":
    sys.exit(main())
