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


def tweak(text: str, iso=200, fnum=4.0, shutter=100, sky=1.0, width=None, height=None,
          materials=False) -> str:
    text = re.sub(r"(\bISO=)[\d.]+", rf"\g<1>{iso}", text, count=1)
    text = re.sub(r"(\bf_number=)[\d.]+", rf"\g<1>{fnum}", text, count=1)
    text = re.sub(r"(\bshutter_speed=)[\d.]+", rf"\g<1>{shutter}", text, count=1)
    if sky is not None:
        text = re.sub(r"(intensity_multiplier=)[\d.]+", rf"\g<1>{sky}", text, count=1)
    if width:
        text = re.sub(r"(\bimg_width=)\d+", rf"\g<1>{width}", text, count=1)
    if height:
        text = re.sub(r"(\bimg_height=)\d+", rf"\g<1>{height}", text, count=1)
    if materials:
        text = apply_materials(text)
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
    a = ap.parse_args()
    out = tweak_file(a.infile, a.outfile, iso=a.iso, fnum=a.fnum, shutter=a.shutter,
                     sky=a.sky, width=a.width, height=a.height, materials=a.materials)
    print(f"tweaked -> {out} (ISO={a.iso} f={a.fnum} shutter=1/{a.shutter} sky={a.sky} materials={a.materials})")
