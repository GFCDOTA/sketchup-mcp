"""#446 / FP-056 R6 — arco de giro da porta do box do BANHO 01 (r005) com abertura declarada de 0,70 m. SO MEDE.

Pergunta (comentario de 2026-10-25 na #446, PR 559): o solver F2 da FEASIBLE para o BANHO 01 com box de abertura 0,70 m
(porta de abrir/pivotante) movendo so o Vaso, "mas nao modela o arco de giro". Aqui o arco e modelado com as ferramentas de
colisao que JA existem e medido contra louca, giro da porta do comodo, parede e as demais pecas do builder.

O que faz:
  1. reproduz `artifacts/review/fp056/p9_r6_errata_2026-10-25/probe_door_opening.py` (PR 559) para r005 / 0,70 m: mesmo
     monkeypatch de `tools.rooms.bathroom.layout._box_front`, mesmas caixas e interfaces, mesmo solver (`solve` + `rank`,
     exatamente o que `intelligent_pipeline.plan_room` chama) e confere status/candidatos/movimentos contra o JSON do PR;
  2. para CADA candidato FEASIBLE, pega a interface do box transformada pelo candidato e constroi o giro de uma folha de
     abrir (90 graus, para fora do box) com as duas dobradicas possiveis, em dois modelos de folha:
       A "declarada": folha = segmento da interface declarada ao solver (0,70 m);
       B "vao usavel": folha = trecho livre que o proprio solver mediu (`usable_segment` da linha shower.entry_width);
     cada um em duas geometrias ja existentes: `door_swings_pt` (quarto de circulo) e `door_sweeps_pt` (varredura da folha
     com espessura = vidro do builder);
  3. mede area de intersecao (cm2) com cada peca (z sobreposto a faixa da folha), com o giro/varredura das portas do comodo
     e com a massa de parede; e o maior angulo de abertura sem PENETRATION (`penetration.door_open_angle`).
Nada e aplicado: nenhum builder, limiar, layout, fixture ou .skp muda; o monkeypatch e desfeito no fim.

Uso (da raiz do repo):
  PT_TO_M=0.0259 PYTHONPATH=. PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe artifacts/review/fp056/p7_446_box_swing/measure_box_swing.py
  (~12 min: o solver avalia os 6 724 candidatos; `--reuse-solve` reaproveita a lista de FEASIBLE gravada em runs/)
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]          # artifacts/review/fp056/p7_446_box_swing -> raiz do repo
OUT_DIR = ROOT / "runs" / "fp056_r6_box_swing"      # saidas pesadas ficam em runs/ (scratch), como diz o README
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "box_swing_r005_opening070.json"
SOLVE_CACHE = OUT_DIR / "solve_cache_r005_opening070.json"
ROOM_ID = "r005"
OPENING_M = 0.70                     # probe_door_opening.py:20 (PR 559): ("abertura 0,70", 0.70)
GLASS_T_M = 0.008                    # tools/rooms/bathroom/layout.py:422 `gt = M(0.008)` (espessura do vidro do box)
LEAF_Z0_M, LEAF_Z1_M = 0.014, 2.44   # tools/rooms/bathroom/layout.py:441-442 (vidro fixo e folha: z 0,014 -> 2,44 m)
HIT_MIN_M2 = 1e-4                    # tools/validation/room_collisions.py:76,82 (`hit.area * PT_TO_M**2 > 1e-4`)
ENTRY_MIN_M = 0.60                   # core/functional_constraints.py:270-273 (shower.entry_width: minimo de referencia 0,60 m)
PR559_JSON = ROOT / "artifacts/review/fp056/p9_r6_errata_2026-10-25/door_opening_alternatives.json"

ORIGINS = {
    "abertura_0_70_m": "artifacts/review/fp056/p9_r6_errata_2026-10-25/probe_door_opening.py:20",
    "monkeypatch_fixw_eq_abertura_mais_0_05": "artifacts/review/fp056/p9_r6_errata_2026-10-25/probe_door_opening.py:12-16",
    "resultado_PR559_FEASIBLE_6724_so_Vaso": "artifacts/review/fp056/p9_r6_errata_2026-10-25/door_opening_alternatives.json:19-29",
    "frente_do_box_fonte_unica": "tools/rooms/bathroom/layout.py:188-205",
    "segmento_e_normal_da_interface_do_box": "tools/rooms/bathroom/layout.py:221-227",
    "espessura_vidro_0_008_m": "tools/rooms/bathroom/layout.py:422",
    "altura_folha_z_0_014_a_2_44_m": "tools/rooms/bathroom/layout.py:441-442",
    "toalheiro_z_1_10_a_1_14_m_a_0_14_m_da_frente": "tools/rooms/bathroom/layout.py:746-762",
    "tapete_z_0_013_a_0_020_m_a_0_12_m_da_frente": "tools/rooms/bathroom/layout.py:835-853",
    "revestimento_kb_parede_pedra_2_cm": "tools/rooms/bathroom/layout.py:606-638",
    "graus_de_liberdade_do_solver": "tools/rooms/bathroom/solver_policy.py:17-21",
    "solver_e_ordem": "tools/rooms/shared/spatial_solver/solver.py:69-98; ranking.py:40-65; "
                      "tools/orchestration/intelligent_pipeline.py:102-126",
    "vao_usavel_medido_pelo_solver": "tools/rooms/shared/spatial_solver/geometry.py:50-64",
    "largura_minima_de_entrada_0_60_m": "core/functional_constraints.py:270-273",
    "laje_entra_0_4_espessura_sob_a_parede": "tools/rooms/shared/clearance.py:6-8 (D-007)",
    "giro_quarto_de_circulo": "tools/rooms/shared/clearance.py:56-77 (door_swings_pt)",
    "varredura_da_folha": "tools/rooms/shared/clearance.py:80-111 (door_sweeps_pt)",
    "massa_de_parede": "tools/rooms/shared/clearance.py:21-25 (wall_mass_pt)",
    "pegada_da_peca": "tools/rooms/shared/clearance.py:114-118 (box_footprint_pt)",
    "limiar_de_hit_1_cm2": "tools/validation/room_collisions.py:76,82",
    "angulo_max_sem_penetracao": "tools/validation/penetration.py:140-163 (door_open_angle), EPS_DEPTH :38",
    "porta_do_comodo_h_o002": "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json:376-420 "
                              "(largura 24.358 pt, hinge left, swing neg; parede m008 :109-119)",
}


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"ERR {exc}"


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]


def _synthetic_door(seg_pt, normal, hinge_end: int, leaf_id: str) -> dict:
    """Consensus minimo (1 parede de espessura 0 + 1 porta) para reusar `door_swings_pt`/`door_sweeps_pt` sem copiar a geometria.
    A 'parede' e a linha da frente do box; a porta ocupa o segmento inteiro; dobradica na ponta `hinge_end` (0/1 do segmento)."""
    (x0, y0), (x1, y1) = seg_pt
    horiz = abs(y0 - y1) < 1e-6
    if not horiz and abs(x0 - x1) >= 1e-6:
        raise ValueError(f"segmento do box nao e axial: {seg_pt}")
    along0, along1 = (x0, x1) if horiz else (y0, y1)
    cross_n = normal[1] if horiz else normal[0]
    hinge_along = (along0, along1)[hinge_end]
    side = "left" if hinge_along <= min(along0, along1) + 1e-9 else "right"
    wall = {"id": "box_front", "start": [x0, y0], "end": [x1, y1], "thickness": 0.0}
    door = {"id": leaf_id, "kind": "door", "wall_id": "box_front", "center": [(x0 + x1) / 2, (y0 + y1) / 2],
            "opening_width_pts": math.hypot(x1 - x0, y1 - y0), "hinge_side": side,
            "swing_side": "pos" if cross_n > 0 else "neg"}
    return {"walls": [wall], "openings": [door]}


def _scale(g, f):
    from shapely.affinity import scale
    return scale(g, f, f, origin=(0, 0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse-solve", action="store_true", help="reaproveita a lista de FEASIBLE de runs/ (pula ~12 min)")
    ap.add_argument("--quick", type=int, default=0, help="DEPURACAO: avalia so os N primeiros candidatos (nao grava cache)")
    args = ap.parse_args()
    if os.environ.get("PT_TO_M") != "0.0259":
        print("PT_TO_M=0.0259 e obrigatorio (escala da planta_74)", file=sys.stderr)
        return 2
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    import tools.orchestration.furnish_apartment as fa
    import tools.rooms.bathroom.layout as bl
    from core.scale import PT_TO_IN, PT_TO_M
    from tools.furnish_apartment import collect_boxes
    from tools.orchestration import intelligent_pipeline as ip
    from tools.room_type import classify_rooms
    from tools.rooms.shared.clearance import (
        box_footprint_pt,
        door_sweeps_pt,
        door_swings_pt,
        wall_mass_pt,
    )
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.rooms.shared.spatial_solver import solver as sv
    from tools.rooms.shared.spatial_solver.candidates import apply_candidate, enumerate_candidates
    from tools.rooms.shared.spatial_solver.engine import evaluate_layout
    from tools.rooms.shared.spatial_solver.problem import build_problem, room_policy
    from tools.rooms.shared.spatial_solver.ranking import rank
    from tools.spatial_model import build_spatial_model
    from tools.validation.functional_clearance import collect_interfaces
    from tools.validation.penetration import classify, door_open_angle

    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    orig = bl._box_front

    def variant(opening_m):                     # COPIA LITERAL de probe_door_opening.py:12-17 (PR 559)
        def f(b, door_c):
            horiz, a0, a1, front, back, sin, fixw, leaf_lo = orig(b, door_c)
            return horiz, a0, a1, front, back, sin, bl.M(opening_m + 0.05), leaf_lo
        return f

    t_start = time.time()
    bl._box_front = variant(OPENING_M)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            boxes, _summary = collect_boxes(con)
            ifaces = collect_interfaces(con, boxes)
        rooms = {r["id"]: r for r in classify_rooms(con)}
        r = rooms[ROOM_ID]
        room_type, room_name = r["room_type"], str(r["name"])
        brain = fa.BRAINS.get(room_type)
        pol = room_policy(room_type)
        problem = build_problem(con, boxes, ROOM_ID, room_type, ifaces, policy=pol)
        cands = {c.candidate_id: c for c in enumerate_candidates(problem)}
        local = sv.neighborhood(con, boxes, ROOM_ID)

        if args.reuse_solve and SOLVE_CACHE.exists():
            cache = json.loads(SOLVE_CACHE.read_text("utf-8"))
            feas_rows = {}
            for cid in cache["feasible_ids"]:
                b2, i2 = apply_candidate(problem, local, ifaces, cands[cid], room_name)
                ev = evaluate_layout(con, b2, ROOM_ID, room_type, i2, room_name)
                assert ev.feasible, cid
                feas_rows[cid] = ev.rows
            solve_info = cache["solve"]
        else:
            t = time.time()
            kw = {"max_candidates": args.quick} if args.quick else {}
            res = sv.solve(problem, con, boxes, ifaces, room_name, **kw)
            ranked = rank(res.results)
            best = ranked[0]
            solve_info = {"status": res.status, "total_candidates": res.total_candidates, "evaluated": res.evaluated,
                          "feasible_count": len(res.feasible), "seconds": round(time.time() - t),
                          "best_candidate_id": best.result.candidate.candidate_id,
                          "best_status": "FEASIBLE" if best.result.feasible else "INFEASIBLE",
                          "best_moves": [m.object_id for m in best.result.candidate.moved],
                          "original_feasible": bool(res.original and res.original.feasible),
                          "original_rank": next(x.rank for x in ranked if x.result.candidate.candidate_id == "ORIGINAL"),
                          "feasible_by_moved_objects": {
                              k: sum(1 for x in res.feasible if "+".join(sorted(m.object_id for m in x.candidate.moved)) == k)
                              for k in sorted({"+".join(sorted(m.object_id for m in x.candidate.moved)) for x in res.feasible})},
                          "builder_symbol": ip._builder_symbol(brain)}
            feas_rows = {x.candidate.candidate_id: x.evaluation.get("rows", []) for x in res.results if x.feasible}
            if not args.quick:
                SOLVE_CACHE.write_text(json.dumps({"solve": solve_info, "feasible_ids": sorted(feas_rows)}, indent=1,
                                                  ensure_ascii=False), "utf-8")

        pr559 = json.loads(PR559_JSON.read_text("utf-8"))["r005:abertura 0,70"]
        repro = {"pr559": {k: pr559[k] for k in ("status", "candidates", "moves")},
                 "agora": {"status": solve_info["status"], "candidates": solve_info["total_candidates"],
                           "moves": solve_info["best_moves"]}}
        repro["reproduz"] = (repro["pr559"]["status"] == repro["agora"]["status"]
                             and repro["pr559"]["candidates"] == repro["agora"]["candidates"]
                             and repro["pr559"]["moves"] == repro["agora"]["moves"])

        # ---------- geometria fixa (pontos do consensus)
        cell_pt = build_spatial_model(con, ROOM_ID)["_geom"]["cell"]
        walls_pt = wall_mass_pt(con)
        room_swings = {k: v for k, v in door_swings_pt(con).items() if v.intersects(cell_pt)}
        room_sweeps = {k: v for k, v in door_sweeps_pt(con).items() if k in room_swings}
        to_m2 = PT_TO_M ** 2
        cm2 = lambda a_pt2: round(a_pt2 * to_m2 * 1e4, 1)          # noqa: E731
        cm = lambda d_pt: round(d_pt * PT_TO_M * 100, 1)             # noqa: E731

        def leaf_models(i2, rows):
            box_if = i2[(ROOM_ID, "Box")]
            seg_decl = [(x / PT_TO_IN, y / PT_TO_IN) for x, y in box_if.segment_in]
            row = next(x for x in rows if x["object_id"] == "Box" and x["constraint"] == "shower.entry_width")
            us = row["witness"]["usable_segment"]
            seg_use = [(x / PT_TO_IN, y / PT_TO_IN) for x, y in us]
            return box_if.normal, {"A_declarada": seg_decl, "B_vao_usavel": seg_use}, row["measured"]

        def end_label(seg_pt, k):
            """'lado_parede' = ponta mais perto da borda do comodo; a outra = 'lado_vidro_fixo'."""
            d = [Point(p).distance(cell_pt.exterior) for p in seg_pt]
            return "lado_parede" if d[k] <= d[1 - k] else "lado_vidro_fixo"

        geo_cache: dict = {}
        depth_cache: dict = {}
        per_candidate = []
        t_arc = time.time()
        for cid in sorted(feas_rows):
            cand = cands[cid]
            b2, i2 = apply_candidate(problem, local, ifaces, cand, room_name)
            normal, segs, entry_measured = leaf_models(i2, feas_rows[cid])
            moved = {m.object_id: {"slide_m": m.slide_m, "rot": m.rotation_deg, "mirror": m.mirrored} for m in cand.moved}
            obstacles = []
            for i, b in enumerate(b2):
                if b.get("room") == room_name and b.get("module") == "Box":
                    continue                           # o proprio box (desenho de correr do builder; a folha de abrir o substitui)
                fp = box_footprint_pt(b, PT_TO_IN)
                if fp is None or fp.is_empty:
                    continue
                z0 = float(b.get("z0_in") or 0.0) * 0.0254
                z1 = z0 + float(b.get("h_in") or 0.0) * 0.0254
                obstacles.append((f"{b.get('room')}|{b.get('module')}|{b.get('kind')}#{i}", b, fp, z0, z1))
            decl = LineString(segs["A_declarada"])
            clad = unary_union([fp for n, b, fp, z0, z1 in obstacles if b.get("kind") == "kb_parede_pedra"
                                and b.get("room") == room_name])
            in_wall = decl.intersection(walls_pt).length
            in_clad = decl.difference(walls_pt).intersection(clad).length if not clad.is_empty else 0.0
            use_len = LineString(segs["B_vao_usavel"]).length
            row_out = {"candidate_id": cid, "moves": moved, "entry_width_measured_m": entry_measured,
                       "declared_segment_breakdown_cm": {
                           "declarado": cm(decl.length), "dentro_da_massa_de_parede": cm(in_wall),
                           "dentro_do_revestimento_kb_parede_pedra": cm(in_clad), "vao_usavel_do_solver": cm(use_len),
                           "resto(folga 0,5 in do _free_without)": cm(decl.length - in_wall - in_clad - use_len)},
                       "leaves": {}}
            # pecas que o candidato MOVE (Vaso/Bancada do comodo) x pecas que ficam paradas (enxoval, pele, espelho, vizinhos)
            movable = [o for o in obstacles if o[1].get("room") == room_name and o[1].get("module") in ("Vaso", "Bancada")]
            fixed = [o for o in obstacles if o not in movable]
            for model, seg in segs.items():
                L_pt = math.hypot(seg[1][0] - seg[0][0], seg[1][1] - seg[0][1])
                for k in (0, 1):
                    lab = end_label(seg, k)
                    gkey = (model, lab, tuple(tuple(round(c, 4) for c in p) for p in seg), tuple(normal))
                    hinge, other = seg[k], seg[1 - k]
                    ux, uy = (other[0] - hinge[0]) / L_pt, (other[1] - hinge[1]) / L_pt
                    cs = 1 if (ux * normal[1] - uy * normal[0]) > 0 else -1

                    def _hit(name, b, fp, z0, z1, quarter, sweep):
                        aq, aw = fp.intersection(quarter).area, fp.intersection(sweep).area
                        if not (aq > 0 or aw > 0):
                            return None
                        z_ok = z1 > LEAF_Z0_M and z0 < LEAF_Z1_M
                        depth = None
                        if z_ok and aw > 0:              # profundidade fisica (MTD) da varredura na peca: penetration.classify
                            dk = gkey + (name, tuple(round(c, 3) for c in fp.bounds))
                            if dk not in depth_cache:
                                depth_cache[dk] = classify(_scale(sweep, PT_TO_M), _scale(fp, PT_TO_M))
                            depth = depth_cache[dk]
                        return {"piece": name, "module": str(b.get("module")), "kind": b.get("kind"),
                                "geometry_intent": b.get("geometry_intent"), "z_m": [round(z0, 4), round(z1, 4)],
                                "z_overlaps_leaf": z_ok, "area_quarter_cm2": cm2(aq), "area_sweep_cm2": cm2(aw),
                                "sweep_depth_mm": None if depth is None else round(depth["depth_m"] * 1000, 1),
                                "sweep_class": None if depth is None else depth["class"],
                                "counts": bool(z_ok and max(aq, aw) * to_m2 > HIT_MIN_M2)}

                    def _angles(obs_m):
                        def _angle(sel):
                            o = {n: g for n, g in obs_m.items() if sel(n)}
                            if not o:
                                return {"max_open_deg": 90.0, "blocked_by": None, "required_deg": 90.0, "ok": True}
                            return door_open_angle((hinge[0] * PT_TO_M, hinge[1] * PT_TO_M), L_pt * PT_TO_M, (ux, uy), cs, o,
                                                   leaf_thickness=GLASS_T_M)
                        return {"todas_as_pecas+parede": _angle(lambda n: True),
                                "sem_tapete": _angle(lambda n: "kb_tapete" not in n),
                                "sem_enxoval(tapete,toalheiro,...)": _angle(lambda n: "|Enxoval|" not in n),
                                "so_loucas+parede": _angle(lambda n: n == "PAREDE" or "|Vaso|" in n or "|Bancada|" in n)}

                    if gkey not in geo_cache:                # geometria da folha + tudo que NAO depende do candidato
                        syn = _synthetic_door(seg, normal, k, f"box_{model}_{lab}")
                        quarter = door_swings_pt(syn)[syn["openings"][0]["id"]]
                        sweep = door_sweeps_pt(syn, leaf_thickness_m=GLASS_T_M)[syn["openings"][0]["id"]]
                        fixed_hits = [h for h in (_hit(*o, quarter, sweep) for o in fixed) if h]
                        obs_fixed = {n: _scale(fp, PT_TO_M) for n, b, fp, z0, z1 in fixed
                                     if z1 > LEAF_Z0_M and z0 < LEAF_Z1_M and fp.intersects(sweep)}
                        wl = walls_pt.intersection(sweep.buffer(L_pt))
                        if not wl.is_empty and wl.intersects(sweep):
                            obs_fixed["PAREDE"] = _scale(wl, PT_TO_M)
                        geo_cache[gkey] = {
                            "quarter": quarter, "sweep": sweep, "fixed_hits": fixed_hits, "obs_fixed": obs_fixed,
                            "angles_fixed": _angles(obs_fixed),
                            "wall_area_quarter_cm2": cm2(walls_pt.intersection(quarter).area),
                            "wall_area_sweep_cm2": cm2(walls_pt.intersection(sweep).area),
                            "outside_room_cell_sweep_cm2": cm2(sweep.difference(cell_pt).area),
                            "room_doors": {d: {"area_quarter_x_swing_cm2": cm2(quarter.intersection(room_swings[d]).area),
                                               "area_sweep_x_sweep_cm2": cm2(sweep.intersection(room_sweeps[d]).area),
                                               "min_gap_cm": cm(sweep.distance(room_sweeps[d]))} for d in room_swings}}
                    g = geo_cache[gkey]
                    mov_hits, near, obs_mov = [], {}, {}
                    for name, b, fp, z0, z1 in movable:
                        mod = str(b.get("module"))
                        dist = fp.distance(g["sweep"])
                        near[mod] = dist if mod not in near else min(near[mod], dist)
                        h = _hit(name, b, fp, z0, z1, g["quarter"], g["sweep"])
                        if h:
                            mov_hits.append(h)
                            if h["z_overlaps_leaf"] and fp.intersects(g["sweep"]):
                                obs_mov[name] = _scale(fp, PT_TO_M)
                    # door_open_angle so recebe pecas que a varredura toca: se nenhuma peca movel toca, o angulo e o das fixas
                    angles = _angles({**g["obs_fixed"], **obs_mov}) if obs_mov else g["angles_fixed"]
                    row_out["leaves"][f"{model}:{lab}"] = {
                        "leaf_len_m": round(L_pt * PT_TO_M, 4), "hinge_pt": [round(hinge[0], 3), round(hinge[1], 3)],
                        "swing_dir": [normal[0], normal[1]],
                        "hits": sorted(g["fixed_hits"] + mov_hits, key=lambda h: -h["area_sweep_cm2"]),
                        "wall_area_quarter_cm2": g["wall_area_quarter_cm2"], "wall_area_sweep_cm2": g["wall_area_sweep_cm2"],
                        "outside_room_cell_sweep_cm2": g["outside_room_cell_sweep_cm2"],
                        "room_doors": g["room_doors"],
                        "min_gap_to_cm": {m: cm(d) for m, d in near.items()},
                        "door_open_angle": angles["todas_as_pecas+parede"],
                        "door_open_angle_by_obstacle_set": angles,
                        # folha aberta a 90 graus fica centrada na linha da dobradica (door_sweeps_pt): passagem = folha - t/2
                        "passage_with_leaf_open_m": round(L_pt * PT_TO_M - GLASS_T_M / 2, 4),
                    }
            per_candidate.append(row_out)
    finally:
        bl._box_front = orig

    # ---------- agregados
    def louca(h):
        return h["counts"] and h["module"] in ("Vaso", "Bancada")

    leaf_keys = sorted({k for c in per_candidate for k in c["leaves"]})
    summary = {}
    for lk in leaf_keys:
        rows = [c["leaves"][lk] for c in per_candidate]
        free_louca = [c for c in per_candidate if not any(louca(h) for h in c["leaves"][lk]["hits"])]
        free_lpd = [c for c in free_louca
                    if all(v["area_sweep_x_sweep_cm2"] == 0 and v["area_quarter_x_swing_cm2"] == 0
                           for v in c["leaves"][lk]["room_doors"].values())
                    and c["leaves"][lk]["wall_area_sweep_cm2"] == 0]
        free_all = [c for c in free_lpd if not any(h["counts"] for h in c["leaves"][lk]["hits"])]
        free_90 = [c for c in per_candidate if c["leaves"][lk]["door_open_angle"]["ok"]]
        per_piece: dict = {}
        for c in per_candidate:
            for h in c["leaves"][lk]["hits"]:
                if not h["counts"]:
                    continue
                p = per_piece.setdefault(f"{h['module']}/{h['kind']}", {"candidates": 0, "max_sweep_cm2": 0.0,
                                                                         "max_quarter_cm2": 0.0, "z_m": h["z_m"],
                                                                         "intent": h["geometry_intent"]})
                p["candidates"] += 1
                p["max_sweep_cm2"] = max(p["max_sweep_cm2"], h["area_sweep_cm2"])
                p["max_quarter_cm2"] = max(p["max_quarter_cm2"], h["area_quarter_cm2"])
        summary[lk] = {
            "feasible_total": len(per_candidate),
            "livre_de_loucas(Vaso,Bancada)": len(free_louca),
            "livre_de_loucas+porta_do_comodo+parede": len(free_lpd),
            "livre_de_tudo(inclui enxoval/pele)": len(free_all),
            "abre_90_sem_penetracao": len(free_90),
            "leaf_len_m": sorted({r["leaf_len_m"] for r in rows}),
            "wall_area_sweep_cm2": sorted({r["wall_area_sweep_cm2"] for r in rows}),
            "wall_area_quarter_cm2": sorted({r["wall_area_quarter_cm2"] for r in rows}),
            "room_doors": {d: {"max_sweep_x_sweep_cm2": max(r["room_doors"][d]["area_sweep_x_sweep_cm2"] for r in rows),
                               "max_quarter_x_swing_cm2": max(r["room_doors"][d]["area_quarter_x_swing_cm2"] for r in rows),
                               "min_gap_cm": min(r["room_doors"][d]["min_gap_cm"] for r in rows)}
                           for d in (rows[0]["room_doors"] if rows else {})},
            "min_gap_to_cm": {m: min(r["min_gap_to_cm"].get(m, math.inf) for r in rows) for m in ("Vaso", "Bancada")},
            "pieces_hit_counting": per_piece,
            "open_angle_distribution": sorted({(r["door_open_angle"]["max_open_deg"], r["door_open_angle"]["blocked_by"]
                                                and r["door_open_angle"]["blocked_by"].split("#")[0]) for r in rows}),
            "abre_90_por_conjunto_de_obstaculos": {
                s: sum(1 for r in rows if r["door_open_angle_by_obstacle_set"][s]["ok"])
                for s in (rows[0]["door_open_angle_by_obstacle_set"] if rows else {})},
            "angulo_por_conjunto_de_obstaculos": {
                s: sorted({(r["door_open_angle_by_obstacle_set"][s]["max_open_deg"],
                            (r["door_open_angle_by_obstacle_set"][s]["blocked_by"] or "-").split("#")[0]) for r in rows})
                for s in (rows[0]["door_open_angle_by_obstacle_set"] if rows else {})},
            "passage_with_leaf_open_m": sorted({r["passage_with_leaf_open_m"] for r in rows}),
        }

    vaso_positions = sorted({c["moves"].get(f"{ROOM_ID}:Vaso", {}).get("slide_m", 0.0) for c in per_candidate})
    out = {
        "what": "#446 R6 — arco de giro da porta do box (BANHO 01 r005, abertura declarada 0,70 m). SO MEDICAO (L1, sem SketchUp).",
        "git_head": _git("rev-parse", "HEAD"), "git_dirty_tracked": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "PT_TO_M": PT_TO_M,
        "code_sha256_16": {p: _sha(p) for p in (
            "tools/rooms/bathroom/layout.py", "tools/rooms/bathroom/solver_policy.py", "tools/rooms/shared/clearance.py",
            "tools/rooms/shared/spatial_solver/solver.py", "tools/rooms/shared/spatial_solver/candidates.py",
            "tools/rooms/shared/spatial_solver/engine.py", "tools/rooms/shared/spatial_solver/geometry.py",
            "tools/validation/room_collisions.py", "tools/validation/penetration.py",
            "artifacts/review/fp056/p9_r6_errata_2026-10-25/probe_door_opening.py",
            "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")},
        "origins": ORIGINS,
        "params": {"opening_m": OPENING_M, "glass_t_m": GLASS_T_M, "leaf_z_m": [LEAF_Z0_M, LEAF_Z1_M],
                   "hit_min_m2": HIT_MIN_M2, "swing_deg": 90, "swing_side": "para fora do box (normal da interface)"},
        "reproduction": repro, "solve": solve_info,
        "room_doors_considered": sorted(room_swings),
        "vaso_slides_in_feasible_m": vaso_positions,
        "summary": summary,
        "per_candidate": per_candidate,
        "seconds_arc": round(time.time() - t_arc), "seconds_total": round(time.time() - t_start),
        "pivot_bound_derived": {
            "entry_width_min_m": ENTRY_MIN_M, "origin": "core/functional_constraints.py:270-273 (shower.entry_width, 0,60 m)",
            "usable_len_m": sorted({c["leaves"][k]["leaf_len_m"] for c in per_candidate for k in c["leaves"]
                                    if k.startswith("B_")}),
            "max_pivot_offset_m": sorted({round(c["leaves"][k]["leaf_len_m"] - ENTRY_MIN_M - GLASS_T_M / 2, 4)
                                          for c in per_candidate for k in c["leaves"] if k.startswith("B_")}),
            "why": "pivo a p da ponta: aberta a 90 graus a parte longa fica na linha do pivo -> passagem = vao_usavel - p - t/2; "
                   "p acima disso reprova a largura de entrada que o proprio solver exige. A parte externa de qualquer pivo "
                   "fica DENTRO do setor de abrir com dobradica na mesma ponta (|E + p.u + r.v - E| <= p + r <= L), entao o "
                   "resultado 'abrir' e envelope da parte externa; a parte interna (raio p, dentro do box) nao foi medida.",
        },
        "not_modeled": [
            "pivotante: PR 559 cita 'abrir/pivotante' mas nao define a posicao do pivo; sem esse valor nao ha poligono",
            "folha com sobreposicao de batente (folha > vao): nenhum valor no codigo/PR",
            "abrir para DENTRO do box: fora do pedido (arco medido para fora)",
        ],
    }
    dest = OUT_JSON.with_name(OUT_JSON.stem + f"_quick{args.quick}.json") if args.quick else OUT_JSON
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), "utf-8")
    print(json.dumps({"reproduction": repro, "solve": solve_info, "summary": summary}, indent=1, ensure_ascii=False,
                     default=str))
    print(f"-> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
