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
    arm_width: float = 0.22          # X do braco
    arm_height: float = 0.62         # Z (topo do braco)
    foot_height: float = 0.10        # Z dos pes
    cushion_thickness: float = 0.15  # espessura da almofada do assento
    cushion_gap: float = 0.03        # VINCO visivel entre almofadas (anti-caixa-unica)
    chaise_depth: float = 1.60       # Y total da perna-chaise (deita as pernas)
    chaise_width: float = 0.95       # X da chaise
    fabric_rgb: tuple = (96, 100, 107)   # tecido cinza-escuro (visivel; KIVIK ~37,38,34)
    feet_rgb: tuple = (38, 38, 40)       # pes escuros

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


if __name__ == "__main__":
    import json
    for v in VARIANTS:
        s = sofa_spec(v)
        print(f"{v:14} bbox_m={s.bbox_m()} seats={s.seats}")
    print("\nschema keys:", list(SOFA_SCHEMA["properties"].keys()))
    print(json.dumps(sofa_spec("chaise_right").to_dict(), indent=2)[:400])
