"""furniture_reference_analyzer.py — segundo passo da skill furniture-reference-analyzer.
Consome o JSON de inspecao (inspect_skp.rb) de um .skp de referencia de MOVEL e produz
uma HIPOTESE SEMANTICA estruturada: tipo do objeto, variante, papeis das pecas
(assento / encosto / braco / pe / base), anatomia (dims em m), material principal,
eixo frontal, e flag is_single_block. NAO abre o SketchUp (consome o JSON).

Pipeline:
  1) SketchUp.exe <ref.skp> -RubyStartup tools/inspect_skp.rb  -> <name>_inspect.json + renders top/front/iso
  2) python tools/furniture_reference_analyzer.py <inspect.json>  -> <name>_analysis.{json,md}

As heuristicas geram HIPOTESE (com confianca), nao verdade — o objetivo e virar
spec/builder/gate, nao copiar o asset. Uso:
  python tools/furniture_reference_analyzer.py <inspect.json> [--out-dir DIR]
"""
import argparse
import json
from pathlib import Path

from shapely.geometry import box as _box
from shapely.ops import unary_union

UNIT = {0: "in", 1: "ft", 2: "mm", 3: "cm", 4: "m"}


def _role(size):
    """Papel provavel de uma peca a partir das dims (m). Assinaturas tipicas de sofa."""
    sx, sy, sz = size
    thin, wide = min(sx, sy), max(sx, sy)
    if max(sx, sy, sz) <= 0.16 and sz <= 0.14:
        return "foot"
    if 0.14 <= thin <= 0.34 and 0.7 <= wide <= 1.10 and 0.35 <= sz <= 0.72:
        return "arm"   # braco: largo ~= profundidade do sofa (nao a largura total)
    if sz >= 0.38 and thin <= 0.32:
        return "back_cushion"
    if 0.18 < sz <= 0.34 and thin >= 0.45 and wide >= 0.45:
        return "seat_base"
    if 0.08 <= sz <= 0.20 and thin >= 0.45 and wide >= 0.45:
        return "seat_cushion"
    return "other"


def _union_footprint(groups):
    rects = []
    for g in groups:
        cx, cy = g["center_m"][0], g["center_m"][1]
        sx, sy = g["size_m"][0], g["size_m"][1]
        rects.append(_box(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2))
    return unary_union(rects).area if rects else 0.0


def _main_material(mats):
    cand = [m for m in mats if m.get("texture")] or mats
    if not cand:
        return None
    m = min(cand, key=lambda x: sum(x["color"]) if x.get("color") else 999)
    return {"name": m["name"], "color": m.get("color"), "texture": m.get("texture")}


def analyze(insp):
    sx, sy, sz = insp["bbox"]["size_m"]
    h = sz
    horiz = sorted([sx, sy], reverse=True)
    defs = insp.get("definitions", [])

    parts = {}
    for d in defs:
        parts.setdefault(_role(d["size_m"]), []).append(
            {"name": d["name"], "size_m": d["size_m"], "instances": d["instances"]})
    n = {k: sum(p["instances"] for p in v) for k, v in parts.items()}

    # --- hipotese de objeto ---
    seating_h = 0.68 <= h <= 1.05 and horiz[0] >= 1.4
    if seating_h and (n.get("back_cushion", 0) + n.get("seat_cushion", 0) + n.get("seat_base", 0)) >= 1:
        obj, conf = "sofa", "alta"
    elif 0.35 <= h <= 0.78 and horiz[0] >= 1.6 and horiz[1] >= 1.4:
        obj, conf = "cama", "media"
    elif h >= 1.6 and min(sx, sy) <= 0.75:
        obj, conf = "guarda_roupa", "media"
    else:
        obj, conf = "desconhecido", "baixa"

    # --- variante (L/chaise) via footprint NAO-preenchido dos grupos grandes ---
    tops = insp.get("hierarchy", [])
    big = [g for g in tops if g.get("center_m") and
           max(g["size_m"][0], g["size_m"][1]) >= 0.8 and g["size_m"][2] >= 0.4]
    variant, chaise_side, fill = "straight", None, None
    if obj == "sofa" and len(big) >= 2:
        bbox_foot = sx * sy
        union_foot = _union_footprint(big)
        fill = round(union_foot / bbox_foot, 2) if bbox_foot else None
        if fill is not None and fill < 0.80:
            variant = "chaise"
            chaise = max(big, key=lambda g: g["size_m"][1])
            body = max([g for g in big if g is not chaise],
                       key=lambda g: g["size_m"][0], default=chaise)
            # convencao: frente = -Y (lado dos assentos); sentado, +X = esquerda
            chaise_side = "left" if chaise["center_m"][0] >= body["center_m"][0] else "right"

    # --- anatomia (dims medias por papel) ---
    def avg(role, idx):
        v = [p["size_m"][idx] for p in parts.get(role, [])]
        return round(sum(v) / len(v), 3) if v else None

    foot_h = avg("foot", 2) or 0.0
    seat_base_h = avg("seat_base", 2) or 0.0
    seat_h = round(foot_h + seat_base_h, 2) if (parts.get("seat_base") or parts.get("foot")) else None
    anatomy = {
        "overall_m": {"width": round(horiz[0], 3), "depth": round(horiz[1], 3), "height": round(h, 3)},
        "seat_height_m": seat_h,
        "seat_cushion_m": {"w": avg("seat_cushion", 0), "d": avg("seat_cushion", 1), "t": avg("seat_cushion", 2)},
        "back_cushion_m": {"w": avg("back_cushion", 0), "d": avg("back_cushion", 1), "h": avg("back_cushion", 2)},
        "arm_m": {"w": avg("arm", 0), "d": avg("arm", 1), "h": avg("arm", 2)},
        "n_seat_cushions": n.get("seat_cushion", 0),
        "n_back_cushions": n.get("back_cushion", 0),
        "n_arms": n.get("arm", 0),
        "n_feet": n.get("foot", 0),
    }

    return {
        "source": insp.get("title"),
        "unit": UNIT.get(insp.get("length_unit_code"), "?"),
        "object_hypothesis": obj,
        "confidence": conf,
        "variant": variant,
        "chaise_side": chaise_side,
        "footprint_fill_ratio": fill,
        "is_single_block": len([d for d in defs]) <= 1,
        "n_definitions": len(defs),
        "parts_detected": n,
        "parts_detail": parts,
        "anatomy": anatomy,
        "main_material": _main_material(insp.get("materials", [])),
        "all_materials": [m["name"] for m in insp.get("materials", [])],
        "front_axis": "-Y (assumido: frente = lado dos assentos/encosto)",
        "renders": ["<name>_top.png", "<name>_front.png", "<name>_iso.png"],
    }


def to_markdown(a, insp):
    L = [f"# Analise de referencia — {a['source']}", "",
         f"**Hipotese:** {a['object_hypothesis']} (confianca {a['confidence']})"
         + (f" — variante **{a['variant']}**" + (f" chaise_{a['chaise_side']}" if a['chaise_side'] else "")),
         f"**Unidade do modelo:** {a['unit']}  |  **single block?** {'SIM' if a['is_single_block'] else 'NAO'}"
         f" ({a['n_definitions']} componentes)", ""]
    bb = insp["bbox"]["size_m"]
    L.append(f"## Bounding box\n- {bb[0]} x {bb[1]} x {bb[2]} m (largura x profundidade x altura)")
    if a.get("footprint_fill_ratio") is not None:
        L.append(f"- footprint preenchido {int(a['footprint_fill_ratio'] * 100)}% do bbox "
                 f"(<80% => L/chaise)")
    an = a["anatomy"]
    L += ["", "## Anatomia detectada",
          f"- overall: {an['overall_m']['width']} x {an['overall_m']['depth']} x {an['overall_m']['height']} m",
          f"- altura do assento ~ {an['seat_height_m']} m",
          f"- assentos: {an['n_seat_cushions']} (cada ~{an['seat_cushion_m']['w']}x{an['seat_cushion_m']['d']}x{an['seat_cushion_m']['t']} m)",
          f"- encostos: {an['n_back_cushions']} (cada ~{an['back_cushion_m']['w']}x{an['back_cushion_m']['d']}x{an['back_cushion_m']['h']} m)",
          f"- bracos: {an['n_arms']} (cada ~{an['arm_m']['w']}x{an['arm_m']['d']}x{an['arm_m']['h']} m)",
          f"- pes: {an['n_feet']}"]
    mm = a.get("main_material")
    L += ["", "## Materiais",
          f"- principal: **{mm['name'] if mm else '?'}** rgb={mm['color'] if mm else '?'}"
          + (f" textura={mm['texture']}" if mm and mm.get('texture') else ""),
          f"- todos: {', '.join(a['all_materials'])}"]
    L += ["", "## Eixo / orientacao", f"- {a['front_axis']}"]
    L += ["", "## Renders", "- top / front / iso (ver PNGs nesta pasta)"]
    L += ["", "## Conclusao p/ o builder",
          f"- NAO e bloco unico: tem {a['n_definitions']} pecas semanticas separadas.",
          "- o SofaBuilder deve reproduzir: base/plataforma + assentos SEPARADOS + "
          "encostos SEPARADOS + bracos + pes" + (" + CHAISE" if a['variant'] == 'chaise' else ""),
          "- material principal = tecido escuro (Dansbo-like); pes escuros."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inspect_json")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    p = Path(args.inspect_json)
    insp = json.loads(p.read_text("utf-8"))
    a = analyze(insp)
    out_dir = Path(args.out_dir) if args.out_dir else p.parent
    stem = p.stem.replace("_inspect", "")
    a["renders"] = [f"{stem}_top.png", f"{stem}_front.png", f"{stem}_iso.png"]
    (out_dir / f"{stem}_analysis.json").write_text(
        json.dumps(a, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / f"{stem}_analysis.md").write_text(to_markdown(a, insp), encoding="utf-8")
    print(f"OBJ={a['object_hypothesis']}({a['confidence']}) variant={a['variant']}"
          + (f" chaise_{a['chaise_side']}" if a['chaise_side'] else "")
          + f" | single_block={a['is_single_block']} | parts={a['parts_detected']}")
    print(f"  -> {out_dir}/{stem}_analysis.json + .md")


if __name__ == "__main__":
    main()
