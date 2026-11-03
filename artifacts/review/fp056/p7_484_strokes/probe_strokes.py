"""FP-056 #484: ID, medida e recorte do PDF de cada traco sem fonte sb000-sb007 da planta_74 (so leitura).

Reproducao (cwd = raiz do repo; escreve so na pasta de saida, por padrao `runs/fp056/p7_484_strokes`):
    PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_484_strokes/probe_strokes.py [pasta_saida]

O que faz, sem escrever em fixtures/, no PDF ou em .skp (SHA-256 do consensus e do PDF conferidos antes e depois):
- le `soft_barriers` sb000-sb007 do consensus (os sem `barrier_type`) e casa cada polyline com o objeto vetorial do PDF que a
  originou (pypdfium2, do uv.lock): modo de desenho, cor de traco/preenchimento, espessura;
- mede cada traco (bbox em pt e m, comprimento, faixa de 1 espessura de parede que o shell subtrai);
- recalcula a laje/`cell` (`compute_room_floors`, o mesmo do shell e dos planejadores) com e sem os tracos, separa a area
  perdida em pecas com ID (`P01`...) e diz quais tracos tocam cada peca, em que comodo, e que paredes/aberturas estao coladas;
- inventaria o que o PDF desenha DENTRO de cada peca (segmentos diagonais = simbolo "X", hachura, texto);
- desenha `strokes_board.png` (8 recortes do PDF com o traco por cima) e `strokes_overview.png` (planta inteira, orientacao
  do PDF) e grava `strokes.json`.
A classificacao proposta em `strokes.json` e do agente (`proposed_by: agent`), nao e fato; "desconhecido" quando nao da.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "runs" / "fp056" / "p7_484_strokes"
CONSENSUS = ROOT / "fixtures" / "planta_74" / "consensus_with_human_walls_and_soft_barriers.json"
from core.scale import PT_TO_M, assert_pt_to_m_for_source  # noqa: E402  (fonte unica de escala)

UNSOURCED = [f"sb00{i}" for i in range(8)]
RENDER_SCALE = 6.0
# pares de tracos: os dois contornos vetoriais do mesmo bloco do PDF (um so de parede, outro com os anexos)
GROUPS = [("sb000", "sb001"), ("sb002", "sb003"), ("sb004",), ("sb005", "sb006"), ("sb007",)]
# Classificacao PROPOSTA pelo agente, depois de ver `contours_zoom.png`/`strokes_board.png`. NAO e fato: o PDF nao escreve
# "shaft" nem "prumada"; a legenda so nomeia a hachura diagonal (DRYWALL OU PLACA CIMENTICIA) e os cinzas (ALVENARIA
# ESTRUTURAL = 78, PAREDE NAO ESTRUTURAL = 164). Retangulo com X dentro de fechamento hachurado e a convencao usual de
# shaft/prumada em planta de vendas -- e uma leitura, nao uma legenda.
_SHAFT = ("retangulo fechado por hachura diagonal (padrao da legenda DRYWALL OU PLACA CIMENTICIA) com X interno, colado na "
          "face da parede")
PROPOSALS: dict[str, dict] = {
    "C01": {"class": "shaft/prumada", "confidence": "media", "reason": _SHAFT + "; area molhada (Lavabo, atras do vaso)"},
    "C02": {"class": "shaft/prumada", "confidence": "media", "reason": _SHAFT + "; area molhada (Banho 01, junto ao box)"},
    "C03": {"class": "shaft/prumada", "confidence": "media", "reason": _SHAFT + "; A.S., ao lado do simbolo de maquina/tanque"},
    "C04": {"class": "shaft/prumada", "confidence": "media",
            "reason": _SHAFT + "; A.S./terraco, ao lado do simbolo da churrasqueira (duto de coifa/churrasqueira e "
                               "plausivel, nao escrito no PDF)"},
    "C05": {"class": "shaft/prumada", "confidence": "media",
            "reason": "0,72 x 0,72 m com X interno; moldura com preenchimento cinza 164 = PAREDE NAO ESTRUTURAL na "
                      "legenda; canto do terraco social"},
    "C06": {"class": "desconhecido", "confidence": "baixa",
            "reason": "0,28 x 0,22 m, mesmo grafismo (hachura + X), mas pequeno demais para afirmar shaft; pilar e "
                      "improvavel (notas do PDF: sistema em alvenaria estrutural), nao descartado"},
    "C07": {"class": "desconhecido", "confidence": "baixa", "reason": "0,25 x 0,16 m, hachura + X; mesmo caso do C06"},
    "C08": {"class": "desconhecido", "confidence": "baixa", "reason": "0,16 x 0,16 m, hachura + X; mesmo caso do C06"},
    "C09": {"class": "shaft/prumada", "confidence": "media", "reason": _SHAFT + "; area molhada (Banho 02, junto ao box)"},
}
_OUTLINE = ("traco fino vetorial do PDF (so contorno, sem preenchimento) que segue a face da massa de parede; 0% da sua area "
            "fechada fica fora das paredes do consensus")
STROKE_PROPOSALS: dict[str, dict] = {
    "sb000": {"class": "alvenaria (contorno) + shaft/prumada", "confidence": "media",
              "reason": "contorno do bloco de paredes Lavabo/Suite 01/Banho 01 que, alem da parede, fecha C01 e C02"},
    "sb001": {"class": "alvenaria", "confidence": "alta", "reason": _OUTLINE + " (par de sb000)"},
    "sb002": {"class": "alvenaria (contorno) + shaft/prumada", "confidence": "media",
              "reason": "contorno interno do bloco oeste (Cozinha/A.S.) que, alem da parede, fecha C03, C04 e C05"},
    "sb003": {"class": "alvenaria", "confidence": "alta", "reason": _OUTLINE + " (par de sb002)"},
    "sb004": {"class": "mureta", "confidence": "media",
              "reason": "linha externa do peitoril H=1,10M do terraco (ja declarado com fonte como h_sb000); 4 vertices, "
                        "nao fecha nada; efeito na laje 0,016 m2"},
    "sb005": {"class": "alvenaria (contorno) + desconhecido", "confidence": "media",
              "reason": "contorno do bloco Suite 02 oeste/norte que, alem da parede, fecha C06 e C07"},
    "sb006": {"class": "alvenaria", "confidence": "alta", "reason": _OUTLINE + " (par de sb005)"},
    "sb007": {"class": "alvenaria (contorno) + shaft/prumada", "confidence": "media",
              "reason": "contorno do bloco Banho 02 leste (sem par) que, alem da parede, fecha C08 e C09"},
}
MAX_POCKET_M2 = 1.5      # face maior que isso e comodo/corredor, nao contorno fechado
MIN_POCKET_M2 = 0.01
MIN_POCKET_SIDE_M = 0.08


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def r(v, n=2):
    return round(float(v), n)


def pdf_objects(page):
    """Objetos de caminho do PDF com seus segmentos em coordenadas da pagina (pt, origem embaixo a esquerda)."""
    import pypdfium2.raw as C
    out = []
    for o in page.get_objects(max_depth=15):
        if o.type != C.FPDF_PAGEOBJ_PATH:
            continue
        m = o.get_matrix()
        segs = []
        for i in range(C.FPDFPath_CountSegments(o.raw)):
            s = C.FPDFPath_GetPathSegment(o.raw, i)
            x, y = ctypes.c_float(), ctypes.c_float()
            C.FPDFPathSegment_GetPoint(s, x, y)
            px = m.a * x.value + m.c * y.value + m.e
            py = m.b * x.value + m.d * y.value + m.f
            segs.append((C.FPDFPathSegment_GetType(s), px, py))
        fill_mode, stroke = ctypes.c_int(), ctypes.c_int()
        C.FPDFPath_GetDrawMode(o.raw, fill_mode, stroke)
        width = ctypes.c_float()
        C.FPDFPageObj_GetStrokeWidth(o.raw, width)

        def color(fn):
            c = [ctypes.c_uint() for _ in range(4)]
            return [v.value for v in c] if fn(o.raw, *c) else None
        out.append({"bbox": o.get_pos(), "segs": segs, "fill_mode": fill_mode.value, "stroke": bool(stroke.value),
                    "fill": color(C.FPDFPageObj_GetFillColor), "stroke_color": color(C.FPDFPageObj_GetStrokeColor),
                    "stroke_width_pt": r(width.value * abs(m.a), 3)})
    return out


def diagonal_segments(obj):
    """Segmentos LINETO inclinados (nem horizontais nem verticais) de um objeto, em pt."""
    out, prev = [], None
    for kind, x, y in obj["segs"]:
        if prev is not None and kind == 0:   # FPDF_SEGMENT_LINETO
            dx, dy = abs(x - prev[0]), abs(y - prev[1])
            if dx > 1.0 and dy > 1.0:
                out.append(((prev[0], prev[1]), (x, y)))
        prev = (x, y)
    return out


def main() -> int:
    assert_pt_to_m_for_source("planta_74.pdf")   # escala verificada da planta_74 (0.0259) ou erro alto
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pypdfium2 as pdfium
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import polygonize, unary_union
    from shapely.validation import make_valid

    from core.project_sources import plant_pdf_path
    from tools.sketchup.shell.build_plan_shell_skp import compute_room_floors, wall_footprint

    pdf_path = plant_pdf_path("planta_74", ROOT)
    before = {"consensus": sha(CONSENSUS), "pdf": sha(pdf_path)}
    con = json.loads(CONSENSUS.read_text("utf-8"))
    wt = float(con["wall_thickness_pts"])
    rooms = {rm["id"]: rm["name"] for rm in con["rooms"]}
    sbs = {s["id"]: s for s in con["soft_barriers"] if s["id"] in UNSOURCED}
    assert sorted(sbs) == UNSOURCED and not any(s.get("barrier_type") for s in sbs.values()), "sb000-sb007 mudaram"

    def strip(s):
        return LineString(s["polyline_pts"]).buffer(wt / 2.0, cap_style=2, join_style=2)
    strips = {k: strip(s) for k, s in sbs.items()}
    wall_fp = {w["id"]: wall_footprint(w, extend_endpoints=True) for w in con["walls"]}

    def floors(drop: set[str]):
        c2 = dict(con)
        c2["soft_barriers"] = [s for s in con["soft_barriers"] if s["id"] not in drop]
        return {rid: Polygon(e["outer"], e.get("holes") or []) for rid, e in compute_room_floors(c2).items()}
    f_all = floors(set())
    f_none = floors(set(UNSOURCED))

    # ---- contornos fechados (os "retangulos" da figura p7), com ID ----
    # Regiao que o traco fecha contra a face da parede do consensus: faces do arranjo (traco + contorno da massa de parede)
    # fora da parede, tocadas pelo traco em >= 30% do perimetro, sem semente de comodo dentro (exclui o proprio comodo) e
    # menores que MAX_POCKET_M2. Uma abertura morfologica de 1 pt separa os retangulos ligados por frestas < 2 pt.
    wall_union = unary_union(list(wall_fp.values()))
    seeds = [Point(rm["seed_pt"]) for rm in con["rooms"] if rm.get("seed_pt")]
    m2 = PT_TO_M ** 2
    cand = []
    for k in UNSOURCED:
        ln = LineString(sbs[k]["polyline_pts"])
        for f in polygonize(unary_union([ln, wall_union.boundary])):
            if f.area * m2 > MAX_POCKET_M2 or f.difference(wall_union).area < 0.7 * f.area:
                continue
            if any(f.contains(sp) for sp in seeds):
                continue
            if ln.buffer(0.3).intersection(f.exterior).length < 0.3 * f.exterior.length:
                continue
            cand.append(f.difference(wall_union))
    opened = unary_union(cand).buffer(-1.0, join_style=2).buffer(1.0, join_style=2) if cand else Polygon()
    lost_all = unary_union(list(f_none.values())).difference(unary_union(list(f_all.values())))
    pieces = []
    for g in (opened.geoms if hasattr(opened, "geoms") else [opened]):
        if g.is_empty or g.geom_type != "Polygon" or g.area * m2 < MIN_POCKET_M2:
            continue
        minx, miny, maxx, maxy = g.bounds
        if min(maxx - minx, maxy - miny) * PT_TO_M < MIN_POCKET_SIDE_M:
            continue
        touch = sorted(k for k in UNSOURCED if LineString(sbs[k]["polyline_pts"]).distance(g) < 1.0)
        room = max(f_none, key=lambda rid: f_none[rid].intersection(g).area)
        pieces.append({"geom": g, "room": room, "sbs": touch, "kind": "contorno_fechado",
                       "lost_m2": lost_all.intersection(g).area * m2})
    pieces.sort(key=lambda p: (p["sbs"][0] if p["sbs"] else "zz", -p["geom"].centroid.y, p["geom"].centroid.x))

    page = pdfium.PdfDocument(str(pdf_path))[0]
    page_w, page_h = page.get_size()
    objs = pdf_objects(page)
    textpage = page.get_textpage()

    def pdf_inside(g):
        """O que o PDF desenha dentro do contorno (+1 pt): segmentos inclinados, preenchimentos, texto. Fato medido, sem rotulo."""
        minx, miny, maxx, maxy = g.bounds
        zone = g.buffer(1.0, join_style=2)
        diag, fills = [], set()
        for o in objs:
            ob = box(*o["bbox"]).buffer(0.01)
            if not zone.intersects(ob):
                continue
            if o["fill_mode"] and zone.contains(ob.centroid) and ob.area <= zone.area * 1.2:
                fills.add(tuple(o["fill"] or ()))
            for a, b in diagonal_segments(o):
                if zone.contains(LineString([a, b])):
                    diag.append(LineString([a, b]))
        text = textpage.get_text_bounded(left=minx, bottom=miny, right=maxx, top=maxy).strip()
        span = Point(minx, miny).distance(Point(maxx, maxy))
        long_ = [d for d in diag if d.length >= 0.8 * span]
        x_mark = any(a.crosses(b) for i, a in enumerate(long_) for b in long_[i + 1:])
        slopes = {}
        for d in diag:
            (x0, y0), (x1, y1) = d.coords
            slopes.setdefault("+" if (x1 - x0) * (y1 - y0) > 0 else "-", []).append(d)
        hatch = max((len(v) for v in slopes.values()), default=0)
        return {"inclined_segments": len(diag), "x_mark_corner_to_corner": x_mark,
                "max_parallel_inclined_segments": hatch,
                "filled_colors_rgba": sorted(list(c) for c in fills if c), "text": text}

    def neighbours(g, dist_pt):
        walls_ = sorted(w for w, fp in wall_fp.items() if fp.distance(g) <= dist_pt)
        ops = sorted(o["id"] for o in con["openings"]
                     if Point(o["center"]).distance(g) <= dist_pt + o.get("opening_width_pts", 0) / 2)
        return walls_, ops

    for i, p in enumerate(pieces, 1):
        p["id"] = f"C{i:02d}"
        g = p["geom"]
        p["walls"], p["openings"] = neighbours(g, wt)
        p["pdf_inside"] = pdf_inside(g)

    # ---- por traco ----
    def gain(drop):
        f_wo = floors(set(drop))
        return {rooms[rid]: r((f_wo[rid].area - f_all[rid].area) * m2, 3) for rid in f_all
                if rid in f_wo and abs(f_wo[rid].area - f_all[rid].area) * m2 >= 0.001}
    strokes = []
    for k in UNSOURCED:
        s = sbs[k]
        pl = LineString(s["polyline_pts"])
        minx, miny, maxx, maxy = pl.bounds
        src = [o for o in objs if all(abs(a - b) < 2.5 for a, b in zip(o["bbox"], (minx, miny, maxx, maxy)))]
        near_walls = pl.intersection(wall_union.buffer(wt)).length / pl.length
        group = next(g for g in GROUPS if k in g)
        walls_, ops = neighbours(pl, wt)
        mine = [p for p in pieces if k in p["sbs"]]
        strokes.append({
            "id": k, "n_vertices": len(s["polyline_pts"]),
            "closed": s["polyline_pts"][0] == s["polyline_pts"][-1],
            "bbox_pt": [r(minx), r(miny), r(maxx), r(maxy)],
            "bbox_m": [r(minx * PT_TO_M), r(miny * PT_TO_M), r(maxx * PT_TO_M), r(maxy * PT_TO_M)],
            "size_m": [r((maxx - minx) * PT_TO_M), r((maxy - miny) * PT_TO_M)],
            "length_m": r(pl.length * PT_TO_M),
            "strip_area_m2": r(strips[k].area * m2, 3),
            "share_of_length_within_1_wall_thickness_of_a_wall": r(near_walls, 2),
            "walls_within_1_thickness": walls_, "openings_near": ops,
            "pdf_source_objects": [{"bbox_pt": [r(v) for v in o["bbox"]], "n_segments": len(o["segs"]),
                                    "fill_mode": o["fill_mode"], "stroked": o["stroke"],
                                    "stroke_color_rgba": o["stroke_color"], "stroke_width_pt": o["stroke_width_pt"]}
                                   for o in src],
            "hausdorff_to_other_strokes_pt": {j: r(pl.hausdorff_distance(LineString(sbs[j]["polyline_pts"])), 1)
                                              for j in UNSOURCED if j != k
                                              and pl.hausdorff_distance(LineString(sbs[j]["polyline_pts"])) < 15.0},
            "slab_gain_if_only_this_one_removed_m2": gain([k]),
            "pair": list(group),
            "slab_gain_if_pair_removed_m2": gain(group) if len(group) > 1 else None,
            "closed_contours": [p["id"] for p in mine],
            # so para polyline fechada: area que o anel fecha FORA da massa de parede do consensus (0 = so contorna parede)
            "ring_area_outside_consensus_walls_m2": (
                r(make_valid(Polygon(s["polyline_pts"])).difference(wall_union).area * m2, 3)
                if s["polyline_pts"][0] == s["polyline_pts"][-1] else None),
            "proposed_classification": STROKE_PROPOSALS[k],
        })

    # ---- pranchas ----
    img = page.render(scale=RENDER_SCALE).to_pil().convert("L")
    extent = (0, page_w, 0, page_h)
    lost_room_side = unary_union(list(f_none.values())).difference(unary_union(list(f_all.values())))

    def draw(ax, ids, bounds, lw=1.4, fs=8):
        ax.imshow(img, cmap="gray", extent=extent, origin="upper", interpolation="lanczos", vmin=0, vmax=255)
        for g in (lost_room_side.geoms if hasattr(lost_room_side, "geoms") else [lost_room_side]):
            ax.fill(*g.exterior.xy, facecolor="#ff7f0e", alpha=0.35, edgecolor="none")
        for w in con["walls"]:
            ax.plot([w["start"][0], w["end"][0]], [w["start"][1], w["end"][1]], color="#1f77b4", lw=0.6, alpha=0.55)
        for p in pieces:
            if not set(p["sbs"]) & set(ids):
                continue
            g = p["geom"]
            ax.plot(*g.exterior.xy, color="#d62728", lw=1.6)
            c = g.centroid
            ax.annotate(p["id"], (c.x, c.y), xytext=(14, 10), textcoords="offset points", color="#d62728", fontsize=fs,
                        fontweight="bold", clip_on=True, arrowprops={"arrowstyle": "-", "color": "#d62728", "lw": 0.8},
                        bbox={"facecolor": "white", "alpha": 0.85, "pad": 0.6, "edgecolor": "#d62728", "lw": 0.5})
        for k in ids:
            ax.plot(*zip(*sbs[k]["polyline_pts"]), color="#9467bd" if k == ids[0] else "#2ca02c", lw=lw, alpha=0.9)
        x0, y0, x1, y1 = bounds
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        ax.tick_params(labelsize=6)

    OUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(4, 2, figsize=(16, 24))
    for ax, k in zip(axes.flat, UNSOURCED):
        st = next(s for s in strokes if s["id"] == k)
        x0, y0, x1, y1 = st["bbox_pt"]
        pad = 8
        draw(ax, [k], (x0 - pad, y0 - pad, x1 + pad, y1 + pad))
        ax.set_title(f"{k}  bbox {st['size_m'][0]:.2f} x {st['size_m'][1]:.2f} m, comprimento {st['length_m']:.1f} m, "
                     f"par: {'+'.join(st['pair'])}\ncontornos fechados: {', '.join(st['closed_contours']) or 'nenhum'}",
                     fontsize=9)
    fig.suptitle("planta_74 #484 - cada traco sem fonte (roxo) sobre o PDF original (mesma orientacao do PDF, eixos em pt)\n"
                 "vermelho = contorno fechado com ID (Cnn); laranja = laje perdida para os 8 tracos; "
                 "azul = eixo das paredes do consensus", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(OUT / "strokes_board.png", dpi=100)
    plt.close(fig)

    # um recorte por contorno fechado (zoom), para dizer o que e cada um
    n = len(pieces)
    cols = 4
    fig, axes = plt.subplots((n + cols - 1) // cols, cols, figsize=(16, 4.2 * ((n + cols - 1) // cols)))
    for ax in axes.flat[n:]:
        ax.axis("off")
    for ax, p in zip(axes.flat, pieces):
        x0, y0, x1, y1 = p["geom"].bounds
        cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) / 2 + 14
        draw(ax, p["sbs"] or UNSOURCED, (cx - half, cy - half, cx + half, cy + half), lw=1.0, fs=9)
        ax.set_title(f"{p['id']} ({rooms[p['room']][:22]}) {(x1 - x0) * PT_TO_M:.2f} x {(y1 - y0) * PT_TO_M:.2f} m\n"
                     f"tracos: {'+'.join(p['sbs'])}; proposta (agente): "
                     f"{PROPOSALS.get(p['id'], {}).get('class', 'desconhecido')}", fontsize=8.5)
    fig.suptitle("planta_74 #484 - zoom em cada contorno fechado (vermelho) sobre o PDF; roxo/verde = tracos", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / "contours_zoom.png", dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 9.5))
    x0, y0, x1, y1 = con["planta_region"]
    draw(ax, UNSOURCED, (x0 - 6, y0 - 6, x1 + 6, y1 + 6), lw=1.0)
    for st in strokes:
        ax.annotate(st["id"], (st["bbox_pt"][0], st["bbox_pt"][3]), fontsize=8, color="#9467bd", fontweight="bold",
                    xytext=(2, 2), textcoords="offset points")
    ax.set_title("planta_74 #484 - tracos sem fonte sb000-sb007 sobre o PDF (mesma orientacao do PDF; "
                 "a figura da p7 tinha o eixo y invertido)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "strokes_overview.png", dpi=110)
    plt.close(fig)

    piece_rows = [{
        "id": p["id"], "kind": p["kind"], "room": rooms[p["room"]], "room_id": p["room"], "touching_strokes": p["sbs"],
        "bbox_pt": [r(v) for v in p["geom"].bounds], "bbox_m": [r(v * PT_TO_M) for v in p["geom"].bounds],
        "size_m": [r((p["geom"].bounds[2] - p["geom"].bounds[0]) * PT_TO_M),
                   r((p["geom"].bounds[3] - p["geom"].bounds[1]) * PT_TO_M)],
        "area_m2": r(p["geom"].area * m2, 3), "slab_missing_inside_m2": r(p["lost_m2"], 3),
        "walls_within_1_thickness": p["walls"], "openings_near": p["openings"],
        "pdf_inside": p["pdf_inside"],
        "proposed_classification": PROPOSALS.get(p["id"], {"class": "desconhecido", "reason": "sem proposta registrada"}),
    } for p in pieces]
    in_contours = sum(p["lost_m2"] for p in pieces)
    lost = {rooms[rid]: r((f_none[rid].area - f_all[rid].area) * m2, 3) for rid in f_none if rid in f_all}
    after = {"consensus": sha(CONSENSUS), "pdf": sha(pdf_path)}
    assert after == before, "arquivo protegido mudou"
    import pypdfium2
    result = {
        "schema": "fp056_484_strokes.v1", "issue": 484, "pt_to_m": PT_TO_M,
        "coordinates": "pt nativos do PDF (origem embaixo a esquerda, y para cima) = coordenadas do consensus; m = pt x PT_TO_M",
        "pdf_library": f"pypdfium2 {pypdfium2.V_PYPDFIUM2}", "render_scale": RENDER_SCALE,
        "protected_sha256_before_after": before,
        "slab_lost_per_room_m2_all_strokes": lost,
        "slab_lost_total_m2": r(sum(lost.values()), 3),
        "slab_lost_inside_closed_contours_m2": r(in_contours, 3),
        "slab_lost_as_band_along_walls_m2": r(sum(lost.values()) - in_contours, 3),
        "stroke_pairs": [list(g) for g in GROUPS],
        "strokes": strokes, "closed_contours": piece_rows,
        "proposed_by": "agent (Claude), a partir do recorte do PDF e da geometria; NAO e fato, decisao do Felipe na #484",
    }
    (OUT / "strokes.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), "utf-8")
    print(json.dumps({"lost_m2": lost, "closed_contours": [p["id"] for p in pieces],
                      "inside_contours_m2": r(in_contours, 3)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
