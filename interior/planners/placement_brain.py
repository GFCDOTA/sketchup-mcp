"""placement_brain.py — Interior Common Sense Engine: FurniturePlacementBrain BASE.
Nucleo GENERICO de inteligencia espacial p/ moveis (extraido do padrao PROVADO do sofa,
sem duplicar). Unifica RoomGraph + CirculationGraph + NoFurnitureZones + WallAffordanceMap
e resolve placement por RESTRICAO: gera CANDIDATOS por parede, pontua (hard rejects + soft
penalties), devolve o melhor + ScoreBreakdown + rejeitados com razao objetiva.

O SofaPlacementBrain (interior/planners/living_room_planner.py) continua como esta (marco
GPT-validado da sala — o sofa AINDA face a TV via aquela logica especializada); este base
e a fundacao reutilizavel p/ cama/guarda-roupa/criado (Fase 2). Deterministico, sem SU.

Uso: python -m interior.planners.placement_brain [room_id] [ftype]
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shapely.ops import unary_union                               # noqa: E402
from interior.semantics.room_graph import build_room_graph, neighbors_through  # noqa: E402
from interior.semantics.wall_affordance import wall_affordance     # noqa: E402
from tools.bedroom_layout import M, _door_zones, _fbox, _wall_setup  # noqa: E402
from tools.spatial_model import PT_TO_M, build_spatial_model        # noqa: E402

from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; env PT_TO_M -> 0.0259)
SCORE_KEY = {"tv": "tv_score", "sofa": "sofa_score", "bed": "bed_score", "wardrobe": "wardrobe_score"}
MIN_LEN = {"tv": 0.9, "sofa": 1.6, "bed": 1.4, "wardrobe": 1.0}


def _inward_normal(ws):
    return (0.0, float(ws["sgn"])) if ws["orient"] == "h" else (float(ws["sgn"]), 0.0)


@dataclass
class ScoreBreakdown:
    wall_id: str
    base_score: float
    hard_rejects: list = field(default_factory=list)
    soft_penalties: list = field(default_factory=list)
    final_score: float = 0.0


@dataclass
class CandidateLayout:
    ftype: str
    wall_id: str
    center_in: list
    facing: list
    w_m: float
    d_m: float
    score: float
    breakdown: dict
    reason: str = ""


class FurniturePlacementBrain:
    """Inteligencia espacial generica de um comodo. Reusa RoomGraph + WallAffordanceMap
    e expoe NoFurnitureZones, CirculationGraph e o solver place_against_wall."""

    def __init__(self, con, room_id):
        self.con, self.room_id = con, room_id
        self.sm = build_spatial_model(con, room_id)
        self.cell = self.sm["_geom"]["cell"]
        self.graph = build_room_graph(con)
        self.affordance = wall_affordance(con, room_id, self.graph)
        self.keepout = self._no_furniture_zones()

    # --- NoFurnitureZones: circulacao + giro de porta (proibido p/ movel grande) ---
    def _no_furniture_zones(self):
        circ = list(self.sm["_geom"]["circ"] or [])
        dz = _door_zones(self.sm)
        if dz is not None:
            circ.append(dz)
        return unary_union(circ) if circ else None

    # --- CirculationGraph: conectores do comodo (portas/passagens p/ vizinhos) ---
    def circulation(self):
        return {"room_id": self.room_id,
                "connectors": neighbors_through(self.graph, self.room_id),
                "has_keepout": self.keepout is not None}

    def wall(self, wid):
        return next((w for w in self.affordance["walls"] if w["wall_id"] == wid), None)

    def best_wall(self, ftype):
        key = SCORE_KEY.get(ftype, "sofa_score")
        ws = sorted(self.affordance["walls"], key=lambda w: -w.get(key, 0))
        return ws[0]["wall_id"] if ws and ws[0].get(key, 0) > 0 else None

    # --- desliza o movel pela parede ate spot dentro do comodo + livre de circulacao ---
    def _slide_clear(self, ws, w_m, d_m):
        lo = ws["along_lo"] + M(w_m / 2 + 0.1)
        hi = ws["along_hi"] - M(w_m / 2 + 0.1)
        if hi <= lo:
            return None
        mid = (lo + hi) / 2
        comodo = self.cell.buffer(M(0.06))
        nstep = max(1, int((hi - lo) / M(0.15)))
        for i in sorted(range(nstep + 1), key=lambda j: abs((lo + (hi - lo) * j / nstep) - mid)):
            ac = lo + (hi - lo) * i / nstep
            b = _fbox(ws["orient"], ws["face"], ws["sgn"], ac, M(0.03), M(w_m), M(d_m))
            if not comodo.contains(b):
                continue
            if self.keepout is not None and b.intersection(self.keepout).area > (0.05 / PT_TO_M ** 2):
                continue
            return ac
        return None

    def place_against_wall(self, ftype, w_m, d_m, min_len_m=None):
        """Gera candidatos (1 por parede), pontua (hard rejects + soft), devolve o
        melhor CandidateLayout + todos os candidatos + rejeitados. Generico: serve
        cama/guarda-roupa/criado (movel encosta na parede, frente p/ dentro do comodo)."""
        key = SCORE_KEY.get(ftype, "sofa_score")
        min_len_m = MIN_LEN.get(ftype, 1.0) if min_len_m is None else min_len_m
        cands, rejected = [], []
        for w in self.affordance["walls"]:
            ws = _wall_setup(self.sm, w["wall_id"])
            bd = ScoreBreakdown(wall_id=w["wall_id"], base_score=round(w.get(key, 0.0), 1))
            if ws is None:
                bd.hard_rejects.append("parede sem setup")
                rejected.append(asdict(bd))
                continue
            if w.get(key, -1) <= 0:
                bd.hard_rejects.append(f"score {ftype}<=0 (inadequada: {w['notes']})")
            if w["length_m"] < min_len_m:
                bd.hard_rejects.append(f"curta ({w['length_m']:.2f}<{min_len_m})")
            along = self._slide_clear(ws, w_m, d_m)
            if along is None:
                bd.hard_rejects.append("sem spot livre de circulacao")
            bd.final_score = round(bd.base_score, 1)
            if bd.hard_rejects:
                rejected.append(asdict(bd))
                continue
            n = _inward_normal(ws)
            perp = ws["face"] + ws["sgn"] * M(d_m / 2 + 0.03)
            pt = (along, perp) if ws["orient"] == "h" else (perp, along)
            cands.append(CandidateLayout(
                ftype=ftype, wall_id=w["wall_id"],
                center_in=[round(pt[0] * PT_TO_IN, 1), round(pt[1] * PT_TO_IN, 1)],
                facing=list(n), w_m=w_m, d_m=d_m, score=bd.final_score,
                breakdown=asdict(bd), reason=f"{ftype}: score {bd.final_score}; {w['notes']}"))
        cands.sort(key=lambda c: -c.score)
        return {"room_id": self.room_id, "ftype": ftype,
                "best": (asdict(cands[0]) if cands else None),
                "candidates": [asdict(c) for c in cands],
                "rejected": rejected}


if __name__ == "__main__":
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    rid = sys.argv[1] if len(sys.argv) > 1 else "r000"
    ftype = sys.argv[2] if len(sys.argv) > 2 else "bed"
    brain = FurniturePlacementBrain(con, rid)
    dims = {"bed": (1.93, 2.03), "wardrobe": (1.80, 0.60), "sofa": (2.20, 0.95)}.get(ftype, (1.5, 0.6))
    rep = brain.place_against_wall(ftype, *dims)
    print(f"=== FurniturePlacementBrain {rid} / {ftype} ===")
    print(f"  best_wall({ftype}) = {brain.best_wall(ftype)} | circ connectors = "
          f"{len(brain.circulation()['connectors'])}")
    for c in rep["candidates"][:4]:
        print(f"  CAND {c['wall_id']:5} score {c['score']:>6} center {c['center_in']} face {c['facing']}")
    for r in rep["rejected"][:6]:
        print(f"  x REJ {r['wall_id']:5} {r['hard_rejects']}")
    out = ROOT / f"artifacts/review/interior/placement_brain_{rid}_{ftype}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  -> {out.relative_to(ROOT)}")
