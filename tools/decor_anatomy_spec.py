"""decor_anatomy_spec.py — Intent-to-Scene slice 1: especificacao de ANATOMIA dos
componentes procedurais de DECOR da sala (rug, coffee_table, side_table, floor_lamp,
wall_art, curtain, plant_placeholder). Mesma convencao do furniture_anatomy_spec:
dims em METROS, X=largura, Y=profundidade (frente=-Y), Z=altura, origem no canto
(0,0,0). Pecas SEPARADAS com kind semantico — nao bloco unico. Os builders
(tools/decor_builders.py) consomem estes specs; o SceneSpatialGate valida bbox
plausivel via DECOR_PLAUSIBLE_BBOX_M.

Regra da slice: componentes nao precisam ser perfeitos; precisam ser coerentes,
proporcionais, leves e componentizados. Cores default = StylePack modern_warm_minimal
(o composer sobrescreve via material_style).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# pecas semanticas OBRIGATORIAS por tipo (gate exige presenca)
DECOR_REQUIRED_PARTS = {
    "rug": ("rug_field",),
    "coffee_table": ("top", "leg"),
    "side_table": ("top", "stem", "base"),
    "floor_lamp": ("base", "stem", "shade"),
    "wall_art": ("frame", "canvas"),
    "curtain": ("panel_fold", "rod"),
    "plant_placeholder": ("pot", "foliage"),
    "accent_seat": ("seat", "back", "leg"),
    "shelf": ("plank",),
    "track_light": ("rail", "spot"),
}

# bbox plausivel (W, D, H) em m por tipo — SpatialGate reprova movel fora da faixa.
# Inclui o sofa (hero) pra o gate cobrir a cena inteira com uma tabela so.
DECOR_PLAUSIBLE_BBOX_M = {
    "sofa": ((1.4, 3.6), (0.8, 1.8), (0.60, 1.10)),
    "rug": ((1.2, 4.5), (1.0, 3.5), (0.005, 0.03)),
    "coffee_table": ((0.6, 1.6), (0.4, 1.0), (0.25, 0.50)),
    "side_table": ((0.30, 0.70), (0.30, 0.70), (0.40, 0.75)),
    "floor_lamp": ((0.20, 0.60), (0.20, 0.60), (1.20, 1.90)),
    "wall_art": ((0.6, 2.2), (0.03, 0.12), (0.50, 1.60)),
    "curtain": ((0.6, 4.0), (0.03, 0.25), (1.80, 2.80)),
    "plant_placeholder": ((0.30, 0.90), (0.30, 0.90), (0.80, 2.00)),
    "accent_seat": ((0.50, 1.20), (0.50, 1.10), (0.35, 0.95)),
    "shelf": ((0.50, 1.80), (0.15, 0.36), (0.04, 1.00)),
    "track_light": ((0.80, 2.40), (0.03, 0.14), (0.05, 0.30)),
}


def _base_dict(s, kind):
    d = asdict(s)
    d["bbox_m"] = s.bbox_m()
    d["required_parts"] = list(DECOR_REQUIRED_PARTS[kind])
    return d


@dataclass
class RugSpec:
    """Tapete plano tecido: campo + borda em moldura (contraste sutil), fino."""
    width: float = 3.0
    depth: float = 2.0
    thickness: float = 0.012
    border_w: float = 0.12
    field_rgb: tuple = (224, 214, 195)    # cream_woven
    border_rgb: tuple = (205, 193, 172)   # tom mais escuro da trama

    def validate(self):
        assert self.width > 2 * self.border_w and self.depth > 2 * self.border_w
        assert 0.004 <= self.thickness <= 0.03
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.depth, 3), round(self.thickness, 3))

    def to_dict(self):
        return _base_dict(self, "rug")


@dataclass
class CoffeeTableSpec:
    """Mesa de centro baixa: tampo-laje pedra (travertino/concreto) + 2 pernas-laje
    metal preto recuadas (le como peca de design, nao caixote)."""
    width: float = 1.10
    depth: float = 0.60
    height: float = 0.36
    top_t: float = 0.06
    leg_t: float = 0.05          # espessura X de cada perna-laje
    leg_inset_x: float = 0.12    # recuo da perna a partir da ponta
    leg_inset_y: float = 0.06    # recuo da perna na profundidade
    top_rgb: tuple = (206, 193, 171)   # travertine
    leg_rgb: tuple = (38, 38, 40)      # black_metal

    def validate(self):
        assert self.height > self.top_t
        assert self.width > 2 * (self.leg_inset_x + self.leg_t)
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.depth, 3), round(self.height, 3))

    def to_dict(self):
        return _base_dict(self, "coffee_table")


@dataclass
class SideTableSpec:
    """Mesa lateral redonda slim: tampo disco + haste fina + base disco (metal)."""
    diameter: float = 0.45
    height: float = 0.55
    top_t: float = 0.025
    stem_t: float = 0.04
    base_d: float = 0.30
    base_t: float = 0.02
    top_rgb: tuple = (38, 38, 40)
    stem_rgb: tuple = (38, 38, 40)
    base_rgb: tuple = (38, 38, 40)

    def validate(self):
        assert self.height > self.top_t + self.base_t
        assert self.base_d < self.diameter * 0.9
        return self

    def bbox_m(self):
        return (round(self.diameter, 3), round(self.diameter, 3), round(self.height, 3))

    def to_dict(self):
        return _base_dict(self, "side_table")


@dataclass
class FloorLampSpec:
    """Luminaria de piso: base disco + haste fina metal + cupula tambor afunilada
    (verts8) em tecido ivory."""
    height: float = 1.65
    base_d: float = 0.28
    base_t: float = 0.025
    stem_t: float = 0.035
    shade_d: float = 0.42        # boca de baixo da cupula
    shade_top_d: float = 0.32    # topo afunilado
    shade_h: float = 0.24
    stem_rgb: tuple = (38, 38, 40)
    base_rgb: tuple = (38, 38, 40)
    shade_rgb: tuple = (238, 228, 204)  # warm_ivory_shade

    def validate(self):
        assert self.height > self.base_t + self.shade_h
        assert self.shade_top_d <= self.shade_d
        return self

    def bbox_m(self):
        w = round(max(self.base_d, self.shade_d), 3)
        return (w, w, round(self.height, 3))

    def to_dict(self):
        return _base_dict(self, "floor_lamp")


@dataclass
class WallArtSpec:
    """Quadro grande abstrato neutro: moldura fina metal + tela + 2 blocos de
    composicao (campo quente + faixa escura) levemente proud — le como arte
    abstrata sem precisar de textura."""
    width: float = 1.40
    height: float = 0.95
    depth: float = 0.06
    frame_t: float = 0.03
    canvas_rgb: tuple = (211, 199, 181)   # neutral_abstract
    frame_rgb: tuple = (38, 38, 40)
    accent_rgb: tuple = (128, 92, 64)     # burnt_umber
    accent2_rgb: tuple = (84, 80, 76)     # cinza quente escuro

    def validate(self):
        assert self.width > 4 * self.frame_t and self.height > 4 * self.frame_t
        assert 0.02 <= self.depth <= 0.12
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.depth, 3), round(self.height, 3))

    def to_dict(self):
        return _base_dict(self, "wall_art")


@dataclass
class CurtainSpec:
    """Cortina painel ondulado low-poly: N dobras verticais alternando offset em
    profundidade (fake wave) + varao metal. Largura = janela + transbordo.
    panel_split=2 abre a cortina em 2 paineis recolhidos nas pontas (cada um com
    panel_w de largura) — a cortina vira MOLDURA da janela, nao parede listrada
    (regra do cycle 002: cortina nao-protagonista)."""
    width: float = 2.2
    height: float = 2.40
    fold_w: float = 0.15
    fold_amp: float = 0.05       # amplitude da onda (offset Y alternado)
    thickness: float = 0.03
    rod_d: float = 0.035
    rod_overhang: float = 0.10   # varao passa da cortina nas pontas
    panel_split: int = 1         # 1 = painel unico fechado; 2 = paineis abertos
    panel_w: float = 0.55        # largura de CADA painel quando panel_split=2
    panel_rgb: tuple = (237, 231, 218)   # light_linen
    rod_rgb: tuple = (38, 38, 40)

    def validate(self):
        assert self.width >= 2 * self.fold_w
        assert self.height >= 1.8
        assert self.panel_split in (1, 2)
        if self.panel_split == 2:
            assert 2 * self.panel_w < self.width, "paineis abertos pedem vao central"
            assert self.panel_w >= self.fold_w
        return self

    def bbox_m(self):
        return (round(self.width + 2 * self.rod_overhang, 3),
                round(self.thickness + self.fold_amp + self.rod_d, 3),
                round(self.height + self.rod_d, 3))

    def to_dict(self):
        return _base_dict(self, "curtain")


@dataclass
class PlantSpec:
    """Planta placeholder: vaso + tronco + volume verde em 3 caixas sobrepostas
    decrescentes (silhueta organica sem botanica real)."""
    height: float = 1.50
    pot_w: float = 0.32
    pot_h: float = 0.30
    trunk_t: float = 0.05
    foliage_w: float = 0.55
    foliage_rgb: tuple = (97, 117, 73)   # soft_olive_green
    pot_rgb: tuple = (45, 43, 41)        # matte_black_pot
    trunk_rgb: tuple = (74, 56, 42)      # dark_walnut

    def validate(self):
        assert self.height > self.pot_h + 0.4
        assert self.foliage_w >= self.pot_w
        return self

    def bbox_m(self):
        return (round(self.foliage_w, 3), round(self.foliage_w, 3), round(self.height, 3))

    def to_dict(self):
        return _base_dict(self, "plant_placeholder")


@dataclass
class AccentSeatSpec:
    """Poltrona leve / assento de acento: 4 pes finos near-black + assento + encosto
    BAIXO em tecido claro. Elemento de contrapeso do hero (cycle 002: quebra o vazio
    da metade oposta ao sofa sem competir com ele — mais baixa e mais clara)."""
    width: float = 0.75
    depth: float = 0.80
    height: float = 0.72
    seat_h: float = 0.40
    leg_h: float = 0.13
    leg_t: float = 0.05
    leg_inset: float = 0.06
    back_t: float = 0.16
    seat_rgb: tuple = (196, 180, 158)   # warm_taupe_boucle
    leg_rgb: tuple = (20, 18, 16)       # near_black_wood

    def validate(self):
        assert self.height > self.seat_h > self.leg_h
        assert self.depth > self.back_t + 0.3, "assento util na frente do encosto"
        assert self.width > 2 * (self.leg_inset + self.leg_t)
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.depth, 3), round(self.height, 3))

    def to_dict(self):
        return _base_dict(self, "accent_seat")


@dataclass
class ShelfSpec:
    """Prateleira FLUTUANTE metal+madeira (industrial): N tabuas de madeira em mãos-
    francesas finas de metal preto. Monta na parede (fundo +Y). Frente = -Y."""
    width: float = 0.95
    depth: float = 0.22
    n_planks: int = 2
    plank_t: float = 0.04
    gap: float = 0.34            # vertical entre tabuas
    bracket_t: float = 0.022     # espessura da mão-francesa
    bracket_drop: float = 0.10   # quanto a mão-francesa desce abaixo da tabua
    plank_rgb: tuple = (96, 70, 48)    # madeira escura
    bracket_rgb: tuple = (30, 30, 33)  # metal preto fosco

    def validate(self):
        assert self.n_planks >= 1
        assert self.width > 0.3 and 0.12 <= self.depth <= 0.36
        return self

    def bbox_m(self):
        h = self.bracket_drop + (self.n_planks - 1) * self.gap + self.plank_t
        return (round(self.width, 3), round(self.depth, 3), round(h, 3))

    def to_dict(self):
        return _base_dict(self, "shelf")


@dataclass
class TrackLightSpec:
    """Trilho de luz de TETO (industrial): rail preto fino + N spots pendurados. Frente
    = -Y. Monta no teto (placement levanta via z_lift). Dirige fills quentes no render."""
    length: float = 1.60
    rail_w: float = 0.04         # largura/profundidade do rail (corre em X)
    rail_h: float = 0.04
    n_spots: int = 3
    spot_d: float = 0.07
    drop: float = 0.07           # quanto os spots descem abaixo do rail
    rail_rgb: tuple = (26, 26, 29)
    spot_rgb: tuple = (34, 34, 38)

    def validate(self):
        assert self.length >= 0.6 and self.n_spots >= 1
        return self

    def bbox_m(self):
        return (round(self.length, 3), round(self.rail_w, 3), round(self.drop + self.rail_h, 3))

    def to_dict(self):
        return _base_dict(self, "track_light")


_SPECS = {
    "rug": RugSpec, "coffee_table": CoffeeTableSpec, "side_table": SideTableSpec,
    "floor_lamp": FloorLampSpec, "wall_art": WallArtSpec, "curtain": CurtainSpec,
    "plant_placeholder": PlantSpec, "accent_seat": AccentSeatSpec,
    "shelf": ShelfSpec, "track_light": TrackLightSpec,
}


def decor_spec(kind, **overrides):
    """Factory padrao (igual sofa_spec): decor_spec('rug', width=3.2)."""
    cls = _SPECS.get(kind)
    assert cls is not None, f"tipo de decor desconhecido: {kind}"
    s = cls()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s.validate()


if __name__ == "__main__":
    for kind in _SPECS:
        s = decor_spec(kind)
        print(f"{kind:18} bbox_m={s.bbox_m()} required={DECOR_REQUIRED_PARTS[kind]}")
