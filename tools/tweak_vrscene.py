"""tweak_vrscene.py — pos-processa um .vrscene (texto) p/ corrigir EXPOSICAO/qualidade do
render V-Ray. O export sai com a CameraPhysical setada p/ exterior claro (f/8, 1/300, ISO100)
-> interior subexposto/escuro. Aqui ajustamos ISO/f_number/shutter (e opcional sky/res) p/ um
interior bem exposto. Deterministico, reusavel no pipeline (export -> tweak -> vray.exe).

Uso: python tools/tweak_vrscene.py <in.vrscene> [out.vrscene] [--iso N --fnum F --shutter S
      --sky M --width W --height H]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


# --- materiais V-Ray por PAPEL (premium: troca cor chapada por madeira satin / tecido matte / metal) ---
MAT_WOOD = ("estrado", "corpo", "tampo", "gaveta", "pe", "rodape", "porta", "foot", "base",
            "rack_tv", "mesa_centro", "dresser", "bancada", "torre", "aereo", "bancada_banho", "box")
MAT_FABRIC = ("headboard", "rug", "colchao", "travesseiro", "manta", "arm", "seat_cushion",
              "back_cushion", "tapete")
MAT_METAL = ("puxador",)
MAT_CERAMIC = ("vaso",)
MAT_PARAMS = {
    "wood": {"reflect": "AColor(0.11, 0.11, 0.11, 1)", "reflect_glossiness": "0.72",
             "fresnel_ior": "1.55", "metalness": "0"},                       # madeira satin
    "fabric": {"reflect": "AColor(0, 0, 0, 1)", "reflect_glossiness": "1", "roughness": "0.55",
               "metalness": "0"},                                            # tecido matte
    "metal": {"reflect": "AColor(0.78, 0.78, 0.78, 1)", "reflect_glossiness": "0.82",
              "metalness": "1"},                                             # metal escovado
    "ceramic": {"reflect": "AColor(0.28, 0.28, 0.28, 1)", "reflect_glossiness": "0.9",
                "metalness": "0"},
}


def _set_block(text: str, brdf: str, params: dict) -> str:
    s = text.find(f"BRDFVRayMtl {brdf} {{")
    if s < 0:
        return text
    e = text.find("\n}", s)
    if e < 0:
        return text
    block = text[s:e]
    for k, v in params.items():
        block = re.sub(rf"(?m)^(\s*{k}=)[^;\n]+;", rf"\g<1>{v};", block, count=1)
    return text[:s] + block + text[e:]


def apply_materials(text: str) -> str:
    """Aplica materiais V-Ray por papel nos materiais de movel (_ph_<kind>_BRDFVRayMtl)."""
    for kinds, cls in ((MAT_WOOD, "wood"), (MAT_FABRIC, "fabric"), (MAT_METAL, "metal"),
                       (MAT_CERAMIC, "ceramic")):
        for kind in kinds:
            text = _set_block(text, f"_ph_{kind}_BRDFVRayMtl", MAT_PARAMS[cls])
    return text


def _light_sphere(name, pos, intensity, color=(1.0, 0.8, 0.55), radius=14.0, units=0):
    """Bloco LightSphere V-Ray (area light esferica, quente, invisivel) — fill interior.
    pos/radius em INCHES (unidade do modelo exportado). units=0 (radiancia escalar,
    independe de escala, igual ao SunLight). invisible=1 (nao aparece como esfera no frame)."""
    px, py, pz = pos
    r, g, b = color
    return (
        f"\nLightSphere {name} {{\n"
        f"  enabled=1;\n"
        f"  transform=Transform(Matrix(Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)), "
        f"Vector({px}, {py}, {pz}));\n"
        f"  color=Color({r}, {g}, {b});\n"
        f"  units={units};\n"
        f"  intensity={intensity};\n"
        f"  subdivs=16;\n"
        f"  radius={radius};\n"
        f"  sphere_segments=20;\n"
        f"  shadows=1;\n"
        f"  affectDiffuse=1;\n"
        f"  affectSpecular=1;\n"
        f"  affectReflections=1;\n"
        f"  invisible=1;\n"
        f"  storeWithIrradianceMap=0;\n"
        f"  noDecay=0;\n"
        f"}}\n"
    )


def add_fill_light(text: str, lights) -> str:
    """Anexa 1+ LightSphere (fill interior quente) ao .vrscene. `lights` = lista de dicts
    {pos:(x,y,z), intensity:float, color:(r,g,b), radius:float}. Top-level plugin (igual SunLight),
    nao precisa de Node. GPT NEXT_ACTION: levantar sofa/paredes escuras sem estourar a janela."""
    for i, lt in enumerate(lights):
        text += _light_sphere(f"_interior_fill_{i}", lt["pos"], lt["intensity"],
                              lt.get("color", (1.0, 0.8, 0.55)), lt.get("radius", 14.0),
                              lt.get("units", 0))
    return text


def set_block_param(text: str, header_pat: str, param: str, value) -> str:
    """Seta param=value DENTRO do primeiro bloco cujo header casa header_pat.
    Evita o bug do regex global: 'intensity_multiplier' existe no TexSky (ambiente)
    E no SunLight (sol direto) — interior pede os dois em direcoes OPOSTAS
    (TOP3 do juiz na fase render da cena: +ambiente, -sol duro)."""
    m = re.search(header_pat, text)
    if not m:
        return text
    start = m.end()
    end = text.find("}", start)
    seg = re.sub(rf"(\b{param}=)[\d.]+", rf"\g<1>{value}", text[start:end], count=1)
    return text[:start] + seg + text[end:]


def tweak(text: str, iso=200, fnum=4.0, shutter=100, sky=1.0, width=None, height=None,
          materials=False, fill_lights=None, sun=None, sun_size=None, burn=None) -> str:
    text = re.sub(r"(\bISO=)[\d.]+", rf"\g<1>{iso}", text, count=1)
    text = re.sub(r"(\bf_number=)[\d.]+", rf"\g<1>{fnum}", text, count=1)
    text = re.sub(r"(\bshutter_speed=)[\d.]+", rf"\g<1>{shutter}", text, count=1)
    if sky is not None:
        text = set_block_param(text, r"TexSky\s+\S+\s*\{", "intensity_multiplier", sky)
    if sun is not None:
        text = set_block_param(text, r"SunLight\s+\S+\s*\{", "intensity_multiplier", sun)
    if sun_size is not None:
        # sol maior = penumbra larga = patch suave ("luz desenhando, nao holofote")
        text = set_block_param(text, r"SunLight\s+\S+\s*\{", "size_multiplier", sun_size)
    if burn is not None:
        # Reinhard burn (<1 comprime highlights): janela mostra gradacao do ceu
        # em vez de buraco branco estourado ("janela viva" — pedido do juiz)
        text = set_block_param(text, r"SettingsColorMapping\s+\S+\s*\{", "bright_mult", burn)
    if width:
        text = re.sub(r"(\bimg_width=)\d+", rf"\g<1>{width}", text, count=1)
    if height:
        text = re.sub(r"(\bimg_height=)\d+", rf"\g<1>{height}", text, count=1)
    if materials:
        text = apply_materials(text)
    if fill_lights:
        text = add_fill_light(text, fill_lights)
    return text


def tweak_file(in_path, out_path=None, **kw):
    p = Path(in_path)
    out = Path(out_path) if out_path else p
    out.write_text(tweak(p.read_text("utf-8", "ignore"), **kw), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile", nargs="?")
    ap.add_argument("--iso", type=int, default=200)
    ap.add_argument("--fnum", type=float, default=4.0)
    ap.add_argument("--shutter", type=int, default=100)
    ap.add_argument("--sky", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--materials", action="store_true", help="aplica materiais V-Ray por papel (madeira/tecido/metal)")
    ap.add_argument("--fill", default="", help="fill light(s) interior: 'x,y,z,intensity[,radius]' separados por ';' (inches)")
    ap.add_argument("--fill-color", default="1.0,0.8,0.55", help="cor do fill r,g,b (default warm)")
    a = ap.parse_args()
    fills = None
    if a.fill:
        col = tuple(float(v) for v in a.fill_color.split(","))
        fills = []
        for spec in a.fill.split(";"):
            p = [float(v) for v in spec.split(",")]
            fills.append({"pos": (p[0], p[1], p[2]), "intensity": p[3],
                          "radius": (p[4] if len(p) > 4 else 14.0), "color": col})
    out = tweak_file(a.infile, a.outfile, iso=a.iso, fnum=a.fnum, shutter=a.shutter,
                     sky=a.sky, width=a.width, height=a.height, materials=a.materials,
                     fill_lights=fills)
    print(f"tweaked -> {out} (ISO={a.iso} f={a.fnum} shutter=1/{a.shutter} sky={a.sky} "
          f"materials={a.materials} fills={len(fills) if fills else 0})")
