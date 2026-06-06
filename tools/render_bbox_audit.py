#!/usr/bin/env python3
"""Deterministic render-framing gate (external-review finding #1).

A stale top render that CLIPPED the plant at the left/right edges got reviewed as
if it were the canonical, producing findings against geometry that no longer
exists. The #29 deterministic camera fixed the clip, but nothing GATED it — so a
regression would silently ship a half-framed plant and invalidate every visual
review.

This gate segments the non-background content of a top render and fails if its
bounding box touches (or comes within `edge_min` px of) any frame edge. Pure
pixel op: no SU, no sidecar, no network.
"""
from __future__ import annotations

import numpy as np


def bbox_margins(rgb: np.ndarray, bg_tol: int = 30) -> dict:
    """L/T/R/B margins (px) between the non-background content bbox and the frame.
    Background = median of the 4 corners (the render's uniform fill)."""
    h, w, _ = rgb.shape
    corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
    bg = np.median(corners, axis=0)
    content = np.abs(rgb.astype(int) - bg).sum(axis=2) > bg_tol
    ys, xs = np.where(content)
    if xs.size == 0:
        return {"empty": True, "bg": bg.astype(int).tolist(),
                "left": 0, "top": 0, "right": 0, "bottom": 0, "w": w, "h": h}
    minx, maxx = int(xs.min()), int(xs.max())
    miny, maxy = int(ys.min()), int(ys.max())
    return {"empty": False, "bg": bg.astype(int).tolist(),
            "left": minx, "top": miny, "right": w - 1 - maxx,
            "bottom": h - 1 - maxy, "w": w, "h": h}


def audit_render_bbox(render_path: str, *, edge_min: int = 32,
                      bg_tol: int = 30) -> dict:
    """{verdict PASS/FAIL, margins, edge_min}. FAIL if the content bbox is empty
    or any margin < edge_min (plant clipped or framed too tight)."""
    from PIL import Image
    try:
        rgb = np.array(Image.open(render_path).convert("RGB"))
    except Exception as e:  # unreadable / not an image -> a framing FAIL
        return {"verdict": "FAIL", "reason": f"unreadable render: {e}",
                "margins": None, "edge_min": edge_min}
    m = bbox_margins(rgb, bg_tol=bg_tol)
    if m["empty"]:
        return {"verdict": "FAIL", "reason": "no content (blank render)",
                "margins": m, "edge_min": edge_min}
    worst = min(m["left"], m["top"], m["right"], m["bottom"])
    verdict = "FAIL" if worst < edge_min else "PASS"
    return {
        "verdict": verdict,
        "reason": (f"content bbox within {worst}px of a frame edge "
                   f"(min {edge_min})" if verdict == "FAIL" else "framed"),
        "margins": {k: m[k] for k in ("left", "top", "right", "bottom")},
        "worst_margin": worst,
        "edge_min": edge_min,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="render framing / clip gate")
    ap.add_argument("render", help="top render PNG")
    ap.add_argument("--edge-min", type=int, default=32)
    a = ap.parse_args()
    res = audit_render_bbox(a.render, edge_min=a.edge_min)
    print(f"[render_bbox] {res['verdict']} margins={res['margins']} "
          f"({res['reason']})")
    raise SystemExit(0 if res["verdict"] == "PASS" else 1)
