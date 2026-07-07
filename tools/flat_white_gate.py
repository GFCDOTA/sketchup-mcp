"""flat_white_gate.py — gate DETERMINISTICO HONESTO (FP-039 v2). NAO julga APARENCIA/estetica (isso e
so do Felipe — IMPROVED/SAME/WORSE nunca e auto, negative_dogfood). Responde SO ao que os pixels
medem de forma CONFIAVEL: "o render esta lavado de branco / monotono / quase-vazio?".

TAXONOMIA (tools/interior_studio/render_fingerprint.METRIC_TIERS):
- CONFIAVEL (decide veredito): near_white_frac (lavado), neutral_dominance (cinza/bege monotono),
  contrast_std (quase-vazio).
- ADVISORY (reportado, NUNCA decide): texture_frac, edge_frac, palette_entropy, large_flat_area_frac.
  Lição FP-036/FP-039: variancia de tile e area-chapada sao TRAICOEIRAS num render de linha do SU
  (tecido sutil, arestas AA, parede/piso solidos legitimos) — reportadas, nao usadas no veredito.
- PROIBIDO (a maquina NUNCA emite): "bonito/premium/elegante/..." (FORBIDDEN_JUDGMENT_TERMS). Travado
  por teste. O `verdict_from_reliable` recebe SO o tier confiavel -> nao consegue ler advisory.

Vocabulario FIXO de flags: chapado_de_branco, quase_branco, neutro_monotono, quase_vazio.
A prova de TEXTURA aplicada continua sendo o log per-kind do place_layout_skp.rb + o olho do Felipe.

Uso: python -m tools.flat_white_gate <render.png> [--style industrial]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# fracao de pixel quase-branco: render lavado/off-white (sinal CONFIAVEL)
WHITE_FRAC_FAIL = 0.55
WHITE_FRAC_WARN = 0.30
# neutro_monotono: MUITO neutro (cinza/bege dessaturado) E de BAIXA variacao = render apagado/'morto'.
# As DUAS condicoes (revisao adversarial): so 'muito neutro' pegaria um greyscale DETALHADO (que
# desenhou algo, nao e morto); exigir tambem contraste baixo garante que e de fato apagado. Calib:
# monotono neutral=0.97/contraste=2; industrial legitimo dessaturado <=0.80 (nao dispara de qualquer forma).
NEUTRAL_DOM_WARN = 0.90
NEUTRAL_CONTRAST_MAX = 15.0
# contraste global minusculo: quase-vazio / nao desenhou (calib: washed=3, monotono=2)
BLANK_STD_WARN = 3.0

_SEV = {"PASS": 0, "WARN": 1, "FAIL": 2}


def verdict_from_reliable(reliable: dict) -> dict:
    """VEREDITO = funcao PURA do tier CONFIAVEL (recebe SO `reliable` -> nao consegue ler advisory
    nem estetica). Devolve {result, flags, fails, warns}. flags = vocabulario FIXO, so descritivo."""
    nw = reliable["near_white_frac"]
    nd = reliable["neutral_dominance"]
    cs = reliable["contrast_std"]
    flags, fails, warns = [], [], []
    if nw >= WHITE_FRAC_FAIL:
        flags.append("chapado_de_branco")
        fails.append(f"chapado_de_branco: {nw:.0%} quase-branco (>{WHITE_FRAC_FAIL:.0%}) - render lavado")
    elif nw >= WHITE_FRAC_WARN:
        flags.append("quase_branco")
        warns.append(f"quase_branco: {nw:.0%} quase-branco (limite {WHITE_FRAC_WARN:.0%})")
    if nd >= NEUTRAL_DOM_WARN and cs < NEUTRAL_CONTRAST_MAX:
        flags.append("neutro_monotono")
        warns.append(f"neutro_monotono: {nd:.0%} cinza/bege dessaturado + contraste {cs} baixo (apagado)")
    if cs < BLANK_STD_WARN:
        flags.append("quase_vazio")
        warns.append(f"quase_vazio: contraste global {cs} (<{BLANK_STD_WARN}) - desenhou pouco?")
    result = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"result": result, "flags": flags, "fails": fails, "warns": warns}


def flat_white_check(png_path, style=None) -> dict:
    """{result, image, style, flags, fails, warns, reliable, advisory, metrics}. O veredito vem SO
    de `reliable` (via verdict_from_reliable); `advisory` e reportado mas nao decide."""
    from tools.interior_studio.render_fingerprint import fingerprint
    fp = fingerprint(png_path)
    v = verdict_from_reliable(fp["reliable"])
    return {
        "result": v["result"], "image": Path(png_path).name, "style": style,
        "flags": v["flags"], "fails": v["fails"], "warns": v["warns"],
        "reliable": fp["reliable"], "advisory": fp["advisory"],
        # compat FP-036 (consumidores leem r["metrics"][...]):
        "metrics": {"near_white_frac": fp["reliable"]["near_white_frac"],
                    "contrast_std": fp["reliable"]["contrast_std"],
                    "texture_frac_advisory": fp["advisory"]["texture_frac"],
                    "clipped_pct": fp["clipped_pct"], "mean_lum": fp["exposure"]["mean_lum"]},
    }


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
