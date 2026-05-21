"""Build a single-shell .skp for an entire floor plan from a consensus.

Parallel, EXPERIMENTAL exporter. Does NOT replace consume_consensus.rb.
See docs/adr/ADR-003-plan-shell-exporter.md for the design rationale.

Pipeline:
    consensus.json
       |
       v
    [1] Compute 2D wall footprints
        Each wall = box(start, end, thickness/2) in PDF point coords.
        For horizontal walls (orientation='h'), the box hugs the y-axis;
        for vertical, it hugs the x-axis. Mirrors consume_consensus.rb
        line 67-90 (`add_wall_volume`).
       |
       v
    [2] shapely.unary_union(all footprints)
        Walls whose footprints touch / overlap merge into one polygon.
        Corners — where two perpendicular walls share the corner cell —
        are auto-resolved here: no per-wall corner pillar, no duplicated
        face at the corner.
       |
       v
    [3] buffer-close-gap idiom (epsilon snap)
        planta_74's walls have endpoint-share ratio = 1.000 (every
        endpoint is unique). Adjacent walls that "look connected" in
        the PDF can be SNAP_EPS_PTS apart. Buffering ±SNAP_EPS_PTS / 2
        bridges the visual gap without distorting wall thickness.
       |
       v
    [4] Subtract opening rectangles
        Each opening with wall_id + center + opening_width_pts becomes
        a 2D rectangle aligned with the host wall axis. Subtracting in
        2D before extrude guarantees a clean door gap in the shell —
        no post-extrusion boolean issues.
       |
       v
    [5] Sliver filter
        After union+subtract, micro-polygons can appear from numerical
        noise. Filter polygons whose area < MIN_SLIVER_AREA_PTS2.
       |
       v
    [6] Serialize to _shell_polygon.json
        Outer ring + holes per polygon piece, in PDF points. The Ruby
        exporter reads this and builds the SU face-with-holes + pushpull.

The Ruby exporter (build_plan_shell_skp.rb) is invoked via the same
autorun_consume.rb plugin mechanism used by skp_from_consensus.py —
we only swap line 3 of autorun_control.txt to point at our .rb.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from tools.disarm_sketchup_autoruns import disarm as disarm_autoruns

SKETCHUP_EXE_DEFAULT = (
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
PLUGINS_DIR_DEFAULT = Path(os.path.expandvars(
    r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
))
RUBY_TEMPLATE = Path(__file__).resolve().parent / "build_plan_shell_skp.rb"
CONTROL_FILE = "autorun_control.txt"
METADATA_SUFFIX = ".metadata.json"

# ---- algorithmic tuning constants ------------------------------------

# Snap tolerance used by the buffer-close-gap idiom. PDF points are
# the unit. For planta_74 (PT_TO_M = 0.19/5.4) this is ~3 mm at 0.1 pt.
# Small enough not to merge distinct walls; large enough to bridge
# endpoint-mismatch artefacts where two walls "should" touch but are
# slightly offset (e.g., centerlines stored without snap during extract).
SNAP_EPS_PTS = 0.1

# Minimum area for a polygon piece to survive the sliver filter, in
# (PDF point)^2. A 0.5 pt^2 sliver is ~0.02 mm^2 in real coordinates —
# pure numerical noise from boolean operations. Anything larger is
# preserved.
MIN_SLIVER_AREA_PTS2 = 0.5

# Opening geometry_origin values whose 2D carve we apply. Mirrors
# CARVING_OPENING_ORIGINS in consume_consensus.rb. The rationale:
# - `svg_arc`, `svg_segments`: arc/segment-shaped openings the SVG
#   extractor found inside continuous walls — gap must be carved.
# - `human_annotation`: openings injected by a reviewer painting on
#   a render; same — gap must be carved.
# - `wall_gap`: the source PDF already drew the flanking walls as
#   separate filled rectangles, so the gap is *already* in the wall
#   data. Carving here would double-shrink the geometry. We instead
#   render a passage marker / window panel on top.
CARVING_ORIGINS = frozenset({"svg_arc", "svg_segments", "human_annotation"})


# ---- core geometry ---------------------------------------------------

def wall_footprint(wall: dict) -> Polygon:
    """Return the 2D rectangle this wall occupies, in PDF points.

    Mirrors the corner computation in consume_consensus.rb's
    ``add_wall_volume`` (lines 67-90): horizontal walls hug the y-axis
    (thickness in y), vertical walls hug the x-axis (thickness in x).
    """
    s = wall["start"]
    e = wall["end"]
    t = wall.get("thickness")
    if t is None:
        raise ValueError(f"wall {wall.get('id')} missing thickness")
    half = t / 2.0
    ori = wall.get("orientation")
    if ori == "h":
        x0, x1 = min(s[0], e[0]), max(s[0], e[0])
        cy = s[1]
        return box(x0, cy - half, x1, cy + half)
    if ori == "v":
        cx = s[0]
        y0, y1 = min(s[1], e[1]), max(s[1], e[1])
        return box(cx - half, y0, cx + half, y1)
    raise ValueError(
        f"wall {wall.get('id')} has unsupported orientation={ori!r}; "
        "this exporter only handles axis-aligned walls"
    )


def opening_carve_rect(opening: dict, host_wall: dict,
                       default_thickness: float) -> Polygon:
    """Compute the 2D rectangle to subtract from the shell for this opening.

    The carve rectangle is aligned with the host wall axis and spans
    ``opening_width_pts`` along the wall plus the wall's full thickness
    perpendicular to it (so the subtraction reaches both faces of the
    wall, not just one side).
    """
    t = host_wall.get("thickness", default_thickness)
    half = t / 2.0
    cx, cy = opening["center"]
    w = opening.get("opening_width_pts")
    if w is None or w <= 0:
        raise ValueError(
            f"opening {opening.get('id')} missing/invalid opening_width_pts"
        )
    half_w = w / 2.0
    ori = host_wall.get("orientation")
    if ori == "h":
        wall_cy = host_wall["start"][1]
        return box(cx - half_w, wall_cy - half, cx + half_w, wall_cy + half)
    if ori == "v":
        wall_cx = host_wall["start"][0]
        return box(wall_cx - half, cy - half_w, wall_cx + half, cy + half_w)
    raise ValueError(
        f"host wall {host_wall.get('id')} orientation={ori!r} unsupported"
    )


def build_shell_polygon(consensus: dict) -> tuple[list[Polygon], dict]:
    """Return (polygons, stats) for the plan shell.

    Each polygon may have holes (interior loops). The list is what the
    Ruby exporter iterates over to create face-with-holes + pushpull.
    """
    walls = consensus.get("walls", [])
    if not walls:
        raise ValueError("consensus has no walls — cannot build shell")
    openings = consensus.get("openings", [])
    default_thickness = consensus.get("wall_thickness_pts")

    # [1] wall footprints
    wall_boxes = [wall_footprint(w) for w in walls]

    # [2] union
    shell = unary_union(wall_boxes)

    # [3] buffer-close-gap with mitre joins.
    # Default round joins would replace every right-angle corner with
    # a fan of 16 short segments — both visually and quantitatively
    # wrong for an axis-aligned floor plan (a 100x100m room would end
    # up with ~64 outer perimeter verts instead of 4). join_style=2
    # (mitre) keeps the corner geometry exact, only filling/bridging
    # micro-gaps under SNAP_EPS_PTS. mitre_limit caps spike length on
    # very acute corners so we don't shoot a needle out at <5 degree
    # bends — shouldn't trigger for axis-aligned walls.
    shell = (
        shell
        .buffer(SNAP_EPS_PTS, join_style=2, mitre_limit=10.0)
        .buffer(-SNAP_EPS_PTS, join_style=2, mitre_limit=10.0)
    )

    # [4] subtract opening rectangles
    walls_by_id = {w["id"]: w for w in walls if "id" in w}
    carve_rects: list[Polygon] = []
    openings_skipped_by_origin: list[dict] = []
    openings_skipped_by_error: list[str] = []
    for op in openings:
        wid = op.get("wall_id")
        host = walls_by_id.get(wid)
        if host is None:
            openings_skipped_by_error.append(
                f"{op.get('id')}: host wall_id={wid!r} not in walls[]"
            )
            continue
        # geometry_origin gates whether we carve OR leave the wall
        # data alone (because the source PDF already encoded the gap).
        origin = op.get("geometry_origin", "")
        if origin and origin not in CARVING_ORIGINS:
            openings_skipped_by_origin.append({
                "id": op.get("id"),
                "geometry_origin": origin,
                "reason": (
                    f"origin {origin!r} not in CARVING_ORIGINS "
                    f"({sorted(CARVING_ORIGINS)}); gap already in wall data"
                ),
            })
            continue
        try:
            carve_rects.append(opening_carve_rect(op, host, default_thickness))
        except ValueError as e:
            openings_skipped_by_error.append(f"{op.get('id')}: {e}")

    if carve_rects:
        carve_union = unary_union(carve_rects)
        shell_with_gaps = shell.difference(carve_union)
    else:
        shell_with_gaps = shell

    # [5] sliver filter + normalise to list of Polygon
    if isinstance(shell_with_gaps, Polygon):
        polygons = [shell_with_gaps]
    elif isinstance(shell_with_gaps, MultiPolygon):
        polygons = list(shell_with_gaps.geoms)
    else:
        raise TypeError(
            f"unexpected geometry type after subtract: {type(shell_with_gaps)}"
        )
    slivers_removed = 0
    kept: list[Polygon] = []
    for p in polygons:
        if not p.is_valid:
            slivers_removed += 1
            continue
        if p.area < MIN_SLIVER_AREA_PTS2:
            slivers_removed += 1
            continue
        kept.append(p)
    if not kept:
        raise RuntimeError(
            "all shell polygons were filtered as slivers — input or "
            "tuning parameters are wrong"
        )

    stats = {
        "input_walls": len(walls),
        "input_openings": len(openings),
        "openings_carved": len(carve_rects),
        # Split into two buckets: by_origin is legitimate (wall_gap
        # origin; gap is already in the wall data, no carve needed).
        # by_error is a real failure (missing wall_id, zero width,
        # etc) and must be 0 on a healthy consensus.
        "openings_skipped_by_origin": openings_skipped_by_origin,
        "openings_skipped_by_error": openings_skipped_by_error,
        # Back-compat: keep the flat field for old test readers, but
        # only populate with the error bucket — origin-based skips
        # are by design and shouldn't trip "skipped is not empty"
        # checks. Removed entirely once test suite migrates.
        "openings_skipped": list(openings_skipped_by_error),
        "shell_pieces_after_union": len(polygons),
        "shell_pieces_after_sliver_filter": len(kept),
        "slivers_removed": slivers_removed,
        "snap_eps_pts": SNAP_EPS_PTS,
        "min_sliver_area_pts2": MIN_SLIVER_AREA_PTS2,
        "carving_origins": sorted(CARVING_ORIGINS),
        "total_shell_area_pts2": round(sum(p.area for p in kept), 4),
    }
    return kept, stats


def serialize_polygons(polygons: list[Polygon],
                       consensus: dict, stats: dict) -> dict:
    """Build the dict that the Ruby exporter reads (`_shell_polygon.json`)."""
    pieces = []
    for poly in polygons:
        outer = list(poly.exterior.coords)
        # Shapely closes rings (last == first); SU's add_face wants
        # distinct vertices, so drop the duplicate close.
        if outer and outer[-1] == outer[0]:
            outer = outer[:-1]
        holes = []
        for ring in poly.interiors:
            h = list(ring.coords)
            if h and h[-1] == h[0]:
                h = h[:-1]
            holes.append([[float(x), float(y)] for x, y in h])
        pieces.append({
            "outer": [[float(x), float(y)] for x, y in outer],
            "holes": holes,
            "area_pts2": round(poly.area, 4),
        })
    return {
        "schema_version": "1.0.0",
        "tool": "build_plan_shell_skp",
        "consensus_source": consensus.get("source"),
        "wall_thickness_pts": consensus.get("wall_thickness_pts"),
        "page_size_pts": consensus.get("page_size_pts"),
        "polygons": pieces,
        "rooms": consensus.get("rooms", []),
        "soft_barriers": consensus.get("soft_barriers", []),
        "stats": stats,
    }


# ---- cache (mirror skp_from_consensus.py sidecar pattern) ----------

def _file_sha256(path: Path) -> str:
    """Stream the file and return its SHA256 hex digest."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def metadata_path(out_skp: Path) -> Path:
    """Path of the sidecar metadata file for a given .skp."""
    return out_skp.with_name(out_skp.name + METADATA_SUFFIX)


def read_metadata(out_skp: Path) -> dict[str, Any] | None:
    """Read the sidecar metadata. Returns None if missing or unparseable."""
    p = metadata_path(out_skp)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_metadata(out_skp: Path, *, consensus_sha256: str,
                   sketchup_exe: Path, command: list[str]) -> Path:
    """Write the sidecar metadata next to the .skp. Returns the path written."""
    p = metadata_path(out_skp)
    data = {
        "schema_version": "1.0.0",
        "exporter": "build_plan_shell_skp",
        "consensus_sha256": consensus_sha256,
        "skp_path": str(out_skp),
        "created_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "sketchup_path": str(sketchup_exe),
        "command": " ".join(command),
    }
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def should_skip(out_skp: Path, consensus_sha256: str) -> bool:
    """True iff the .skp exists and its sidecar's consensus_sha256 matches.

    Caller is responsible for honouring `force_skp` BEFORE calling this —
    we don't take that flag here so the helper stays trivially testable.
    """
    if not out_skp.exists():
        return False
    meta = read_metadata(out_skp)
    if not meta:
        return False
    # Only skip when the SAME exporter produced the cached .skp.
    # Otherwise consume-produced .skp would be reused for a plan-shell
    # request (and vice-versa), corrupting the user's intent.
    if meta.get("exporter") != "build_plan_shell_skp":
        return False
    return meta.get("consensus_sha256") == consensus_sha256


# ---- launcher --------------------------------------------------------

def write_control(plugins_dir: Path, consensus: Path, out_skp: Path) -> None:
    plugins_dir.mkdir(parents=True, exist_ok=True)
    txt = "\n".join([
        str(consensus.resolve()).replace("\\", "/"),
        str(out_skp.resolve()).replace("\\", "/"),
        str(RUBY_TEMPLATE.resolve()).replace("\\", "/"),
    ])
    (plugins_dir / CONTROL_FILE).write_text(txt, encoding="utf-8")


def find_bootstrap(out_skp: Path) -> Path | None:
    candidates = sorted(
        (p for p in out_skp.parent.glob("*.skp") if p != out_skp),
        key=lambda p: -p.stat().st_mtime,
    )
    if candidates:
        return candidates[0]
    template_dir = Path(
        r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
        r"\resources\en-US\Templates"
    )
    for name in ("Temp01a - Simple.skp", "Temp01b - Simple.skp"):
        t = template_dir / name
        if t.exists():
            bootstrap = out_skp.parent / "_bootstrap.skp"
            if not bootstrap.exists():
                shutil.copy2(t, bootstrap)
            return bootstrap
    return None


def run(consensus_path: Path, out_skp: Path, *, sketchup_exe: Path,
        plugins_dir: Path = PLUGINS_DIR_DEFAULT,
        timeout_s: int = 180,
        out_png_iso: Path | None = None,
        out_png_top: Path | None = None,
        out_report: Path | None = None,
        out_shell_json: Path | None = None,
        soft_barriers_mode: str = "groups",
        force_skp: bool = False) -> dict[str, Any]:
    """Build the plan shell .skp end-to-end.

    Args:
      consensus_path: input consensus_model.json (or
        amended_observed.json — overrides-blind per ADR-001).
      out_skp: output .skp path.
      soft_barriers_mode: "groups" (emit at 1.10m as SoftBarrier_Group_N)
        or "skip" (record in report, do not emit).
      force_skp: bypass the content-hash cache. Default False.

    Returns a dict with paths and stats. Honours the content-hash
    cache via a sidecar `<out_skp>.metadata.json` (matches the
    skp_from_consensus.py pattern); reruns short-circuit when the
    consensus SHA256 matches and force_skp is False.
    """
    started = time.time()
    out_skp.parent.mkdir(parents=True, exist_ok=True)
    if out_png_iso is None:
        out_png_iso = out_skp.with_name("model_iso.png")
    if out_png_top is None:
        out_png_top = out_skp.with_name("model_top.png")
    if out_report is None:
        out_report = out_skp.with_name("geometry_report.json")
    if out_shell_json is None:
        out_shell_json = out_skp.with_name("_shell_polygon.json")

    # ---- skip path: re-use unchanged .skp ----
    consensus_sha = (
        _file_sha256(consensus_path) if consensus_path.exists() else None
    )
    if (
        not force_skp
        and consensus_sha is not None
        and should_skip(out_skp, consensus_sha)
    ):
        elapsed = time.time() - started
        print(
            f"[skip] {out_skp} unchanged consensus "
            f"(sha {consensus_sha[:12]}); skipped SU launch"
        )
        return {
            "ok": True,
            "skipped": True,
            "skp_path": str(out_skp),
            "consensus_sha256": consensus_sha,
            "elapsed_s": round(elapsed, 4),
        }

    # Clean stale outputs (incl. stale sidecar metadata).
    meta_p = metadata_path(out_skp)
    for p in (out_skp, out_png_iso, out_png_top, out_report,
              out_shell_json, meta_p):
        if p.exists():
            p.unlink()

    # [Python phase] consensus -> shell polygon JSON
    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    polygons, stats = build_shell_polygon(consensus)
    payload = serialize_polygons(polygons, consensus, stats)
    out_shell_json.write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"[py] shell polygon -> {out_shell_json}")
    print(
        f"[py] stats: walls={stats['input_walls']} "
        f"openings_carved={stats['openings_carved']} "
        f"pieces={stats['shell_pieces_after_sliver_filter']} "
        f"area={stats['total_shell_area_pts2']:.1f} pts^2"
    )

    # [Ruby phase] launch SU, autorun reads control file
    for p in disarm_autoruns(plugins_dir):
        print(f"[pre-launch disarm] removed orphan {p.name}")
    write_control(plugins_dir, consensus_path, out_skp)

    bootstrap = find_bootstrap(out_skp)
    cmd = [str(sketchup_exe)]
    if bootstrap:
        cmd.append(str(bootstrap))

    env = os.environ.copy()
    env["PNG_ISO_OUT"] = str(out_png_iso.resolve()).replace("\\", "/")
    env["PNG_TOP_OUT"] = str(out_png_top.resolve()).replace("\\", "/")
    env["REPORT_OUT"] = str(out_report.resolve()).replace("\\", "/")
    env["SHELL_JSON_IN"] = str(out_shell_json.resolve()).replace("\\", "/")
    env["SOFT_BARRIERS_MODE"] = soft_barriers_mode
    print(f"[run] launching SU: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        env=env,
    )

    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if out_skp.exists():
                time.sleep(2)  # flush
                print(f"[ok] {out_skp} ({out_skp.stat().st_size} bytes)")
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                # Persist sidecar metadata so a future run with the
                # same consensus short-circuits the cache check.
                if consensus_sha is not None:
                    write_metadata(
                        out_skp,
                        consensus_sha256=consensus_sha,
                        sketchup_exe=sketchup_exe,
                        command=cmd,
                    )
                return {
                    "ok": True,
                    "skipped": False,
                    "skp_path": str(out_skp),
                    "png_iso": str(out_png_iso),
                    "png_top": str(out_png_top),
                    "report": str(out_report),
                    "shell_json": str(out_shell_json),
                    "consensus_sha256": consensus_sha,
                    "elapsed_s": round(time.time() - started, 4),
                    "stats": stats,
                }
            if proc.poll() is not None:
                err_file = plugins_dir / "autorun_error.txt"
                print(
                    f"[err] SU exited prematurely code={proc.returncode}"
                )
                if err_file.exists():
                    print("---- ruby error ----")
                    print(err_file.read_text(
                        encoding="utf-8", errors="replace"
                    ))
                return {"ok": False, "stats": stats}
            time.sleep(1)
        print(f"[err] timeout {timeout_s}s waiting for {out_skp}")
        try:
            proc.terminate()
            time.sleep(2)
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "stats": stats, "timeout": True}
    finally:
        for p in disarm_autoruns(plugins_dir):
            print(f"[post-run disarm] removed {p.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("consensus", type=Path,
                    help="consensus_model.json or amended_observed.json")
    ap.add_argument("--out", type=Path, required=True,
                    help="output .skp path")
    ap.add_argument("--sketchup", type=Path,
                    default=Path(SKETCHUP_EXE_DEFAULT))
    ap.add_argument("--plugins", type=Path, default=PLUGINS_DIR_DEFAULT)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--soft-barriers", choices=("groups", "skip"),
                    default="groups",
                    help='"groups": emit each as SoftBarrier_Group_N at '
                         '1.10 m; "skip": skip and record in report')
    ap.add_argument("--force-skp", action="store_true",
                    help="bypass the consensus-hash cache, always launch SU")
    args = ap.parse_args()
    result = run(
        args.consensus.resolve(), args.out.resolve(),
        sketchup_exe=args.sketchup,
        plugins_dir=args.plugins,
        timeout_s=args.timeout,
        soft_barriers_mode=args.soft_barriers,
        force_skp=args.force_skp,
    )
    if result.get("skipped"):
        sha = result.get("consensus_sha256") or ""
        print(f"SKIPPED_UNCHANGED_CONSENSUS sha={sha[:12]}")
    raise SystemExit(0 if result.get("ok") else 1)
