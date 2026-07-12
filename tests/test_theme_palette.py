"""test_theme_palette.py — o binding tema→pixel do sweep su-free.

Rails: placeholder primário NUNCA sobrevive; temas distintos → pixels distintos;
whitelist (louça/colchão) intacta; tema desconhecido degrada honesto; puro.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.theme_palette import THEMES, apply_theme_palette  # noqa: E402

PLACEHOLDERS = [
    {"kind": "sofa_3", "rgb": [21, 101, 192]},     # azul debug
    {"kind": "rack_tv", "rgb": [106, 27, 154]},    # roxo debug
    {"kind": "mesa_centro", "rgb": [239, 108, 0]}, # laranja debug
]


def _spread(rgb):
    return max(rgb) - min(rgb)


def test_placeholders_never_survive_any_theme():
    for theme in (None, "warm_compact", "black_wood_gold", "dark_walnut", "tema_x"):
        out = apply_theme_palette([dict(b) for b in PLACEHOLDERS], theme)
        for b in out:
            assert _spread(b["rgb"]) <= 90, (theme, b)


def test_themes_are_visually_distinct():
    sofa = [{"kind": "sofa_3", "rgb": [21, 101, 192]}]
    got = {t: tuple(apply_theme_palette(sofa, t)[0]["rgb"])
           for t in ("warm_compact", "black_wood_gold", "dark_walnut")}
    assert len(set(got.values())) == 3          # 3 temas → 3 cores de sofá
    assert got["black_wood_gold"] == (48, 48, 52)


def test_preset_binding_black_wood_gold():
    boxes = [{"kind": "kc_porta", "rgb": [195, 171, 141]},   # cabinetry → preto fosco
             {"kind": "kc_puxador", "rgb": [44, 45, 50]},    # metal → dourado
             {"kind": "colchao", "rgb": [205, 196, 178]}]    # whitelist intacta
    out = apply_theme_palette(boxes, "black_wood_gold")
    assert out[0]["rgb"] == [28, 28, 30]
    assert out[1]["rgb"] == [176, 141, 66]
    assert out[2]["rgb"] == [205, 196, 178]


def test_unknown_theme_only_kills_placeholders():
    boxes = [{"kind": "porta", "rgb": [132, 106, 78]},       # neutro legítimo: fica
             {"kind": "misterio", "rgb": [239, 108, 0]}]     # placeholder: neutraliza
    out = apply_theme_palette(boxes, "tema_que_nao_existe")
    assert out[0]["rgb"] == [132, 106, 78]
    assert _spread(out[1]["rgb"]) <= 90


def test_pure_and_deterministic():
    src = [dict(b) for b in PLACEHOLDERS]
    a = apply_theme_palette(src, "dark_walnut")
    b = apply_theme_palette(src, "dark_walnut")
    assert a == b
    assert src[0]["rgb"] == [21, 101, 192]      # entrada nunca muta


def test_all_theme_palettes_are_interior_plausible():
    for theme, pal in THEMES.items():
        for role, rgb in pal.items():
            assert _spread(rgb) <= 110, (theme, role, rgb)  # dourado passa, debug não
