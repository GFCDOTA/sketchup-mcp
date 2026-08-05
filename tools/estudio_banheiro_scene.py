"""estudio_banheiro_scene.py — ESTUDIO BANHEIRO (2026-08-05): recria o banheiro da
imagem-referencia gerada pelo GPT (chat fixo /c/6a526f31...) como CENA sintetica
Intent-to-Scene (runs/scenes/estudio_banheiro_vN), para o loop de nota 0-10.

Spec oficial: artifacts/estudio_banheiro/REFERENCE_SPEC.md (E:/Claude/apps/...).
Resumo: banheiro 1.65x2.45x2.50; gabinete suspenso nogueira 1.20m na parede OESTE
com nicho de toalhas + LED; bancada pedra escura 6cm com cuba retangular esculpida;
torneira PRETA de bancada com ANEL dourado (unico ponto de ouro junto da moldura
champagne do espelho); espelho 1.00x1.10 halo LED; vaso preto suspenso na parede
NORTE (esq.); box vidro/perfil preto no canto NE com pedra antracite + nicho LED;
paredes cimento queimado taupe; piso pedra grafite. Camera na porta (sul), 1.60m.

Convencao: metros, origem SW, X=leste (0..W), Y=norte (0..D). Deterministico.
Uso: python -m tools.estudio_banheiro_scene [--out runs/scenes/estudio_banheiro_v1]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from interior.composer.scene_composer import build_room_shell, write_scene  # noqa: E402

W, D, H = 1.65, 2.45, 2.50

STYLE = {"materials": {"wall": {"rgb": [166, 152, 136]},     # cimento queimado taupe
                       "floor": {"rgb": [66, 62, 58]},        # pedra grafite media
                       "ceiling": {"rgb": [58, 54, 50]}}}

RGB = {"nogueira": [96, 68, 44], "gola": [22, 22, 24], "pedra_escura": [30, 28, 30],
       "pedra_box": [40, 38, 40], "cuba_poco": [10, 10, 12], "preto_fosco": [24, 24, 26],
       "dourado": [186, 148, 84], "champagne": [178, 148, 96], "espelho": [188, 196, 202],
       "led": [255, 244, 214], "vidro": [172, 188, 196], "toalha_a": [52, 50, 50],
       "toalha_b": [88, 82, 74], "arte": [38, 34, 30], "frasco": [46, 42, 38],
       "planta": [72, 86, 56], "vaso_deco": [20, 20, 22]}


# trims finos legit (<1in² de footprint) — mesma politica do variant_sweep:
# decorative=True fica ISENTO de degenerate_* no gate (fix na causa, ce7f132)
DECORATIVE = {"moldura", "puxador", "barra", "gola", "anel", "led_halo",
              "nicho_led", "led_under", "lente", "cabeca",   # cabeca: octogono (off_axis intencional)
              "perfil"}   # perfil 22mm do box (GPT it.3) — trim fino, nao estrutura


def _p(item, label, x0, y0, x1, y1, z0, z1, rgb, alpha=None):
    part = {"kind": label, "item": item, "label": label,
            "x0": round(min(x0, x1), 4), "y0": round(min(y0, y1), 4),
            "x1": round(max(x0, x1), 4), "y1": round(max(y0, y1), 4),
            "z0": round(z0, 4), "z1": round(z1, 4), "rgb": rgb,
            "decorative": label in DECORATIVE}
    if alpha is not None:
        part["alpha"] = alpha
    return part


def build_parts():
    parts = build_room_shell(
        {"width_m": W, "depth_m": D, "height_m": H},
        [{"wall": "south", "type": "door", "center_along_m": 1.20,
          "width_m": 0.70, "head_m": 2.10}],
        STYLE)

    # ---------------- GABINETE suspenso (parede OESTE, 1.20m: y 0.35..1.55)
    gy0, gy1, gdep = 0.35, 1.55, 0.50
    # nicho aberto inferior de toalhas (fundo + laterais + prateleira)
    parts += [
        _p("gabinete", "nicho_fundo", 0.02, gy0 + 0.02, 0.08, gy1 - 0.02, 0.20, 0.40, RGB["gola"]),
        _p("gabinete", "corpo", 0.02, gy0, 0.05, gy1, 0.18, 0.84, RGB["nogueira"]),      # costas
        _p("gabinete", "lateral", 0.02, gy0, gdep, gy0 + 0.02, 0.18, 0.84, RGB["nogueira"]),
        _p("gabinete", "lateral", 0.02, gy1 - 0.02, gdep, gy1, 0.18, 0.84, RGB["nogueira"]),
        _p("gabinete", "prateleira", 0.02, gy0, gdep - 0.02, gy1, 0.18, 0.22, RGB["nogueira"]),
        _p("gabinete", "led_under", 0.06, gy0 + 0.04, gdep - 0.06, gy1 - 0.04, 0.405, 0.42, RGB["led"]),
    ]
    # toalhas dobradas no nicho (3 pilhas, alturas variadas)
    for i, (tc, th) in enumerate(((0.62, 0.10), (0.95, 0.13), (1.28, 0.08))):
        parts.append(_p("gabinete", "toalha_a" if i % 2 == 0 else "toalha_b",
                        0.08, tc - 0.13, gdep - 0.06, tc + 0.13, 0.22, 0.22 + th,
                        RGB["toalha_a"] if i % 2 == 0 else RGB["toalha_b"]))
    # corpo de gavetas 0.42..0.84 com 4 FRENTES horizontais (gaps de sombra)
    parts.append(_p("gabinete", "corpo", 0.02, gy0, gdep - 0.015, gy1, 0.42, 0.84, RGB["nogueira"]))
    fz = 0.42
    for i in range(4):
        fh = (0.84 - 0.42 - 3 * 0.008) / 4
        parts.append(_p("gabinete", "frente", gdep - 0.015, gy0 + 0.01, gdep, gy1 - 0.01,
                        fz, fz + fh, RGB["nogueira"]))
        if i < 3:
            parts.append(_p("gabinete", "gola", gdep - 0.013, gy0 + 0.01, gdep - 0.002,
                            gy1 - 0.01, fz + fh, fz + fh + 0.008, RGB["gola"]))
        fz += fh + 0.008

    # ---------------- BANCADA pedra escura (6cm) + cuba retangular esculpida
    bx1, by0, by1 = gdep + 0.03, gy0 - 0.02, gy1 + 0.02
    parts.append(_p("bancada", "tampo", 0.0, by0, bx1, by1, 0.84, 0.90, RGB["pedra_escura"]))
    parts.append(_p("bancada", "frontal", bx1 - 0.02, by0, bx1, by1, 0.78, 0.84, RGB["pedra_escura"]))
    cx, cy, cw, cd = 0.27, 0.95, 0.40, 0.30                       # cuba retangular
    parts.append(_p("bancada", "cuba_anel", cx - cw / 2, cy - cd / 2, cx + cw / 2, cy + cd / 2,
                    0.900, 0.903, RGB["gola"]))
    parts.append(_p("bancada", "cuba_poco", cx - cw / 2 + 0.03, cy - cd / 2 + 0.03,
                    cx + cw / 2 - 0.03, cy + cd / 2 - 0.03, 0.898, 0.900, RGB["cuba_poco"]))

    # ---------------- TORNEIRA preta de bancada + ANEL dourado (1 ponto de ouro)
    tx, ty = 0.10, 0.95
    parts += [
        _p("torneira", "corpo", tx - 0.02, ty - 0.02, tx + 0.02, ty + 0.02, 0.90, 1.08, RGB["preto_fosco"]),
        _p("torneira", "bica", tx, ty - 0.015, tx + 0.16, ty + 0.015, 1.05, 1.08, RGB["preto_fosco"]),
        _p("torneira", "anel", tx - 0.024, ty - 0.024, tx + 0.024, ty + 0.024, 0.90, 0.925, RGB["dourado"]),
        _p("torneira", "manopla", tx - 0.015, ty + 0.10, tx + 0.015, ty + 0.16, 0.92, 0.95, RGB["preto_fosco"]),
    ]
    # amenities da bancada (frasco ambar + vasinho com planta)
    parts += [
        _p("deco", "frasco", 0.16, 1.30, 0.22, 1.36, 0.90, 1.08, RGB["frasco"]),
        _p("deco", "frasco", 0.24, 1.32, 0.28, 1.36, 0.90, 1.02, RGB["frasco"]),
        _p("deco", "vaso_deco", 0.12, 1.40, 0.20, 1.48, 0.90, 1.00, RGB["vaso_deco"]),
        _p("deco", "planta", 0.10, 1.38, 0.22, 1.50, 1.00, 1.14, [34, 42, 28]),
    ]

    # ---------------- ESPELHO 1.00x1.10 com halo LED + moldura champagne fina
    # iter3 (GPT): espelho PROTAGONISTA — halo continuo VISIVEL transbordando
    # 3.5cm alem da borda nos 4 lados
    my0, my1, mz0, mz1 = 0.45, 1.45, 1.10, 2.20
    parts.append(_p("espelho", "led_halo", 0.004, my0 - 0.035, 0.012, my1 + 0.035,
                    mz0 - 0.035, mz1 + 0.035, RGB["led"]))
    parts.append(_p("espelho", "vidro", 0.012, my0, 0.024, my1, mz0, mz1, RGB["espelho"]))
    for za, zb in ((mz0 - 0.012, mz0), (mz1, mz1 + 0.012)):        # moldura top/bottom
        parts.append(_p("espelho", "moldura", 0.010, my0 - 0.012, 0.026, my1 + 0.012, za, zb, RGB["champagne"]))
    for ya, yb in ((my0 - 0.012, my0), (my1, my1 + 0.012)):        # moldura laterais
        parts.append(_p("espelho", "moldura", 0.010, ya, 0.026, yb, mz0, mz1, RGB["champagne"]))

    # ---------------- VASO suspenso preto (parede NORTE, entre gabinete e box —
    # VISIVEL como na referencia, nao atras do vidro)
    vx0, vx1 = 0.16, 0.54
    parts += [
        _p("vaso", "bacia", vx0, 1.95, vx1, 2.43, 0.30, 0.44, RGB["preto_fosco"]),
        _p("vaso", "tampa", vx0 + 0.02, 1.97, vx1 - 0.02, 2.41, 0.44, 0.47, RGB["preto_fosco"]),
        _p("vaso", "placa_flush", vx0 + 0.10, 2.435, vx1 - 0.10, 2.445, 1.00, 1.15, RGB["gola"]),
    ]

    # ---------------- ARTE (parede norte, entre espelho e box)
    parts += [
        _p("arte", "moldura", 0.06, 2.425, 0.52, 2.44, 1.30, 1.98, RGB["gola"]),
        _p("arte", "quadro", 0.075, 2.42, 0.505, 2.425, 1.315, 1.965, RGB["arte"]),
    ]

    # ---------------- BOX na lateral LESTE (como na referencia): vidro de FRENTE
    # pro ambiente (plano x=bxx0 correndo em y), pedra antracite no fundo/lateral
    bxx0, bxy0 = 0.75, 1.35                                        # box 0.90 (x) x 1.10 (y)
    parts += [
        _p("box", "piso_pedra", bxx0, bxy0, W, D, 0.0, 0.012, RGB["pedra_box"]),
        _p("box", "pedra_e", W - 0.02, bxy0, W, D, 0.012, 2.40, RGB["pedra_box"]),          # lateral leste
    ]
    # pedra do fundo (norte, trecho do box) com NICHO horizontal 0.66x0.20 + LED
    nx0, nx1, nz0, nz1 = 0.90, 1.55, 1.10, 1.30
    parts += [
        _p("box", "pedra_n", bxx0, D - 0.045, W, D, 0.012, nz0, RGB["pedra_box"]),          # abaixo
        _p("box", "pedra_n", bxx0, D - 0.045, W, D, nz1, 2.30, RGB["pedra_box"]),           # acima
        _p("box", "pedra_n", bxx0, D - 0.045, nx0, D, nz0, nz1, RGB["pedra_box"]),          # esq
        _p("box", "pedra_n", nx1, D - 0.045, W, D, nz0, nz1, RGB["pedra_box"]),             # dir
        _p("box", "nicho_fundo", nx0, D - 0.02, nx1, D, nz0, nz1, RGB["gola"]),             # fundo
        _p("box", "nicho_base", nx0, D - 0.045, nx1, D - 0.02, nz0, nz0 + 0.012, RGB["pedra_box"]),
        _p("box", "nicho_led", nx0 + 0.01, D - 0.043, nx1 - 0.01, D - 0.033, nz1 - 0.018, nz1 - 0.006, RGB["led"]),
        _p("box", "frasco", 1.04, D - 0.085, 1.08, D - 0.045, nz0 + 0.012, nz0 + 0.13, RGB["frasco"]),
        _p("box", "frasco", 1.12, D - 0.085, 1.16, D - 0.045, nz0 + 0.012, nz0 + 0.11, RGB["frasco"]),
    ]
    gt = 0.008                                                     # vidro 8mm
    parts += [                                                     # plano frontal x=bxx0 (porta de correr)
        _p("box", "vidro_frente", bxx0, bxy0, bxx0 + gt, D - 0.045, 0.012, 2.10, RGB["vidro"], alpha=0.10),
        _p("box", "vidro_retorno", bxx0, bxy0, W - 0.02, bxy0 + gt, 0.012, 2.10, RGB["vidro"], alpha=0.10),
        _p("box", "perfil", bxx0 - 0.011, bxy0 - 0.011, bxx0 + 0.011, bxy0 + 0.011, 0.0, 2.12, RGB["preto_fosco"]),
        _p("box", "perfil", bxx0 - 0.011, D - 0.022, bxx0 + 0.011, D, 0.0, 2.12, RGB["preto_fosco"]),
        _p("box", "perfil", bxx0 - 0.009, bxy0 - 0.011, W, bxy0 + 0.009, 2.10, 2.135, RGB["preto_fosco"]),
        _p("box", "perfil", bxx0 - 0.011, bxy0 - 0.009, bxx0 + 0.009, D, 2.10, 2.135, RGB["preto_fosco"]),
        _p("box", "puxador", bxx0 - 0.025, 1.55, bxx0, 1.58, 0.95, 1.45, RGB["preto_fosco"]),
    ]

    # ---------------- DUCHA preta: rain shower REDONDO (octogono ~o0.28) +
    # barra/ducha manual + comando maiores (iter3: "mostrar com clareza")
    dcx, dcy = (bxx0 + W) / 2, D - 0.30
    oct_r = 0.14
    octg = [[round(dcx + oct_r * math.cos(a), 4), round(dcy + oct_r * math.sin(a), 4)]
            for a in [math.pi / 8 + i * math.pi / 4 for i in range(8)]]
    cab = _p("ducha", "cabeca", dcx - oct_r, dcy - oct_r, dcx + oct_r, dcy + oct_r,
             2.14, 2.17, RGB["preto_fosco"])
    cab["poly"] = octg
    parts += [
        _p("ducha", "braco", dcx - 0.014, D - 0.30, dcx + 0.014, D - 0.045, 2.18, 2.22, RGB["preto_fosco"]),
        cab,
        _p("ducha", "barra", W - 0.065, 1.66, W - 0.035, 1.69, 0.95, 1.95, RGB["preto_fosco"]),
        _p("ducha", "manual", W - 0.085, 1.635, W - 0.045, 1.715, 1.55, 1.82, RGB["preto_fosco"]),
        _p("ducha", "comando", W - 0.055, 1.92, W - 0.015, 2.08, 1.02, 1.18, RGB["preto_fosco"]),
    ]

    # ---------------- SPOTS de teto (2700-3000K): circulacao/espelho + box
    for sx, sy in ((0.50, 0.90), (1.10, 1.95)):
        parts.append(_p("spot", "lente", sx - 0.032, sy - 0.032, sx + 0.032, sy + 0.032,
                        H - 0.008, H - 0.001, RGB["led"]))
    return parts


def build_scene(out_dir):
    parts = build_parts()
    # iter 2 (GPT): 4:5 vertical, 1.60m, lente ~35-40mm, MENOS tilt pra baixo,
    # recuada junto a porta — gabinete/espelho/vaso/box INTEIROS no quadro
    eye = [1.41, 0.10, 1.60]   # maximo recuo/direita FISICO (vao da porta x0.85-1.55)
    target = [0.52, 1.80, 1.28]
    dx, dy, dz = eye[0] - target[0], eye[1] - target[1], eye[2] - target[2]
    cam = {"kind": "reference_match_door", "eye": eye, "target": target,
           "elev_deg": round(math.degrees(math.atan2(dz, math.hypot(dx, dy))), 1),
           "azim_deg": round(math.degrees(math.atan2(dy, dx)), 1),
           "hide_walls": ["south", "east"], "min_hero_coverage": 0.10}
    placements = [
        {"type": "vanity", "role": "hero", "center": [0.26, 0.95], "bbox": [0.0, 0.33, 0.53, 1.57]},
        {"type": "toilet", "role": "anchor", "center": [0.35, 2.19], "bbox": [0.16, 1.95, 0.54, 2.45]},
        {"type": "shower_box", "role": "anchor", "center": [1.20, 1.90], "bbox": [0.75, 1.35, 1.65, 2.45]},
    ]
    scene = {"scene_id": Path(out_dir).name,
             "room": {"width_m": W, "depth_m": D, "height_m": H},
             "openings": [{"wall": "south", "type": "door", "center_along_m": 1.20,
                           "width_m": 0.70, "head_m": 2.10}],
             "placements": placements, "camera": cam, "parts": parts,
             "report": {"style_id": "estudio_banheiro_dark_stone",
                        "reference": "artifacts/estudio_banheiro/REFERENCE_SPEC.md",
                        "n_parts": len(parts)}}
    out = write_scene(scene, out_dir)
    return out, parts


def run_gates(parts):
    from tools.geometry_sanity import audit
    from tools.render_scene_views import scene_boxes
    structural = [p for p in parts if not p.get("decorative")]
    boxes = scene_boxes(structural)
    fixtures = [b for b in boxes if not (b["label"].startswith("wall_")
                or b["label"] in ("floor", "ceiling"))]
    rep = audit(fixtures, to_m=0.0254)
    inside = all(-0.01 <= p["x0"] and p["x1"] <= W + 0.01
                 and -0.01 <= p["y0"] and p["y1"] <= D + 0.05
                 for p in parts if p.get("item"))
    return {"geometry_sanity": rep, "all_inside_room": inside}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs/scenes/estudio_banheiro_v1"))
    ns = ap.parse_args()
    out, parts = build_scene(ns.out)
    gates = run_gates(parts)
    (Path(out) / "gates.json").write_text(json.dumps(gates, indent=2, default=str),
                                          encoding="utf-8")
    sanity = gates["geometry_sanity"].get("overall")
    ok = gates["all_inside_room"] and sanity != "FAIL"
    fails = [f for f in gates["geometry_sanity"].get("findings", [])
             if f["severity"] == "FAIL"]
    print(json.dumps({"scene": str(out), "n_parts": len(parts),
                      "gates_ok": ok, "sanity_overall": sanity,
                      "fails": fails[:10],
                      "inside": gates["all_inside_room"]}, indent=2))
    sys.exit(0 if ok else 1)
