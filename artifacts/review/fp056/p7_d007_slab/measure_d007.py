"""FP-056 / #447 (D-007, "vao de mobiliar = laje"): mede as alternativas EM MEMORIA com as ferramentas do CI.

Reproducao (cwd = raiz do repo, commit limpo; nada e escrito fora da pasta de saida):
    PT_TO_M=0.0259 PYTHONPATH=. PYTHONIOENCODING=utf-8 python artifacts/review/fp056/p7_d007_slab/measure_d007.py \
        artifacts/review/fp056/p7_d007_slab/d007_alternatives.json

Alternativas (nada e aplicado ao gerador, ao consensus, as fixtures nem ao .skp; SketchUp nao e aberto):
  a  laje entra FLOOR_UNDER_FRAC (0,4) x espessura sob a parede = estado atual de develop; os planejadores usam a laje como cell
  b  FLOOR_UNDER_FRAC = 0 (laje sem entrar sob a parede), no shell (laje do gemeo) E nos planejadores (cache de geometria limpo)
  c  todos os planejadores usam a regiao utilizavel global (FP-056 P2: laje - massa de parede/barreira); o shell nao muda
  c:<rid>  a regiao utilizavel so no comodo <rid> (adocao comodo a comodo, #431 / D-010)
Cada uma tambem com a alternativa (b) da #484 (tracos sem fonte sb000-sb007 retirados do consensus EM MEMORIA): sufixo "+484b".

Medidas por variante (mesmas funcoes do CI, `tools.validation.quality_geometry_gate.evaluate`):
  caixas por comodo (`collect_boxes`), pre-voo por comodo (`layout_preflight.preflight` com `planta74_twin`),
  gemeo em caixas (`box_geometry.validate_boxes`) x `defect_baseline.json` da FP-055 P4 (novos/piores/resolvidos), programa
  perdido (`program_baseline.json` da FP-056 P2, menos as lacunas registradas em known_gaps.json), causas R1..R5 dos achados
  do gemeo (`defect_baseline.build_baseline`, regras geometricas do proprio modulo), ancora da pia
  (`tools.rooms.kitchen.anchor_rules.validate`). Se a geracao aborta, registra onde/por que e mede de novo em DIAGNOSTICO
  (o gate que abortou vira no-op so nessa medida; a geracao real continuaria abortada).
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROTECTED = ("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json", "artifacts/planta_74/planta_74.skp",
             "artifacts/planta_74/furnished/planta_74_furnished.skp")
UNSOURCED = {f"sb00{i}" for i in range(8)}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*a: str) -> str:
    return subprocess.check_output(["git", *a], cwd=ROOT, text=True).strip()


def poly_to_floor(poly) -> dict:
    return {"outer": [list(p) for p in list(poly.exterior.coords)[:-1]],
            "holes": [[list(p) for p in list(r.coords)[:-1]] for r in poly.interiors]}


class Variant:
    """Aplica uma alternativa em memoria e desfaz no fim (constante do shell, cache de geometria, cell dos planejadores)."""

    def __init__(self, under_frac: float, usable_rooms: tuple[str, ...]):
        self.under_frac, self.usable_rooms = under_frac, usable_rooms

    def __enter__(self):
        from tools.rooms.shared import spatial_model as sm
        from tools.sketchup.shell import build_plan_shell_skp as shell
        from tools.validation import circulation_gate
        self.shell, self.sm, self.cg = shell, sm, circulation_gate
        self.old_frac, self.old_geom = shell.FLOOR_UNDER_FRAC, sm._consensus_geometry
        shell.FLOOR_UNDER_FRAC = self.under_frac
        self._clear()
        if self.usable_rooms:
            from tools.rooms.shared.placement_region import usable_placement_region
            orig, regions = sm._consensus_geometry, {}

            def patched(con):
                wt, foot, env, floors = orig(con)
                key = hashlib.sha1(json.dumps(con, sort_keys=True, default=str).encode("utf-8")).hexdigest()
                if key not in regions:            # regiao calculada sobre a laje ORIGINAL do mesmo consensus
                    sm._consensus_geometry = orig
                    try:
                        regions[key] = {r: usable_placement_region(con, r)[0] for r in self.usable_rooms if r in floors}
                    finally:
                        sm._consensus_geometry = patched
                return wt, foot, env, {**floors, **{r: poly_to_floor(p) for r, p in regions[key].items()}}
            sm._consensus_geometry = patched
        return self

    def _clear(self):
        self.sm._GEOMETRY_CACHE.clear()
        self.cg._eroded_regions.cache_clear()

    def __exit__(self, *exc):
        self.shell.FLOOR_UNDER_FRAC, self.sm._consensus_geometry = self.old_frac, self.old_geom
        self._clear()
        return False


def short_tb(exc: BaseException) -> list[str]:
    frames = traceback.extract_tb(exc.__traceback__)
    rel = [f for f in frames if "site-packages" not in f.filename]
    return [f"{Path(f.filename).resolve().relative_to(ROOT).as_posix() if str(ROOT) in str(Path(f.filename).resolve()) else f.filename}"
            f":{f.lineno} {f.name}" for f in rel[-4:]] + [f"{type(exc).__name__}: {str(exc)[:200]}"]


def measure(con: dict, label: str) -> dict:
    from core.plan_frame import frame_for_consensus
    from core.scale import PT_TO_M
    from tools.furnish_apartment import collect_boxes
    from tools.rooms.kitchen import anchor_rules
    from tools.rooms.kitchen import validation as kval
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.rooms.shared.spatial_model import build_spatial_model
    from tools.validation import box_geometry as bx
    from tools.validation import built_geometry as bg
    from tools.validation import defect_baseline as db
    from tools.validation import known_gaps, layout_preflight
    t0 = time.time()
    out: dict = {"label": label, "generation": "OK", "abort": None}
    out["cell_m2"] = {r["id"]: round(build_spatial_model(con, r["id"])["_geom"]["cell"].area * PT_TO_M ** 2, 3) for r in con["rooms"]}
    anc = anchor_rules.validate(con, "r004")
    out["sink_anchor"] = {"result": anc["result"], "checks": anc["checks"]}
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            boxes, summary = collect_boxes(con)
    except BaseException as exc:  # noqa: BLE001 — SystemExit do gate da pia tambem e achado
        out["generation"] = "ABORTED"
        out["abort"] = {"traceback": short_tb(exc), "stdout_tail": log.getvalue().strip().splitlines()[-3:]}
        orig = kval.require_kitchen_anchor
        kval.require_kitchen_anchor = lambda c, r: None          # DIAGNOSTICO: so para medir os outros comodos
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                boxes, summary = collect_boxes(con)
            out["abort"]["diagnostic_continuation"] = "gate da ancora da pia desligado SO para medir; a geracao real aborta"
        except BaseException as exc2:  # noqa: BLE001
            out["abort"]["diagnostic_continuation"] = short_tb(exc2)
            out["seconds"] = round(time.time() - t0, 1)
            return out
        finally:
            kval.require_kitchen_anchor = orig
    out["trade_offs"] = [ln for ln in log.getvalue().splitlines() if "TRADE-OFF" in ln]
    out["n_boxes"] = len(boxes)
    out["boxes_by_room"] = {str(r[0]): r[4] for r in summary}
    out["planner_result_by_room"] = {str(r[0]): str(r[3]) for r in summary}
    twin = layout_preflight.planta74_twin(PLANTA_74_CONSENSUS)
    pre = layout_preflight.preflight(con, boxes, summary, twin)
    by_room: dict = {}
    for row in pre["rooms"]:
        d = by_room.setdefault(row["room_id"], {"status": [], "blocking": {}})
        d["status"].append(row["status"])
        if row["status"] in ("FAIL", "BLOCKED_MISSING_INPUT"):
            d["blocking"][row["gate"]] = row["reasons"]
    from core.constraint_result import combine
    out["preflight"] = pre["status"]
    out["preflight_by_room"] = {r: {"status": combine(d["status"]), "blocking": d["blocking"]} for r, d in by_room.items()}
    rooms = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
    reports = bx.validate_boxes(con, copy.deepcopy(boxes), PLANTA_74_CONSENSUS, rooms)
    base = json.loads((ROOT / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))["defects"]
    program = json.loads((ROOT / "artifacts/review/fp056/p2/program_baseline.json").read_text("utf-8"))["program"]
    reg = db.regression(reports, base, program)
    known = known_gaps.load()
    border = set(known.get("twin_borderline", {}))
    new = [d for d in reg["new"] if d["key"] not in border]
    out["twin"] = {"new": new, "worse": reg["worse"], "resolved": reg["resolved"], "vanished_with_piece": reg["vanished_with_piece"],
                   "twin_borderline_ignored": [d["key"] for d in reg["new"] if d["key"] in border],
                   "missing_program": reg["missing_program"],
                   "missing_program_unregistered": sorted(set(reg["missing_program"]) - set(known.get("program", {})))}
    r1_base = {b["key"]: b["measure"] for b in base if b["cause"] == "R1"}
    got = {db.key(rid, f): db.measure(f) for rid, rep in reports.items() for f in rep["findings"]
           if f.get("check") in ("CONTAINMENT", "WALL", "OBJECTS", "DOOR") and (f.get("module") or f.get("modules") or f.get("door"))}
    out["r1_baseline_keys"] = {k: {"baseline": m, "now": got.get(k)} for k, m in sorted(r1_base.items())}
    out["r1_baseline_persisting"] = sum(1 for k in r1_base if k in got)
    frame = frame_for_consensus(PLANTA_74_CONSENSUS)
    idx = bg.group_index(bx.build_result(con, copy.deepcopy(boxes), frame))
    rows = db.build_baseline(idx, rooms, bg.door_kinematics_m(con, frame))
    out["twin_findings_by_cause"] = dict(sorted(Counter(r["cause"] for r in rows).items()))
    out["twin_r1_findings"] = sorted(r["key"] for r in rows if r["cause"] == "R1")
    out["twin_findings_total"] = len(rows)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main() -> int:
    dest = Path(sys.argv[1]).resolve()
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    head, dirty = git("rev-parse", "HEAD"), git("status", "--porcelain")
    before = {p: sha(ROOT / p) for p in PROTECTED}
    con0 = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    con484 = copy.deepcopy(con0)
    con484["soft_barriers"] = [s for s in con484["soft_barriers"] if s.get("id") not in UNSOURCED]
    rooms = [r["id"] for r in con0["rooms"]]
    plan = [("a_atual", 0.4, ()), ("b_under0", 0.0, ()), ("c_usable_global", 0.4, tuple(rooms))]
    plan += [(f"c_usable_only_{r}", 0.4, (r,)) for r in rooms]
    res: dict = {"commit": head, "dirty": bool(dirty), "issue": 447, "variants": {}}
    for name, frac, usable in plan:
        for suffix, con in (("", con0), ("+484b", con484)):
            label = name + suffix
            with Variant(frac, usable):
                try:
                    res["variants"][label] = measure(copy.deepcopy(con), label)
                except BaseException as exc:  # noqa: BLE001
                    res["variants"][label] = {"label": label, "error": short_tb(exc)}
            v = res["variants"][label]
            print(label, v.get("generation"), v.get("n_boxes"), v.get("preflight"), "new", len(v.get("twin", {}).get("new", [])),
                  "worse", len(v.get("twin", {}).get("worse", [])), "R1", v.get("r1_baseline_persisting"),
                  "anchor", v.get("sink_anchor", {}).get("result"), f"{v.get('seconds')}s", flush=True)
    res["protected_before"], res["protected_after"] = before, {p: sha(ROOT / p) for p in PROTECTED}
    res["protected_unchanged"] = before == res["protected_after"]
    dest.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print("protected_unchanged", res["protected_unchanged"], "->", dest)
    return 0 if res["protected_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
