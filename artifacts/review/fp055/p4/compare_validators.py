"""FP-055 P4 — regressao entre o validador antigo (V1, area) e o novo (V2, profundidade direcional + movimento de porta)
sobre a GEOMETRIA BRUTA ja extraida do SketchUp (inspect_geometry), sem rodar SketchUp de novo.

    PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp055/p4/compare_validators.py <dir_da_prova> <saida.json>

Entradas: <dir>/D_real_r006/geometry (apartamento real inteiro: 8 comodos) e as fixtures A, B, C_forced. Registra cada
mudanca de classificacao por comodo e por cheque, com os achados das duas versoes lado a lado. Nada aqui altera limiar.
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

V1_TO_V2 = {"EXTRACTION": "EXTRACTION", "CONTAINMENT": "CONTAINMENT", "WALL": "WALL", "DOOR_SWING": "DOOR",
            "OBJECTS": "OBJECTS"}


def _geom(d: Path) -> tuple[dict, str]:
    f = glob.glob(str(d / "geometry" / "*result*.json"))[0]
    raw = Path(f).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def compare(idx, con, frame, rooms: dict[str, str]) -> list[dict]:
    from tools.validation import built_geometry as bg
    swings = bg.door_swings_m(con, frame)
    kin = bg.door_kinematics_m(con, frame)
    out = []
    for rid, name in rooms.items():
        v1 = bg.validate_room_v1(idx, rid, name, door_swings=swings)
        v2 = bg.validate_room(idx, rid, name, doors=kin)
        changes = []
        for k1, k2 in V1_TO_V2.items():
            a, b = v1["checks"].get(k1), v2["checks"].get(k2)
            if a != b:
                changes.append({"check": k2, "v1": a, "v2": b,
                                "v1_findings": [f for f in v1["findings"] if f.get("check") == k1],
                                "v2_findings": [f for f in v2["findings"] if f.get("check") == k2]})
        out.append({"room_id": rid, "room": name, "v1": v1["checks"], "v2": v2["checks"], "changes": changes,
                    "v2_findings": v2["findings"], "door_motion": v2.get("door_motion"), "finishes": v2["finishes"]})
    return out


def main(proof: Path, out_path: Path) -> int:
    from core.plan_frame import frame_for_consensus
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    from tools.validation import built_geometry as bg
    res = {"inputs": {}, "cases": {}}
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    g, h = _geom(proof / "D_real_r006")
    res["inputs"]["D_real_r006"] = h
    rooms = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
    res["cases"]["planta_74 (8 comodos; r006 = proposta diagnostica)"] = compare(
        bg.group_index(g), con, frame_for_consensus(PLANTA_74_CONSENSUS), rooms)
    for case in ("A_fixture_valid", "B_fixture_notch", "C_forced"):
        d = proof / case
        cpath = proof / ("A_fixture_valid" if case == "C_forced" else case) / "consensus_synthetic.json"
        if not glob.glob(str(d / "geometry" / "*result*.json")) or not cpath.exists():
            res["cases"][case] = "SEM_GEOMETRIA"
            continue
        g, h = _geom(d)
        res["inputs"][case] = h
        c = json.loads(cpath.read_text("utf-8"))
        res["cases"][case] = compare(bg.group_index(g), c, frame_for_consensus(cpath), {"r_syn": "SINTETICO"})
    n = sum(len(r["changes"]) for v in res["cases"].values() if isinstance(v, list) for r in v)
    res["classification_changes"] = n
    out_path.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str) + "\n", "utf-8")
    for case, rows in res["cases"].items():
        if not isinstance(rows, list):
            print(case, rows)
            continue
        for r in rows:
            print(f"{case[:22]:22} {r['room_id']:5} {r['room'][:16]:16} v1={r['v1']} v2={r['v2']}")
            for c in r["changes"]:
                print(f"      MUDOU {c['check']}: {c['v1']} -> {c['v2']}  v2: {c['v2_findings'][:3]}")
    print("mudancas de classificacao:", n)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
