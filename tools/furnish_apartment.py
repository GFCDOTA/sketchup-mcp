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
# Escala verificada da planta_74 (cota-anchored; core.scale.PLANT_PT_TO_M["planta_74"])
# DEVE ser setada ANTES de core.scale ser importado pelos brains abaixo. Sem isso o
# placement cai no default 0.0352 e a mobilia flutua ~1.36x FORA do shell 0.0259
# (top render: comodos embaixo, moveis soltos em cima). core.scale congela PT_TO_M no
# 1o import, entao nao da pra corrigir depois. Este pipeline e planta_74-only.
if not os.environ.get("PT_TO_M"):
    os.environ["PT_TO_M"] = "0.0259"
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
PLANT = "planta_74"   # pipeline planta_74-only (mesmo escopo do resto do modulo)


def _gallery_corpus_root() -> Path:
    """Raiz do corpus de galeria = a MESMA do variant_sweep/feeder
    (data/runs/noc_variant_sweep sob a raiz do WORKSPACE), pra o apê mobiliado
    virar mais um item da UNICA galeria que a curadoria/RAG ja leem — nao um
    silo paralelo. Fallback repo-relativo se a raiz do workspace nao resolver."""
    try:
        from tools.claude_bridge._paths import WORKSPACE_ROOT
        return WORKSPACE_ROOT / "data" / "runs" / "noc_variant_sweep"
    except Exception:  # noqa: BLE001 — checkout solto / sem apps+ops: repo-relativo
        return ROOT / "data" / "runs" / "noc_variant_sweep"


GALLERY_CORPUS_ROOT = _gallery_corpus_root()

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
        parts, _ = build_bed(bed_spec(size, width=round(w_m, 3), length=round(l_m, 3),
                                      headboard_style="upholstered"))
        bed_parts = place_bed_boxes(parts, cen, (fx, fy))
        for _b in bed_parts:
            _b["module"] = "Cama"
        # a anatomia do build_bed JA tem a 'cabeceira'; o 'headboard' do designer vira
        # PAINEL RIPADO nogueira (diretriz suítes 2026-08-03) — não some mais.
        boxes = [b for b in boxes if b.get("kind") not in ("bed", "headboard")] + bed_parts
        out["bed_parametric"] = {"size": size, "n_parts": len(bed_parts),
                                 "W_m": round(w_m, 2), "L_m": round(l_m, 2)}
        # PAINEL RIPADO de cabeceira (gramática da cozinha: sulco-sombra desenha) +
        # LED 2700K no topo + ARANDELAS com aro bronze (só master; o único ouro).
        hb_item = next((it for it in items if it.get("type") == "headboard"), None)
        _area = float(out.get("area_m2") or (sm or {}).get("area_m2") or 0)
        _is_master = _area >= 18
        if hb_item is not None:
            pw_m, _pd_m, pcen = _wd_dims(hb_item["box"], (fx, fy))
            ph_m = 2.20 if _is_master else 1.60
            boxes.append(_oriented_box("ks_painel_base", pcen, (fx, fy), pw_m, 0.05, 0.0,
                                       ph_m, [56, 42, 30], module="Painel cabeceira"))
            import math as _mm
            _fn = _mm.hypot(fx, fy) or 1.0
            _ux, _uy = fx / _fn, fy / _fn
            _px, _py = -_uy, _ux                       # eixo ao longo da parede
            M2IN_ = 39.3700787402
            _n_ripas = max(8, int(pw_m / 0.08))
            for _i in range(_n_ripas):
                _off = (_i + 0.5) / _n_ripas * pw_m - pw_m / 2
                _rc = (pcen[0] + _px * _off * M2IN_ + _ux * 0.02 * M2IN_,
                       pcen[1] + _py * _off * M2IN_ + _uy * 0.02 * M2IN_)
                boxes.append(_oriented_box("ks_ripa", _rc, (fx, fy), 0.06, 0.025, 0.0,
                                           ph_m, [108, 80, 58], module="Painel cabeceira"))
            boxes.append(_oriented_box("ks_led", (pcen[0] + _ux * 0.045 * M2IN_, pcen[1] + _uy * 0.045 * M2IN_),
                                       (fx, fy), pw_m - 0.15, 0.02, ph_m - 0.04, 0.02,
                                       [255, 250, 232], module="Painel cabeceira"))
            if _is_master:
                for _side in (-1, 1):
                    _aoff = _side * (w_m / 2 + 0.30)
                    _ac = (pcen[0] + _px * _aoff * M2IN_ + _ux * 0.09 * M2IN_,
                           pcen[1] + _py * _aoff * M2IN_ + _uy * 0.09 * M2IN_)
                    boxes.append(_oriented_box("ks_arandela", _ac, (fx, fy), 0.14, 0.16, 1.28,
                                               0.14, [28, 28, 30], module="Arandela"))
                    boxes.append(_oriented_box("ks_bronze", _ac, (fx, fy), 0.15, 0.14, 1.26,
                                               0.018, [171, 119, 63], module="Arandela"))
            else:
                # suíte pequena: o único bronze mora num friso fino do painel
                # (o guarda-roupa pode nem caber no cômodo — 8m² reais)
                boxes.append(_oriented_box("ks_bronze", (pcen[0] + _ux * 0.05 * M2IN_,
                                                         pcen[1] + _uy * 0.05 * M2IN_),
                                           (fx, fy), 0.30, 0.02, 0.92, 0.02,
                                           [171, 119, 63], module="Painel cabeceira"))

    # CRIADOS SUSPENSOS handleless (diretriz suítes 2026-08-03): morre o builder de
    # pés+knob — corpo grafite flutuando (0.32-0.52) + gola sombra + tampo nogueira
    # proud + LED 2700K por baixo (eco under_cabinet_led).
    ns_items = [it for it in items if it.get("type") == "nightstand"]
    if ns_items:
        ns_boxes, n_ns = [], 0
        for it in ns_items:
            nw, nd, ncen = _wd_dims(it["box"], bed_facing)
            nw, nd = round(max(nw, 0.40), 3), round(max(nd, 0.34), 3)
            n_ns += 1
            _mod = f"Criado-mudo {n_ns}"
            _cb = [
                _oriented_box("ks_criado_corpo", ncen, bed_facing, nw, nd, 0.32, 0.20,
                              [30, 31, 32], module=_mod),
                _oriented_box("ks_criado_frente", ncen, bed_facing, nw - 0.03, nd + 0.006, 0.335, 0.165,
                              [44, 45, 47], module=_mod),
                _oriented_box("ks_gola", ncen, bed_facing, nw - 0.07, nd + 0.008, 0.322, 0.012,
                              [24, 24, 24], module=_mod),
                _oriented_box("ks_criado_tampo", ncen, bed_facing, nw + 0.02, nd + 0.02, 0.52, 0.025,
                              [118, 90, 66], module=_mod),
                _oriented_box("ks_led", ncen, bed_facing, nw - 0.06, nd - 0.06, 0.30, 0.014,
                              [255, 250, 232], module=_mod),
            ]
            ns_boxes += _cb
        boxes = [b for b in boxes if b.get("kind") != "nightstand"] + ns_boxes
        out["nightstand_parametric"] = {"count": n_ns, "n_parts": len(ns_boxes), "floating": True}

    # GUARDA-ROUPA golden (corpo+portas+puxadores+rodape) no mesmo footprint/facing (portas
    # viram p/ dentro do quarto). Troca o bloco roxo liso 'wardrobe'.
    wd_item = next((it for it in items if it.get("type") == "wardrobe"), None)
    if wd_item is not None:
        wfx, wfy = _wd_facing(wd_item)
        ww_m, wd_m, wcen = _wd_dims(wd_item["box"], (wfx, wfy))
        wparts, _ = build_wardrobe(wardrobe_spec(width=round(ww_m, 3), depth=round(max(wd_m, 0.45), 3)))
        wboxes = place_wardrobe_boxes(wparts, wcen, (wfx, wfy))
        # HANDLELESS até o TETO (diretriz suítes): mata a barra de puxador; recolor
        # por papel (carcaça escura x porta por suíte); maleiro 2.20->2.69 com junta
        # sombra; gola contínua no rodapé das portas; S02 leva o bronze na gola central.
        _area_w = float(out.get("area_m2") or (sm or {}).get("area_m2") or 0)
        _porta_rgb = [44, 45, 47] if _area_w >= 18 else [108, 80, 58]
        wboxes = [b for b in wboxes if b.get("kind") != "puxador"]
        for _b in wboxes:
            _b["module"] = "Guarda-roupa"
            if _b["kind"] == "corpo":
                _b["rgb"] = [30, 31, 32]
            elif _b["kind"] == "porta":
                _b["rgb"] = _porta_rgb
            elif _b["kind"] == "rodape":
                _b["rgb"] = [18, 18, 20]
        _wtop = max(_b["z0_in"] + _b["h_in"] for _b in wboxes) / 39.3700787402
        if _wtop < 2.60:
            boxes_mal = [
                _oriented_box("ks_gola", wcen, (wfx, wfy), ww_m - 0.02, max(wd_m, 0.45), _wtop - 0.002, 0.014,
                              [24, 24, 24], module="Guarda-roupa"),
                _oriented_box("ks_maleiro", wcen, (wfx, wfy), ww_m, max(wd_m, 0.45), _wtop + 0.012,
                              2.69 - (_wtop + 0.012), _porta_rgb, module="Guarda-roupa"),
            ]
            wboxes += boxes_mal
        _pz0 = min((_b["z0_in"] for _b in wboxes if _b["kind"] == "porta"), default=None)
        if _pz0 is not None:
            wboxes.append(_oriented_box("ks_gola", wcen, (wfx, wfy), ww_m - 0.06, max(wd_m, 0.45) + 0.006,
                                        _pz0 / 39.3700787402 + 0.012, 0.012, [24, 24, 24], module="Guarda-roupa"))
        if _area_w < 18:
            wboxes.append(_oriented_box("ks_bronze", wcen, (wfx, wfy), 0.28,
                                        max(wd_m, 0.45) + 0.01, 1.10, 0.025, [171, 119, 63],
                                        module="Guarda-roupa"))
        boxes = [b for b in boxes if b.get("kind") != "wardrobe"] + wboxes
        out["wardrobe_parametric"] = {"n_parts": len(wboxes), "W_m": round(ww_m, 2),
                                      "D_m": round(wd_m, 2), "to_ceiling": True}
    # paleta ks_* nas peças herdadas dos builders golden (cores neutras -> diretriz)
    _KS_BY_KIND = {"estrado": [38, 39, 40], "colchao": [214, 202, 184],
                   "travesseiro": [222, 212, 196], "manta": [176, 128, 88],
                   "cabeceira": [172, 150, 124], "tapete": [122, 110, 98], "rug": [122, 110, 98]}
    for _b in boxes:
        _new = _KS_BY_KIND.get(str(_b.get("kind", "")))
        if _new:
            _b["rgb"] = _new
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


def _oct_in(kind, cx, cy, r_m, z0_m, h_m, rgb, module):
    """Disco octogonal flat em INCHES (cx,cy do shell) — leitura circular low-poly
    (cúpula de pendente; mesma gramática dos discos do cooktop)."""
    import math
    M2IN = 39.3700787402
    r = r_m * M2IN
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a))
           for a in (math.pi / 8 + i * math.pi / 4 for i in range(8))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"kind": kind, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": [[round(px, 2), round(py, 2)] for px, py in pts],
            "h_in": round(h_m * M2IN, 2), "z0_in": round(z0_m * M2IN, 2), "rgb": rgb,
            "label": kind, "module": module, "ambiguous": False, "decorative": False}


def _dining_table_rect(w=1.60, d=0.90, h=0.75, top_t=0.04, top_rgb=(108, 80, 58), leg_rgb=(30, 30, 33)):
    """Mesa de jantar RETANGULAR 6 lugares (1.60x0.90 real, joelho >=0.60): tampo
    sólido nogueira + saia + 4 pernas metal inset. Metros, origem no canto."""
    from tools.sofa_builder import _p
    lt, ins = 0.08, 0.05
    parts = [_p("top", "top", 0.0, 0.0, w, d, h - top_t, h, top_rgb)]
    parts.append(_p("apron", "saia", ins, ins, w - ins, d - ins, h - top_t - 0.10, h - top_t, leg_rgb))
    for x0, y0 in ((ins, ins), (w - ins - lt, ins), (ins, d - ins - lt), (w - ins - lt, d - ins - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, h - top_t, leg_rgb))
    return parts


def _dining_table_square(side=0.92, h=0.76, top_t=0.045, top_rgb=(96, 70, 48), leg_rgb=(30, 30, 33)):
    """Mesa de jantar QUADRADA: tampo SÓLIDO (não fatias/palito) + 4 pernas grossas +
    saia fina. Metros, origem no canto. (preferência do Felipe: quadrada/canto alemão)."""
    from tools.sofa_builder import _p
    lt, ins = 0.07, 0.05
    parts = [_p("top", "top", 0.0, 0.0, side, side, h - top_t, h, top_rgb)]          # tampo sólido
    sa = 0.07                                                                          # saia sob o tampo
    parts.append(_p("apron", "saia", ins, ins, side - ins, side - ins, h - top_t - sa, h - top_t, leg_rgb))
    for x0, y0 in ((ins, ins), (side - ins - lt, ins), (ins, side - ins - lt), (side - ins - lt, side - ins - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, h - top_t, leg_rgb))
    return parts


def _chair_parts():
    """Cadeira de jantar ESTOFADA (frame metal preto + assento/encosto grafite =
    tecido do sofá). Metros, frente = -Y (encosto em +Y). place_sofa_boxes orienta."""
    from tools.sofa_builder import _p
    w, d, sh, bh, lt = 0.45, 0.50, 0.45, 0.90, 0.028
    fabric, frame = (74, 72, 78), (26, 26, 29)
    parts = []
    for x0, y0 in ((0.02, 0.02), (w - 0.02 - lt, 0.02), (0.02, d - 0.02 - lt), (w - 0.02 - lt, d - 0.02 - lt)):
        parts.append(_p("leg", "foot", x0, y0, x0 + lt, y0 + lt, 0.0, sh - 0.05, frame))
    parts.append(_p("seat_frame", "frame", 0.02, 0.02, w - 0.02, d - 0.02, sh - 0.05, sh - 0.03, frame))
    parts.append(_p("seat", "seat", 0.015, 0.015, w - 0.015, d - 0.015, sh - 0.03, sh + 0.02, fabric))
    parts.append(_p("back_frame", "frame", 0.03, d - 0.045, w - 0.03, d - 0.02, sh, bh - 0.02, frame))
    parts.append(_p("back", "back", 0.02, d - 0.06, w - 0.02, d - 0.038, sh + 0.10, bh, fabric))
    return parts


def _bwg_recolor(boxes):
    """Linguagem black_wood_gold (GOLDEN_SAMPLE_004) na SALA: madeira escura coordenada +
    preto/grafite controlado + tecido escuro + tapete neutro quente + LED quente. SO cor (rgb),
    NUNCA geometria/posicao -> o layout JA validado fica intacto. Coerente com a cozinha."""
    WOOD = [108, 80, 58]
    BLACK = [44, 44, 48]
    FABRIC = [74, 72, 78]
    RUG = [140, 128, 112]
    LED = [255, 240, 212]
    bk = ("foot", "leg", "perna", "pe", "frame", "base", "soculo", "bracket", "vidro", "boca", "door")
    fk = ("cushion", "seat", "back", "arm")
    wk = ("top", "corpo", "porta", "front", "body", "plank", "panel", "shelf", "tampo", "gaveta", "board", "stem")
    for b in boxes:
        mod = str(b.get("module", "")).lower()
        kind = str(b.get("kind", "")).lower()
        if kind.startswith(("rug_", "pend_", "tv_", "painel", "almofada", "lv_led")):
            continue                                        # peças novas já nascem na paleta certa
        if "spot" in kind:
            b["rgb"] = LED                                  # spot quente
        elif "rail" in kind or "trilho" in mod:
            b["rgb"] = BLACK                                # trilho preto
        elif "tapete" in mod:
            b["rgb"] = RUG
        elif "parede" in mod or "concreto" in mod:
            b["rgb"] = BLACK                                # painel de midia DARK (nao concreto claro)
        elif "planta" in mod or "foliage" in kind or "quadro" in mod:
            continue                                        # acento (verde/arte) — mantem
        elif "sofa" in mod:
            b["rgb"] = BLACK if any(k in kind for k in bk) else FABRIC
        elif "cadeira" in mod:
            b["rgb"] = BLACK if any(k in kind for k in bk) else FABRIC   # estofado = tecido do sofá
        elif any(k in kind for k in bk):
            b["rgb"] = BLACK
        elif any(k in kind for k in wk):
            b["rgb"] = WOOD
        elif any(k in kind for k in fk):
            b["rgb"] = FABRIC
    return boxes


def living_room_boxes(con, room_id):
    """Sala via COMMON SENSE ENGINE (placement solver): o sofa GOLDEN deixa de
    flutuar no centro — fica ANCORADO numa parede de FRENTE pra TV (eixo sofa->rack),
    fora da circulacao; rack de MADEIRA na parede-TV (limpa), mesa de centro + tapete
    no eixo entre os dois. Corrige o veredito do GPT (objeto PASS, placement FAIL):
    o solver rejeita sofa em circulacao / sem eixo pra TV. Fallback: brain antigo."""
    from tools.sofa_builder import build_sofa, place_sofa_boxes
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
    # FASE 1 do laco classe->.skp: a CLASSE escolhe os LUGARES (per_seat na faixa) e o
    # sofa nasce do arquetipo VENEZIA curado pelo Felipe (sofa-ref-02 venezia-slate main:
    # bracos finos + pes de ferro). Substitui a heuristica `3 se w>=2.0 senao 2` que
    # esticava per_seat fora da classe (defeito que a Fase 0 revelou). So a largura e'
    # fixada ao nicho; o resto e' in-class por construcao.
    from tools.sofa_class import derive_living_sofa, sofa_class_gate
    _sofa_spec = derive_living_sofa(width_m)
    parts, _ = build_sofa(_sofa_spec)
    # gate de classe no caminho REAL (Fase 0): agora o sofa nasce in-class, entao isto e'
    # guarda-corpo contra REGRESSAO futura (ex.: mexer no arquetipo). WARN-log, nao aborta.
    _sgate = sofa_class_gate(_sofa_spec, parts)
    if _sgate["result"] != "PASS":
        _why = "; ".join(_sgate["errors"] or _sgate["warnings"]) or "(sem detalhe)"
        print(f"[furnish-apt] sofa_class_gate => {_sgate['result']} (WARN-log, nao aborta): {_why}")
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
    # RACK = painel/credenza PLANEJADO ancorado na parede-TV (planned_niche_system, NUNCA cubo proxy).
    # LIVING_ROOM_LAYOUT_FIX_OPTION_A: a FORMA entra SEMPRE (sai do proxy); a cor é neutra no baseline
    # e escura só sob FURNISH_STYLE (a estética black_wood_gold entra numa fase posterior).
    from tools.rack_class import build_rack, derive_rack_spec
    # BLACK_WOOD_GOLD DIRETO (programa apê-inteiro 2026-08-03): a sala nasce
    # estilizada como a cozinha — a estética não depende mais de FURNISH_STYLE.
    _rlen = round(min(1.55, max(1.30, _rack_wall_len - 0.35)), 2)
    _rspec = derive_rack_spec("55", "low_credenza", length=_rlen,
                              body_rgb=(38, 39, 40), front_rgb=(44, 45, 47),
                              feet_rgb=(26, 26, 28))
    _rparts, _ = build_rack(_rspec)
    rfx, rfy = rack_f
    _rn2 = _m.hypot(rfx, rfy) or 1.0
    rfx, rfy = rfx / _rn2, rfy / _rn2
    # rack avança 7cm pra abrir espaço pro PAINEL na parede (sem interseção)
    _rack_c2 = (rack_c[0] + rfx * 0.07 * M2IN, rack_c[1] + rfy * 0.07 * M2IN)
    _rb = place_sofa_boxes(_rparts, _rack_c2, rack_f)
    for _b in _rb:
        _b["module"] = "Rack TV"
    boxes += _rb
    # PAINEL DE TV em NOGUEIRA (SEMPRE — substitui o proxy gated 'parede_concreto'):
    # é o fundo que faz rack+TV lerem como estar planejado. Fita LED 2700K no topo.
    _pan_w = round(max(1.80, min(_rack_wall_len - 0.10, 2.60)), 2)
    _pan_c = (rack_c[0] - rfx * 0.15 * M2IN, rack_c[1] - rfy * 0.15 * M2IN)
    boxes.append(_oriented_box("painel_tv", _pan_c, rack_f, _pan_w, 0.05, 0.0, 2.40,
                               [92, 64, 46], module="Painel TV"))
    boxes.append(_oriented_box("lv_led", (_pan_c[0] + rfx * 0.033 * M2IN, _pan_c[1] + rfy * 0.033 * M2IN),
                               rack_f, _pan_w - 0.20, 0.016, 2.32, 0.02, [255, 250, 232], module="Painel TV"))
    # TV 55" REAL em produção (era só proxy na matriz do juiz): moldura fina +
    # vidro preto profundo — o preto mais escuro do ambiente, montada no painel.
    _tv_c = (_pan_c[0] + rfx * 0.045 * M2IN, _pan_c[1] + rfy * 0.045 * M2IN)
    boxes.append(_oriented_box("tv_frame", _tv_c, rack_f, 1.27, 0.025, 0.735, 0.73, [22, 22, 26], module="TV"))
    boxes.append(_oriented_box("tv_glass", (_tv_c[0] + rfx * 0.014 * M2IN, _tv_c[1] + rfy * 0.014 * M2IN),
                               rack_f, 1.23, 0.012, 0.755, 0.69, [16, 16, 18], module="TV"))
    # almofadas soltas no sofá (decor mínimo, pontuação não frase)
    for _adx, _aang in ((-0.55, 12), (0.55, -12)):
        _af = (fnx * _m.cos(_m.radians(_aang)) - fny * _m.sin(_m.radians(_aang)),
               fnx * _m.sin(_m.radians(_aang)) + fny * _m.cos(_m.radians(_aang)))
        _ac = (sofa_c[0] - fnx * 0.18 * M2IN + (-fny) * _adx * M2IN,
               sofa_c[1] - fny * 0.18 * M2IN + fnx * _adx * M2IN)
        boxes.append(_oriented_box("almofada", _ac, _af, 0.45, 0.14, 0.47, 0.45,
                                   [96, 88, 76], module="Sofa"))
    # tapete COM BORDA (campo + moldura 8cm mais escura — deixa de ser laje)
    boxes.append(_oriented_box("rug_border", _ahead(0.70), sofa_f, 1.80, 1.20, 0.0, 0.018, [96, 88, 76], module="Tapete"))
    boxes.append(_oriented_box("rug_field", _ahead(0.70), sofa_f, 1.64, 1.04, 0.0, 0.02, [140, 128, 112], module="Tapete"))
    # MESA DE CENTRO: tampo pedra preta (eco do tampo da cozinha) + pernas metal
    from tools.coffee_table_class import CoffeeTableClassSpec, build_coffee_table_v2
    _ct = CoffeeTableClassSpec(style="two_tier", length=0.95, width=0.50, height=0.38, shelf=True,
                               top_rgb=(30, 29, 32), leg_rgb=(26, 26, 28))
    _ctp, _ = build_coffee_table_v2(_ct.validate())
    _ctb = place_sofa_boxes(_ctp, _ahead(0.80), sofa_f)
    for _b in _ctb:
        _b["module"] = "Mesa de centro"
    boxes += _ctb

    # cell + helper (SEMPRE — jantar e decor usam o polígono do cômodo)
    from shapely.geometry import Point, Polygon

    from core.scale import PT_TO_IN
    from tools.spatial_model import build_spatial_model
    cell_in = Polygon([(x * PT_TO_IN, y * PT_TO_IN)
                       for x, y in build_spatial_model(con, room_id)["_geom"]["cell"].exterior.coords])
    cen = cell_in.centroid

    def _inside(pt, margin_in=9.0):
        p = Point(pt)
        return cell_in.contains(p) and cell_in.exterior.distance(p) >= margin_in

    # ---- ZONA DE JANTAR (SEMPRE — forma/zona, NÃO estética). Mesa COMPACTA p/ 4 (apê 74m²,
    # nada de trambolho); na maior zona LIVRE longe do estar; NÃO bloqueia porta/passagem
    # (geometry_sanity + overlap conferem). LIVING_ROOM_LAYOUT_FIX_OPTION_A.
    from shapely.ops import unary_union as _uni
    _occ = [Polygon([(c[0], c[1]) for c in _b["corners"]]) for _b in boxes if _b.get("corners")]
    _free = cell_in.buffer(-M2IN * 0.12).difference(_uni([p.buffer(M2IN * 0.32) for p in _occ]))
    if _free.geom_type == "MultiPolygon":
        _free = max(_free.geoms, key=lambda g: g.area)
    if (not _free.is_empty) and _free.area > (2.4 * M2IN * M2IN):
        _dc = _free.centroid
        # MESA RETANGULAR 6 LUGARES real (1.60x0.90, tampo nogueira = painel TV,
        # pernas metal) — a quadrada de 4 saiu; cadeiras em posições de MESA
        # (2+2 laterais + 2 cabeceiras), não radiais.
        _dtp = _dining_table_rect(w=1.60, d=0.90, top_rgb=(108, 80, 58), leg_rgb=(30, 30, 33))
        _dtb = place_sofa_boxes(_dtp, (_dc.x, _dc.y), (0.0, 1.0))
        for _b in _dtb:
            _b["module"] = "Mesa de jantar"
        boxes += _dtb
        _chair_spots = [(-0.38, 0.72, (0.0, -1.0)), (0.38, 0.72, (0.0, -1.0)),
                        (-0.38, -0.72, (0.0, 1.0)), (0.38, -0.72, (0.0, 1.0)),
                        (-1.08, 0.0, (1.0, 0.0)), (1.08, 0.0, (-1.0, 0.0))]
        for _dx, _dy, _cf in _chair_spots:
            _chc = (_dc.x + _dx * M2IN, _dc.y + _dy * M2IN)
            _pt = Point(_chc)
            if cell_in.contains(_pt) and cell_in.exterior.distance(_pt) >= 4:
                _chb = place_sofa_boxes(_chair_parts(), _chc, _cf)
                for _b in _chb:
                    _b["module"] = "Cadeira jantar"
                boxes += _chb
        # PENDENTE sobre a mesa: cúpula octogonal preta + cabo — e o ÚNICO ponto
        # de bronze da sala no anel da cúpula (regra global: 1 bronze por ambiente;
        # a célula open-plan é UM campo visual, o estar recebe zero).
        boxes.append(_oriented_box("pend_cabo", (_dc.x, _dc.y), (0.0, 1.0),
                                   0.015, 0.015, 2.10, 0.60, [26, 26, 28], module="Pendente"))
        boxes.append(_oct_in("pend_cupula", _dc.x, _dc.y, 0.20, 1.85, 0.25, [30, 31, 32], "Pendente"))
        boxes.append(_oct_in("pend_bronze", _dc.x, _dc.y, 0.206, 1.842, 0.010, [171, 119, 63], "Pendente"))

    # ---- camada de ESTILO (gated, AESTHETIC — NÃO entra no layout-fix): parede de concreto na
    # parede-TV + decor (planta/quadro/prateleira/trilho). Só sob FURNISH_STYLE.
    style = os.environ.get("FURNISH_STYLE")
    if style in ("industrial", "modern_warm"):

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
        rperp = (-rfy, rfx)
        plant_c = (rack_c[0] + rperp[0] * 0.50 * M2IN, rack_c[1] + rperp[1] * 0.50 * M2IN)
        if _inside(plant_c, margin_in=2.0):
            boxes += place_decor_boxes("plant_placeholder", plant_c, rack_f, z_lift=0.52,
                                       height=0.55, pot_w=0.16, pot_h=0.10, foliage_w=0.30,
                                       module="Planta")
        art_c = (wall_c[0] + rfx * 0.04 * M2IN, wall_c[1] + rfy * 0.04 * M2IN)
        boxes += place_decor_boxes("wall_art", art_c, rack_f, z_lift=1.15, module="Quadro",
                                   width=0.90, height=0.62)
        perp = (-rfy, rfx)
        shelf_c = (wall_c[0] + perp[0] * 0.45 * M2IN + rfx * 0.14 * M2IN,
                   wall_c[1] + perp[1] * 0.45 * M2IN + rfy * 0.14 * M2IN)
        if _inside(shelf_c, margin_in=4.0):
            boxes += place_decor_boxes("shelf", shelf_c, rack_f, z_lift=1.42, module="Prateleira",
                                       width=0.85, n_planks=2)
        mid = ((sofa_c[0] + rack_c[0]) / 2.0, (sofa_c[1] + rack_c[1]) / 2.0)
        track_face = (-fny, fnx)                 # perp ao facing do sofa -> trilho ao longo do eixo
        boxes += place_decor_boxes("track_light", mid, track_face, z_lift=2.15, module="Trilho de luz",
                                   length=1.5, n_spots=3)

    # LINGUAGEM black_wood_gold SEMPRE (programa apê-inteiro): só cor, layout intacto.
    _bwg_recolor(boxes)

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
        # GATE DE FIDELIDADE: a pia da cozinha é ponto hidráulico do PDF (parede oeste).
        # Falha o build ANTES de render se a pia migrar (Felipe: KITCHEN_PDF_ANCHOR_FIX).
        if r["room_type"] == KITCHEN:
            from tools.kitchen_validation import validate as _kval
            kv = _kval(con, r["id"])
            print("\n".join(kv["lines"]))
            print(f"kitchen_validation => {kv['result']}\n")
            if kv["result"] != "PASS":
                raise SystemExit(f"[furnish-apt] BUILD ABORTADO: cozinha reprovou o anchor da pia ({kv['checks'].get('sink_wall')})")
        for b in (boxes or []):              # cada box leva COMODO + MODULO -> grupos editaveis no .skp
            b["room"] = str(r.get("name") or r["id"])
            b.setdefault("module", str(b.get("kind", "movel")))
        # GUARD anti-regressao (wet room): banheiro so aceita kinds de LOUCA. Se um movel de
        # quarto/sala vazar pra ca, LOGA (nao aborta) -> pega regressao futura de roteamento.
        if r["room_type"] == BATHROOM:
            _WET = {"gabinete", "bancada_banho", "cuba", "espelho", "vaso", "box_vidro", "box"}
            estranhos = sorted({str(b.get("kind")) for b in (boxes or []) if str(b.get("kind")) not in _WET})
            if estranhos:
                print(f"[furnish-apt] WARN wet-room {r['name']!r}: kind(s) fora da louca -> {estranhos}")
        n = len(boxes) if boxes else 0
        all_boxes += boxes or []
        summary.append((r["id"], r["name"], r["room_type"], out.get("result"), n))
    # camada de ESTILO (gated): recolore por kind = fonte unica do material SU ph_<kind>,
    # ANTES de qualquer serializacao LAYOUT_BOXES. Kind fora do mapa fica intacto.
    style = os.environ.get("FURNISH_STYLE")
    if style:
        from tools.style_spec import apply_style, attach_materials
        nrec = apply_style(all_boxes, style)
        print(f"[furnish-apt] estilo '{style}': {nrec} boxes recoloridos")
        # FP-037: resolve material por (familia_de_modulo, kind) e anexa por box. Destrava madeira
        # no rack/mesa (kinds base/top/front) SEM contaminar o sofa (sofa.base = flat/grafite).
        ntex = attach_materials(all_boxes, style)
        print(f"[furnish-apt] material por modulo: {ntex} boxes com textura resolvida")
    return all_boxes, summary


def _emit_furnished_gallery_item(iso_png, *, skp, style, plant=PLANT,
                                 flat_white=None, corpus=None):
    """APARENCIA NAO-BLOQUEIA (Bloco 2): DEPOIS que o .skp canonico + renders +
    flat_white_gate ja rodaram (geracao INTACTA, isto e' additivo puro), emite um
    item de galeria PENDENTE do apê mobiliado canonico e SEGUE. human_verdict fica
    None; verdict = PENDING_VISION (o furnish nao coleta visao). O flat_white e'
    um sinal de APARENCIA — vai pro gate_detail (recuperavel pelo olho do Felipe),
    NUNCA como gate FAIL que travaria o item. Reusa variant_sweep.build_record via
    emit_gallery_item (fabrica canonica + append idempotente por variant_id).
    NUNCA espera veredito nem aborta o furnish."""
    from tools.variant_axes import Variant
    from tools.variant_sweep import emit_gallery_item
    corpus = Path(corpus) if corpus else (GALLERY_CORPUS_ROOT / plant / "corpus.jsonl")
    corpus.parent.mkdir(parents=True, exist_ok=True)
    v = Variant(plant=plant, style=style or None, theme="", layout_seed=0)
    gate_detail = {"source": "furnish_apartment", "skp": Path(skp).name if skp else None}
    if isinstance(flat_white, dict):  # sinal de aparencia, NAO-bloqueante
        gate_detail["flat_white"] = {"result": flat_white.get("result"),
                                     "flags": flat_white.get("flags", []),
                                     "fails": flat_white.get("fails", []),
                                     "warns": flat_white.get("warns", [])}
    # kitchen_validation PASSOU (o build abortaria em collect_boxes se nao); e' o
    # unico gate deterministico que conhecemos aqui, e nao e' FAIL -> PENDING_VISION.
    return emit_gallery_item(corpus, v, png=iso_png,
                             gates={"kitchen_validation": "PASS"},
                             gate_detail=gate_detail, findings=None,
                             renderer="sketchup")


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

    # FP-036: textura por kind no path INTERATIVO — o .skp que o Felipe abre deixa de sair com
    # cor chapada. So sob FURNISH_STYLE; fonte unica = style_spec.texture_env (nunca a 1a peca em tudo).
    style = os.environ.get("FURNISH_STYLE")
    if style:
        from tools.style_spec import texture_env
        tex_env = texture_env(style, (ROOT / "assets/textures/procedural").resolve())
        env.update(tex_env)
        if tex_env:
            print(f"[furnish-apt] textura interativa: "
                  f"{len(json.loads(tex_env['LAYOUT_TEX_MAP']))} kind(s) mapeados (estilo {style})")

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

    # FP-036: gate DETERMINISTICO anti-chapado (nao julga estetica; so 'os moveis tem textura?').
    # Roda no render gerado ANTES de entregar pro veredito do Felipe. FAIL = provavel sem textura.
    fw = None
    if after_iso.exists():
        try:
            from tools.flat_white_gate import flat_white_check
            fw = flat_white_check(after_iso, os.environ.get("FURNISH_STYLE"))
            print(f"\n[furnish-apt] flat_white_check({after_iso.name}) => {fw['result']}")
            for line in fw.get("fails", []) + fw.get("warns", []):
                print(f"    {line}")
            if fw["result"] == "FAIL":
                print("[furnish-apt] /!\\ render CHAPADO (provavel sem textura) — inspecionar antes do veredito")
        except Exception as e:  # noqa: BLE001
            print(f"[furnish-apt] flat_white_check pulado: {e}")

    # APARENCIA NAO-BLOQUEIA: o .skp canonico + renders JA existem (geracao acima
    # INTACTA). Emite um item de galeria PENDENTE (human_verdict=None) na MESMA
    # galeria do sweep e SEGUE — o veredito de aparencia e' do Felipe, offline, e
    # NUNCA trava o pipeline. Best-effort: falhar aqui nunca derruba o furnish.
    try:
        rec = _emit_furnished_gallery_item(
            after_iso if after_iso.exists() else None,
            skp=skp_out, style=os.environ.get("FURNISH_STYLE"), flat_white=fw)
        print(f"[furnish-apt] item de galeria: {rec['variant_id']} "
              f"=> {rec['verdict']} (human_verdict={rec['human_verdict']})")
    except Exception as e:  # noqa: BLE001 — galeria nunca bloqueia a cozinha/apê
        print(f"[furnish-apt] item de galeria pulado (nao-fatal): {e}")

    print(f"\n[furnish-apt] -> {OUT_DIR}/")
    print(f"  SKP:   {skp_out.name}")
    print(f"  AFTER: {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
