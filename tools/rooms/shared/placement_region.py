"""UsablePlacementRegion (FP-056 contrato 1): onde um movel pode ocupar o piso — a laje do comodo MENOS a massa de parede e
de barreira (guarda-corpo), as mesmas pegadas que o shell builder usa. Nao e um recuo fixo do poligono.

`build_spatial_model` continua entregando a laje construtiva como `cell` (ConstructedFloorGeometry, 0,4t sob a parede —
RC-A / FP-043 D-007) para nao invalidar provas L2 que dependem dele; cada planejador passa a usar esta regiao quando a
adaptacao DELE estiver pronta e provada (FP-056 D-010: comodo por comodo). Unidade: pontos do PDF (a mesma do `cell`).
"""
from __future__ import annotations

from shapely.geometry import LineString
from shapely.ops import unary_union


def barrier_mass_pt(con: dict):
    """Massa de parede (pegadas com pontas estendidas) + guarda-corpos (`soft_barriers`, meia espessura de parede)."""
    from tools.rooms.shared.spatial_model import _consensus_geometry
    wt, foot, _env, _floors = _consensus_geometry(con)
    rails = [LineString([tuple(p) for p in s["polyline_pts"]]).buffer(wt / 2.0, cap_style=2, join_style=2)
             for s in con.get("soft_barriers", []) or [] if len(s.get("polyline_pts") or []) >= 2]
    return unary_union(list(foot.values()) + rails)


def usable_placement_region(con: dict, room_id: str) -> tuple:
    """(regiao em pontos, relatorio). Se a subtracao deixar mais de um pedaco, fica o maior; a area descartada vai no
    relatorio (nunca some em silencio)."""
    from core.scale import PT_TO_M
    from tools.rooms.shared.spatial_model import build_spatial_model
    slab = build_spatial_model(con, room_id)["_geom"]["cell"]
    free = slab.difference(barrier_mass_pt(con))
    parts = sorted((g for g in getattr(free, "geoms", [free]) if g.geom_type == "Polygon" and not g.is_empty),
                   key=lambda g: -g.area)
    region = parts[0] if parts else slab
    m2 = PT_TO_M ** 2
    return region, {"room_id": room_id, "slab_m2": round(slab.area * m2, 4), "usable_m2": round(region.area * m2, 4),
                    "under_walls_m2": round((slab.area - free.area) * m2, 4),
                    "dropped_pieces_m2": [round(g.area * m2, 5) for g in parts[1:]]}
