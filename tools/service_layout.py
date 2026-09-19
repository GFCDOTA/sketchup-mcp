"""service_layout.py — brain do comodo SERVICE da planta_74: `A.S. | TERRACO
SOCIAL | TERRACO TECNICO` (r001). Era o UNICO comodo da planta sem brain
("skip(sem brain)" no furnish_apartment) — 15.3 m2, ~20% da area util, saindo
vazio em todo .skp mobiliado.

O comodo e' UM poligono no consensus porque os 3 ambientes nao tem parede entre
si (o polygonize fundiu 3 seeds -> `merged_seeds` + `label_ids`). Aqui eles sao
re-separados por ZONA, e cada zona tem um PROGRAMA proprio. A separacao NAO e'
inventada: cada zona e' validada contra o seed do rotulo do PDF que lhe pertence
(`_split_zones` levanta se um seed cair na zona errada -> degrada, nao inventa).

Fonte do programa = NOTAS DO PROPRIO PDF (planta_74.pdf, bloco "OBSERVACOES"):
  - "SERA ENTREGUE INFRAESTRUTURA DE PONTO DE AGUA E ESGOTO, PARA OS AMBIENTES DE
     TERRACO SOCIAL E AREA DE SERVICO, PARA FUTURA INSTALACAO DE BANCADA, CUBA,
     TORNEIRA, TANQUE (AREA DE SERVICO)."
  - "SERA ENTREGUE INFRAESTRUTURA PARA COIFA E CHURRASQUEIRA A CARVAO NO TERRACO
     SOCIAL."
Ou seja: tanque na A.S. e churrasqueira+coifa+bancada+cuba no terraco social sao
PREVISTOS PELA PLANTA, nao decoracao inventada. O terraco TECNICO e' tecnico:
so condensadora (a nota de ar-condicionado do mesmo bloco), nada de estar.

Colocacao = guloso por PRIORIDADE com fallback de largura: cada peca desliza ao
longo da parede da sua zona procurando vaga; se nao couber, encolhe; se ainda nao
couber, e' DESCARTADA e registrada em out["dropped"] (nunca empurrada por cima de
outra peca nem pra dentro da circulacao). Circulacao/vao de porta vem do
spatial_model (mesma fonte dos outros brains).

Uso:
    from tools.service_layout import build_boxes
    boxes, out = build_boxes(con, "r001")
    PT_TO_M=0.0259 python -m tools.service_layout        # relatorio textual
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shapely.geometry import Point, Polygon, box as _shp_box   # noqa: E402
from shapely.ops import unary_union                            # noqa: E402

from core.scale import PT_TO_IN                                # noqa: E402
from tools.spatial_model import build_spatial_model            # noqa: E402

IN2M = 0.0254
M2IN = 39.3700787402

# ---- zonas ----------------------------------------------------------------
# Limites lidos da ESTRUTURA do proprio poligono do comodo (degraus reais da
# planta), nao de chute: x=3.26m e' onde a faixa estreita da A.S. termina e o
# comodo se abre pro terraco; x=5.95m e' onde nasce o apendice do terraco
# tecnico; y=11.30m e' onde a faixa da A.S. deixa de existir (o poligono recua
# pra x>=2.26 por causa da prumada da coifa). `_split_zones` confere cada zona
# contra o seed do rotulo do PDF correspondente antes de devolver.
AS = "A.S."
SOCIAL = "TERRACO SOCIAL"
TECNICO = "TERRACO TECNICO"
_AS_MAX_X_M = 3.26
_TEC_MIN_X_M = 5.95
_AS_MIN_Y_M = 11.30

# ordem dos merged_seeds == ordem dos label_ids == ordem do nome do comodo
_SEED_ORDER = (AS, SOCIAL, TECNICO)

# ---- paleta (mesma linguagem do resto do ape: madeira + grafite + bronze) ---
RGB = {
    "madeira": [92, 64, 46],
    "grafite": [38, 39, 40],
    "preto": [26, 26, 28],
    "inox": [168, 170, 172],
    "branco": [226, 224, 219],
    "bronze": [171, 119, 63],
    "pedra": [78, 78, 80],
    "verde": [74, 96, 66],
    "tijolo": [122, 78, 62],
}

_CLEAR_M = 0.04          # folga anti-encosto entre pecas (nao e' circulacao)
_DOOR_TOL_M2 = 0.02      # area tolerada de invasao da zona de circulacao


# ---------------------------------------------------------------------------
def _cell_m(sm):
    """Poligono util do comodo em METROS (o spatial_model entrega em inches)."""
    cell = sm["_geom"]["cell"]
    return Polygon([(x * IN2M, y * IN2M) for x, y in cell.exterior.coords])


def _circ_m(sm):
    """Uniao das zonas de circulacao (giro de porta/vao) em METROS, ou None."""
    circ = sm["_geom"].get("circ") or []
    if not circ:
        return None
    polys = [Polygon([(x * IN2M, y * IN2M) for x, y in g.exterior.coords])
             for g in circ if not g.is_empty]
    return unary_union(polys) if polys else None


def _split_zones(con, room_id, cell):
    """Re-separa o poligono fundido nas 3 zonas e VALIDA cada uma contra o seed
    do rotulo do PDF. Devolve {zona: Polygon} ou None se a validacao falhar
    (degrada honesto: sem zona confiavel, o brain nao mobilia)."""
    minx, miny, maxx, maxy = cell.bounds
    big = max(maxx - minx, maxy - miny) + 10.0
    cuts = {
        AS: _shp_box(minx - big, _AS_MIN_Y_M, _AS_MAX_X_M, maxy + big),
        TECNICO: _shp_box(_TEC_MIN_X_M, miny - big, maxx + big, maxy + big),
    }
    zones = {AS: cell.intersection(cuts[AS]), TECNICO: cell.intersection(cuts[TECNICO])}
    zones[SOCIAL] = cell.difference(cuts[AS]).difference(cuts[TECNICO])
    for name, z in list(zones.items()):
        if z.is_empty:
            return None, f"zona {name!r} vazia apos o corte"
        if z.geom_type == "MultiPolygon":       # fica com a parte principal
            zones[name] = max(z.geoms, key=lambda g: g.area)

    room = next((r for r in con.get("rooms", []) if r.get("id") == room_id), None)
    seeds = (room or {}).get("merged_seeds") or []
    if len(seeds) != len(_SEED_ORDER):
        return None, f"esperava {len(_SEED_ORDER)} seeds rotulados, achei {len(seeds)}"
    for (sx, sy), name in zip(seeds, _SEED_ORDER):
        p = Point(sx * PT_TO_IN * IN2M, sy * PT_TO_IN * IN2M)
        owner = next((n for n, z in zones.items() if z.buffer(0.12).contains(p)), None)
        if owner != name:
            return None, (f"seed do rotulo {name!r} caiu na zona {owner!r} — "
                          "corte de zona nao confere com o PDF")
    return zones, None


# ---------------------------------------------------------------------------
def _wall_line(zone, side, along_lo, along_hi, samples=9):
    """Coordenada da PAREDE da zona no lado pedido, medida no trecho [lo,hi] do
    eixo livre. Amostra o poligono pra achar a borda mais 'pra dentro' do trecho
    — assim a peca fica flush na parede SEM furar um degrau/pilar."""
    vals = []
    for i in range(samples):
        t = along_lo + (along_hi - along_lo) * i / (samples - 1)
        if side in ("west", "east"):
            line = _shp_box(zone.bounds[0] - 1, t - 0.01, zone.bounds[2] + 1, t + 0.01)
        else:
            line = _shp_box(t - 0.01, zone.bounds[1] - 1, t + 0.01, zone.bounds[3] + 1)
        seg = zone.intersection(line)
        if seg.is_empty:
            return None
        b = seg.bounds
        vals.append({"west": b[0], "east": b[2], "south": b[1], "north": b[3]}[side])
    return max(vals) if side in ("west", "south") else min(vals)


_FACING = {"west": (1.0, 0.0), "east": (-1.0, 0.0),
           "south": (0.0, 1.0), "north": (0.0, -1.0)}


def _flush_rect(zone, side, along_c, w_m, d_m):
    """Retangulo de w x d encostado em `side`, centrado em `along_c` no eixo
    livre. Devolve (poly, center_xy) ou None se a parede nao existir ali."""
    lo, hi = along_c - w_m / 2, along_c + w_m / 2
    line = _wall_line(zone, side, lo, hi)
    if line is None:
        return None
    if side == "west":
        rect = _shp_box(line, lo, line + d_m, hi)
    elif side == "east":
        rect = _shp_box(line - d_m, lo, line, hi)
    elif side == "south":
        rect = _shp_box(lo, line, hi, line + d_m)
    else:
        rect = _shp_box(lo, line - d_m, hi, line)
    c = rect.centroid
    return rect, (c.x, c.y)


def _slide(zone, side, prefer, w_m, d_m, placed, circ, step=0.05, span=4.0):
    """Desliza a peca ao longo da parede procurando a vaga LIVRE mais perto de
    `prefer`. Livre = dentro da zona, sem tocar peca ja aceita (folga _CLEAR_M)
    e sem invadir circulacao/giro de porta."""
    n = int(span / step)
    for k in range(n + 1):
        for sgn in ((0,) if k == 0 else (-1, 1)):
            got = _flush_rect(zone, side, prefer + sgn * k * step, w_m, d_m)
            if got is None:
                continue
            rect, center = got
            if not zone.buffer(0.02).contains(rect):
                continue
            if circ is not None and rect.intersection(circ).area > _DOOR_TOL_M2:
                continue
            if any(rect.intersection(p.buffer(_CLEAR_M)).area > 0.005 for p in placed):
                continue
            return rect, center
    return None


# ---------------------------------------------------------------------------
def _programa(zones):
    """Programa por zona, em ordem de PRIORIDADE (primeiro = mais essencial).
    Cada item: (kind, module, side, prefer_along, [larguras], depth, z0, h, rgb).
    A lista de larguras e' o fallback "encolhe antes de desistir"."""
    zas, zso, ztec = zones[AS], zones[SOCIAL], zones[TECNICO]
    as_x0, as_y0, as_x1, as_y1 = zas.bounds
    so_x0, so_y0, so_x1, so_y1 = zso.bounds
    te_x0, te_y0, te_x1, te_y1 = ztec.bounds
    P = []

    # --- A.S. — tudo numa fita unica na parede oeste (a faixa tem ~1.8m: fita de
    # 0.62 deixa >=1.15m de passagem livre ate a parede oposta) ---------------
    P += [
        dict(zone=AS, kind="tanque", module="Tanque", side="west",
             prefer=as_y1 - 0.95, widths=[0.80, 0.70, 0.60], d=0.62,
             z0=0.0, h=0.92, rgb=RGB["branco"],
             why="ponto de agua/esgoto previsto em nota do PDF"),
        dict(zone=AS, kind="maq_lavar", module="Maquina de lavar", side="west",
             prefer=as_y1 - 1.85, widths=[0.66, 0.62], d=0.64,
             z0=0.0, h=0.86, rgb=RGB["branco"], why="lavanderia basica"),
        dict(zone=AS, kind="armario_servico", module="Armario de servico", side="west",
             prefer=as_y1 - 2.75, widths=[0.90, 0.75, 0.60], d=0.60,
             z0=0.0, h=2.10, rgb=RGB["grafite"], why="guarda de produtos/vassoura"),
        dict(zone=AS, kind="maq_secar", module="Secadora", side="west",
             prefer=as_y1 - 3.50, widths=[0.66, 0.62], d=0.64,
             z0=0.0, h=0.86, rgb=RGB["branco"], why="par da lavadora se sobrar fita"),
        # aereos/varal: z alto, nao disputam piso (o overlap_gate ja usa faixa de Z)
        dict(zone=AS, kind="prateleira_servico", module="Prateleira servico", side="west",
             prefer=as_y1 - 1.85, widths=[1.60, 1.20, 0.90], d=0.32,
             z0=1.62, h=0.04, rgb=RGB["madeira"], why="apoio acima da lavadora"),
        dict(zone=AS, kind="varal_teto", module="Varal de teto", side="west",
             prefer=as_y1 - 1.85, widths=[1.30, 1.00], d=0.55,
             z0=2.02, h=0.06, rgb=RGB["inox"], why="secagem sem ocupar piso"),
    ]

    # --- TERRACO SOCIAL — churrasqueira embutida na UNICA alvenaria cega da zona
    # (a face x=3.26 que divide o terraco da A.S., so existe acima de y=11.30) +
    # bancada gourmet no peitoril sul + banquetas. Tudo previsto no PDF. -------
    _alv_y = max(_AS_MIN_Y_M + 0.75, so_y0 + 1.60)   # trecho de alvenaria cega
    P += [
        dict(zone=SOCIAL, kind="churrasqueira", module="Churrasqueira", side="west",
             prefer=_alv_y, widths=[1.00, 0.85, 0.70], d=0.62,
             z0=0.0, h=1.05, rgb=RGB["tijolo"],
             why="infra de coifa+churrasqueira a carvao (nota do PDF), na alvenaria cega"),
        dict(zone=SOCIAL, kind="coifa", module="Coifa", side="west",
             prefer=_alv_y, widths=[1.00, 0.85, 0.70], d=0.58,
             z0=1.55, h=0.55, rgb=RGB["preto"], why="exaustao da churrasqueira"),
        # bancada na FAIXA LARGA do terraco (x > _AS_MAX_X_M): no trecho estreito
        # do peitoril oeste a zona so tem ~1.05m de profundidade — bancada la
        # deixaria a banqueta sem area pra sentar.
        dict(zone=SOCIAL, kind="bancada_gourmet", module="Bancada gourmet", side="south",
             prefer=_AS_MAX_X_M + 1.30, widths=[1.80, 1.50, 1.25, 1.00], d=0.60,
             z0=0.0, h=0.95, rgb=RGB["madeira"],
             why="bancada/cuba/torneira previstas em nota do PDF"),
        dict(zone=SOCIAL, kind="cuba_gourmet", module="Bancada gourmet", side="south",
             prefer=_AS_MAX_X_M + 1.30, widths=[0.42], d=0.36,
             z0=0.86, h=0.10, rgb=RGB["inox"], why="cuba da bancada", rides="bancada_gourmet"),
        dict(zone=SOCIAL, kind="jardineira", module="Jardineira", side="east",
             prefer=so_y0 + 0.70, widths=[1.20, 0.90, 0.70], d=0.32,
             z0=0.0, h=0.45, rgb=RGB["verde"], why="verde no peitoril, sem roubar piso"),
    ]

    # --- TERRACO TECNICO — tecnico de verdade: condensadora e ponto final.
    P += [
        dict(zone=TECNICO, kind="condensadora", module="Condensadora", side="east",
             prefer=(te_y0 + te_y1) / 2, widths=[0.90, 0.80, 0.70], d=0.34,
             z0=0.12, h=0.70, rgb=RGB["inox"],
             why="nota do PDF preve condensadora de ar-condicionado"),
    ]
    return P


def _stools(zone, bancada, placed, circ, n_max=3):
    """Banquetas de frente pra bancada gourmet. Em terraco pequeno isto e' o que
    substitui a mesa: assento sem roubar o piso de circulacao. Entra uma a uma e
    so se tiver area de uso real (assento + recuo pra sentar)."""
    if bancada is None:
        return []
    bx0, by0, bx1, by1 = bancada.bounds
    # a propria bancada nao e' obstaculo da banqueta (a banqueta encaixa nela)
    others = [p for p, _pm in placed if not p.equals(bancada)]
    out = []
    for i in range(n_max):
        cx = bx0 + (bx1 - bx0) * (i + 0.5) / n_max
        cy = by1 + 0.18 + 0.17                     # encostada na frente da bancada
        seat = _shp_box(cx - 0.17, cy - 0.17, cx + 0.17, cy + 0.17)
        use = seat.buffer(0.20)                    # recuo pra sentar/levantar
        if not zone.buffer(-0.02).contains(use):
            continue
        if circ is not None and seat.intersection(circ).area > _DOOR_TOL_M2:
            continue
        if any(use.intersects(p.buffer(0.02)) for p in others + [o[2] for o in out]):
            continue
        out.append(("banqueta", "Banqueta", seat, (cx, cy), (0.0, -1.0),
                    0.0, 0.74, RGB["grafite"], 0.34, 0.34))
    return out


def _table_set(zone, placed, circ):
    """Mesa externa redonda + cadeiras, na maior folga do terraco social. Cada
    cadeira so entra se couber livre — cadeira sem area de uso e' pior que
    cadeira ausente (regra do Felipe: reduzir antes de forcar)."""
    inner = zone.buffer(-0.06)
    x0, y0, x1, y1 = zone.bounds
    best = None                                   # (-n_lugares, dist_ao_centro, payload)
    cx0, cy0 = (x0 + x1) / 2, (y0 + y1) / 2
    for diam in (0.90, 0.80, 0.70, 0.60):
        table_ok = []
        gx = x0
        while gx <= x1:
            gy = y0
            while gy <= y1:
                table = Point(gx, gy).buffer(diam / 2, quad_segs=8)
                gy += 0.05
                if not inner.contains(table):
                    continue
                if any(table.intersects(p.buffer(pm)) for p, pm in placed):
                    continue      # pm = passagem exigida por AQUELE obstaculo
                if circ is not None and table.intersection(circ).area > _DOOR_TOL_M2:
                    continue
                table_ok.append((gx, gy - 0.05, table))
            gx += 0.05
        for tx, ty, table in table_ok:
            chairs = []
            for dx, dy in ((0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)):
                cc = (tx + dx * (diam / 2 + 0.28), ty + dy * (diam / 2 + 0.28))
                ch = _shp_box(cc[0] - 0.22, cc[1] - 0.22, cc[0] + 0.22, cc[1] + 0.22)
                pulled = ch.buffer(0.16)              # cadeira PUXADA precisa caber
                if not zone.buffer(-0.02).contains(pulled):
                    continue
                if circ is not None and ch.intersection(circ).area > _DOOR_TOL_M2:
                    continue
                if any(pulled.intersects(p.buffer(0.03))
                       for p in [q for q, _ in placed] + [x[0] for x in chairs]):
                    continue
                chairs.append((ch, cc, (-dx, -dy)))
            if len(chairs) < 2:
                continue
            score = (-len(chairs), (tx - cx0) ** 2 + (ty - cy0) ** 2)
            if best is None or score < best[0]:
                best = (score, diam, (tx, ty), table, chairs)
        if best is not None:
            break
    if best is None:
        return [], "mesa externa OMITIDA — nenhuma posicao preserva folga de uso"
    _score, diam, (tx, ty), table, chairs = best
    out = [("mesa_externa", "Mesa externa", table, (tx, ty), (0.0, 1.0),
            0.0, 0.74, RGB["madeira"], diam, diam)]
    for ch, cc, face in chairs:
        out.append(("cadeira_externa", "Cadeira externa", ch, cc, face,
                    0.0, 0.86, RGB["grafite"], 0.44, 0.44))
    note = (None if len(chairs) >= 4 else
            f"mesa externa entrou com {len(chairs)} lugares (4 nao cabem com folga de uso)")
    return out, note


# ---------------------------------------------------------------------------
def build_boxes(con, room_id):
    """Brain do comodo de servico. Devolve (boxes, out) no formato do
    place_layout (mesmo contrato dos outros brains do furnish_apartment)."""
    from tools.furnish_apartment import _oriented_box          # lazy: evita ciclo

    sm = build_spatial_model(con, room_id)
    cell = _cell_m(sm)
    circ = _circ_m(sm)
    zones, err = _split_zones(con, room_id, cell)
    if zones is None:
        return [], {"result": "NO_VALID_LAYOUT", "room_name": sm.get("room_name"),
                    "reason": err, "placement": "service_layout"}

    boxes, placed, dropped, decisions = [], [], [], []
    by_kind = {}

    def _emit(kind, module, rect, center, facing, z0, h, rgb, w, d):
        cx_in, cy_in = center[0] * M2IN, center[1] * M2IN
        b = _oriented_box(kind, (cx_in, cy_in), facing, w, d, z0, h, rgb, module=module)
        boxes.append(b)
        by_kind[kind] = rect
        return b

    for spec in _programa(zones):
        zone = zones[spec["zone"]]
        rides = spec.get("rides")
        if rides is not None:                    # peca que POUSA sobre outra (cuba)
            host = by_kind.get(rides)
            if host is None:
                dropped.append((spec["kind"], f"sem {rides} pra apoiar"))
                continue
            c = host.centroid
            rect = _shp_box(c.x - spec["widths"][0] / 2, c.y - spec["d"] / 2,
                            c.x + spec["widths"][0] / 2, c.y + spec["d"] / 2)
            _emit(spec["kind"], spec["module"], rect, (c.x, c.y), _FACING[spec["side"]],
                  spec["z0"], spec["h"], spec["rgb"], spec["widths"][0], spec["d"])
            decisions.append({"kind": spec["kind"], "zona": spec["zone"],
                              "w_m": spec["widths"][0], "motivo": spec["why"]})
            continue

        # peca so briga com quem divide a FAIXA DE Z com ela (mesma regra do
        # furniture_overlap_gate): varal a 2.02m passa por cima da lavadora.
        z0, z1 = spec["z0"], spec["z0"] + spec["h"]
        obst = [p for p, (a, b) in placed if a < z1 and z0 < b]
        got, used_w = None, None
        for w in spec["widths"]:
            got = _slide(zone, spec["side"], spec["prefer"], w, spec["d"], obst, circ)
            if got is not None:
                used_w = w
                break
        if got is None:
            dropped.append((spec["kind"], "nao coube com folga em nenhuma largura"))
            continue
        rect, center = got
        _emit(spec["kind"], spec["module"], rect, center, _FACING[spec["side"]],
              spec["z0"], spec["h"], spec["rgb"], used_w, spec["d"])
        placed.append((rect, (z0, z1)))
        decisions.append({"kind": spec["kind"], "zona": spec["zone"], "w_m": used_w,
                          "encolheu": used_w != spec["widths"][0], "motivo": spec["why"]})

    # banquetas e mesa por ultimo: usam a folga QUE SOBROU (nunca empurram o
    # fixo). So o que esta NO PISO conta (coifa/varal/prateleira passam por cima),
    # e cada obstaculo pede a passagem PROPORCIONAL a ele: movel de pe exige
    # circulacao de gente (0.55m); jardineira/banco baixo so pede contorno (0.30m).
    floor = [(p, 0.55 if (b - a) >= 0.60 else 0.30) for p, (a, b) in placed if a < 1.20]
    for kind, module, rect, center, facing, z0, h, rgb, w, d in _stools(
            zones[SOCIAL], by_kind.get("bancada_gourmet"), floor, circ):
        _emit(kind, module, rect, center, facing, z0, h, rgb, w, d)
        placed.append((rect, (z0, z0 + h)))
        floor.append((rect, 0.45))
        decisions.append({"kind": kind, "zona": SOCIAL,
                          "motivo": "assento da bancada gourmet (substitui mesa em terraco compacto)"})
    tset, tnote = _table_set(zones[SOCIAL], floor, circ)
    for kind, module, rect, center, facing, z0, h, rgb, w, d in tset:
        _emit(kind, module, rect, center, facing, z0, h, rgb, w, d)
        placed.append((rect, (z0, z0 + h)))
    if tnote:
        decisions.append({"kind": "mesa_externa", "zona": SOCIAL, "motivo": tnote})
        if "OMITIDA" in tnote:
            dropped.append(("mesa_externa", tnote))

    out = {"result": "OK" if boxes else "NO_VALID_LAYOUT",
           "room_name": sm.get("room_name"), "n_placed": len(boxes),
           "placement": "service_layout",
           "zonas": {n: round(z.area, 2) for n, z in zones.items()},
           "dropped": dropped, "placement_decisions": decisions}
    return boxes, out


def main():
    import json
    from tools.furnish_apartment import CONSENSUS
    con = json.loads(Path(CONSENSUS).read_text("utf-8"))
    boxes, out = build_boxes(con, "r001")
    print(f"[service] {out['result']} — {out.get('n_placed', 0)} boxes")
    print(f"[service] zonas (m2): {out.get('zonas')}")
    for d in out.get("placement_decisions", []):
        enc = " (encolheu)" if d.get("encolheu") else ""
        print(f"   + {d['kind']:20} {d['zona']:15} {d.get('w_m', '-')}{enc}  {d['motivo']}")
    for k, why in out.get("dropped", []):
        print(f"   - {k:20} DESCARTADO: {why}")


if __name__ == "__main__":
    main()
