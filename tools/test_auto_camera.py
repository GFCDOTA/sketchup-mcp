"""Regressao do auto_camera: nos 3 comodos, o eye fica DENTRO do poligono do comodo, eye-level,
com fov/dist sãos. Garante que a camera auto-derivada nunca cai fora do comodo nem vira overview."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shapely.geometry import Point, Polygon  # noqa: E402

from tools.auto_camera import PT_TO_IN, auto_camera  # noqa: E402
from tools.furnish_apartment import CONSENSUS  # noqa: E402
from tools.spatial_model import build_spatial_model  # noqa: E402


def main():
    con = json.loads(CONSENSUS.read_text("utf-8"))
    for rid in ("r002", "r000", "r003"):
        cam = auto_camera(con, rid)
        ex, ey, ez = cam["eye"]
        cell = build_spatial_model(con, rid)["_geom"]["cell"]
        poly = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in cell.exterior.coords])
        inside = poly.contains(Point(ex, ey))
        good = inside and 50 <= ez <= 80 and 50 <= cam["fov"] <= 70 and 60 <= cam["dist"] <= 230
        print(f"[{'OK' if good else 'XX'}] {rid}: eye_in_room={inside} z={ez} fov={cam['fov']} dist={cam['dist']}")
        assert good, f"auto_camera {rid} fora dos limites: {cam}"
    print("\nTEST auto_camera OK: eye dentro do comodo, eye-level, fov/dist sãos nos 3 comodos.")


if __name__ == "__main__":
    main()
