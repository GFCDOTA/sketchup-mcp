"""Walk both repos' runs/ trees and emit a flat metrics JSON used by server.py."""
from __future__ import annotations

import json
from pathlib import Path

REPOS = {
    "main": Path("E:/Claude/sketchup-mcp"),
    "expdedup": Path("E:/Claude/sketchup-mcp-exp-dedup"),
}
OUT = Path(__file__).resolve().parent / "_metrics.json"
DETECTIONS = Path(__file__).resolve().parent / "detections"


def _has_cv(run_dir: Path) -> bool:
    """True if at least one *_<basename>.json exists in dashboard/detections/."""
    if not DETECTIONS.exists():
        return False
    basename = run_dir.name
    suffix = f"_{basename}.json"
    for p in DETECTIONS.glob(f"*{suffix}"):
        if p.is_file():
            return True
    return False

PHASE_LOOKUP = {
    "h1_planta_74": "F1 baseline (representative-anchored dedup)",
    "h1b_planta_74": "F1 v2",
    "h1c_planta_74": "F1 v3",
    "h2_planta_74": "F2 audit log + topology snapshot",
    "h3_planta_74": "F3 DedupReport + adversarial",
    "h4_final_planta_74": "F4 final",
    "h4a_planta_74": "F4a sliver filter v1",
    "h4b_planta_74": "F4b",
    "h4c_planta_74": "F4c",
    "h4d_planta_74": "F4d",
    "h4e_planta_74": "F4e",
    "h4f_planta_74": "F4f",
    "h5_planta_74": "F5 strip room merge",
    "h5b_planta_74": "F5b",
    "h5c_planta_74": "F5c",
    "h5d_planta_74": "F5d",
    "h5e_planta_74": "F5e",
    "h5f_planta_74": "F5f",
    "h5_final": "F5 final",
    "f6_baseline_planta_74": "F6 baseline (input pre-merge)",
    "f6_planta_74": "F6 room dedup",
    "f7_planta_74": "F7 openings calibration",
    "f12_baseline": "F12 baseline (raw Hough)",
    "f12_planta_74": "F12 furniture/legend filter",
    "final_planta_74": "F13 final state",
    "wave2_baseline": "wave2 baseline",
    "_tmp_f12_p12_test": "p12_red regression gate",
    "_tmp_f12_planta_74_test": "planta_74 regression gate",
    "baseline": "pre-hardening baseline",
    "p8_red_v5_run": "proto p8 red v5",
    "p8_red_v7_run": "proto p8 red v7",
    "p9_v3_run": "proto p9 v3",
    "p9_v4_run": "proto p9 v4",
    "p10_v1_run": "proto p10",
    "p11_v1_run": "proto p11",
    "p12_v1_run": "proto p12 (red baseline)",
}

OVERLAY_PRIORITY = (
    "overlay_audited.png",
    "overlay_openings.png",
    "overlay_with_openings.png",
    "overlay_semantic.png",
    "debug_combined.png",
    "raw_page.png",
)


def best_overlay(run_dir: Path) -> str | None:
    for name in OVERLAY_PRIORITY:
        if (run_dir / name).exists():
            return name
    return None


def collect_run(repo: str, run_dir: Path) -> dict | None:
    om = run_dir / "observed_model.json"
    if not om.exists():
        return None
    try:
        m = json.loads(om.read_text())
    except Exception:
        return None
    conn = {}
    cr = run_dir / "connectivity_report.json"
    if cr.exists():
        try:
            conn = json.loads(cr.read_text())
        except Exception:
            pass
    scores = m.get("scores", {})
    metadata = m.get("metadata", {})
    rel = run_dir.relative_to(REPOS[repo] / "runs").as_posix()
    return {
        "repo": repo,
        "name": rel,
        "phase": PHASE_LOOKUP.get(run_dir.name, ""),
        "walls": len(m.get("walls", [])),
        "rooms": len(m.get("rooms", [])),
        "juncs": len(m.get("junctions", [])),
        "openings": len(m.get("openings", [])),
        "peitoris": len(m.get("peitoris", [])),
        "pdf": m.get("source", {}).get("filename", "?"),
        "overlay": best_overlay(run_dir),
        "has_openings": len(m.get("openings", [])) > 0,
        "orphan_count": conn.get("orphan_node_count"),
        "largest_ratio": conn.get("largest_component_ratio"),
        "edges": conn.get("edge_count"),
        "components": conn.get("component_count"),
        "topology_score": scores.get("topology"),
        "rooms_score": scores.get("rooms"),
        "geometry_score": scores.get("geometry"),
        "topology_hash": metadata.get("topology_snapshot_sha256", "")[:12],
        "warnings": len(m.get("warnings", [])),
        "has_cv": _has_cv(run_dir),
    }


def main() -> int:
    out = []
    for repo, root in REPOS.items():
        runs = root / "runs"
        if not runs.exists():
            continue
        for run_dir in sorted(runs.rglob("*")):
            if not run_dir.is_dir():
                continue
            entry = collect_run(repo, run_dir)
            if entry:
                out.append(entry)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {len(out)} runs to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
