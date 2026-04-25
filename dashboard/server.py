from __future__ import annotations

import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

REPOS = {
    "main": Path("E:/Claude/sketchup-mcp"),
    "expdedup": Path("E:/Claude/sketchup-mcp-exp-dedup"),
}
HERE = Path(__file__).resolve().parent
METRICS_FILE = HERE / "_metrics.json"
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"
DETECTIONS = HERE / "detections"

app = FastAPI(title="sketchup-mcp dashboard", version="2.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES))
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def _load_metrics() -> list[dict[str, Any]]:
    if not METRICS_FILE.exists():
        return []
    return json.loads(METRICS_FILE.read_text())


def _phase_group(name: str, repo: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if base.startswith("h1"): return "F1 dedup colinear"
    if base.startswith("h2"): return "F2 audit + snapshot"
    if base.startswith("h3"): return "F3 DedupReport"
    if base.startswith("h4"): return "F4 sliver filter"
    if base.startswith("h5"): return "F5 strip room merge"
    if base.startswith("f6"): return "F6 room dedup"
    if base.startswith("f7"): return "F7 openings calibration"
    if base.startswith("f12"): return "F12 furniture filter"
    if base == "final_planta_74": return "F13 final state"
    if base == "wave2_baseline": return "wave2"
    if base.startswith("_tmp"): return "regression gates"
    if base == "baseline": return "pre-hardening"
    if repo == "main" and name.startswith("proto/"):
        return "main proto runs"
    if repo == "main": return "main"
    return "outros"


SECTION_ORDER = [
    "pre-hardening", "F1 dedup colinear", "F2 audit + snapshot",
    "F3 DedupReport", "F4 sliver filter", "F5 strip room merge",
    "F6 room dedup", "F7 openings calibration", "F12 furniture filter",
    "F13 final state", "wave2", "regression gates",
    "main proto runs", "main", "outros",
]


def _find(metrics, repo, name):
    return next(
        (m for m in metrics if m["repo"] == repo and m["name"] == name),
        None,
    )


def _safe_run_path(repo: str, name: str) -> Path:
    if repo not in REPOS:
        raise HTTPException(404, f"unknown repo: {repo}")
    base = (REPOS[repo] / "runs").resolve()
    target = (base / name).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(400, "path traversal blocked")
    return target


@app.get("/")
def index(request: Request):
    metrics = _load_metrics()
    grouped: dict[str, list[dict]] = {}
    for m in metrics:
        g = _phase_group(m["name"], m["repo"])
        grouped.setdefault(g, []).append(m)
    sections = [(g, grouped[g]) for g in SECTION_ORDER if g in grouped]
    final = _find(metrics, "expdedup", "final_planta_74")
    baseline = _find(metrics, "expdedup", "baseline")
    return templates.TemplateResponse(
        request, "index.html",
        {"sections": sections, "total": len(metrics),
         "final": final, "baseline": baseline},
    )


@app.get("/run/{repo}/{name:path}")
def run_detail(request: Request, repo: str, name: str):
    metrics = _load_metrics()
    m = _find(metrics, repo, name)
    if m is None:
        raise HTTPException(404, f"run not found: {repo}/{name}")
    run_dir = _safe_run_path(repo, name)
    artifacts = []
    for fname in ("observed_model.json", "connectivity_report.json",
                  "dedup_report.json", "room_topology_check.json"):
        p = run_dir / fname
        if p.exists():
            try:
                artifacts.append({
                    "name": fname,
                    "size": p.stat().st_size,
                    "preview": json.dumps(json.loads(p.read_text()), indent=2)[:4000],
                })
            except Exception as e:
                artifacts.append({"name": fname, "size": p.stat().st_size,
                                  "preview": f"<<error: {e}>>"})
    other_runs = [(x["repo"], x["name"]) for x in metrics
                  if not (x["repo"] == repo and x["name"] == name)]
    return templates.TemplateResponse(
        request, "run.html",
        {"m": m, "artifacts": artifacts, "other_runs": other_runs},
    )


@app.get("/compare")
def compare(request: Request, a_repo: str, a: str, b_repo: str, b: str):
    metrics = _load_metrics()
    ma = _find(metrics, a_repo, a)
    mb = _find(metrics, b_repo, b)
    if ma is None: raise HTTPException(404, f"run not found: {a_repo}/{a}")
    if mb is None: raise HTTPException(404, f"run not found: {b_repo}/{b}")
    diff_keys = ["walls", "rooms", "juncs", "openings", "peitoris",
                 "orphan_count", "largest_ratio", "components",
                 "topology_score", "rooms_score", "geometry_score", "warnings"]
    rows = []
    for k in diff_keys:
        va, vb = ma.get(k), mb.get(k)
        try:
            delta = (vb - va) if (va is not None and vb is not None) else None
        except TypeError:
            delta = None
        rows.append({"key": k, "a": va, "b": vb, "delta": delta})
    return templates.TemplateResponse(
        request, "compare.html",
        {"a": ma, "b": mb, "rows": rows},
    )


@app.get("/img/{repo}/{path:path}")
def serve_image(repo: str, path: str, download: int = 0):
    p = _safe_run_path(repo, path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"file not found: {repo}/{path}")
    headers = {"Content-Disposition": f'attachment; filename="{p.name}"'} if download else {}
    return FileResponse(str(p), headers=headers)


@app.get("/svg/{repo}/{name:path}")
def svg_openings(repo: str, name: str):
    """Compose walls + junctions + opening diamonds as inline SVG from observed_model."""
    run_dir = _safe_run_path(repo, name)
    om = run_dir / "observed_model.json"
    if not om.exists():
        raise HTTPException(404, f"observed_model.json not found: {repo}/{name}")
    m = json.loads(om.read_text())
    walls = m.get("walls", [])
    juncs = m.get("junctions", [])
    openings = m.get("openings", [])
    pages = m.get("bounds", {}).get("pages", [])
    if not pages:
        raise HTTPException(422, "no bounds in observed_model")
    page = pages[0]
    pad = 30
    minx, miny = page["min_x"] - pad, page["min_y"] - pad
    w = (page["max_x"] - page["min_x"]) + 2 * pad
    h = (page["max_y"] - page["min_y"]) + 2 * pad
    scores = m.get("scores", {})

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{minx} {miny} {w} {h}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="background:#ffffff;font-family:monospace">'
    )
    header = (
        f"walls={len(walls)} juncs={len(juncs)} "
        f"rooms={len(m.get('rooms', []))} openings={len(openings)} "
        f"geom={scores.get('geometry', 0):.3f} topo={scores.get('topology', 0):.3f}"
    )
    parts.append(
        f'<text x="{minx + 8}" y="{miny + 18}" font-size="14" fill="#222">{header}</text>'
    )

    for wall in walls:
        sx, sy = wall["start"]
        ex, ey = wall["end"]
        parts.append(
            f'<line x1="{sx}" y1="{sy}" x2="{ex}" y2="{ey}" '
            f'stroke="#dc3c3c" stroke-width="3" stroke-linecap="round">'
            f'<title>{wall.get("wall_id", "")} t={wall.get("thickness", 0):.1f}</title></line>'
        )

    for j in juncs:
        pt = j.get("point") or j.get("coord")
        if not pt: continue
        cx, cy = pt
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="5" fill="#3c78dc">'
            f'<title>{j.get("junction_id", "")} {j.get("kind", "")}</title></circle>'
        )

    for op in openings:
        cx, cy = op["center"]
        s = 11
        oid = op.get("opening_id", "")
        kind = op.get("kind", "?")
        width = op.get("width", 0)
        hinge = op.get("hinge_side", "?")
        parts.append(
            f'<polygon points="{cx},{cy - s} {cx + s},{cy} {cx},{cy + s} {cx - s},{cy}" '
            f'fill="#f09632" stroke="#7a4500" stroke-width="1.5">'
            f'<title>{oid} {kind} w={width:.1f} hinge={hinge}</title></polygon>'
        )
        label = oid.replace("opening-", "")
        if label:
            parts.append(
                f'<text x="{cx + s + 3}" y="{cy + 4}" font-size="11" '
                f'fill="#7a4500">{label}</text>'
            )

    parts.append("</svg>")
    return Response(content="".join(parts), media_type="image/svg+xml")


def _detector_kind(model: str) -> str:
    m = (model or "").lower()
    if "yolo" in m: return "yolo"
    if "cubicasa" in m or "cubi" in m: return "cubicasa"
    if "qwen" in m or "vl" in m: return "qwen_vl"
    return "other"


def _count_detections(payload: dict) -> dict:
    """Count doors/windows/walls from any of the supported JSON schemas."""
    counts = {"doors": None, "windows": None, "walls": None}
    totals = payload.get("totals") or {}
    if isinstance(totals, dict):
        if "doors" in totals: counts["doors"] = totals["doors"]
        if "windows" in totals: counts["windows"] = totals["windows"]
        if "walls" in totals: counts["walls"] = totals["walls"]
    cc = payload.get("class_counts") or {}
    if isinstance(cc, dict):
        for key in ("door", "doors"):
            if key in cc and counts["doors"] is None:
                counts["doors"] = cc[key]
        for key in ("window", "windows"):
            if key in cc and counts["windows"] is None:
                counts["windows"] = cc[key]
        for key in ("wall", "walls"):
            if key in cc and counts["walls"] is None:
                counts["walls"] = cc[key]
    if "parsed_doors" in payload and counts["doors"] is None:
        v = payload["parsed_doors"]
        counts["doors"] = len(v) if isinstance(v, list) else v
    if "parsed_windows" in payload and counts["windows"] is None:
        v = payload["parsed_windows"]
        counts["windows"] = len(v) if isinstance(v, list) else v
    if counts["doors"] is None or counts["windows"] is None:
        dets = payload.get("detections") or []
        if isinstance(dets, list):
            d = w = 0
            for det in dets:
                cls = str(det.get("class", "")).lower()
                if cls in ("door", "doors"): d += 1
                elif cls in ("window", "windows"): w += 1
            if counts["doors"] is None: counts["doors"] = d
            if counts["windows"] is None: counts["windows"] = w
    return counts


def _list_detections_for(name: str) -> list[dict]:
    """Find all detection JSONs whose filename ends with _<basename>.json."""
    if not DETECTIONS.exists():
        return []
    basename = name.rsplit("/", 1)[-1]
    suffix = f"_{basename}.json"
    out = []
    for p in sorted(DETECTIONS.glob(f"*{suffix}")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            out.append({
                "file": p.name,
                "model": p.stem,
                "kind": "error",
                "error": str(e),
                "counts": {"doors": None, "windows": None, "walls": None},
                "latency": None,
                "annotated_png": None,
                "json_dump": "",
                "raw": {},
            })
            continue
        model = payload.get("model") or p.stem.split("_")[0]
        png_name = p.stem + ".png"
        png_path = DETECTIONS / png_name
        out.append({
            "file": p.name,
            "model": model,
            "kind": _detector_kind(model),
            "error": None,
            "counts": _count_detections(payload),
            "latency": payload.get("latency_seconds"),
            "annotated_png": png_name if png_path.exists() else None,
            "json_dump": json.dumps(payload, indent=2, ensure_ascii=False)[:6000],
            "raw": payload,
        })
    return out


ARTIFACT_VISUAL_EXTS = {".png", ".jpg", ".jpeg", ".svg"}
ARTIFACT_DATA_EXTS = {".json"}
ARTIFACT_PDF_EXTS = {".pdf"}
ARTIFACT_MODEL_EXTS = {".skp", ".glb", ".gltf", ".obj"}


def _classify_ext(ext: str) -> str:
    e = ext.lower()
    if e in ARTIFACT_VISUAL_EXTS: return "image"
    if e in ARTIFACT_PDF_EXTS: return "pdf"
    if e in ARTIFACT_DATA_EXTS: return "json"
    if e in ARTIFACT_MODEL_EXTS: return "model"
    return "other"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def _build_artifact_entry(repo: str, name: str, p: Path) -> dict:
    """Uniform artifact descriptor (used for run-dir files)."""
    ext = p.suffix.lower()
    rel = p.name  # files are flat under run_dir
    rel_path = f"runs/{name}/{p.name}"
    # /artifact/ enforces attachment headers; /img/ stays inline for embeds
    inline_url = f"/img/{repo}/{name}/{p.name}"
    download_url = f"/artifact/{repo}/{name}/{p.name}"
    stat = p.stat()
    return {
        "name": p.name,
        "ext": ext.lstrip("."),
        "kind": _classify_ext(ext),
        "size": stat.st_size,
        "size_kb": stat.st_size / 1024,
        "size_human": _fmt_size(stat.st_size),
        "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "abs_path": str(p),
        "rel_path": rel_path,
        "url": inline_url,
        "view_url": inline_url,
        "download_url": download_url,
    }


def _collect_run_artifacts(repo: str, name: str) -> dict:
    """List ALL artifacts in runs/{repo}/{name}/ classified by kind for the dashboard cards."""
    run_dir = _safe_run_path(repo, name)
    visuals: list[dict] = []
    data: list[dict] = []
    pdfs: list[dict] = []
    models: list[dict] = []
    others: list[dict] = []
    all_files: list[dict] = []
    if not run_dir.exists():
        return {"visuals": visuals, "data": data, "pdfs": pdfs, "models": models,
                "others": others, "all": all_files}
    for p in sorted(run_dir.iterdir()):
        if not p.is_file():
            continue
        entry = _build_artifact_entry(repo, name, p)
        all_files.append(entry)
        kind = entry["kind"]
        if kind == "image":
            visuals.append(entry)
        elif kind == "json":
            data.append(entry)
        elif kind == "pdf":
            pdfs.append(entry)
        elif kind == "model":
            models.append(entry)
        else:
            others.append(entry)
    return {"visuals": visuals, "data": data, "pdfs": pdfs, "models": models,
            "others": others, "all": all_files}


def _expected_artifacts(repo: str, name: str) -> list[dict]:
    """Return descriptors for known-expected artifacts; mark missing ones as pendente."""
    run_dir = _safe_run_path(repo, name)
    expected_names = [
        "logical_walls_overlay.png",
        "pdf_vs_skp_topview.png",
        "generated_from_consensus.skp",
    ]
    out: list[dict] = []
    for fn in expected_names:
        p = run_dir / fn
        if p.exists() and p.is_file():
            entry = _build_artifact_entry(repo, name, p)
            entry["status"] = "ok"
            out.append(entry)
        else:
            out.append({
                "name": fn,
                "ext": Path(fn).suffix.lstrip("."),
                "kind": _classify_ext(Path(fn).suffix),
                "abs_path": str(p),
                "rel_path": f"runs/{name}/{fn}",
                "status": "pendente",
            })
    return out


def _list_alternate_detections_for(name: str) -> list[dict]:
    """Find detection JSONs with extra qualifier (e.g. *_clean_<basename>.json)."""
    if not DETECTIONS.exists():
        return []
    basename = name.rsplit("/", 1)[-1]
    primary_suffix = f"_{basename}.json"
    out: list[dict] = []
    for p in sorted(DETECTIONS.glob(f"*{basename}.json")):
        if p.name.endswith(primary_suffix):
            stem_no_basename = p.stem[: -len(basename) - 1]
            if "_" not in stem_no_basename:
                continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            payload = {"_error": str(e)}
        model = payload.get("model") or p.stem.split("_")[0]
        png_name = p.stem + ".png"
        png_path = DETECTIONS / png_name
        out.append({
            "file": p.name,
            "model": model,
            "kind": _detector_kind(model),
            "label": p.stem,
            "counts": _count_detections(payload) if "_error" not in payload else
                      {"doors": None, "windows": None, "walls": None},
            "annotated_png": png_name if png_path.exists() else None,
            "json_url": f"/detections/{p.name}",
            "json_download_url": f"/detections/{p.name}?download=1",
            "png_url": f"/detections/{png_name}" if png_path.exists() else None,
            "png_download_url": f"/detections/{png_name}?download=1" if png_path.exists() else None,
            "abs_json": str(p),
            "abs_png": str(png_path) if png_path.exists() else None,
            "json_size_kb": p.stat().st_size / 1024,
            "png_size_kb": (png_path.stat().st_size / 1024) if png_path.exists() else None,
        })
    return out


@app.get("/cv/{repo}/{name:path}")
def cross_validate(request: Request, repo: str, name: str):
    metrics = _load_metrics()
    m = _find(metrics, repo, name)
    if m is None:
        raise HTTPException(404, f"run not found: {repo}/{name}")
    run_dir = _safe_run_path(repo, name)
    om_path = run_dir / "observed_model.json"
    pipeline_counts = {"doors": m.get("openings", 0),
                       "windows": m.get("peitoris", 0),
                       "walls": m.get("walls", 0)}
    if om_path.exists():
        try:
            om = json.loads(om_path.read_text())
            pipeline_counts["doors"] = len(om.get("openings", []))
            pipeline_counts["windows"] = len(om.get("peitoris", []))
            pipeline_counts["walls"] = len(om.get("walls", []))
        except Exception:
            pass
    detectors = _list_detections_for(name)
    for d in detectors:
        png = d.get("annotated_png")
        d["png_url"] = f"/detections/{png}" if png else None
        d["png_download_url"] = f"/detections/{png}?download=1" if png else None
        d["json_url"] = f"/detections/{d['file']}"
        d["json_download_url"] = f"/detections/{d['file']}?download=1"
        d["abs_json"] = str(DETECTIONS / d["file"])
        d["abs_png"] = str(DETECTIONS / png) if png else None
        d["json_size_kb"] = (DETECTIONS / d["file"]).stat().st_size / 1024
        d["png_size_kb"] = (DETECTIONS / png).stat().st_size / 1024 if png else None
    alternates = _list_alternate_detections_for(name)
    artifacts = _collect_run_artifacts(repo, name)
    expected = _expected_artifacts(repo, name)

    # Run dir metadata
    run_dir_stat = run_dir.stat() if run_dir.exists() else None
    run_dir_mtime = (datetime.fromtimestamp(run_dir_stat.st_mtime).isoformat(timespec="seconds")
                     if run_dir_stat else "—")

    # Pick the best overlay candidate for the side-by-side
    best_overlay = None
    for cand in ("pdf_vs_consensus.png", "pdf_vs_skp_topview.png",
                 "consensus_overlay.png", "logical_walls_overlay.png",
                 "overlay_audited.png", m.get("overlay") or ""):
        if not cand:
            continue
        cp = run_dir / cand
        if cp.exists():
            best_overlay = _build_artifact_entry(repo, name, cp)
            break

    pdf_info = None
    pdf_filename = m.get("pdf")
    if pdf_filename:
        pdf_path = REPOS[repo] / pdf_filename
        if pdf_path.exists():
            pdf_info = {
                "name": pdf_path.name,
                "abs_path": str(pdf_path),
                "size_kb": pdf_path.stat().st_size / 1024,
                "size_human": _fmt_size(pdf_path.stat().st_size),
                "mtime_iso": datetime.fromtimestamp(pdf_path.stat().st_mtime).isoformat(timespec="seconds"),
                "url": f"/pdf/{repo}/{pdf_path.name}",
                "download_url": f"/pdf/{repo}/{pdf_path.name}?download=1",
                "thumb_url": f"/pdf-thumb/{repo}/{pdf_path.name}",
            }
    return templates.TemplateResponse(
        request, "cross_validate.html",
        {"m": m, "pipeline": pipeline_counts, "detectors": detectors,
         "alternates": alternates, "artifacts": artifacts, "pdf_info": pdf_info,
         "expected": expected, "best_overlay": best_overlay,
         "run_dir": str(run_dir), "run_dir_mtime": run_dir_mtime,
         "svg_url": f"/svg/{repo}/{name}",
         "svg_abs_path": str(om_path),
         "detections_dir": str(DETECTIONS)},
    )


@app.get("/pdf/{repo}/{filename:path}")
def serve_pdf(repo: str, filename: str, download: int = 0):
    """Serve PDF files from the repo root (sibling of runs/)."""
    if repo not in REPOS:
        raise HTTPException(404, f"unknown repo: {repo}")
    base = REPOS[repo].resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(400, "path traversal blocked")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"pdf not found: {repo}/{filename}")
    headers = {"Content-Disposition": f'attachment; filename="{p.name}"'} if download else {}
    return FileResponse(str(p), media_type="application/pdf", headers=headers)


_PDF_THUMB_CACHE: dict[str, bytes] = {}


@app.get("/artifact/{repo}/{path:path}")
def serve_artifact(repo: str, path: str):
    """Robust file download endpoint for any run-dir artifact.

    Returns FileResponse with explicit Content-Disposition: attachment regardless
    of file type (PNG, JPG, SVG, PDF, JSON, SKP, GLB, etc). Browsers SHOULD save
    rather than render inline. Use /img/ for inline embeds.
    """
    p = _safe_run_path(repo, path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"file not found: {repo}/{path}")
    media_type, _ = mimetypes.guess_type(p.name)
    if media_type is None:
        # Common ones mimetypes misses
        ext = p.suffix.lower()
        media_type = {
            ".skp": "application/vnd.sketchup.skp",
            ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json",
        }.get(ext, "application/octet-stream")
    headers = {"Content-Disposition": f'attachment; filename="{p.name}"'}
    return FileResponse(str(p), media_type=media_type, headers=headers,
                        filename=p.name)


@app.get("/pdf-thumb/{repo}/{filename:path}")
def pdf_thumbnail(repo: str, filename: str, page: int = 0, dpi: int = 100):
    """Render a single PDF page as PNG (server-side, cached in-memory)."""
    if repo not in REPOS:
        raise HTTPException(404, f"unknown repo: {repo}")
    base = REPOS[repo].resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(400, "path traversal blocked")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"pdf not found: {repo}/{filename}")
    cache_key = f"{p}:{page}:{dpi}"
    if cache_key not in _PDF_THUMB_CACHE:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise HTTPException(501, "PyMuPDF not installed")
        with fitz.open(str(p)) as doc:
            if page >= len(doc):
                raise HTTPException(404, f"page {page} out of range ({len(doc)} pages)")
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = doc[page].get_pixmap(matrix=mat, alpha=False)
            _PDF_THUMB_CACHE[cache_key] = pix.tobytes("png")
    return Response(content=_PDF_THUMB_CACHE[cache_key], media_type="image/png")


@app.get("/detections/{filename:path}")
def serve_detection(filename: str, download: int = 0):
    """Serve detector artifacts (PNG annotations, JSON dumps) from the detections dir."""
    p = (DETECTIONS / filename).resolve()
    base = DETECTIONS.resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(400, "path traversal blocked")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"detection file not found: {filename}")
    headers = {"Content-Disposition": f'attachment; filename="{p.name}"'} if download else {}
    return FileResponse(str(p), headers=headers)


@app.get("/fusion/{repo}/{name:path}")
def fusion_view(request: Request, repo: str, name: str):
    metrics = _load_metrics()
    m = _find(metrics, repo, name)
    if m is None:
        raise HTTPException(404, f"run not found: {repo}/{name}")
    run_dir = _safe_run_path(repo, name)
    consensus_file = run_dir / "consensus_model.json"
    consensus = None
    if consensus_file.exists():
        try:
            consensus = json.loads(consensus_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return templates.TemplateResponse(
        request, "fusion.html",
        {"m": m, "consensus": consensus,
         "has_overlay": (run_dir / "consensus_overlay.png").exists(),
         "has_sbs": (run_dir / "pdf_vs_consensus.png").exists()},
    )


@app.get("/3d/{repo}/{name:path}")
def viewer_3d(request: Request, repo: str, name: str):
    """Render the three.js viewer for <run_dir>/consensus_3d.glb."""
    run_dir = _safe_run_path(repo, name)
    glb = run_dir / "consensus_3d.glb"
    glb_exists = glb.exists()
    glb_size_kb = round(glb.stat().st_size / 1024.0, 2) if glb_exists else None
    return templates.TemplateResponse(
        request, "viewer3d.html",
        {"repo": repo, "name": name,
         "glb_exists": glb_exists, "glb_size_kb": glb_size_kb,
         "glb_abs_path": str(glb)},
    )


@app.get("/api/metrics")
def api_metrics():
    return JSONResponse(_load_metrics())


@app.get("/api/run/{repo}/{name:path}")
def api_run_detail(repo: str, name: str):
    """REST endpoint: full run summary as JSON (no HTML).

    Returns metadata, consensus existence + diagnostics, all artifacts
    (using _build_artifact_entry), and detection totals (counts only,
    not the raw response_text)."""
    metrics = _load_metrics()
    m = _find(metrics, repo, name)
    if m is None:
        raise HTTPException(404, f"run not found: {repo}/{name}")
    run_dir = _safe_run_path(repo, name)
    if not run_dir.exists():
        raise HTTPException(404, f"run dir not found: {run_dir}")

    stat = run_dir.stat()
    run_meta = {
        "name": name,
        "repo": repo,
        "abs_path": str(run_dir),
        "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "mtime_epoch": stat.st_mtime,
    }

    # Consensus existence + diagnostics
    consensus_path = run_dir / "consensus_model.json"
    consensus_block: dict[str, Any] = {
        "exists": consensus_path.exists(),
        "abs_path": str(consensus_path),
        "diagnostics": None,
        "metadata": None,
    }
    if consensus_path.exists():
        try:
            cm = json.loads(consensus_path.read_text(encoding="utf-8"))
            consensus_block["diagnostics"] = cm.get("diagnostics")
            consensus_block["metadata"] = cm.get("metadata")
            consensus_block["counts"] = {
                "walls": len(cm.get("walls", [])),
                "openings": len(cm.get("openings", [])),
                "rooms": len(cm.get("rooms", [])),
                "furniture": len(cm.get("furniture", [])),
                "walls_consolidated": len(cm.get("walls_consolidated", []))
                if "walls_consolidated" in cm else None,
            }
        except Exception as e:
            consensus_block["error"] = str(e)

    # Artifacts (uniform _build_artifact_entry shape, flat list of all files)
    artifacts: list[dict] = []
    for p in sorted(run_dir.iterdir()):
        if p.is_file():
            artifacts.append(_build_artifact_entry(repo, name, p))

    # Detection totals only (no response_text)
    detector_summary = {"yolo": None, "cubicasa": None, "qwen": None,
                        "svg_native": None}
    for d in _list_detections_for(name):
        kind = d.get("kind")
        counts = d.get("counts", {})
        entry = {
            "model": d.get("model"),
            "file": d.get("file"),
            "doors": counts.get("doors"),
            "windows": counts.get("windows"),
            "walls": counts.get("walls"),
            "latency_seconds": d.get("latency"),
            "error": d.get("error"),
        }
        if kind == "yolo":
            detector_summary["yolo"] = entry
        elif kind == "cubicasa":
            detector_summary["cubicasa"] = entry
        elif kind == "qwen_vl":
            detector_summary["qwen"] = entry
    # svg_native lives as a separate detections file (svg_parsed_*.json)
    if DETECTIONS.exists():
        basename = name.rsplit("/", 1)[-1]
        svg_native_path = DETECTIONS / f"svg_parsed_{basename}.json"
        if svg_native_path.exists():
            try:
                payload = json.loads(svg_native_path.read_text(encoding="utf-8"))
                counts = _count_detections(payload)
                detector_summary["svg_native"] = {
                    "model": payload.get("model") or "svg_parsed",
                    "file": svg_native_path.name,
                    "doors": counts.get("doors"),
                    "windows": counts.get("windows"),
                    "walls": counts.get("walls"),
                    "latency_seconds": payload.get("latency_seconds"),
                    "error": None,
                }
            except Exception as e:
                detector_summary["svg_native"] = {
                    "model": "svg_parsed", "file": svg_native_path.name,
                    "doors": None, "windows": None, "walls": None,
                    "latency_seconds": None, "error": str(e),
                }

    return JSONResponse({
        "run": run_meta,
        "metrics": m,
        "consensus": consensus_block,
        "artifacts": artifacts,
        "detections": detector_summary,
    })


@app.get("/health")
def health():
    return {"status": "ok", "service": "sketchup-mcp-dashboard",
            "runs_loaded": len(_load_metrics())}
