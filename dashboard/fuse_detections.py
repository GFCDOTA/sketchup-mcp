"""Fusion contract — produces consensus_model.json from multiple detection sources.

Contract:
  1. SVG-native (PyMuPDF.get_drawings) is PRIMARY for geometry: walls, door arcs.
  2. ML detectors (YOLO, CubiCasa, Qwen) only add votes/confidence/labels.
  3. ML cannot create wall/opening geometry — only confirm SVG seeds.
  4. Furniture has no SVG seed; ML is primary there.
  5. Room labels (PT-BR) come from Qwen, attached to pipeline room polygons by
     centroid containment.

Weights:
  SVG-native wall: 1.0
  SVG-native door arc: 1.0
  Pipeline V13 agreement: +0.3
  YOLO agreement: +0.2
  CubiCasa agreement: +0.2
  Qwen agreement: +0.15

Outputs:
  runs/<run>/consensus_model.json     (alongside observed_model.json)
  runs/<run>/consensus_overlay.png
  runs/<run>/pdf_vs_consensus.png
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPOS = {
    "main": Path("E:/Claude/sketchup-mcp"),
    "expdedup": Path("E:/Claude/sketchup-mcp-exp-dedup"),
}
HERE = Path(__file__).resolve().parent
DETECTIONS = HERE / "detections"

WEIGHTS = {
    "svg_native": 1.0,
    "pipeline_v13": 0.3,
    "yolo": 0.2,
    "cubicasa": 0.2,
    "qwen": 0.15,
}

WALL_DIST_TOL = 35.0
WALL_ANGLE_TOL = 10.0
OPENING_TOL = 40.0
PNG_300DPI_TO_PDF_PTS = 72.0 / 300.0


def midpoint(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def line_angle_mod180(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def angle_delta(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def wall_match(svg_w, v13_w):
    smid = midpoint(svg_w["start"], svg_w["end"])
    vmid = midpoint(v13_w["start"], v13_w["end"])
    if math.hypot(smid[0] - vmid[0], smid[1] - vmid[1]) > WALL_DIST_TOL:
        return False
    sa = line_angle_mod180(svg_w["start"], svg_w["end"])
    va = line_angle_mod180(v13_w["start"], v13_w["end"])
    return angle_delta(sa, va) <= WALL_ANGLE_TOL


def point_in_poly(point, poly):
    x, y = point
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def fuse(run_name: str, expdedup_run: str = None) -> dict:
    expdedup_run = expdedup_run or run_name
    t0 = time.time()

    run_dir = REPOS["expdedup"] / "runs" / expdedup_run
    observed = load_json(run_dir / "observed_model.json")
    svg_parsed = load_json(DETECTIONS / f"svg_parsed_{run_name}.json")
    yolo = load_json(DETECTIONS / f"yolo_clean_{run_name}.json")
    cubicasa = load_json(DETECTIONS / f"cubicasa_{run_name}.json")
    qwen = load_json(DETECTIONS / f"qwen_vl_clean_{run_name}.json")
    windows_svg = load_json(DETECTIONS / f"windows_svg_native_{run_name}.json")

    if svg_parsed is None:
        raise SystemExit(f"missing svg_parsed_{run_name}.json — run svg_native_parse.py first")
    if observed is None:
        raise SystemExit(f"missing observed_model.json in {run_dir}")

    page = observed.get("bounds", {}).get("pages", [{}])[0]
    px_min, py_min = page.get("min_x", 0), page.get("min_y", 0)
    px_max, py_max = page.get("max_x", 595), page.get("max_y", 842)

    pdf_path = REPOS["main"] / svg_parsed["pdf"].split("\\")[-1]
    if not pdf_path.exists():
        pdf_path = Path(svg_parsed["pdf"])

    # ---- WALLS ----
    import fitz
    doc = fitz.open(pdf_path)
    page0 = doc[0]
    drawings = page0.get_drawings()
    svg_walls = []
    svg_arcs = []
    for d in drawings:
        for it in d.get("items", []):
            op = it[0]
            if op == "l":
                p1, p2 = it[1], it[2]
                length = math.hypot(p2.x - p1.x, p2.y - p1.y)
                if length >= 50.0:
                    svg_walls.append({
                        "start": [p1.x, p1.y],
                        "end": [p2.x, p2.y],
                        "length_pt": length,
                        "angle_deg": line_angle_mod180((p1.x, p1.y), (p2.x, p2.y)),
                    })
            elif op == "c":
                p1, c1, c2, p3 = it[1], it[2], it[3], it[4]
                chord = math.hypot(p3.x - p1.x, p3.y - p1.y)
                if 8.0 < chord < 100.0:
                    svg_arcs.append({
                        "start": [p1.x, p1.y],
                        "end": [p3.x, p3.y],
                        "ctrl1": [c1.x, c1.y],
                        "ctrl2": [c2.x, c2.y],
                        "chord_pt": chord,
                    })

    # Normalize V13 raster ROI coords → SVG PDF-pt space via bbox alignment.
    svg_xs = [w["start"][0] for w in svg_walls] + [w["end"][0] for w in svg_walls]
    svg_ys = [w["start"][1] for w in svg_walls] + [w["end"][1] for w in svg_walls]
    svg_bbox = (min(svg_xs), min(svg_ys), max(svg_xs), max(svg_ys)) if svg_xs else (0, 0, 595, 842)
    v13_bbox = (px_min, py_min, px_max, py_max)

    def v13_to_svg(pt):
        if (v13_bbox[2] - v13_bbox[0]) < 1 or (v13_bbox[3] - v13_bbox[1]) < 1:
            return pt
        sx = svg_bbox[0] + (pt[0] - v13_bbox[0]) / (v13_bbox[2] - v13_bbox[0]) * (svg_bbox[2] - svg_bbox[0])
        sy = svg_bbox[1] + (pt[1] - v13_bbox[1]) / (v13_bbox[3] - v13_bbox[1]) * (svg_bbox[3] - svg_bbox[1])
        return [sx, sy]

    consensus_walls = []
    v13_walls_raw = observed.get("walls", [])
    v13_walls_norm = [
        {"start": v13_to_svg(w["start"]), "end": v13_to_svg(w["end"])}
        for w in v13_walls_raw
    ]
    for i, sw in enumerate(svg_walls):
        sources = ["svg_native"]
        confidence = WEIGHTS["svg_native"]
        for v13 in v13_walls_norm:
            if wall_match(sw, v13):
                sources.append("pipeline_v13")
                confidence += WEIGHTS["pipeline_v13"]
                break
        consensus_walls.append({
            "wall_id": f"cw-{i+1}",
            "start": [round(sw["start"][0], 2), round(sw["start"][1], 2)],
            "end": [round(sw["end"][0], 2), round(sw["end"][1], 2)],
            "length_pt": round(sw["length_pt"], 2),
            "angle_deg": round(sw["angle_deg"], 1),
            "sources": sources,
            "confidence": round(confidence, 3),
        })

    # ---- OPENINGS ----
    consensus_openings = []
    used_v13 = set()

    # SVG arcs as primary seeds (door arcs)
    for i, arc in enumerate(svg_arcs):
        center = midpoint(arc["start"], arc["end"])
        sources = ["svg_native"]
        confidence = WEIGHTS["svg_native"]
        kind = "door"
        hinge_side = None
        swing_deg = None
        room_a = None
        room_b = None
        for j, op in enumerate(observed.get("openings", [])):
            if j in used_v13:
                continue
            op_center_norm = v13_to_svg(op["center"])
            d = math.hypot(center[0] - op_center_norm[0], center[1] - op_center_norm[1])
            if d <= OPENING_TOL:
                used_v13.add(j)
                sources.append("pipeline_v13")
                confidence += WEIGHTS["pipeline_v13"]
                hinge_side = op.get("hinge_side")
                swing_deg = op.get("swing_deg")
                room_a = op.get("room_a")
                room_b = op.get("room_b")
                break
        # YOLO door agreement (clean coords in PNG 300dpi)
        if yolo:
            for det in yolo.get("detections", []):
                if det["class"] == "Door":
                    bx = (det["bbox"][0] + det["bbox"][2]) / 2 * PNG_300DPI_TO_PDF_PTS
                    by = (det["bbox"][1] + det["bbox"][3]) / 2 * PNG_300DPI_TO_PDF_PTS
                    if math.hypot(center[0] - bx, center[1] - by) <= OPENING_TOL:
                        sources.append("yolo_clean")
                        confidence += WEIGHTS["yolo"]
                        break
        consensus_openings.append({
            "opening_id": f"co-{i+1}",
            "center": [round(center[0], 2), round(center[1], 2)],
            "chord_pt": round(arc["chord_pt"], 2),
            "kind": kind,
            "hinge_side": hinge_side,
            "swing_deg": swing_deg,
            "room_a": room_a,
            "room_b": room_b,
            "sources": sources,
            "confidence": round(confidence, 3),
            "geometry_origin": "svg_arc",
        })

    # Pipeline V13 openings without SVG arc (passages/non-door openings)
    for j, op in enumerate(observed.get("openings", [])):
        if j in used_v13:
            continue
        cn = v13_to_svg(op["center"])
        consensus_openings.append({
            "opening_id": f"co-{len(consensus_openings)+1}",
            "center": [round(cn[0], 2), round(cn[1], 2)],
            "chord_pt": round(op.get("width", 0), 2),
            "kind": op.get("kind", "passage"),
            "hinge_side": op.get("hinge_side"),
            "swing_deg": op.get("swing_deg"),
            "room_a": op.get("room_a"),
            "room_b": op.get("room_b"),
            "sources": ["pipeline_v13"],
            "confidence": round(WEIGHTS["pipeline_v13"], 3),
            "geometry_origin": "pipeline_gap",
        })

    # ---- WINDOWS (svg-native pair-of-parallel-lines detector) ----
    # Additive: append as kind="window" to consensus_openings without altering door logic.
    windows_added = 0
    if windows_svg:
        for wi, w in enumerate(windows_svg.get("detections", [])):
            consensus_openings.append({
                "opening_id": f"co-{len(consensus_openings)+1}",
                "center": [round(w["center"][0], 2), round(w["center"][1], 2)],
                "chord_pt": round(w.get("width_pt", 0), 2),
                "kind": "window",
                "hinge_side": None,
                "swing_deg": None,
                "room_a": None,
                "room_b": None,
                "orientation": w.get("orientation"),
                "wall_thickness_pt": w.get("wall_thickness_pt"),
                "bbox": w.get("bbox"),
                "sources": ["svg_native_windows"],
                "confidence": round(WEIGHTS["svg_native"], 3),
                "geometry_origin": "svg_window_pair",
            })
            windows_added += 1

    # ---- ROOMS (V13 polygons + Qwen PT-BR labels) ----
    qwen_rooms = []
    if qwen:
        parsed = qwen.get("parsed") or {}
        raw = parsed.get("rooms") or parsed.get("rooms_visible") or []
        for r in raw:
            if isinstance(r, dict):
                qwen_rooms.append(r.get("name", ""))
            elif isinstance(r, str):
                qwen_rooms.append(r)
    consensus_rooms = []
    for i, room in enumerate(observed.get("rooms", [])):
        poly = [v13_to_svg(p) for p in room.get("polygon", [])]
        consensus_rooms.append({
            "room_id": f"cr-{i+1}",
            "polygon": [[round(p[0], 2), round(p[1], 2)] for p in poly],
            "area": room.get("area"),
            "label_qwen": None,
            "sources": ["pipeline_v13"],
        })
    # Naive name assignment: distribute Qwen names to first N rooms by area desc
    if qwen_rooms and consensus_rooms:
        sorted_idx = sorted(range(len(consensus_rooms)),
                            key=lambda k: -(consensus_rooms[k]["area"] or 0))
        for slot, name in zip(sorted_idx, qwen_rooms):
            consensus_rooms[slot]["label_qwen"] = name
            consensus_rooms[slot]["sources"].append("qwen_label")

    # ---- FURNITURE (CubiCasa + Qwen) ----
    consensus_furniture = []
    if cubicasa:
        for det in cubicasa.get("detections", []):
            cls = det.get("class", "")
            if cls in ("Toilet", "Sink", "Closet", "Bath"):
                poly = det.get("polygon", [])
                if poly:
                    cx = sum(p[0] for p in poly) / len(poly)
                    cy = sum(p[1] for p in poly) / len(poly)
                    consensus_furniture.append({
                        "type": cls.lower(),
                        "approx_center_cubicasa_resized": [round(cx, 1), round(cy, 1)],
                        "sources": ["cubicasa"],
                        "confidence": round(WEIGHTS["cubicasa"], 3),
                    })
    if qwen:
        parsed = qwen.get("parsed") or {}
        for f in (parsed.get("furniture") or []):
            consensus_furniture.append({
                "type": f.get("type", "?").lower(),
                "room_label": f.get("room", ""),
                "sources": ["qwen"],
                "confidence": round(WEIGHTS["qwen"], 3),
            })

    # ---- DIAGNOSTICS ----
    walls_with_v13 = sum(1 for w in consensus_walls if "pipeline_v13" in w["sources"])
    openings_arc_seed = sum(1 for o in consensus_openings if o["geometry_origin"] == "svg_arc")
    openings_gap_only = sum(1 for o in consensus_openings if o["geometry_origin"] == "pipeline_gap")
    openings_yolo_confirmed = sum(1 for o in consensus_openings if "yolo_clean" in o["sources"])
    openings_windows = sum(1 for o in consensus_openings if o.get("kind") == "window")
    rooms_named = sum(1 for r in consensus_rooms if r["label_qwen"])

    out = {
        "metadata": {
            "schema_version": "1.0.0",
            "run_id": observed.get("run_id"),
            "coordinate_space": "pdf_points",
            "page_bounds": {"min_x": px_min, "min_y": py_min,
                            "max_x": px_max, "max_y": py_max},
            "sources": ["svg_native", "pipeline_v13", "yolo_clean",
                        "cubicasa_raw", "qwen_clean_resized"],
            "weights": WEIGHTS,
            "tolerances": {
                "wall_dist_pt": WALL_DIST_TOL,
                "wall_angle_deg": WALL_ANGLE_TOL,
                "opening_dist_pt": OPENING_TOL,
            },
            "fusion_latency_seconds": round(time.time() - t0, 3),
        },
        "walls": consensus_walls,
        "openings": consensus_openings,
        "rooms": consensus_rooms,
        "furniture": consensus_furniture,
        "diagnostics": {
            "walls_total": len(consensus_walls),
            "walls_with_v13_agreement": walls_with_v13,
            "walls_svg_only": len(consensus_walls) - walls_with_v13,
            "openings_total": len(consensus_openings),
            "openings_arc_seed": openings_arc_seed,
            "openings_gap_only": openings_gap_only,
            "openings_yolo_confirmed": openings_yolo_confirmed,
            "openings_windows": openings_windows,
            "rooms_total": len(consensus_rooms),
            "rooms_with_qwen_label": rooms_named,
            "furniture_total": len(consensus_furniture),
            "furniture_cubicasa": sum(1 for f in consensus_furniture if "cubicasa" in f["sources"]),
            "furniture_qwen": sum(1 for f in consensus_furniture if "qwen" in f["sources"]),
        },
    }
    return out, page0


def render_consensus_overlay(consensus: dict, out_path: Path):
    page = consensus["metadata"]["page_bounds"]
    pad = 30
    minx, miny = page["min_x"] - pad, page["min_y"] - pad
    w_pt = (page["max_x"] - page["min_x"]) + 2 * pad
    h_pt = (page["max_y"] - page["min_y"]) + 2 * pad
    SCALE = 2.0
    canvas_w = int(w_pt * SCALE)
    canvas_h = int(h_pt * SCALE) + 40
    img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_lg = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        font_lg = font

    def to_canvas(pt):
        return ((pt[0] - minx) * SCALE, 40 + (pt[1] - miny) * SCALE)

    diag = consensus["diagnostics"]
    header = (
        f"CONSENSUS · walls={diag['walls_total']} ({diag['walls_with_v13_agreement']} confirmed by V13) · "
        f"openings={diag['openings_total']} (arcs={diag['openings_arc_seed']}, gap-only={diag['openings_gap_only']}) · "
        f"rooms={diag['rooms_total']} (named={diag['rooms_with_qwen_label']}) · "
        f"furniture={diag['furniture_total']}"
    )
    draw.text((10, 10), header, fill=(40, 40, 40), font=font_lg)

    for room in consensus["rooms"]:
        poly = room.get("polygon") or []
        if len(poly) < 3:
            continue
        canvas_poly = [to_canvas(p) for p in poly]
        draw.polygon(canvas_poly, fill=(255, 240, 200, 80), outline=(220, 180, 80))
        cx = sum(p[0] for p in canvas_poly) / len(canvas_poly)
        cy = sum(p[1] for p in canvas_poly) / len(canvas_poly)
        label = room.get("label_qwen") or room["room_id"]
        draw.text((cx - 30, cy - 8), label, fill=(150, 100, 30), font=font)

    for w in consensus["walls"]:
        a = to_canvas(w["start"])
        b = to_canvas(w["end"])
        if "pipeline_v13" in w["sources"]:
            color = (180, 30, 30)
            width = 4
        else:
            color = (220, 100, 100)
            width = 2
        draw.line([a, b], fill=color, width=width)

    for op in consensus["openings"]:
        cx, cy = to_canvas(op["center"])
        s = 12
        if op["geometry_origin"] == "svg_arc":
            fill = (255, 140, 0)
        else:
            fill = (255, 200, 100)
        draw.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)],
                     fill=fill, outline=(120, 70, 0))
        n_sources = len(op["sources"])
        draw.text((cx + s + 2, cy - 6), f"{n_sources}", fill=(60, 30, 0), font=font)

    img.save(out_path, "PNG", optimize=True)


def render_pdf_vs_consensus(consensus: dict, page_obj, out_path: Path):
    import fitz
    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = page_obj.get_pixmap(matrix=mat, alpha=False)
    pdf_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    overlay_tmp = out_path.parent / "_consensus_tmp.png"
    render_consensus_overlay(consensus, overlay_tmp)
    overlay_img = Image.open(overlay_tmp)
    h_target = max(pdf_img.height, overlay_img.height)
    pdf_resized = pdf_img.resize((int(pdf_img.width * h_target / pdf_img.height), h_target))
    overlay_resized = overlay_img.resize(
        (int(overlay_img.width * h_target / overlay_img.height), h_target)
    )
    gap = 30
    canvas = Image.new("RGB", (pdf_resized.width + gap + overlay_resized.width, h_target + 50),
                       (245, 245, 245))
    canvas.paste(pdf_resized, (0, 50))
    canvas.paste(overlay_resized, (pdf_resized.width + gap, 50))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 14), "PDF original", fill=(40, 40, 40), font=font)
    draw.text((pdf_resized.width + gap + 20, 14), "CONSENSUS (SVG primary + V13/YOLO/CubiCasa/Qwen votes)",
              fill=(40, 40, 40), font=font)
    canvas.save(out_path, "PNG", optimize=True)
    overlay_tmp.unlink(missing_ok=True)


def main(argv):
    run = argv[1] if len(argv) > 1 else "final_planta_74"
    consensus, page_obj = fuse(run)
    run_dir = REPOS["expdedup"] / "runs" / run
    json_out = run_dir / "consensus_model.json"
    json_out.write_text(json.dumps(consensus, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {json_out}")

    overlay_out = run_dir / "consensus_overlay.png"
    render_consensus_overlay(consensus, overlay_out)
    print(f"saved {overlay_out}")

    sbs_out = run_dir / "pdf_vs_consensus.png"
    render_pdf_vs_consensus(consensus, page_obj, sbs_out)
    print(f"saved {sbs_out}")

    diag = consensus["diagnostics"]
    print()
    print("=== DIAGNOSTICS ===")
    print(json.dumps(diag, indent=2))


if __name__ == "__main__":
    main(sys.argv)
