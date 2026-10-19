"""Entrada do gabinete: grandezas com unidade E origem, sem medida padrao.

Toda medida chega como `{"value", "unit", "origin"}`. Falta de valor, unidade ou origem, valor nao finito/negativo
e origem `default_declared` (ou qualquer origem fora do vocabulario) recusam com `CabinetInputError` — o gabinete
nunca inventa dimensao para o apartamento.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

ORIGINS = ("user_request", "consensus", "pdf", "derived")
LENGTH_UNITS = {"m": 1.0, "cm": 0.01, "mm": 0.001}
GRAINS = ("along_width", "along_height", "along_depth", "none")
CARCASS_ROLES = ("carcass", "back", "front")        # papeis de material sempre presentes
SCHEMA_REQUEST = "cabinet_request.v1"


class CabinetInputError(ValueError):
    """Entrada recusada. `code` e estavel (usado por testes e pelo especialista); `field` aponta o campo."""

    def __init__(self, code: str, field: str, message: str):
        super().__init__(f"{code}: {field}: {message}")
        self.code, self.field, self.message = code, field, message


def quantity(node, field: str, *, kind: str = "length", allow_zero: bool = False) -> float:
    """Converte `{"value","unit","origin"}` para a unidade canonica (m, ou graus em `kind='angle'`)."""
    if not isinstance(node, dict):
        raise CabinetInputError("MISSING_QUANTITY", field, "grandeza ausente (esperado {value, unit, origin})")
    value, unit, origin = node.get("value"), node.get("unit"), node.get("origin")
    if not unit:
        raise CabinetInputError("MISSING_UNIT", field, "unidade ausente")
    if not origin:
        raise CabinetInputError("MISSING_ORIGIN", field, "origem ausente")
    if origin not in ORIGINS:
        raise CabinetInputError("INVALID_ORIGIN", field, f"origem {origin!r} fora de {ORIGINS} (sem 'default')")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CabinetInputError("MISSING_VALUE", field, "valor ausente ou nao numerico")
    if not math.isfinite(value):
        raise CabinetInputError("NON_FINITE", field, "valor nao finito")
    if kind == "angle":
        if unit != "deg":
            raise CabinetInputError("INVALID_UNIT", field, "angulo exige unidade 'deg'")
        return float(value)
    if unit not in LENGTH_UNITS:
        raise CabinetInputError("INVALID_UNIT", field, f"unidade {unit!r} fora de {tuple(LENGTH_UNITS)}")
    meters = float(value) * LENGTH_UNITS[unit]
    if meters < 0 or (meters == 0 and not allow_zero):
        raise CabinetInputError("NON_POSITIVE", field, "valor deve ser positivo")
    return meters


@dataclass(frozen=True)
class Params:
    request_id: str
    width: float
    depth: float
    height: float
    side: float
    top_bottom: float
    back: float
    front: float
    shelf_t: float | None
    front_clearance: float
    front_reveal: float
    fronts: int
    shelf_count: int
    shelf_z: float | None
    materials: dict
    grain: dict
    pose: dict          # {"x","y","z"} em m (referencia: quadro do projeto) e "rotation_deg" em graus


def _ident(request_id) -> str:
    if not isinstance(request_id, str) or not request_id.strip() or any(c in request_id for c in " /\\:"):
        raise CabinetInputError("INVALID_REQUEST_ID", "request_id", "id estavel obrigatorio (sem espaco, / \\ ou :)")
    return request_id


def parse_request(request: dict) -> Params:
    if not isinstance(request, dict) or request.get("schema_version") != SCHEMA_REQUEST:
        raise CabinetInputError("INVALID_SCHEMA", "schema_version", f"esperado {SCHEMA_REQUEST!r}")
    rid = _ident(request.get("request_id"))
    dims, panels = request.get("dimensions") or {}, request.get("panels") or {}
    gaps, fronts, shelf = request.get("gaps") or {}, request.get("fronts") or {}, request.get("shelf") or {}
    q = quantity
    width, depth, height = (q(dims.get(k), f"dimensions.{k}") for k in ("width", "depth", "height"))
    side, top_bottom = q(panels.get("side"), "panels.side"), q(panels.get("top_bottom"), "panels.top_bottom")
    back, front = q(panels.get("back"), "panels.back"), q(panels.get("front"), "panels.front")
    clearance = q(gaps.get("front_clearance"), "gaps.front_clearance", allow_zero=True)
    reveal = q(gaps.get("front_reveal"), "gaps.front_reveal", allow_zero=True)
    n_fronts = fronts.get("count")
    if n_fronts not in (1, 2):
        raise CabinetInputError("INVALID_FRONT_COUNT", "fronts.count", "frentes lisas: 1 ou 2")
    shelf_count = shelf.get("count")
    if shelf_count not in (0, 1):
        raise CabinetInputError("INVALID_SHELF_COUNT", "shelf.count", "prateleira opcional: 0 ou 1")
    shelf_t = shelf_z = None
    if shelf_count == 1:
        shelf_t = q(panels.get("shelf"), "panels.shelf")
        shelf_z = q(shelf.get("height_from_bottom"), "shelf.height_from_bottom")
    materials = dict(request.get("materials") or {})
    roles = list(CARCASS_ROLES) + (["shelf"] if shelf_count == 1 else [])
    for role in roles:
        if not isinstance(materials.get(role), str) or not materials[role].strip():
            raise CabinetInputError("MISSING_MATERIAL", f"materials.{role}", "material por peca e obrigatorio")
    grain = dict(request.get("grain") or {})
    for role in roles:
        if grain.get(role) not in GRAINS:
            raise CabinetInputError("INVALID_GRAIN", f"grain.{role}", f"orientacao do veio fora de {GRAINS}")
    pose_in = request.get("pose") or {}
    # posicao de projeto pode ser negativa (origem do consensus); so tamanho/espessura/folga exigem >= 0
    pose = {k: _signed(pose_in.get(k), f"pose.{k}") for k in ("x", "y", "z")}
    pose["rotation_deg"] = q(pose_in.get("rotation_deg"), "pose.rotation_deg", kind="angle")
    return Params(rid, width, depth, height, side, top_bottom, back, front, shelf_t, clearance, reveal,
                  n_fronts, shelf_count, shelf_z, materials, grain, pose)


def _signed(node, field: str) -> float:
    """Posicao de projeto: pode ser negativa (origem do consensus), mas segue exigindo valor, unidade e origem."""
    if not isinstance(node, dict):
        raise CabinetInputError("MISSING_QUANTITY", field, "grandeza ausente (esperado {value, unit, origin})")
    if not node.get("unit"):
        raise CabinetInputError("MISSING_UNIT", field, "unidade ausente")
    if not node.get("origin"):
        raise CabinetInputError("MISSING_ORIGIN", field, "origem ausente")
    value = node.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CabinetInputError("MISSING_VALUE", field, "valor ausente ou nao numerico")
    if not math.isfinite(value):
        raise CabinetInputError("NON_FINITE", field, "valor nao finito")
    if node["origin"] not in ORIGINS:
        raise CabinetInputError("INVALID_ORIGIN", field, f"origem {node['origin']!r} fora de {ORIGINS}")
    if node["unit"] not in LENGTH_UNITS:
        raise CabinetInputError("INVALID_UNIT", field, f"unidade {node['unit']!r} fora de {tuple(LENGTH_UNITS)}")
    return float(value) * LENGTH_UNITS[node["unit"]]
