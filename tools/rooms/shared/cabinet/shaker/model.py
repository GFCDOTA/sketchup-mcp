"""Entrada da porta Shaker: grandezas com unidade E origem, sem medida padrao (mesma regra do gabinete)."""
from __future__ import annotations

from dataclasses import dataclass

from ..model import GRAINS, CabinetInputError, quantity

SCHEMA_REQUEST = "shaker_door_request.v1"
STYLES = ("recessed_shaker",)
ROLES = ("frame", "panel")
GRAIN_SUPPORT = "NOT_SUPPORTED"          # UV/veio nao e aplicado; o plano apenas registra a orientacao pedida (R-14)


@dataclass(frozen=True)
class ShakerParams:
    request_id: str
    parent_request_id: str
    target_front: str
    stile_width: float
    rail_height: float
    frame_thickness: float
    panel_thickness: float
    recess: float
    materials: dict
    grain: dict
    origin_context: dict


def _ident(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(c in value for c in " /\\:"):
        raise CabinetInputError("INVALID_REQUEST_ID", field, "id estavel obrigatorio (sem espaco, / \\ ou :)")
    return value


def parse_shaker_request(request: dict) -> ShakerParams:
    if not isinstance(request, dict) or request.get("schema_version") != SCHEMA_REQUEST:
        raise CabinetInputError("INVALID_SCHEMA", "schema_version", f"esperado {SCHEMA_REQUEST!r}")
    if request.get("style") not in STYLES:
        raise CabinetInputError("UNSUPPORTED_STYLE", "style", f"estilos suportados: {STYLES} (veneziana/ferragem/gaveta nao existem)")
    rid = _ident(request.get("request_id"), "request_id")
    parent = _ident(request.get("parent_cabinet_request_id"), "parent_cabinet_request_id")
    target = _ident(request.get("target_front"), "target_front")
    frame, panel = request.get("frame") or {}, request.get("panel") or {}
    stile = quantity(frame.get("stile_width"), "frame.stile_width")
    rail = quantity(frame.get("rail_height"), "frame.rail_height")
    thickness = quantity(frame.get("frame_thickness"), "frame.frame_thickness")
    p_thickness = quantity(panel.get("thickness"), "panel.thickness")
    recess = quantity(panel.get("recess_from_frame_front"), "panel.recess_from_frame_front", allow_zero=True)
    materials, grain = dict(request.get("materials") or {}), dict(request.get("grain") or {})
    for role in ROLES:
        if not isinstance(materials.get(role), str) or not materials[role].strip():
            raise CabinetInputError("MISSING_MATERIAL", f"materials.{role}", "material por peca e obrigatorio")
        if grain.get(role) not in GRAINS:
            raise CabinetInputError("INVALID_GRAIN", f"grain.{role}", f"orientacao do veio fora de {GRAINS}")
    ctx = request.get("origin_context")
    if (not isinstance(ctx, dict) or not ctx.get("recipe_id") or not ctx.get("source_id")
            or not isinstance(ctx.get("source_verified"), bool)):
        raise CabinetInputError("MISSING_ORIGIN_CONTEXT", "origin_context",
                                "recipe_id, source_id e source_verified (bool) sao obrigatorios; a fonte nunca e presumida")
    return ShakerParams(rid, parent, target, stile, rail, thickness, p_thickness, recess,
                        {r: materials[r] for r in ROLES}, {r: grain[r] for r in ROLES},
                        {"recipe_id": ctx["recipe_id"], "source_id": ctx["source_id"], "source_verified": ctx["source_verified"]})
