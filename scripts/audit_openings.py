"""Auditoria one-shot: openings 15 -> 71 explosion post-hardening.

Gera artefatos JSON/MD:
  - distribuicoes por kind / orientation / width buckets
  - top suspects (width extrema)
  - map opening -> (room_a, room_b) via point-in-polygon do center deslocado
    perpendicularmente pra cada lado do opening
  - classificacao genuine (pelo menos um lado em room "legitima" > 3000 px2)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
CUR = ROOT / "runs" / "openings_audit" / "observed_model.json"
BASE = ROOT / "runs" / "baseline_pre_fix_main" / "observed_model.json"

LEGIT_AREA = 3000.0
OFFSET_PX = 8.0  # desloca do center pro centro da room de cada lado


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def room_polys(model: dict) -> list[tuple[str, float, Polygon]]:
    out: list[tuple[str, float, Polygon]] = []
    for r in model.get("rooms", []):
        poly = r.get("polygon") or []
        if len(poly) < 3:
            continue
        try:
            pg = Polygon(poly)
            if pg.is_valid and pg.area > 0:
                out.append((r["room_id"], r["area"], pg))
        except Exception:
            continue
    return out


def locate_rooms_for_opening(op: dict, rooms: list[tuple[str, float, Polygon]]):
    cx, cy = op["center"]
    orient = op["orientation"]
    # vetor perpendicular ao vao
    if orient == "horizontal":
        off = (0.0, OFFSET_PX)
    else:
        off = (OFFSET_PX, 0.0)
    side_a = Point(cx - off[0], cy - off[1])
    side_b = Point(cx + off[0], cy + off[1])

    def pick(pt):
        best = None
        for rid, area, pg in rooms:
            if pg.contains(pt):
                if best is None or area > best[1]:
                    best = (rid, area)
        return best

    return pick(side_a), pick(side_b)


def bucket(width: float) -> str:
    if width < 10:
        return "absurd_<10"
    if width < 60:
        return "tiny_10-60"
    if width < 110:
        return "door_60-110"
    if width < 200:
        return "wide_door_110-200"
    if width < 280:
        return "window_or_passage_200-280"
    return "suspect_>280"


def summarize(model: dict, label: str) -> dict:
    ops = model.get("openings", [])
    rooms = room_polys(model)
    legit_ids = {rid for rid, area, _ in rooms if area >= LEGIT_AREA}
    by_kind: dict[str, int] = {}
    by_orient: dict[str, int] = {}
    by_bucket: dict[str, int] = {}
    enriched = []
    for op in ops:
        k = op.get("kind", "?")
        o = op.get("orientation", "?")
        w = float(op.get("width", 0))
        by_kind[k] = by_kind.get(k, 0) + 1
        by_orient[o] = by_orient.get(o, 0) + 1
        b = bucket(w)
        by_bucket[b] = by_bucket.get(b, 0) + 1
        ra, rb = locate_rooms_for_opening(op, rooms)
        room_a_id = ra[0] if ra else None
        room_a_area = ra[1] if ra else None
        room_b_id = rb[0] if rb else None
        room_b_area = rb[1] if rb else None
        legit_a = bool(ra and ra[0] in legit_ids)
        legit_b = bool(rb and rb[0] in legit_ids)
        genuine = legit_a or legit_b
        enriched.append({
            **op,
            "room_a": room_a_id,
            "room_a_area": room_a_area,
            "room_b": room_b_id,
            "room_b_area": room_b_area,
            "legit_a": legit_a,
            "legit_b": legit_b,
            "genuine": genuine,
            "bucket": b,
        })
    n_rooms_legit = len(legit_ids)
    genuine_count = sum(1 for e in enriched if e["genuine"])
    return {
        "label": label,
        "n_openings": len(ops),
        "n_walls": len(model.get("walls", [])),
        "n_rooms_total": len(model.get("rooms", [])),
        "n_rooms_legit": n_rooms_legit,
        "legit_area_thr": LEGIT_AREA,
        "by_kind": by_kind,
        "by_orient": by_orient,
        "by_bucket": by_bucket,
        "genuine_count": genuine_count,
        "suspect_count": len(enriched) - genuine_count,
        "enriched": enriched,
    }


def main():
    cur = summarize(load(CUR), "post-hardening (2a268fe+hardening @ HEAD)")
    base = summarize(load(BASE), "baseline (pre-fix main dcb9751)")
    out = {"current": cur, "baseline": base}
    out_json = ROOT / "runs" / "openings_audit" / "audit_summary.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out_json)
    print("---CURRENT---")
    print(f"  n_openings={cur['n_openings']} n_walls={cur['n_walls']} n_rooms={cur['n_rooms_total']} (legit>={LEGIT_AREA}px2: {cur['n_rooms_legit']})")
    print("  by_kind", cur["by_kind"])
    print("  by_orient", cur["by_orient"])
    print("  by_bucket", cur["by_bucket"])
    print(f"  genuine={cur['genuine_count']} suspect={cur['suspect_count']}")
    print("---BASELINE---")
    print(f"  n_openings={base['n_openings']} n_walls={base['n_walls']} n_rooms={base['n_rooms_total']} (legit>={LEGIT_AREA}px2: {base['n_rooms_legit']})")
    print("  by_kind", base["by_kind"])
    print("  by_orient", base["by_orient"])
    print("  by_bucket", base["by_bucket"])
    print(f"  genuine={base['genuine_count']} suspect={base['suspect_count']}")


if __name__ == "__main__":
    main()
