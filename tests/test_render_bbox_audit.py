"""render_bbox_audit — framing/clip gate (external-review finding #1)."""
from __future__ import annotations

import numpy as np

from tools.render_bbox_audit import audit_render_bbox, bbox_margins


def _canvas(bg=200):
    return np.full((100, 200, 3), bg, np.uint8)


def test_centered_content_has_margins():
    img = _canvas()
    img[40:60, 80:120] = 10
    m = bbox_margins(img)
    assert not m["empty"]
    assert min(m["left"], m["top"], m["right"], m["bottom"]) >= 32


def test_clipped_content_touches_edge():
    img = _canvas()
    img[0:60, 0:120] = 10  # touches top + left
    m = bbox_margins(img)
    assert m["left"] == 0 and m["top"] == 0


def test_empty_render_is_empty():
    assert bbox_margins(_canvas())["empty"]


def test_audit_verdicts(tmp_path):
    from PIL import Image
    ok = _canvas(); ok[40:60, 80:120] = 10
    p1 = tmp_path / "ok.png"; Image.fromarray(ok).save(p1)
    assert audit_render_bbox(str(p1))["verdict"] == "PASS"

    clip = _canvas(); clip[0:60, 0:120] = 10
    p2 = tmp_path / "clip.png"; Image.fromarray(clip).save(p2)
    r = audit_render_bbox(str(p2))
    assert r["verdict"] == "FAIL"
    assert r["margins"]["left"] == 0
