"""Contrato canonico de escala, unidades, origem e transformacao (FP-055 P4). Dominio puro, sem SketchUp.

Referenciais da cadeia, todos com a MESMA origem (o ponto (0,0) do PDF) e sem espelhamento — o que muda e so a unidade:

    consensus (pt do PDF) --x pt_to_m--> plano (m)
    plano (m)             --/0.0254--> caixas do solver/builder e mundo do SketchUp (polegadas)
    mundo do SketchUp     --x0.0254--> inspecao (m)

O unico parametro livre e `pt_to_m`, e ele tem UMA regra: `core.scale.expected_pt_to_m(consensus_path=...)` — a mesma que o
shell builder aplica (`resolve_plant_pt_to_m`: planta registrada em `fixtures/<planta>/` usa a escala ancorada na cota; o
resto usa o padrao historico). O processo que gera as caixas congela `core.scale.PT_TO_M` no 1o import. Se os dois divergem,
`check_chain` devolve BLOCKED antes de qualquer construcao (achado da P4: shell a 0,0352 com caixas a 0,0259 — tudo
"conforme" e o armario 0,88 m fora do comodo).

`verify_against_built` confere o contrato contra a REALIDADE: as paredes do consensus transformadas pelo contrato precisam
coincidir com a massa de parede que o SketchUp construiu (IoU). Sem isso a escala declarada e so uma afirmacao.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

M_PER_IN = 0.0254
SCALE_TOL = 1e-6
# Limiares da verificacao do referencial contra o construido. O shell builder extruda EXATAMENTE o poligono de parede
# esperado; a unica diferenca legitima e o arredondamento da exportacao (0,1 mm no Ruby). Um erro de escala de 1,36x numa
# parede de 3 m desloca ~0,8 m. Por isso:
#   - WALL_IOU_MIN (global, 0,95) e so um filtro grosseiro: IoU global pode ficar alto com UMA parede errada numa planta
#     grande (parede de 0,5 m2 em 20 m2 mexe ~2%) — nao decide sozinho;
#   - por parede (decisivo): cobertura >= 0,99, excesso <= 1%, desvio maximo do contorno (Hausdorff) <= 1 cm e
#     comprimento/espessura com diferenca <= 1 cm (100x o arredondamento, ~1/80 do menor erro de escala que importa).
WALL_IOU_MIN = 0.95
WALL_COVER_MIN = 0.99
WALL_EXCESS_MAX = 0.01
WALL_HAUSDORFF_MAX_M = 0.01
WALL_DIM_TOL_M = 0.01
# Abertura morfologica (2 mm) aplicada IGUAL ao esperado e ao construido SO antes de contorno (Hausdorff) e dimensao
# (cobertura e excesso usam a geometria bruta; contencao/colisao/porta/funcional nunca passam por aqui): remove lascas com menos de
# 4 mm de largura que o corredor de uma parede corta de elementos vizinhos (planta_74: lasca de 3 mm2 gerava desvio de 5 cm em
# 9 paredes com area 100% coincidente). Um erro real que importa (>= 1 cm numa parede de 14 cm) tem 1 cm de largura e sobrevive.
SLIVER_OPEN_M = 0.002


@dataclass(frozen=True)
class PlanFrame:
    pt_to_m: float
    origin_pt: tuple[float, float] = (0.0, 0.0)
    flip_y: bool = False
    source: str = ""                     # de onde veio o pt_to_m (regra + caminho)

    @property
    def pt_to_in(self) -> float:
        return self.pt_to_m / M_PER_IN

    def pt_to_world_m(self, p) -> tuple[float, float]:
        x, y = p[0] - self.origin_pt[0], p[1] - self.origin_pt[1]
        return (x * self.pt_to_m, (-y if self.flip_y else y) * self.pt_to_m)

    def to_dict(self) -> dict:
        return {**asdict(self), "pt_to_in": self.pt_to_in}


def frame_for_consensus(consensus_path) -> PlanFrame:
    """O referencial que o SHELL BUILDER usa para este consensus (mesma regra, mesma funcao)."""
    from core.scale import expected_pt_to_m
    v = expected_pt_to_m(consensus_path=consensus_path)
    return PlanFrame(v, source=f"core.scale.expected_pt_to_m({consensus_path})")


def process_frame() -> PlanFrame:
    """O referencial em que ESTE processo gera as caixas (core.scale.PT_TO_M congelado no 1o import)."""
    from core.scale import PT_TO_M
    return PlanFrame(PT_TO_M, source="core.scale.PT_TO_M (processo)")


def check_chain(consensus_path) -> dict:
    """Shell x caixas x solver: um so referencial, ou BLOCKED com os dois valores."""
    shell, proc = frame_for_consensus(consensus_path), process_frame()
    same = abs(shell.pt_to_m - proc.pt_to_m) <= SCALE_TOL and shell.origin_pt == proc.origin_pt and shell.flip_y == proc.flip_y
    transforms = [
        {"from": "consensus", "to": "plano", "op": f"x pt_to_m ({proc.pt_to_m:.8f} m/pt)", "origin": "PDF (0,0)"},
        {"from": "plano", "to": "caixas solver/builder", "op": f"/ {M_PER_IN} (m -> in)", "origin": "PDF (0,0)"},
        {"from": "caixas", "to": "mundo SketchUp", "op": "identidade (polegadas)", "origin": "PDF (0,0)"},
        {"from": "mundo SketchUp", "to": "inspecao", "op": f"x {M_PER_IN} (in -> m)", "origin": "PDF (0,0)"},
    ]
    return {"status": "OK" if same else "BLOCKED_SCALE_MISMATCH", "shell": shell.to_dict(), "process": proc.to_dict(),
            "transforms": transforms,
            "reason": None if same else (f"shell em {shell.pt_to_m:.6f} m/pt e caixas em {proc.pt_to_m:.6f} m/pt "
                                         f"(fator {shell.pt_to_m / proc.pt_to_m:.4f})")}


def to_world_m(geom_pt, frame: PlanFrame):
    """Geometria shapely em pontos do PDF -> plano (m), pelo contrato."""
    from shapely.ops import transform
    return transform(lambda x, y, z=None: frame.pt_to_world_m((x, y)), geom_pt)


def _extent(geom, u):
    import math
    pts = []
    for g in getattr(geom, "geoms", [geom]):
        if hasattr(g, "exterior"):
            pts += list(g.exterior.coords)
    if not pts:
        return 0.0
    proj = [x * u[0] + y * u[1] for x, y in pts]
    return max(proj) - min(proj) if math.isfinite(max(proj)) else 0.0


def polygonal(g):
    """So a parte de AREA de uma geometria (interseccoes em juntas de parede devolvem GeometryCollection com linhas/pontos)."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union
    if g is None or g.is_empty:
        return Polygon()
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    parts = [x for x in getattr(g, "geoms", []) if isinstance(x, (Polygon, MultiPolygon)) and not x.is_empty]
    return unary_union(parts) if parts else Polygon()


def per_wall(walls: list[dict], expected_m, built, frame: PlanFrame, corridor_pad_m: float = 0.05) -> list[dict]:
    """Uma linha por parede do consensus: o que se esperava e o que foi construido DENTRO do corredor dessa parede."""
    import math

    from shapely.geometry import LineString
    out = []
    for w in walls:
        a, b = frame.pt_to_world_m(w["start"]), frame.pt_to_world_m(w["end"])
        L = math.dist(a, b)
        if L <= 1e-9:
            continue
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        n = (-u[1], u[0])
        t = float(w.get("thickness") or 0) * frame.pt_to_m
        corr = LineString([a, b]).buffer(t / 2 + corridor_pad_m, cap_style=2, join_style=2)
        exp, got = polygonal(expected_m.intersection(corr)), polygonal(built.intersection(corr))
        exp_o = polygonal(exp.buffer(-SLIVER_OPEN_M, join_style=2).buffer(SLIVER_OPEN_M, join_style=2))
        got_o = polygonal(got.buffer(-SLIVER_OPEN_M, join_style=2).buffer(SLIVER_OPEN_M, join_style=2))
        rem_e, rem_g = polygonal(exp.difference(exp_o)), polygonal(got.difference(got_o))
        if exp.is_empty:
            continue                                  # parede inteira dentro de vao (nada extrudado): nada a conferir
        cover = exp.intersection(got).area / exp.area
        excess = got.difference(exp).area / exp.area
        haus = exp_o.boundary.hausdorff_distance(got_o.boundary) if not got_o.is_empty else float("inf")
        dl, dt = abs(_extent(exp_o, u) - _extent(got_o, u)), abs(_extent(exp_o, n) - _extent(got_o, n))
        ok = (cover >= WALL_COVER_MIN and excess <= WALL_EXCESS_MAX and haus <= WALL_HAUSDORFF_MAX_M
              and dl <= WALL_DIM_TOL_M and dt <= WALL_DIM_TOL_M)
        out.append({"wall": w.get("id"), "ok": ok, "cover": round(cover, 4), "excess": round(excess, 4),
                    "hausdorff_m": round(haus, 4) if math.isfinite(haus) else None,
                    "d_length_m": round(dl, 4), "d_thickness_m": round(dt, 4),
                    # o que a normalizacao TIROU (so destas metricas de contorno/dimensao; cobertura e excesso usam o bruto)
                    "normalization": {"op": "opening", "radius_m": SLIVER_OPEN_M, "join": "mitre",
                                      "removed_expected_m2": round(rem_e.area, 8), "removed_built_m2": round(rem_g.area, 8),
                                      "removed_max_extent_m": round(max((max(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
                                                                         for g in getattr(rem_g, "geoms", [rem_g]) if not g.is_empty),
                                                                        default=0.0), 5)}})
    return out


def verify_against_built(expected_walls_pt, frame: PlanFrame, built_walls, walls: list[dict] | None = None) -> dict:
    """Referencial x realidade. Global (IoU, so filtro) + POR PAREDE (decisivo): uma boa sobreposicao global nao esconde uma
    parede errada. Sem parede esperada/construida ou sem a lista de paredes: BLOCKED (nunca OK por falta de dado)."""
    if built_walls is None or built_walls.is_empty:
        return {"status": "BLOCKED", "reason": "massa de parede construida ausente no modelo reaberto"}
    if expected_walls_pt is None or expected_walls_pt.is_empty:
        return {"status": "BLOCKED", "reason": "massa de parede esperada ausente"}
    exp = to_world_m(expected_walls_pt, frame)
    inter, union = exp.intersection(built_walls).area, exp.union(built_walls).area
    iou = inter / union if union else 0.0
    out = {"wall_iou": round(iou, 4), "min_iou": WALL_IOU_MIN, "expected_area_m2": round(exp.area, 4),
           "built_area_m2": round(built_walls.area, 4),
           "thresholds": {"cover_min": WALL_COVER_MIN, "excess_max": WALL_EXCESS_MAX,
                          "hausdorff_max_m": WALL_HAUSDORFF_MAX_M, "dim_tol_m": WALL_DIM_TOL_M}}
    if walls is None:
        return {**out, "status": "BLOCKED", "reason": "lista de paredes ausente: verificacao por parede nao executada"}
    rows = per_wall(walls, exp, built_walls, frame)
    bad = [r for r in rows if not r["ok"]]
    out["walls_checked"], out["walls_failed"], out["per_wall"] = len(rows), [r["wall"] for r in bad], rows
    if not rows:
        return {**out, "status": "BLOCKED", "reason": "nenhuma parede conferida"}
    out["status"] = "OK" if iou >= WALL_IOU_MIN and not bad else "BLOCKED_FRAME_MISMATCH"
    return out
