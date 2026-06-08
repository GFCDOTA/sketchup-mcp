"""furniture_anatomy_spec.py — slice 2: especificacao de ANATOMIA parametrica de movel.
Comeca pelo SOFA. Define as PECAS semanticas obrigatorias + dimensoes (m), derivadas
da analise da referencia (Group_60 / KIVIK L-chaise) + padroes de ergonomia. O
SofaBuilder (slice 3) consome este spec; o gate (slice 5) valida contra ele.

Regra (Felipe): um sofa NAO pode ser uma caixa unica. Tem que ter base, assentos
SEPARADOS, encostos SEPARADOS, bracos, pes e (opcional) chaise — com orientacao
frontal clara (frente = -Y).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

VARIANTS = ("straight", "chaise_left", "chaise_right")

# pecas semanticas OBRIGATORIAS de um sofa (o gate exige presenca):
SOFA_REQUIRED_PARTS = ("base", "seat_cushion", "back_cushion", "arm", "foot")


@dataclass
class SofaSpec:
    """Anatomia parametrica de um sofa. Dims em metros. Convencao: X=largura,
    Y=profundidade (frente=0, fundo/encosto=Y maior), Z=altura; frente vira -Y
    quando posicionado na sala."""
    variant: str = "straight"        # straight | chaise_left | chaise_right
    seats: int = 3                   # n de lugares (= n de assentos/encostos)
    width: float = 2.20              # X total
    depth: float = 0.95              # Y do corpo principal
    height: float = 0.85             # Z (topo do encosto)
    seat_height: float = 0.45        # topo do assento (onde senta) a partir do chao
    seat_depth: float = 0.58         # profundidade util do assento (Y)
    back_thickness: float = 0.18     # profundidade do encosto (Y)
    arm_width: float = 0.18          # X do braco (GPT cycle2: 0.22 grosso demais -> afinar)
    arm_height: float = 0.62         # Z (topo do braco)
    foot_height: float = 0.10        # Z dos pes
    cushion_thickness: float = 0.15  # espessura da almofada do assento
    cushion_gap: float = 0.05        # VINCO/costura entre almofadas (GPT: fresta natural)
    cushion_bevel: float = 0.04      # chanfro/topo inset das almofadas (GPT: menos cubico)
    chaise_depth: float = 1.60       # Y total da perna-chaise (deita as pernas)
    chaise_width: float = 0.95       # X da chaise
    fabric_rgb: tuple = (182, 172, 153)  # tecido neutro linho/bege (GPT: nao cinza chapado)
    feet_rgb: tuple = (48, 40, 32)       # pes madeira escura

    def validate(self):
        assert self.variant in VARIANTS, f"variant invalido: {self.variant}"
        assert self.seats >= 1
        assert self.seat_height > self.foot_height
        assert self.height >= self.seat_height
        return self

    def bbox_m(self):
        """bbox esperado (W, D, H) — D cresce se houver chaise."""
        d = self.depth if self.variant == "straight" else max(self.depth, self.chaise_depth)
        return (round(self.width, 3), round(d, 3), round(self.height, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        d["required_parts"] = list(SOFA_REQUIRED_PARTS)
        return d


def sofa_spec(variant="straight", seats=3, **overrides):
    s = SofaSpec(variant=variant, seats=seats)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s.validate()


# JSON-schema (documental) do sofa — vira base do FurnitureAnatomySpec geral (msg 2).
SOFA_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SofaAnatomySpec",
    "type": "object",
    "required": ["variant", "seats", "width", "depth", "height", "required_parts"],
    "properties": {
        "variant": {"enum": list(VARIANTS)},
        "seats": {"type": "integer", "minimum": 1},
        "width": {"type": "number"}, "depth": {"type": "number"}, "height": {"type": "number"},
        "seat_height": {"type": "number"}, "seat_depth": {"type": "number"},
        "back_thickness": {"type": "number"},
        "arm_width": {"type": "number"}, "arm_height": {"type": "number"},
        "foot_height": {"type": "number"},
        "cushion_thickness": {"type": "number"}, "cushion_gap": {"type": "number"},
        "chaise_depth": {"type": "number"}, "chaise_width": {"type": "number"},
        "fabric_rgb": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
        "feet_rgb": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
        "required_parts": {"type": "array", "items": {"type": "string"}},
        "front_axis": {"const": "-Y"},
    },
}


# ---------------------------------------------------------------- CAMA (bed)
# pecas semanticas OBRIGATORIAS de uma cama (o gate exige presenca):
BED_REQUIRED_PARTS = ("estrado", "colchao", "travesseiro", "manta")
BED_SIZES = {"solteiro": (0.88, 1.88), "casal": (1.38, 1.88),
             "queen": (1.58, 1.98), "king": (1.93, 2.03)}


@dataclass
class BedSpec:
    """Anatomia parametrica de uma CAMA. Dims em metros. Convencao igual ao sofa:
    X=largura (ao longo da cabeceira), Y=comprimento (PE em Y=0=frente=-Y; CABECA em
    Y=L, encosta no painel/parede), Z=altura. Pecas SEPARADAS — NAO bloco unico:
    estrado (madeira), colchao (linho), travesseiros (cabeceira), manta dobrada no pe."""
    size: str = "king"               # solteiro | casal | queen | king
    width: float = 1.93              # X (sobrescrito por size)
    length: float = 2.03             # Y
    base_z0: float = 0.10            # estrado comeca elevado (plinto recuado)
    base_top: float = 0.38           # topo do estrado (onde deita o colchao)
    mattress_top: float = 0.55       # superficie de dormir
    mattress_inset: float = 0.03     # colchao levemente menor que o estrado? (na vdd transborda)
    pillow_h: float = 0.10           # espessura do travesseiro
    pillow_w: float = 0.50           # largura de cada travesseiro
    pillow_depth: float = 0.34       # profundidade (Y) do travesseiro
    n_pillows: int = 2
    blanket_h: float = 0.06          # manta/edredom dobrado no pe
    blanket_depth: float = 0.55      # quanto a manta cobre do pe (Y)
    bevel: float = 0.04              # chanfro/inset nas pecas macias (colchao/travesseiro/manta)
    estrado_rgb: tuple = (74, 56, 42)      # madeira escura
    mattress_rgb: tuple = (205, 196, 178)  # linho/creme (roupa de cama)
    pillow_rgb: tuple = (224, 218, 205)     # fronha clara
    blanket_rgb: tuple = (168, 140, 112)    # manta caramelo (acento quente)

    def validate(self):
        assert self.base_top > self.base_z0
        assert self.mattress_top > self.base_top
        assert self.n_pillows >= 1
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.length, 3),
                round(self.mattress_top + self.pillow_h, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        d["required_parts"] = list(BED_REQUIRED_PARTS)
        return d


def bed_spec(size="king", **overrides):
    w, l = BED_SIZES.get(size, BED_SIZES["king"])
    s = BedSpec(size=size, width=w, length=l)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s.validate()


# ---------------------------------------------------------------- GUARDA-ROUPA (wardrobe)
WARDROBE_REQUIRED_PARTS = ("corpo", "porta", "puxador", "rodape")


@dataclass
class WardrobeSpec:
    """Anatomia parametrica de um GUARDA-ROUPA. Dims em m. Convencao: X=largura (ao longo
    da parede), Y=profundidade (frente=0=-Y vira p/ dentro do quarto), Z=altura. Pecas
    SEPARADAS: rodape recuado + corpo + N portas (com frestas/divisoes) + puxadores."""
    width: float = 1.80          # X
    depth: float = 0.58          # Y (profundidade real de guarda-roupa)
    height: float = 2.20         # Z
    plinth_h: float = 0.08       # rodape recuado
    door_t: float = 0.03         # espessura da porta (proud da frente)
    door_gap: float = 0.02       # fresta entre portas (divisao vertical)
    handle_h: float = 0.40       # altura util do puxador
    body_rgb: tuple = (96, 74, 54)      # corpo madeira escura
    door_rgb: tuple = (132, 106, 78)    # portas madeira/laca mais clara (le como painel)
    handle_rgb: tuple = (44, 44, 48)    # puxador metal escuro
    plinth_rgb: tuple = (60, 46, 34)    # rodape mais escuro

    def n_doors(self):
        return 3 if self.width >= 1.8 else (2 if self.width >= 0.9 else 1)

    def validate(self):
        assert self.height > self.plinth_h
        assert self.width > 0 and self.depth > 0
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.depth, 3), round(self.height, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        d["n_doors"] = self.n_doors()
        d["required_parts"] = list(WARDROBE_REQUIRED_PARTS)
        return d


def wardrobe_spec(width=1.80, depth=0.58, height=2.20, **overrides):
    s = WardrobeSpec(width=width, depth=depth, height=height)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s.validate()


# ---------------------------------------------------------------- CRIADO-MUDO (nightstand)
NIGHTSTAND_REQUIRED_PARTS = ("corpo", "tampo", "gaveta", "pe")


@dataclass
class NightstandSpec:
    """Anatomia parametrica de um CRIADO-MUDO. Dims em m. Convencao: X=largura,
    Y=profundidade (FRENTE=Y=0=-Y, gaveta vira p/ fora), Z=altura. Pecas SEPARADAS:
    4 pes + corpo + tampo (transborda) + gaveta (frente) + knob."""
    width: float = 0.45
    depth: float = 0.40
    height: float = 0.55
    foot_h: float = 0.08
    top_t: float = 0.03          # espessura do tampo
    drawer_t: float = 0.02       # frente da gaveta (proud)
    body_rgb: tuple = (120, 95, 68)     # corpo madeira
    top_rgb: tuple = (82, 64, 48)       # tampo mais escuro (contraste)
    drawer_rgb: tuple = (142, 116, 86)  # frente de gaveta mais clara
    foot_rgb: tuple = (50, 42, 34)      # pes escuros
    knob_rgb: tuple = (44, 44, 48)      # puxador metal escuro

    def validate(self):
        assert self.height > self.foot_h + self.top_t
        assert self.width > 0 and self.depth > 0
        return self

    def bbox_m(self):
        return (round(self.width, 3), round(self.depth, 3), round(self.height, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        d["required_parts"] = list(NIGHTSTAND_REQUIRED_PARTS)
        return d


def nightstand_spec(width=0.45, depth=0.40, height=0.55, **overrides):
    s = NightstandSpec(width=width, depth=depth, height=height)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s.validate()


if __name__ == "__main__":
    import json
    for v in VARIANTS:
        s = sofa_spec(v)
        print(f"{v:14} bbox_m={s.bbox_m()} seats={s.seats}")
    print("\nschema keys:", list(SOFA_SCHEMA["properties"].keys()))
    print(json.dumps(sofa_spec("chaise_right").to_dict(), indent=2)[:400])
    print("\n--- camas ---")
    for sz in BED_SIZES:
        s = bed_spec(sz)
        print(f"{sz:10} bbox_m={s.bbox_m()} required={list(BED_REQUIRED_PARTS)}")
    print("\n--- guarda-roupas ---")
    for w in (1.2, 1.8, 2.4):
        s = wardrobe_spec(width=w)
        print(f"W={w} bbox_m={s.bbox_m()} portas={s.n_doors()} required={list(WARDROBE_REQUIRED_PARTS)}")
