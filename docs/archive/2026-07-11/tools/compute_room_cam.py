import json, sys
sys.path.insert(0, ".")
from tools.furnish_apartment import living_room_boxes, CONSENSUS
from tools.spatial_model import build_spatial_model

con = json.loads(CONSENSUS.read_text("utf-8"))
from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; env PT_TO_M -> 0.0259)
boxes, _ = living_room_boxes(con, "r002")
seat_kinds = ("base", "seat_cushion", "back_cushion", "arm", "foot", "rack_tv", "mesa_centro", "tapete")
seat = [b for b in boxes if b["kind"] in seat_kinds]
xs = [c[0] for b in seat for c in b["corners"]]
ys = [c[1] for b in seat for c in b["corners"]]
sx0, sy0, sx1, sy1 = min(xs), min(ys), max(xs), max(ys)
cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2

sm = build_spatial_model(con, "r002")
cell = sm["_geom"]["cell"]
bx0, by0, bx1, by1 = [v * PT_TO_IN for v in cell.bounds]

# eye: canto do cell mais distante do grupo (3/4 view), recuado da parede, elevado ~75in
ex = (bx1 - 30) if abs(bx1 - cx) > abs(cx - bx0) else (bx0 + 30)
ey = (by1 - 30) if abs(by1 - cy) > abs(cy - by0) else (by0 + 30)
ez = 78.0
tgt = (round(cx, 1), round(cy, 1), 22.0)
print(f"SEAT bbox_in: ({sx0:.0f},{sy0:.0f})-({sx1:.0f},{sy1:.0f}) center=({cx:.0f},{cy:.0f})")
print(f"CELL bbox_in: ({bx0:.0f},{by0:.0f})-({bx1:.0f},{by1:.0f})")
print(f"VRAY_EYE={ex:.1f},{ey:.1f},{ez:.1f}")
print(f"VRAY_TARGET={tgt[0]},{tgt[1]},{tgt[2]}")
