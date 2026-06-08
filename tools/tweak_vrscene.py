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


def tweak(text: str, iso=200, fnum=4.0, shutter=100, sky=1.0, width=None, height=None) -> str:
    text = re.sub(r"(\bISO=)[\d.]+", rf"\g<1>{iso}", text, count=1)
    text = re.sub(r"(\bf_number=)[\d.]+", rf"\g<1>{fnum}", text, count=1)
    text = re.sub(r"(\bshutter_speed=)[\d.]+", rf"\g<1>{shutter}", text, count=1)
    if sky is not None:
        text = re.sub(r"(intensity_multiplier=)[\d.]+", rf"\g<1>{sky}", text, count=1)
    if width:
        text = re.sub(r"(\bimg_width=)\d+", rf"\g<1>{width}", text, count=1)
    if height:
        text = re.sub(r"(\bimg_height=)\d+", rf"\g<1>{height}", text, count=1)
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
    a = ap.parse_args()
    out = tweak_file(a.infile, a.outfile, iso=a.iso, fnum=a.fnum, shutter=a.shutter,
                     sky=a.sky, width=a.width, height=a.height)
    print(f"tweaked -> {out} (ISO={a.iso} f={a.fnum} shutter=1/{a.shutter} sky={a.sky})")
