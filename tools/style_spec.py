"""style_spec.py — gramatica de ESTILO de interior (tokens reusaveis): a camada que
FALTAVA. Mapeia `kind -> rgb` (e textura) por ESTILO e aplica nos boxes em tempo de
coleta, SEM reescrever builder. Espelha o programa de CLASSE de movel (dataclass +
tabela de tokens + gate). Slice 1 = "industrial" compacto (alvo: foto-referencia do
Felipe). Felipe 2026-06-18.

Cor entra por `apply_style` (reescreve b['rgb'] por kind = fonte UNICA do material SU
`ph_<kind>`, place_layout_skp.rb:113), rodando DENTRO da coleta antes do dump
LAYOUT_BOXES. Textura/BRDF entram no render (vray_export.rb / tweak_vrscene.py gated
por VRAY_STYLE). `texture_map_for` documenta o mapa que o .rb usa (mantido em sincronia).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StyleSpec:
    name: str
    kind_rgb: dict          # kind -> (r,g,b)   override de cor por papel
    kind_texture: dict      # kind -> textura png (espelha o tex_map gated do .rb)
    light_kelvin: int = 2700
    fill_color: tuple = (1.0, 0.82, 0.6)   # fill quente (~2700K)
    floor: str = "polished_concrete"
    must_style: tuple = ()  # kinds que TEM que ser recoloridos (checado no gate)


# ---- INDUSTRIAL compacto: sofa chumbo, rack baixo madeira escura, parede de concreto,
#      tapete cinza escuro, luz quente. (rack/mesa em peca unica aqui; black+wood
#      multi-part = slice 2 quando rack_class for wired). ----
_INDUSTRIAL_RGB = {
    "seat_cushion": (64, 66, 70), "back_cushion": (56, 58, 62), "arm": (60, 62, 66),
    "base": (34, 35, 38), "foot": (24, 24, 26),                 # sofa charcoal + base/pes escuros
    "rack_tv": (74, 56, 42),                                    # rack madeira escura (single-box)
    "mesa_centro": (60, 46, 34),                                # mesa de centro madeira escura
    "tapete": (54, 54, 58),                                     # tapete cinza escuro
    "parede_concreto": (165, 162, 158),                         # concreto aparente atras da TV
    "frame": (38, 38, 40),                                      # moldura do quadro = metal preto
}
_INDUSTRIAL_TEX = {
    "parede_concreto": "concrete.png",
    "rack_tv": "wood_dark.png", "mesa_centro": "wood_dark.png",
    "seat_cushion": "fabric_charcoal.png", "back_cushion": "fabric_charcoal.png",
    "arm": "fabric_charcoal.png", "tapete": "fabric_charcoal.png",
    "frame": "metal_black_matte.png",
}

STYLE_TOKENS = {
    "industrial": StyleSpec(
        name="industrial", kind_rgb=_INDUSTRIAL_RGB, kind_texture=_INDUSTRIAL_TEX,
        light_kelvin=2700, fill_color=(1.0, 0.82, 0.6), floor="polished_concrete",
        must_style=("seat_cushion", "back_cushion", "arm", "tapete"),
    ),
}


def get_style(name):
    return STYLE_TOKENS.get(name)


def apply_style(boxes, style_name):
    """Reescreve b['rgb'] por kind conforme o estilo (IN-PLACE). Fonte UNICA da cor do
    material SU ph_<kind>. Roda DENTRO da coleta, ANTES do dump LAYOUT_BOXES. Kinds fora
    do mapa (ex. foliage/pot da planta, ja industrial) ficam intactos. Devolve nº recolorido."""
    st = STYLE_TOKENS.get(style_name)
    if not st:
        return 0
    n = 0
    for b in boxes:
        rgb = st.kind_rgb.get(b.get("kind"))
        if rgb is not None:
            b["rgb"] = list(rgb)
            n += 1
    return n


def texture_map_for(style_name):
    """kind -> textura png (espelha o tex_map gated do vray_export.rb)."""
    st = STYLE_TOKENS.get(style_name)
    return dict(st.kind_texture) if st else {}


if __name__ == "__main__":
    for name, st in STYLE_TOKENS.items():
        print(f"STYLE {name}: {len(st.kind_rgb)} kinds, must_style={st.must_style}, "
              f"kelvin={st.light_kelvin}")
