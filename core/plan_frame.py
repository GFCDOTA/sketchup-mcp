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
WALL_IOU_MIN = 0.95


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


def verify_against_built(expected_walls_pt, frame: PlanFrame, built_walls) -> dict:
    """IoU entre a massa de parede ESPERADA (o poligono que o shell builder extruda, em pt, levado ao plano pelo contrato) e a
    massa de parede CONSTRUIDA lida do modelo reaberto. Sem uma das duas: BLOCKED (nunca OK por falta de dado)."""
    if built_walls is None or built_walls.is_empty:
        return {"status": "BLOCKED", "reason": "massa de parede construida ausente no modelo reaberto"}
    if expected_walls_pt is None or expected_walls_pt.is_empty:
        return {"status": "BLOCKED", "reason": "massa de parede esperada ausente"}
    exp = to_world_m(expected_walls_pt, frame)
    inter, union = exp.intersection(built_walls).area, exp.union(built_walls).area
    iou = inter / union if union else 0.0
    return {"status": "OK" if iou >= WALL_IOU_MIN else "BLOCKED_FRAME_MISMATCH", "wall_iou": round(iou, 4),
            "min_iou": WALL_IOU_MIN, "expected_area_m2": round(exp.area, 4), "built_area_m2": round(built_walls.area, 4)}
