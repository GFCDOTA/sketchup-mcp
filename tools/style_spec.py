"""Legacy public style API; shared room materials live in tools.rooms.shared.materials.

Preserves exported objects and callables without duplicating the style tables.
"""
from __future__ import annotations

from tools.rooms.shared import materials as _shared  # noqa: E402

StyleSpec = _shared.StyleSpec
STYLE_TOKENS = _shared.STYLE_TOKENS
get_style = _shared.get_style
apply_style = _shared.apply_style
resolve_material = _shared.resolve_material
attach_materials = _shared.attach_materials
module_family = _shared.module_family
texture_map_for = _shared.texture_map_for
finish_map_for = _shared.finish_map_for
tile_map_for = _shared.tile_map_for
texture_env = _shared.texture_env


def __getattr__(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_shared, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_shared)))
