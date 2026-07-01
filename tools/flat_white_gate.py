"""flat_white_gate.py — gate DETERMINISTICO anti-"chapado de branco / render lavado" (FP-036).
Espelha o molde dos *_gate (PASS/WARN/FAIL + metrics + CLI). NAO julga APARENCIA/estetica (isso e
so do Felipe — veredito visual IMPROVED/SAME/WORSE); responde ao objetivo deterministico e CONFIAVEL:
"o render esta chapado de BRANCO / lavado?" (proxy do 'moveis brancos' que o Felipe viu).

VEREDITO = near_white_frac (fracao de pixel quase-branco >=235). Sinal limpo e robusto: separa um
render lavado/off-white de qualquer render com cor.

texture_frac ('tem textura?') e REPORTADO como ADVISORY, mas NAO decide veredito. A revisao
adversarial provou que a variancia de tile NAO distingue de forma confiavel textura de material de
cor-chapada num render de LINHA do SketchUp: (a) as texturas de TECIDO do pipeline sao sutis (quase
no piso de ruido) e liam como chapadas -> falso-FAIL do proprio sofa que o FP-036 entrega; (b)
arestas antialiased do SU inflam o numero sem material -> falso-PASS. Entao a PROVA de textura
aplicada e o LOG PER-KIND do place_layout_skp.rb ("tex ph_<kind> <- <png>") + o olho do Felipe,
nao um limiar de pixel.

Uso: python -m tools.flat_white_gate <render.png> [--style industrial]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# fracao de pixel quase-branco: render lavado/off-white sem cor (o sinal CONFIAVEL do gate)
WHITE_FRAC_FAIL = 0.55
WHITE_FRAC_WARN = 0.30
# render quase-VAZIO/uniforme (nao desenhou / uma unica cor): contraste global minusculo
BLANK_STD_WARN = 3.0


def flat_white_check(png_path, style=None) -> dict:
    """{result, image, style, fails, warns, metrics}. FAIL = render lavado/chapado de branco
    (pega o 'moveis brancos' que o Felipe viu). texture_frac vai nas metrics como ADVISORY."""
    from tools.interior_studio.render_fingerprint import fingerprint
    fp = fingerprint(png_path)
    white = round(fp["near_white_pct"] / 100.0, 4)
    contrast = fp["exposure"]["contrast_std"]
    tex = fp["texture_frac"]                      # ADVISORY (nao decide veredito — ver docstring)
    fails, warns = [], []
    if white >= WHITE_FRAC_FAIL:
        fails.append(f"flat_white: {white:.0%} quase-branco (>{WHITE_FRAC_FAIL:.0%}) - render lavado/chapado")
    elif white >= WHITE_FRAC_WARN:
        warns.append(f"flat_white: {white:.0%} quase-branco (limite {WHITE_FRAC_WARN:.0%})")
    if contrast < BLANK_STD_WARN:
        warns.append(f"render quase-vazio: contraste global {contrast} (<{BLANK_STD_WARN}) - desenhou pouco?")
    result = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"result": result, "image": Path(png_path).name, "style": style,
            "fails": fails, "warns": warns,
            "metrics": {"near_white_frac": white, "contrast_std": contrast,
                        "texture_frac_advisory": tex,   # reportado, NAO usado no veredito
                        "clipped_pct": fp["clipped_pct"],
                        "mean_lum": fp["exposure"]["mean_lum"]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("--style", default=None)
    a = ap.parse_args()
    res = flat_white_check(a.png, a.style)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    sys.exit(1 if res["result"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
