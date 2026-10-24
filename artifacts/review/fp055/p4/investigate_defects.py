"""Uso: PT_TO_M=0.0259 python artifacts/review/fp055/p4/investigate_defects.py <dir com geometry/> <saida.json>

Investigacao read-only das penetracoes reais (FP-055 P4): por achado, comodo/objeto/parte, parede do consensus mais
proxima, coordenadas, profundidade e o que ha no lugar (laje sob a parede? outro comodo? fora do envelope?)."""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from shapely.geometry import LineString  # noqa: E402

from core.plan_frame import frame_for_consensus  # noqa: E402
from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS  # noqa: E402
from tools.validation import built_geometry as bg  # noqa: E402
from tools.validation.penetration import outside_depth  # noqa: E402

proof = Path(sys.argv[1])
con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
fr = frame_for_consensus(PLANTA_74_CONSENSUS)
g = json.loads(Path(glob.glob(str(proof / "geometry" / "*result*.json"))[0]).read_text("utf-8"))
idx = bg.group_index(g)
walls = bg.built_walls(idx)
rooms = {r["id"]: str(r.get("name") or r["id"]) for r in con["rooms"]}
cwalls = [(w["id"], LineString([fr.pt_to_world_m(w["start"]), fr.pt_to_world_m(w["end"])]), float(w.get("thickness") or 0) * fr.pt_to_m)
          for w in con["walls"]]
floors = {rid: bg.room_floor(idx, rid) for rid in rooms}
slabs = {rid: bg.room_slab(idx, rid) for rid in rooms}
envelope = None
for f in floors.values():
    if f is not None:
        envelope = f if envelope is None else envelope.union(f)
envelope = envelope.union(walls)
doors = bg.door_kinematics_m(con, fr)
rows = []
for rid, name in rooms.items():
    rep = bg.validate_room(idx, rid, name, doors=doors)
    mods = bg.module_groups(idx, name)
    for f in rep["findings"]:
        if f["check"] not in ("CONTAINMENT", "WALL"):
            if f["check"] in ("OBJECTS", "DOOR"):
                rows.append({"room": f"{rid} {name}", "check": f["check"],
                             **{k: f.get(k) for k in ("modules", "door", "depth_m", "area_m2", "parts", "max_open_deg",
                                                      "blocked_by", "leaf_z_m", "z_overlap_m")}})
            continue
        m = f["module"]
        worst = None
        for fp, z0, z1, path in bg.parts(mods[m]):
            if z0 >= bg.FLOOR_LEVEL_M and f["check"] == "CONTAINMENT":
                continue
            d = outside_depth(fp, floors[rid]) if f["check"] == "CONTAINMENT" else (
                bg.wall_depth(fp, walls)["depth_m"] if fp.intersects(walls) else 0.0)
            if worst is None or d > worst[0]:
                worst = (d, fp, z0, z1, path)
        d, fp, z0, z1, path = worst
        out = fp.difference(floors[rid]) if f["check"] == "CONTAINMENT" else fp.intersection(walls)
        c = out.centroid if not out.is_empty else fp.centroid
        near = min(cwalls, key=lambda w: w[1].distance(c))
        where = []
        if slabs[rid] is not None and slabs[rid].contains(c):
            where.append("sobre a laje SOB a parede (D-007)")
        if walls.contains(c) or walls.distance(c) < 1e-6:
            where.append("dentro da massa de parede construida")
        for orid, of in floors.items():
            if orid != rid and of is not None and of.contains(c):
                where.append(f"dentro do piso de outro comodo: {orid} {rooms[orid]}")
        if not envelope.contains(c):
            where.append("FORA do envelope construido (nem comodo nem parede)")
        rows.append({"room": f"{rid} {name}", "check": f["check"], "module": m, "part": path.split("/")[-1],
                     "z_m": [round(z0, 3), round(z1, 3)], "depth_m": round(d, 4), "at_m": [round(c.x, 3), round(c.y, 3)],
                     "nearest_wall": near[0], "wall_thickness_m": round(near[2], 4),
                     "dist_to_wall_axis_m": round(near[1].distance(c), 4), "where": where or ["(nenhuma das hipoteses)"]})
Path(sys.argv[2]).write_text(json.dumps(rows, indent=1, ensure_ascii=False), "utf-8")
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
