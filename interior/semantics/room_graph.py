"""room_graph.py — Interior Common Sense Engine (slice 1a): RoomGraph. Constroi o
grafo semantico da planta a partir da consensus: cada comodo com seus walls + aberturas,
e a ADJACENCIA (quais comodos uma porta/passagem/porta-balcao conecta). Base pro
CirculationGraph, NoFurnitureZones e WallAffordanceMap. NAO mexe em parede/geometria.

Uso: python interior/semantics/room_graph.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.room_type import classify_rooms          # noqa: E402
from tools.spatial_model import build_spatial_model  # noqa: E402

CONNECTOR_KINDS = ("interior_door", "interior_passage", "glazed_balcony")


def build_room_graph(con):
    rooms = classify_rooms(con)
    room_data, op2rooms = {}, {}
    for r in rooms:
        sm = build_spatial_model(con, r["id"])
        room_data[r["id"]] = {
            "name": r["name"], "type": r["room_type"], "area_m2": round(sm["area_m2"], 1),
            "walls": [w["id"] for w in sm["walls"]],
            "openings": [{"wall_id": o["wall_id"], "kind": o.get("kind"),
                          "center": [round(c, 1) for c in o["center"]]} for o in sm["openings"]],
        }
        for o in sm["openings"]:
            key = (o["wall_id"], round(o["center"][0], 1), round(o["center"][1], 1))
            op2rooms.setdefault(key, {"kind": o.get("kind"), "rooms": set()})["rooms"].add(r["id"])

    adj = {r["id"]: set() for r in rooms}
    connectors = []
    for (wid, cx, cy), v in op2rooms.items():
        if v["kind"] in CONNECTOR_KINDS and len(v["rooms"]) >= 2:
            rs = sorted(v["rooms"])
            connectors.append({"wall_id": wid, "kind": v["kind"], "rooms": rs, "center": [cx, cy]})
            for a in rs:
                adj[a] |= set(rs) - {a}
    return {"rooms": room_data,
            "adjacency": {k: sorted(v) for k, v in adj.items()},
            "connectors": connectors}


def neighbors_through(graph, room_id):
    """Comodos vizinhos + por qual abertura (pra detectar 'TV de costas pra X')."""
    out = []
    for c in graph["connectors"]:
        if room_id in c["rooms"]:
            for other in c["rooms"]:
                if other != room_id:
                    out.append({"room": other, "wall_id": c["wall_id"], "kind": c["kind"]})
    return out


if __name__ == "__main__":
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    g = build_room_graph(con)
    print("=== ADJACENCIA ===")
    for rid, nb in g["adjacency"].items():
        nm = g["rooms"][rid]["name"][:18]
        print(f"  {rid} {nm:18} -> {nb}")
    out = ROOT / "artifacts/review/interior/room_graph_planta_74.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out.relative_to(ROOT)}")
