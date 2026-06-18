"""furnish_apartment.py — mobilia a planta INTEIRA num UNICO .skp: classifica
cada comodo (tools.room_type), roda o brain certo por tipo, junta TODOS os boxes
e materializa um so planta_74_furnished.skp (+ renders) no shell real. REUSA
tools/place_layout_skp.rb (generico). Pasta fixa artifacts/planta_74/furnished/.

Hoje mobilia: BEDROOM (bedroom_layout). Arquitetura cresce: e so registrar mais
brains em BRAINS (KITCHEN, BATHROOM, LIVING). Felipe 2026-06-05. Placeholders,
NAO 3D Warehouse.

ATENCAO: sem --dry-run, da taskkill SketchUp.exe e LANCA o SketchUp.
Uso: python tools/furnish_apartment.py [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # roda standalone
from tools import bedroom_designer   # noqa: E402  (quartos: brain novo GPT-approved)
from tools.bathroom_layout import build_boxes as bath_boxes   # noqa: E402
from tools.kitchen_layout import build_boxes as kitchen_boxes   # noqa: E402
from tools.place_layout_skp import build_boxes as living_boxes   # noqa: E402
from tools.room_type import (BATHROOM, BEDROOM, KITCHEN, LIVING,   # noqa: E402
                             classify_rooms)

ROOT = Path(__file__).resolve().parents[1]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP = Path(os.environ.get("FURNISH_BASE_SKP") or str(ROOT / "artifacts/planta_74/planta_74.skp"))  # shell override p/ escala: @0.0259 usa o shell rebuildado (base default 0.0352 intacta)
OUT_DIR = ROOT / "artifacts/planta_74/furnished"   # pasta UNICA fixa
RB = ROOT / "tools/place_layout_skp.rb"

def bedroom_designer_boxes(con, room_id):
    """Adapter: roda o bedroom_designer (cama por tamanho do quarto + cabeceira +
    criados + tapete + guarda-roupa + console; GPT-approved) e devolve os boxes no
    formato place_layout. Troca o placeholder 'bed' (BLOCO UNICO azul) pela CAMA
    GOLDEN composta (bed_builder: plinto+estrado+colchao+travesseiros+manta, material
    por papel + bevel) no MESMO footprint/facing. Substitui o place_bedroom_skp antigo."""
    from tools.bed_builder import build_bed, place_bed_boxes
    from tools.furniture_anatomy_spec import bed_spec, nightstand_spec, wardrobe_spec
    from tools.nightstand_builder import build_nightstand, place_nightstand_boxes
    from tools.wardrobe_builder import build_wardrobe, place_wardrobe_boxes
    sm, out = bedroom_designer.run(con, room_id, minimalist=True)
    if out.get("result") != "OK":
        return None, out
    items = out["_winner_items"]
    boxes = bedroom_designer._items_to_boxes(items)
    # escala via ENV (default = wall-thickness 0.0352); casa com spatial_model/geometry_sanity.
    # sem isso, footprint dimensionado no PT_TO_M novo (0.0259) era reconvertido a 0.0352 ->
    # movel 1.36x grande + centro fora do comodo (geometry_sanity FAIL). sofa_builder.PT_TO_IN
    # ja e m->in (39.37), entao a anatomia das parts nao muda; so o pt->m/in do placement.
    from core.scale import PT_TO_M, PT_TO_IN  # fonte unica (env PT_TO_M -> 0.0259)
    pt_m = PT_TO_M
    pt_in = PT_TO_IN

    def _wd_facing(it, default=(0.0, 1.0)):
        f = it.get("facing") or default
        return (float(f[0]), float(f[1]))

    def _wd_dims(box, facing):
        x0, y0, x1, y1 = box.bounds
        fx, fy = facing
        if abs(fy) >= abs(fx):                      # corre em X (largura), profundidade em Y
            return (x1 - x0) * pt_m, (y1 - y0) * pt_m, ((x0 + x1) / 2 * pt_in, (y0 + y1) / 2 * pt_in)
        return (y1 - y0) * pt_m, (x1 - x0) * pt_m, ((x0 + x1) / 2 * pt_in, (y0 + y1) / 2 * pt_in)

    bed_facing = (0.0, 1.0)
    bed_item = next((it for it in items if it.get("type") == "bed"), None)
    if bed_item is not None:
        fx, fy = _wd_facing(bed_item)
        bed_facing = (fx, fy)
        w_m, l_m, cen = _wd_dims(bed_item["box"], (fx, fy))
        nm = str(bed_item.get("name", ""))
        size = next((s for s in ("king", "queen", "casal", "solteiro") if s in nm), "king")
        parts, _ = build_bed(bed_spec(size, width=round(w_m, 3), length=round(l_m, 3)))
        bed_parts = place_bed_boxes(parts, cen, (fx, fy))
        for _b in bed_parts:
            _b["module"] = "Cama"
        # a anatomia do build_bed JA tem a 'cabeceira'; dropa tambem o 'headboard' do
        # _items_to_boxes pra nao duplicar o painel (ruido visual no render). Felipe 2026-06-08.
        boxes = [b for b in boxes if b.get("kind") not in ("bed", "headboard")] + bed_parts
        out["bed_parametric"] = {"size": size, "n_parts": len(bed_parts),
                                 "W_m": round(w_m, 2), "L_m": round(l_m, 2)}

    # CRIADOS golden (pes+corpo+tampo+gaveta+knob), gaveta vira p/ fora (facing da cama).
    ns_items = [it for it in items if it.get("type") == "nightstand"]
    if ns_items:
        ns_boxes, n_ns = [], 0
        for it in ns_items:
            nw, nd, ncen = _wd_dims(it["box"], bed_facing)
            nparts, _ = build_nightstand(nightstand_spec(width=round(nw, 3), depth=round(max(nd, 0.30), 3)))
            n_ns += 1
            _cb = place_nightstand_boxes(nparts, ncen, bed_facing)
            for _b in _cb:                                  # cada criado = modulo separado
                _b["module"] = f"Criado-mudo {n_ns}"
            ns_boxes += _cb
        boxes = [b for b in boxes if b.get("kind") != "nightstand"] + ns_boxes
        out["nightstand_parametric"] = {"count": n_ns, "n_parts": len(ns_boxes)}

    # GUARDA-ROUPA golden (corpo+portas+puxadores+rodape) no mesmo footprint/facing (portas
    # viram p/ dentro do quarto). Troca o bloco roxo liso 'wardrobe'.
    wd_item = next((it for it in items if it.get("type") == "wardrobe"), None)
    if wd_item is not None:
        wfx, wfy = _wd_facing(wd_item)
        ww_m, wd_m, wcen = _wd_dims(wd_item["box"], (wfx, wfy))
        wparts, _ = build_wardrobe(wardrobe_spec(width=round(ww_m, 3), depth=round(max(wd_m, 0.45), 3)))
        wboxes = place_wardrobe_boxes(wparts, wcen, (wfx, wfy))
        for _b in wboxes:
            _b["module"] = "Guarda-roupa"
        boxes = [b for b in boxes if b.get("kind") != "wardrobe"] + wboxes
        out["wardrobe_parametric"] = {"n_parts": len(wboxes), "W_m": round(ww_m, 2), "D_m": round(wd_m, 2)}
    return boxes, out


def _oriented_box(kind, center_in, facing, w_m, d_m, z0_m, h_m, rgb, label=None, module=None):
    """Caixa (rack/mesa/tapete) centrada em center_in (shell inches) com a FRENTE
    (-Y local) apontando 'facing'. Mesma rotacao do place_sofa_boxes -> qualquer
    angulo. w=largura (perp ao facing), d=profundidade (ao longo do facing)."""
    import math
    M2IN = 39.3700787402
    cx, cy = center_in
    fx, fy = facing
    nrm = math.hypot(fx, fy) or 1.0
    fx, fy = fx / nrm, fy / nrm
    theta = math.atan2(fx, -fy)
    ct, st = math.cos(theta), math.sin(theta)
    corners = []
    for lx, ly in ((-w_m / 2, -d_m / 2), (w_m / 2, -d_m / 2),
                   (w_m / 2, d_m / 2), (-w_m / 2, d_m / 2)):
        wx, wy = lx * ct - ly * st, lx * st + ly * ct
        corners.append([round(cx + wx * M2IN, 2), round(cy + wy * M2IN, 2)])
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return {"kind": kind, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": corners, "h_in": round(h_m * M2IN, 2), "z0_in": round(z0_m * M2IN, 2),
            "rgb": rgb, "label": label or kind, "module": module or kind,
            "ambiguous": False, "decorative": False}


def place_decor_boxes(kind, center_in, facing, z_lift=0.0, module=None, **overrides):
    """Adapter de DECOR: build_decor(kind) (parts em metros, frente -Y) -> boxes
    orientados pra 'facing' em center_in (inches), REUSANDO place_sofa_boxes (rotacao
    provada). z_lift (m) sobe a peca (quadro na parede). module = grupo editavel no .skp."""
    from tools.decor_builders import build_decor
    from tools.sofa_builder import place_sofa_boxes
    parts, _ = build_decor(kind, **overrides)
    if z_lift:
        for p in parts:
            p["z0"] += z_lift
            p["z1"] += z_lift
    bx = place_sofa_boxes(parts, center_in, facing)
    for b in bx:
        b["module"] = module or kind
    return bx


def _chair_parts():
    """Cadeira de jantar simples (Tolix-ish, metal preto): 4 pés + assento + encosto.
    Metros, frente = -Y (encosto em +Y). Orientada por place_sofa_boxes."""
    from tools.sofa_builder import _p
    w, d, sh, bh, lt = 0.42, 0.44, 0.46, 0.86, 0.028
    seat, frame = (52, 52, 56), (26, 26, 29)
    parts = []
    for x0, y0 in ((0.02, 0.02), (w - 0.02 - lt, 0.02), (0.02, d - 0.02 - lt), (w - 0.02 - lt, d - 0.02 - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, sh, frame))
    parts.append(_p("seat", "seat", 0.0, 0.0, w, d, sh, sh + 0.04, seat))
    parts.append(_p("back", "back", 0.0, d - 0.05, w, d, sh, bh, frame))
    return parts


def living_room_boxes(con, room_id):
    """Sala via COMMON SENSE ENGINE (placement solver): o sofa GOLDEN deixa de
    flutuar no centro — fica ANCORADO numa parede de FRENTE pra TV (eixo sofa->rack),
    fora da circulacao; rack de MADEIRA na parede-TV (limpa), mesa de centro + tapete
    no eixo entre os dois. Corrige o veredito do GPT (objeto PASS, placement FAIL):
    o solver rejeita sofa em circulacao / sem eixo pra TV. Fallback: brain antigo."""
    from tools.sofa_builder import build_sofa, place_sofa_boxes, sofa_spec
    from interior.planners.living_room_planner import plan_living
    plan = plan_living(con, room_id)
    if not plan.get("plan"):
        # sem parede util no comodo (raríssimo): NAO flutua moveis — sala vazia e
        # honesto, sofa flutuando nao. O degrade do plan_living ja garante plano
        # ANCORADO (WARN) p/ sala apertada; o brain antigo FLUTUANTE foi removido.
        return [], {"result": plan.get("result"), "room_name": plan.get("room_name"),
                    "placement": "no_plan_skip"}
    p = plan["plan"]
    sofa_c = tuple(p["sofa"]["center_in"]); sofa_f = tuple(p["sofa"]["facing"])
    rack_c = tuple(p["tv_rack"]["center_in"]); rack_f = tuple(p["tv_rack"]["facing"])
    width_m = round(p["sofa"]["width_m"], 3)
    # seats adaptados a largura que cabe no nicho (3-lug so se a parede comporta).
    _seats = 3 if width_m >= 2.0 else 2
    parts, _ = build_sofa(sofa_spec("straight", seats=_seats, width=width_m, depth=0.95))
    boxes = place_sofa_boxes(parts, sofa_c, sofa_f)         # sofa de frente pra TV
    for _b in boxes:                                        # cada movel = modulo editavel separado
        _b["module"] = "Sofa"
    # mesa + tapete AGRUPADOS perto do sofa (nao esticados ate o rack); rack na parede-TV
    import math as _m
    fnx, fny = sofa_f
    _fn = _m.hypot(fnx, fny) or 1.0
    fnx, fny = fnx / _fn, fny / _fn
    M2IN = 39.3700787402

    def _ahead(dist_m):                                     # ponto 'dist_m' a frente do sofa
        return (sofa_c[0] + fnx * dist_m * M2IN, sofa_c[1] + fny * dist_m * M2IN)

    # rack na parede-TV: o plan_living ja o posiciona FRENTE-A-FRENTE com o sofa,
    # centrado no nicho (sem a projecao antiga que o empurrava pra boca/corredor).
    # COMPACTO (Felipe: "diminuir o rack; tava tomando o corredor"): largura modesta
    # (~ largura do sofa, teto 1.20m) e raso (0.35), flush na parede — apê pequeno
    # pede movel compacto que nao rouba circulacao.
    from interior.semantics.wall_affordance import wall_affordance
    _aff = wall_affordance(con, room_id)
    _rack_wall_len = next((w["length_m"] for w in _aff["walls"]
                           if w["wall_id"] == p["tv_rack"]["wall_id"]), 1.80)
    rack_w = round(min(1.20, max(0.90, min(width_m, _rack_wall_len - 0.40))), 2)
    if os.environ.get("FURNISH_STYLE") == "industrial":
        # RACK = MÓVEL PLANEJADO real (rack_class PASS): pés/corpo/tampo/gavetas/nicho,
        # derivado da TV + linha de visão. NÃO mais caixa. low_credenza preto+madeira.
        # Gated industrial p/ não regredir o render default. place_sofa_boxes orienta (parts em m).
        from tools.rack_class import build_rack, derive_rack_spec
        _rlen = round(min(1.55, max(1.30, _rack_wall_len - 0.35)), 2)
        _rspec = derive_rack_spec("55", "low_credenza", length=_rlen,
                                  body_rgb=(60, 47, 36), front_rgb=(80, 62, 46), feet_rgb=(26, 26, 28))
        _rparts, _ = build_rack(_rspec)
        _rb = place_sofa_boxes(_rparts, rack_c, rack_f)
        for _b in _rb:
            _b["module"] = "Rack TV"
        boxes += _rb
    else:
        boxes.append(_oriented_box("rack_tv", rack_c, rack_f, rack_w, 0.35, 0.0, 0.50, [120, 85, 55], module="Rack TV"))
    # tapete + mesa COMPACTOS, agrupados perto do sofa (nao transbordam o nicho).
    boxes.append(_oriented_box("tapete", _ahead(0.70), sofa_f, 1.60, 1.10, 0.0, 0.02, [165, 156, 140], module="Tapete"))
    if os.environ.get("FURNISH_STYLE") == "industrial":
        # MESA DE CENTRO = classe planejada (coffee_table_class PASS): tampo madeira +
        # pernas metal preto + prateleira inferior. NÃO mais caixa.
        from tools.coffee_table_class import CoffeeTableClassSpec, build_coffee_table_v2
        _ct = CoffeeTableClassSpec(style="two_tier", length=0.95, width=0.50, height=0.38,
                                   shelf=True, top_rgb=(80, 62, 46), leg_rgb=(30, 30, 33))
        _ctp, _ = build_coffee_table_v2(_ct.validate())
        _ctb = place_sofa_boxes(_ctp, _ahead(0.80), sofa_f)
        for _b in _ctb:
            _b["module"] = "Mesa de centro"
        boxes += _ctb
    else:
        boxes.append(_oriented_box("mesa_centro", _ahead(0.80), sofa_f, 0.90, 0.50, 0.0, 0.40, [92, 72, 56], module="Mesa de centro"))

    # ---- camada de ESTILO (gated): parede de concreto na parede-TV + decor reusando
    # os builders que JA existem (planta, quadro). So adiciona; cor entra via apply_style.
    style = os.environ.get("FURNISH_STYLE")
    if style == "industrial":
        from shapely.geometry import Point, Polygon

        from core.scale import PT_TO_IN
        from tools.spatial_model import build_spatial_model
        cell_in = Polygon([(x * PT_TO_IN, y * PT_TO_IN)
                           for x, y in build_spatial_model(con, room_id)["_geom"]["cell"].exterior.coords])
        cen = cell_in.centroid

        def _inside(pt, margin_in=9.0):
            p = Point(pt)
            return cell_in.contains(p) and cell_in.exterior.distance(p) >= margin_in

        def _toward_centroid(start, frac0=0.35):
            """Ponto entre start e o centroide, recuado ate ficar DENTRO com margem
            (decor nunca atravessa parede / sai do comodo em L)."""
            frac = frac0
            for _ in range(9):
                pt = (start[0] + (cen.x - start[0]) * frac, start[1] + (cen.y - start[1]) * frac)
                if _inside(pt):
                    return pt
                frac += 0.08
            return (cen.x, cen.y) if _inside((cen.x, cen.y)) else None

        rfx, rfy = rack_f
        _rn = _m.hypot(rfx, rfy) or 1.0
        rfx, rfy = rfx / _rn, rfy / _rn
        # parede de concreto ATRAS do rack (recuada ~0.19m contra o facing = na parede)
        wall_c = (rack_c[0] - rfx * 0.19 * M2IN, rack_c[1] - rfy * 0.19 * M2IN)
        wall_w = round(min(_rack_wall_len, 3.6), 2)
        boxes.append(_oriented_box("parede_concreto", wall_c, rack_f, wall_w, 0.04, 0.0, 2.40,
                                   [165, 162, 158], module="Parede concreto"))
        # planta PEQUENA sobre o RACK (acento de verde no móvel, como a referência) —
        # no apê apertado não sobra piso livre p/ planta grande sem colidir. Vai numa
        # ponta do rack (fora do centro da TV), apoiada no tampo (z_lift = altura do rack).
        rperp = (-rfy, rfx)
        plant_c = (rack_c[0] + rperp[0] * 0.50 * M2IN, rack_c[1] + rperp[1] * 0.50 * M2IN)
        if _inside(plant_c, margin_in=2.0):
            boxes += place_decor_boxes("plant_placeholder", plant_c, rack_f, z_lift=0.52,
                                       height=0.55, pot_w=0.16, pot_h=0.10, foliage_w=0.30,
                                       module="Planta")
        # quadro emoldurado na parede de concreto, acima do rack (z_lift = altura do olho)
        art_c = (wall_c[0] + rfx * 0.04 * M2IN, wall_c[1] + rfy * 0.04 * M2IN)
        boxes += place_decor_boxes("wall_art", art_c, rack_f, z_lift=1.15, module="Quadro",
                                   width=0.90, height=0.62)
        # prateleira flutuante metal+madeira na parede de concreto (lado oposto ao quadro)
        perp = (-rfy, rfx)
        shelf_c = (wall_c[0] + perp[0] * 0.45 * M2IN + rfx * 0.14 * M2IN,
                   wall_c[1] + perp[1] * 0.45 * M2IN + rfy * 0.14 * M2IN)
        if _inside(shelf_c, margin_in=4.0):
            boxes += place_decor_boxes("shelf", shelf_c, rack_f, z_lift=1.42, module="Prateleira",
                                       width=0.85, n_planks=2)
        # trilho de luz no TETO sobre o eixo sofa->rack (corre ao longo do eixo)
        mid = ((sofa_c[0] + rack_c[0]) / 2.0, (sofa_c[1] + rack_c[1]) / 2.0)
        track_face = (-fny, fnx)                 # perp ao facing do sofa -> trilho ao longo do eixo
        boxes += place_decor_boxes("track_light", mid, track_face, z_lift=2.15, module="Trilho de luz",
                                   length=1.5, n_spots=3)
        # MESA DE JANTAR (lado jantar): na maior zona LIVRE da sala, longe do cluster de estar.
        from shapely.ops import unary_union as _uni
        _occ = [Polygon([(c[0], c[1]) for c in _b["corners"]]) for _b in boxes if _b.get("corners")]
        _free = cell_in.buffer(-M2IN * 0.12).difference(_uni([p.buffer(M2IN * 0.32) for p in _occ]))
        if _free.geom_type == "MultiPolygon":
            _free = max(_free.geoms, key=lambda g: g.area)
        if (not _free.is_empty) and _free.area > (2.4 * M2IN * M2IN):
            _dc = _free.centroid
            from tools.dining_table_class import DiningTableSpec, build_dining_table
            _dt = DiningTableSpec(shape="round", seats=4, length=0.92, width=0.92, height=0.75,
                                  top_rgb=(92, 68, 46), base_rgb=(30, 30, 33))
            _dtp, _ = build_dining_table(_dt.validate())
            _dtb = place_sofa_boxes(_dtp, (_dc.x, _dc.y), (0.0, 1.0))
            for _b in _dtb:
                _b["module"] = "Mesa de jantar"
            boxes += _dtb
            _nch = 0
            for _ang in range(0, 360, 45):                 # 8 direções; pega as que cabem
                _ux, _uy = _m.cos(_m.radians(_ang)), _m.sin(_m.radians(_ang))
                _chc = (_dc.x + _ux * 0.70 * M2IN, _dc.y + _uy * 0.70 * M2IN)
                _pt = Point(_chc)
                if cell_in.contains(_pt) and cell_in.exterior.distance(_pt) >= 4:
                    _chb = place_sofa_boxes(_chair_parts(), _chc, (-_ux, -_uy))
                    for _b in _chb:
                        _b["module"] = "Cadeira jantar"
                    boxes += _chb
                    _nch += 1
                    if _nch >= 4:
                        break

    out = {"result": "OK", "room_name": plan.get("room_name"), "n_placed": len(boxes),
           "placement": "common_sense_solver", "tv_wall": plan.get("tv_wall"),
           "sofa_wall": p["sofa"]["wall_id"], "view_dist_m": p["sofa"]["rule"]}
    return boxes, out


# dispatch por tipo de comodo (cresce conforme novos brains entram)
BRAINS = {BEDROOM: bedroom_designer_boxes, KITCHEN: kitchen_boxes, LIVING: living_room_boxes,
          BATHROOM: bath_boxes}


def collect_boxes(con):
    """Junta os boxes de TODOS os comodos com brain disponivel. Devolve
    (boxes, summary[(id,name,type,result,n_boxes)])."""
    rooms = classify_rooms(con)
    all_boxes, summary = [], []
    for r in rooms:
        brain = BRAINS.get(r["room_type"])
        if brain is None:
            summary.append((r["id"], r["name"], r["room_type"], "skip(sem brain)", 0))
            continue
        boxes, out = brain(con, r["id"])
        for b in (boxes or []):              # cada box leva COMODO + MODULO -> grupos editaveis no .skp
            b["room"] = str(r.get("name") or r["id"])
            b.setdefault("module", str(b.get("kind", "movel")))
        n = len(boxes) if boxes else 0
        all_boxes += boxes or []
        summary.append((r["id"], r["name"], r["room_type"], out.get("result"), n))
    # camada de ESTILO (gated): recolore por kind = fonte unica do material SU ph_<kind>,
    # ANTES de qualquer serializacao LAYOUT_BOXES. Kind fora do mapa fica intacto.
    style = os.environ.get("FURNISH_STYLE")
    if style:
        from tools.style_spec import apply_style
        nrec = apply_style(all_boxes, style)
        print(f"[furnish-apt] estilo '{style}': {nrec} boxes recoloridos")
    return all_boxes, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, summary = collect_boxes(con)
    n_rooms = sum(1 for s in summary if s[4])
    print(f"[furnish-apt] {len(boxes)} placeholders em {n_rooms} comodo(s):")
    for rid, name, rt, res, n in summary:
        print(f"  {str(rid):5} {str(name)[:28]:28} {rt:9} {str(res):16} {n} boxes")
    if args.dry_run or not boxes:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skp_out = OUT_DIR / "planta_74_furnished.skp"
    before = OUT_DIR / "planta_74_furnished_before_top.png"
    after_top = OUT_DIR / "planta_74_furnished_after_top.png"
    after_iso = OUT_DIR / "planta_74_furnished_after_iso.png"
    log_path = OUT_DIR / "planta_74_furnished_log.txt"
    # mata o SketchUp ANTES de apagar os arquivos (senao o .skp fica travado)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    for p in (skp_out, before, after_top, after_iso, log_path):
        try:
            if p.exists():
                p.unlink()
        except PermissionError:
            pass

    env = os.environ.copy()
    env["LAYOUT_BOXES"] = json.dumps(boxes)
    env["LAYOUT_OUT"] = str(skp_out).replace("\\", "/")
    env["LAYOUT_BEFORE"] = str(before).replace("\\", "/")
    env["LAYOUT_AFTER_TOP"] = str(after_top).replace("\\", "/")
    env["LAYOUT_AFTER_ISO"] = str(after_iso).replace("\\", "/")
    env["LAYOUT_LOG"] = str(log_path).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    cmd = [SKETCHUP_EXE, str(BASE_SKP), "-RubyStartup", str(RB)]
    print("[furnish-apt] launching SU...")
    subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if log_path.exists():
        print("[furnish-apt] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[furnish-apt] TIMEOUT — SU nao produziu log")
        sys.exit(1)
    print(f"\n[furnish-apt] -> {OUT_DIR}/")
    print(f"  SKP:   {skp_out.name}")
    print(f"  AFTER: {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
