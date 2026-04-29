"""CubiCasa5K DL oracle for the floor-plan extraction pipeline.

Runs the vendored Hourglass network (`hg_furukawa_original`) on a rasterised
PDF page and emits a schema-compliant `cubicasa_observed.json` with walls,
junctions, rooms, and openings. Strictly a dev-time COMPARATIVE oracle: the
pipeline core never imports from this script (CLAUDE.md invariants Section 6).

Usage:
    python scripts/oracle/cubicasa.py --pdf planta_74.pdf --out runs/cubicasa_p74
    python scripts/oracle/cubicasa.py --pdf X.pdf --out runs/Y --raster-size 1024
    python scripts/oracle/cubicasa.py --pdf X.pdf --out runs/Y --device cuda

Output: <out>/cubicasa_observed.json (validated against
docs/schema/observed_model.schema.json before write).

Channel layout of the 44-channel network output:
    0:21   junction / corner heatmaps
    21:33  room segmentation (12 classes, softmax)
    33:44  icon segmentation (11 classes; ch34 = window, ch35 = door)

License of vendored CubiCasa5K weights and code:
    Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
    https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE
This oracle is NON-COMMERCIAL use only. Do not ship its output as part of a
paid product.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import jsonschema
import numpy as np

# Resolve project layout. This script lives at scripts/oracle/cubicasa.py so
# go up two levels to reach the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = PROJECT_ROOT / "vendor" / "CubiCasa5k"
VENDOR_REPO = VENDOR_DIR / "repo"
WEIGHTS_PATH = VENDOR_DIR / "weights" / "model_best_val_loss_var.pkl"
SCHEMA_PATH = PROJECT_ROOT / "docs" / "schema" / "observed_model.schema.json"

SCHEMA_VERSION = "2.2.0"

# Channel layout (vendor README section 6).
HEATMAP_COUNT = 21
ROOM_COUNT = 12
ICON_COUNT = 11

HEATMAPS_OFFSET = 0
ROOMS_OFFSET = HEATMAPS_OFFSET + HEATMAP_COUNT  # 21
ICONS_OFFSET = ROOMS_OFFSET + ROOM_COUNT        # 33

# Icon-class local indices (within channels 33..43).
ICON_NO_ICON = 0
ICON_WINDOW = 1
ICON_DOOR = 2

# ImageNet normalisation (vendor README section 6.3).
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# Wall-mask + opening thresholds. Tuned conservatively; adjust if recall drops.
WALL_PROB_THRESHOLD = 0.30      # heatmap activation threshold for wall pixels
ROOM_BACKGROUND_INDEX = 0       # local room index treated as "no room"
MIN_OPENING_BLOB_PX = 12
DOOR_PROB_THRESHOLD = 0.40
WINDOW_PROB_THRESHOLD = 0.40
MIN_ROOM_AREA_PX = 200          # below this, room polygons are noise
MIN_WALL_LENGTH_PX = 8
DEFAULT_WALL_THICKNESS_PX = 4.0
JUNCTION_MERGE_TOLERANCE = 6.0  # px - endpoints closer than this share a junction
DEFAULT_CONFIDENCE = 0.95


# ---------- setup checks ----------


def _fail_setup(reason: str) -> None:
    raise RuntimeError(
        f"{reason}\n"
        f"Run `python scripts/oracle/cubicasa_download.py` first, then retry. "
        f"See vendor/CubiCasa5k/README.md for the full setup."
    )


def _require_setup() -> None:
    """Verify weights + repo are present BEFORE we touch torch / floortrans."""
    if not WEIGHTS_PATH.is_file():
        _fail_setup(f"CubiCasa5K weights not found at {WEIGHTS_PATH}.")
    if not (VENDOR_REPO / "floortrans" / "__init__.py").is_file():
        _fail_setup(f"CubiCasa5K repo not cloned at {VENDOR_REPO}.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- PDF -> raster ----------


def rasterize_pdf_first_page(pdf_path: Path, raster_size: int) -> np.ndarray:
    """Render page 0 of `pdf_path` to an RGB uint8 numpy array, scaled so the
    larger side is `raster_size` pixels.

    Uses the project's own ingest service for consistency with the rest of
    the pipeline (does NOT alter the pipeline; just consumes its public API).
    """
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Lazy import to keep top-level imports tight (and avoid loading
    # pypdfium2 if --pdf was somehow not provided).
    sys.path.insert(0, str(PROJECT_ROOT))
    from ingest import ingest_pdf  # noqa: E402

    pdf_bytes = pdf_path.read_bytes()
    document = ingest_pdf(pdf_bytes, filename=pdf_path.name, scale=2.0)
    page = document.pages[0]
    rgb = page.image  # H x W x 3 uint8

    h, w = rgb.shape[:2]
    longer = max(h, w)
    if longer != raster_size:
        scale = raster_size / float(longer)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        rgb = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(rgb)


# ---------- Model loading ----------


def load_cubicasa_model(device: str):
    """Build hg_furukawa_original, load the CubiCasa5K checkpoint, return
    (model, torch_device, weights_sha256).

    Prints missing/unexpected state_dict keys VERBATIM (CLAUDE.md invariant:
    never silently swallow load failures).
    """
    _require_setup()

    if str(VENDOR_REPO) not in sys.path:
        sys.path.insert(0, str(VENDOR_REPO))

    try:
        import torch  # noqa: E402
    except ImportError as exc:
        _fail_setup(f"PyTorch is not installed ({exc}). pip install torch torchvision.")
        raise

    try:
        from floortrans.models import get_model  # noqa: E402
    except ImportError as exc:
        _fail_setup(f"Could not import floortrans.models ({exc}).")
        raise

    weights_sha = _sha256(WEIGHTS_PATH)
    n_classes = HEATMAP_COUNT + ROOM_COUNT + ICON_COUNT  # 44

    # `init_weights` in hg_furukawa_original loads model_1427.pth via a
    # relative path. chdir into the vendor repo for the constructor.
    prev_cwd = os.getcwd()
    try:
        os.chdir(str(VENDOR_REPO))
        model = get_model("hg_furukawa_original", 51)  # 51 = original training head
    finally:
        os.chdir(prev_cwd)

    # Replace final conv + upsample to match the published 44-class checkpoint.
    model.conv4_ = torch.nn.Conv2d(256, n_classes, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(
        n_classes, n_classes, kernel_size=4, stride=4
    )

    checkpoint = torch.load(WEIGHTS_PATH, map_location="cpu", weights_only=False)
    state = checkpoint.get("model_state", checkpoint) if isinstance(checkpoint, dict) else checkpoint
    state = {k.replace("module.", ""): v for k, v in state.items()}

    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        print(f"[oracle] MISSING state_dict keys ({len(missing)}):", file=sys.stderr)
        for k in missing:
            print(f"  - {k}", file=sys.stderr)
    if unexpected:
        print(f"[oracle] UNEXPECTED state_dict keys ({len(unexpected)}):", file=sys.stderr)
        for k in unexpected:
            print(f"  - {k}", file=sys.stderr)
    if not missing and not unexpected:
        print("[oracle] state_dict loaded cleanly (0 missing, 0 unexpected)", file=sys.stderr)

    torch_device = torch.device(device)
    model = model.to(torch_device).eval()
    return model, torch_device, weights_sha


# ---------- Inference ----------


def run_inference(model, torch_device, rgb: np.ndarray) -> np.ndarray:
    """Forward pass. Returns a (44, H, W) numpy array cropped to input size."""
    import torch  # local; vendor sys.path already prepared

    h, w = rgb.shape[:2]
    pad_h = (32 - h % 32) % 32
    pad_w = (32 - w % 32) % 32
    if pad_h or pad_w:
        padded = cv2.copyMakeBorder(rgb, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
    else:
        padded = rgb

    arr = padded.astype(np.float32) / 255.0
    arr = (arr - np.array(IMAGENET_MEAN)) / np.array(IMAGENET_STD)
    chw = np.transpose(arr, (2, 0, 1))[None, ...].astype(np.float32)
    batch = torch.from_numpy(chw).to(torch_device)

    with torch.no_grad():
        out = model(batch)  # (1, 44, 4*Hp, 4*Wp) - 4x upsample is internal

    # Resize back to padded raster size so each output pixel maps 1:1.
    if out.shape[-2:] != padded.shape[:2]:
        out = torch.nn.functional.interpolate(
            out, size=padded.shape[:2], mode="bilinear", align_corners=False
        )

    # Strip padding and convert to numpy.
    return out[0, :, :h, :w].detach().cpu().numpy()


# ---------- Geometry extraction ----------


@dataclass
class WallSeg:
    wall_id: str
    start: tuple[float, float]
    end: tuple[float, float]
    thickness: float
    orientation: str  # "horizontal" | "vertical"


def _wall_mask_from_heatmaps(output: np.ndarray) -> np.ndarray:
    """Build a binary wall mask from the 21 heatmap channels.

    The Hourglass heatmaps light up at wall corners / junctions. We use the
    max-across-channels response as a wall-presence proxy and threshold it.
    """
    heatmaps = output[HEATMAPS_OFFSET : HEATMAPS_OFFSET + HEATMAP_COUNT]
    max_resp = heatmaps.max(axis=0)
    # Sigmoid-ish normalisation so the threshold is comparable across plans.
    norm = (max_resp - max_resp.min()) / max(max_resp.max() - max_resp.min(), 1e-6)
    mask = (norm > WALL_PROB_THRESHOLD).astype(np.uint8) * 255
    # Close small gaps so HoughLinesP picks up continuous walls.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    return mask


def _segments_from_wall_mask(mask: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Hough-fit line segments on the wall mask.

    Returns [(x1, y1, x2, y2), ...]. We snap each segment to the dominant
    axis (horizontal/vertical) since CubiCasa floor plans are axis-aligned in
    the vast majority of cases; this keeps wall.orientation deterministic
    without any extra classifier.
    """
    if mask.sum() == 0:
        return []
    lines = cv2.HoughLinesP(
        mask,
        rho=1,
        theta=np.pi / 180.0,
        threshold=40,
        minLineLength=MIN_WALL_LENGTH_PX,
        maxLineGap=8,
    )
    if lines is None:
        return []
    segs: list[tuple[float, float, float, float]] = []
    for line in lines:
        x1, y1, x2, y2 = (float(v) for v in line[0])
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) >= abs(dy):
            # Snap horizontal: keep average y.
            y_avg = (y1 + y2) / 2.0
            segs.append((x1, y_avg, x2, y_avg))
        else:
            x_avg = (x1 + x2) / 2.0
            segs.append((x_avg, y1, x_avg, y2))
    return segs


def _extract_walls(output: np.ndarray) -> list[WallSeg]:
    mask = _wall_mask_from_heatmaps(output)
    raw = _segments_from_wall_mask(mask)
    walls: list[WallSeg] = []
    for i, (x1, y1, x2, y2) in enumerate(raw):
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < MIN_WALL_LENGTH_PX:
            continue
        orientation = "horizontal" if abs(x2 - x1) >= abs(y2 - y1) else "vertical"
        wid = f"cubicasa-wall-{i + 1}"
        walls.append(
            WallSeg(
                wall_id=wid,
                start=(round(x1, 3), round(y1, 3)),
                end=(round(x2, 3), round(y2, 3)),
                thickness=DEFAULT_WALL_THICKNESS_PX,
                orientation=orientation,
            )
        )
    return walls


def _extract_rooms(output: np.ndarray) -> list[dict[str, Any]]:
    """Argmax over the 12 room channels, then connected components -> polygons."""
    rooms_logits = output[ROOMS_OFFSET : ROOMS_OFFSET + ROOM_COUNT]
    e = np.exp(rooms_logits - rooms_logits.max(axis=0, keepdims=True))
    probs = e / e.sum(axis=0, keepdims=True)
    labels = probs.argmax(axis=0).astype(np.int32)

    rooms: list[dict[str, Any]] = []
    counter = 1
    for cls in range(ROOM_COUNT):
        if cls == ROOM_BACKGROUND_INDEX:
            continue
        cls_mask = (labels == cls).astype(np.uint8) * 255
        if cls_mask.sum() == 0:
            continue
        n, comp = cv2.connectedComponents(cls_mask, connectivity=8)
        for ci in range(1, n):
            blob = (comp == ci).astype(np.uint8) * 255
            area_px = int(blob.sum() // 255)
            if area_px < MIN_ROOM_AREA_PX:
                continue
            contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            # Polygon simplification: keep within ~1% of perimeter.
            perim = cv2.arcLength(contour, True)
            poly = cv2.approxPolyDP(contour, 0.01 * perim, True).reshape(-1, 2)
            if len(poly) < 3:
                continue
            area = float(cv2.contourArea(contour))
            m = cv2.moments(contour)
            if m["m00"] > 0:
                cx = m["m10"] / m["m00"]
                cy = m["m01"] / m["m00"]
            else:
                cx = float(poly[:, 0].mean())
                cy = float(poly[:, 1].mean())
            rooms.append({
                "room_id": f"cubicasa-room-{counter}",
                "polygon": [[round(float(x), 3), round(float(y), 3)] for x, y in poly],
                "area": round(area, 3),
                "centroid": [round(cx, 3), round(cy, 3)],
            })
            counter += 1
    return rooms


def _extract_openings(output: np.ndarray) -> list[dict[str, Any]]:
    """Read door (ch35) + window (ch34) icon channels; blob each and emit."""
    icons_logits = output[ICONS_OFFSET : ICONS_OFFSET + ICON_COUNT]
    e = np.exp(icons_logits - icons_logits.max(axis=0, keepdims=True))
    probs = e / e.sum(axis=0, keepdims=True)

    openings: list[dict[str, Any]] = []
    counter = 1
    for kind, prob_map, thresh in (
        ("door", probs[ICON_DOOR], DOOR_PROB_THRESHOLD),
        ("window", probs[ICON_WINDOW], WINDOW_PROB_THRESHOLD),
    ):
        mask = (prob_map > thresh).astype(np.uint8) * 255
        if mask.sum() == 0:
            continue
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            if cv2.contourArea(contour) < MIN_OPENING_BLOB_PX:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            cx = x + bw / 2.0
            cy = y + bh / 2.0
            if bw >= bh:
                orientation = "horizontal"
                width_px = float(bw)
            else:
                orientation = "vertical"
                width_px = float(bh)
            openings.append({
                "opening_id": f"cubicasa-opening-{counter}",
                "page_index": 0,
                "orientation": orientation,
                "center": [round(cx, 3), round(cy, 3)],
                "width": round(width_px, 3),
                # Oracle has no wall topology -> empty strings (schema requires string type).
                "wall_a": "",
                "wall_b": "",
                "kind": kind,
            })
            counter += 1
    return openings


# ---------- Topology ----------


def _build_junctions(
    walls: list[WallSeg],
) -> tuple[list[dict[str, Any]], list[int]]:
    """Cluster wall endpoints; degree -> kind.

    Returns (junctions, cluster_of) where `cluster_of[2*i]` and
    `cluster_of[2*i+1]` are the cluster IDs of walls[i].start and
    walls[i].end respectively. Caller uses this to build the wall graph for
    the connectivity report.
    """
    if not walls:
        return [], []
    points: list[tuple[float, float]] = []
    for w in walls:
        points.append(w.start)
        points.append(w.end)

    # Greedy clustering with JUNCTION_MERGE_TOLERANCE radius.
    cluster_of: list[int] = [-1] * len(points)
    centers: list[tuple[float, float]] = []
    for i, p in enumerate(points):
        assigned = False
        for ci, c in enumerate(centers):
            if (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 <= JUNCTION_MERGE_TOLERANCE ** 2:
                cluster_of[i] = ci
                # Update center as running mean.
                members = sum(1 for x in cluster_of if x == ci)
                centers[ci] = (
                    (c[0] * (members - 1) + p[0]) / members,
                    (c[1] * (members - 1) + p[1]) / members,
                )
                assigned = True
                break
        if not assigned:
            cluster_of[i] = len(centers)
            centers.append(p)

    degrees: dict[int, int] = defaultdict(int)
    for ci in cluster_of:
        degrees[ci] += 1

    junctions: list[dict[str, Any]] = []
    for ci, center in enumerate(centers):
        deg = degrees[ci]
        if deg == 1:
            kind = "end"
        elif deg == 2:
            kind = "pass_through"
        elif deg == 3:
            kind = "tee"
        else:
            kind = "cross"
        junctions.append({
            "junction_id": f"cubicasa-j-{ci + 1}",
            "point": [round(center[0], 3), round(center[1], 3)],
            "degree": deg,
            "kind": kind,
        })
    return junctions, cluster_of


def _connectivity_report(walls: list[WallSeg], cluster_of: list[int], rooms_count: int) -> dict[str, Any]:
    """Walls -> graph -> connectivity numbers required by ConnectivityReport.

    Each wall contributes one edge between two junction-cluster nodes.
    """
    node_count = max(cluster_of) + 1 if cluster_of else 0
    edge_count = len(walls)

    # Adjacency.
    adj: dict[int, set[int]] = defaultdict(set)
    for i in range(len(walls)):
        a = cluster_of[2 * i]
        b = cluster_of[2 * i + 1]
        if a != b:
            adj[a].add(b)
            adj[b].add(a)
        else:
            adj[a]  # ensure node exists

    # Connected components via BFS.
    visited: set[int] = set()
    component_sizes: list[int] = []
    for n in range(node_count):
        if n in visited:
            continue
        stack = [n]
        size = 0
        while stack:
            x = stack.pop()
            if x in visited:
                continue
            visited.add(x)
            size += 1
            stack.extend(adj[x] - visited)
        component_sizes.append(size)
    component_sizes.sort(reverse=True)
    component_count = len(component_sizes)
    largest_ratio = (component_sizes[0] / node_count) if node_count else 0.0

    # All walls live on page 0 in this oracle (single-page).
    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "component_count": component_count,
        "component_sizes": component_sizes,
        "largest_component_ratio": round(largest_ratio, 4),
        "rooms_detected": rooms_count,
        "page_count": 1 if walls else 0,
        "max_components_within_page": component_count,
        "min_intra_page_connectivity_ratio": round(largest_ratio, 4),
        "orphan_component_count": max(0, component_count - 1),
        "orphan_node_count": sum(component_sizes[1:]) if component_count > 1 else 0,
    }


# ---------- Schema-compliant payload ----------


def _topology_score(connectivity: dict[str, Any]) -> float:
    intra = connectivity["min_intra_page_connectivity_ratio"]
    max_within = connectivity["max_components_within_page"] or 1
    return round((intra + (1.0 / max_within)) / 2.0, 4)


def _rooms_score(rooms_count: int, edges_count: int) -> float:
    if rooms_count == 0 or edges_count == 0:
        return 0.0
    return round(min(1.0, 0.5 + rooms_count / max(edges_count, 1)), 4)


def _topology_quality(score: float) -> str:
    if score >= 0.8:
        return "good"
    if score >= 0.5:
        return "fair"
    return "poor"


def _bounds(walls: list[WallSeg], image_h: int, image_w: int) -> dict[str, Any]:
    if walls:
        xs = [p for w in walls for p in (w.start[0], w.end[0])]
        ys = [p for w in walls for p in (w.start[1], w.end[1])]
        return {"pages": [{
            "page_index": 0,
            "min_x": float(min(xs)),
            "min_y": float(min(ys)),
            "max_x": float(max(xs)),
            "max_y": float(max(ys)),
        }]}
    return {"pages": [{
        "page_index": 0,
        "min_x": 0.0, "min_y": 0.0,
        "max_x": float(image_w), "max_y": float(image_h),
    }]}


def build_payload(
    pdf_path: Path,
    pdf_sha256: str,
    walls: list[WallSeg],
    junctions: list[dict[str, Any]],
    rooms: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    connectivity: dict[str, Any],
    image_h: int,
    image_w: int,
) -> dict[str, Any]:
    walls_dicts = [{
        "wall_id": w.wall_id,
        "parent_wall_id": w.wall_id,  # no split happened, parent == self
        "page_index": 0,
        "start": [w.start[0], w.start[1]],
        "end": [w.end[0], w.end[1]],
        "thickness": w.thickness,
        "orientation": w.orientation,
        "source": "cubicasa",
        "confidence": DEFAULT_CONFIDENCE,
    } for w in walls]

    topology = _topology_score(connectivity)
    rooms_score = _rooms_score(len(rooms), connectivity["edge_count"])
    quality = _topology_quality(topology)

    warnings: list[str] = ["dl_oracle"]

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": uuid.uuid4().hex,
        "source": {
            "filename": str(pdf_path),
            "source_type": "raster",  # oracle always rasters first, even from PDF
            "page_count": 1,
            "sha256": pdf_sha256,
        },
        "bounds": _bounds(walls, image_h, image_w),
        "roi": [],  # oracle does not run the ROI step
        "walls": walls_dicts,
        "junctions": junctions,
        "rooms": rooms,
        "scores": {
            "geometry": 1.0,  # DL output has no candidate filtering -> retention is 1.0
            "topology": topology,
            "rooms": rooms_score,
        },
        "metadata": {
            "rooms_detected": len(rooms),
            "topology_quality": quality,
            "connectivity": connectivity,
            "warnings": warnings,
        },
        "warnings": warnings,
        "openings": openings,
        "peitoris": [],
    }


def validate_against_schema(payload: dict[str, Any]) -> str | None:
    """Return None on success, or an error message on failure."""
    if not SCHEMA_PATH.is_file():
        return f"Schema file missing: {SCHEMA_PATH}"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.ValidationError as exc:
        return f"{exc.message} (path: {list(exc.absolute_path)})"
    return None


# ---------- CLI ----------


def run(pdf_path: Path, out_dir: Path, raster_size: int, device: str) -> dict[str, Any]:
    pdf_sha256 = _sha256(pdf_path)
    rgb = rasterize_pdf_first_page(pdf_path, raster_size)
    image_h, image_w = rgb.shape[:2]

    model, torch_device, weights_sha = load_cubicasa_model(device)
    output = run_inference(model, torch_device, rgb)

    walls = _extract_walls(output)
    junctions, cluster_of = _build_junctions(walls)
    rooms = _extract_rooms(output)
    openings = _extract_openings(output)
    connectivity = _connectivity_report(walls, cluster_of, len(rooms))

    payload = build_payload(
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        walls=walls,
        junctions=junctions,
        rooms=rooms,
        openings=openings,
        connectivity=connectivity,
        image_h=image_h,
        image_w=image_w,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    err = validate_against_schema(payload)
    if err is None:
        target = out_dir / "cubicasa_observed.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        target = out_dir / "cubicasa_observed.invalid.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[oracle] SCHEMA VIOLATION: {err}", file=sys.stderr)
        print(f"[oracle] wrote INVALID payload to {target}", file=sys.stderr)

    summary = {
        "walls": len(walls),
        "junctions": len(junctions),
        "rooms": len(rooms),
        "openings": len(openings),
        "weights_sha256": weights_sha,
        "output": str(target),
        "valid": err is None,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", required=True, type=Path, help="Path to PDF input.")
    parser.add_argument("--out", required=True, type=Path, help="Output directory.")
    parser.add_argument(
        "--raster-size", type=int, default=512,
        help="Larger-side pixel count for the rasterised page. Default 512.",
    )
    parser.add_argument(
        "--device", default="cpu", choices=("cpu", "cuda"),
        help="Torch device. Default cpu.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run(args.pdf, args.out, args.raster_size, args.device)
    except RuntimeError as exc:
        print(f"[oracle] setup error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"[oracle] input error: {exc}", file=sys.stderr)
        return 2

    valid_tag = "OK" if summary["valid"] else "INVALID"
    print(
        f"[oracle] [{valid_tag}] walls={summary['walls']} "
        f"junctions={summary['junctions']} rooms={summary['rooms']} "
        f"openings={summary['openings']}"
    )
    print(f"[oracle] weights sha256: {summary['weights_sha256']}")
    print(f"[oracle] output: {summary['output']}")
    return 0 if summary["valid"] else 3


if __name__ == "__main__":
    sys.exit(main())
