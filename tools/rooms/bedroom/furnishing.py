"""Adapter de quartos entre bedroom_designer e boxes paramétricos.

Movido do orquestrador sem mudar algoritmos, escala, paleta, anatomia,
nem contrato (boxes, out). O entrypoint legado permanece reexportado.
"""
from __future__ import annotations

from tools import bedroom_designer
from tools.rooms.shared.furniture import _chair_parts
from tools.rooms.shared.geometry import _oriented_box


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
            # Mesmas dimensoes aceitas pelo planner (inclui tampo saliente).
            nw, nd, top_w, top_d = bedroom_designer.nightstand_real_dimensions(nw, nd)
            n_ns += 1
            _mod = f"Criado-mudo {n_ns}"
            _cb = [
                _oriented_box("ks_criado_corpo", ncen, bed_facing, nw, nd, 0.32, 0.20,
                              [30, 31, 32], module=_mod),
                _oriented_box("ks_criado_frente", ncen, bed_facing, nw - 0.03, nd + 0.006, 0.335, 0.165,
                              [44, 45, 47], module=_mod),
                _oriented_box("ks_gola", ncen, bed_facing, nw - 0.07, nd + 0.008, 0.322, 0.012,
                              [24, 24, 24], module=_mod),
                _oriented_box("ks_criado_tampo", ncen, bed_facing, top_w, top_d, 0.52, 0.025,
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
    # ESCRIVANINHA / mesa de PC (2026-09-11): tampo nogueira + saia + 2 laterais
    # estrutura preta + gaveteiro suspenso; cadeira = a MESMA da mesa de jantar
    # (linguagem única no apê). Troca o bloco chapado 'desk'/'desk_chair'.
    dk_item = next((it for it in items if it.get("type") == "desk"), None)
    if dk_item is not None:
        from tools.sofa_builder import _p, place_sofa_boxes
        dfx, dfy = _wd_facing(dk_item)
        dw_m, dd_m, dcen = _wd_dims(dk_item["box"], (dfx, dfy))
        h, tt, lt = 0.75, 0.035, 0.05
        dparts = [_p("top", "top", 0.0, 0.0, dw_m, dd_m, h - tt, h, (108, 80, 58)),
                  _p("apron", "saia", 0.06, 0.05, dw_m - 0.06, dd_m - 0.05,
                     h - tt - 0.08, h - tt, (30, 31, 32))]
        for x0 in (0.04, dw_m - 0.04 - lt):                       # laterais estrutura
            dparts.append(_p("leg", "foot", x0, 0.05, x0 + lt, dd_m - 0.05, 0.0, h - tt, (26, 26, 29)))
        dparts.append(_p("gaveteiro", "base", dw_m - 0.52, 0.08, dw_m - 0.10, dd_m - 0.08,
                         0.34, h - tt - 0.09, (44, 45, 47)))      # suspenso: nao toca o piso
        dparts.append(_p("ks_gola", "frame", dw_m - 0.52, 0.07, dw_m - 0.10, 0.085,
                         0.33, h - tt - 0.08, (24, 24, 24)))
        dboxes = place_sofa_boxes(dparts, dcen, (dfx, dfy))
        for _b in dboxes:
            _b["module"] = "Escrivaninha"
        boxes = [b for b in boxes if b.get("kind") != "desk"] + dboxes
        out["desk_parametric"] = {"n_parts": len(dboxes), "W_m": round(dw_m, 2),
                                  "D_m": round(dd_m, 2)}
    dc_item = next((it for it in items if it.get("type") == "desk_chair"), None)
    if dc_item is not None:
        from tools.sofa_builder import place_sofa_boxes
        cfx, cfy = _wd_facing(dc_item)
        _, _, ccen = _wd_dims(dc_item["box"], (cfx, cfy))
        # a cadeira encara a mesa: facing oposto ao da escrivaninha
        cboxes = place_sofa_boxes(_chair_parts(), ccen, (-cfx, -cfy))
        for _b in cboxes:
            _b["module"] = "Cadeira escrivaninha"
        boxes = [b for b in boxes if b.get("kind") != "desk_chair"] + cboxes

    # paleta ks_* nas peças herdadas dos builders golden (cores neutras -> diretriz)
    _KS_BY_KIND = {"estrado": [38, 39, 40], "colchao": [214, 202, 184],
                   "travesseiro": [222, 212, 196], "manta": [176, 128, 88],
                   "cabeceira": [172, 150, 124], "tapete": [122, 110, 98], "rug": [122, 110, 98]}
    for _b in boxes:
        _new = _KS_BY_KIND.get(str(_b.get("kind", "")))
        if _new:
            _b["rgb"] = _new
    return boxes, out
