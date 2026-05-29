"""FP-030 negative dogfood — deterministic-part contract tests.

The real oracle run is non-deterministic (a vision model) and is exercised as
evidence, not in CI. Here we lock the parts that MUST be deterministic:
the corruption recipe and the discrimination decision. Plus a guard that the
planta_74 recipe still targets a wall (catches a render-palette drift).
"""
from __future__ import annotations

import pytest

from tools.negative_dogfood import (
    CORRUPTION_RECIPES,
    REPO_ROOT,
    corrupt_render,
    discrimination_decision,
    localized_gap_findings,
)


def _make_img(path, size=(40, 30), color=(10, 20, 30)):
    from PIL import Image
    Image.new("RGB", size, color).save(path)


# ---- corruption recipe is deterministic ------------------------------


def test_corrupt_render_is_deterministic(tmp_path):
    src = tmp_path / "src.png"
    _make_img(src)
    o1, o2 = tmp_path / "o1.png", tmp_path / "o2.png"
    m1 = corrupt_render(src, o1, (5, 5, 15, 15), (0, 0))
    m2 = corrupt_render(src, o2, (5, 5, 15, 15), (0, 0))
    assert m1["out_sha256"] == m2["out_sha256"]


def test_corrupt_render_actually_changes_image(tmp_path):
    src = tmp_path / "src.png"
    _make_img(src, color=(10, 20, 30))
    out = tmp_path / "out.png"
    # ref_point (0,0) is the base color; fill a region with a DIFFERENT color
    # by first painting a patch so the sampled ref differs from the region.
    from PIL import Image
    im = Image.open(src).convert("RGB")
    im.putpixel((0, 0), (200, 200, 200))  # ref_point becomes light
    im.save(src)
    meta = corrupt_render(src, out, (5, 5, 15, 15), (0, 0))
    assert meta["out_sha256"] != meta["src_sha256"]
    assert meta["fill_rgb"] == [200, 200, 200]


def test_corrupt_render_rejects_oob_rect(tmp_path):
    src = tmp_path / "src.png"
    _make_img(src, size=(20, 20))
    with pytest.raises(ValueError):
        corrupt_render(src, tmp_path / "o.png", (0, 0, 50, 50), (0, 0))


def test_corrupt_render_rejects_oob_ref(tmp_path):
    src = tmp_path / "src.png"
    _make_img(src, size=(20, 20))
    with pytest.raises(ValueError):
        corrupt_render(src, tmp_path / "o.png", (1, 1, 5, 5), (99, 99))


# ---- discrimination decision logic -----------------------------------


def test_discrimination_catches_worse():
    assert discrimination_decision("PASS", "FAIL")["discriminated"]
    assert discrimination_decision("PASS", "WARN")["discriminated"]
    assert discrimination_decision("WARN", "FAIL")["discriminated"]


def test_discrimination_same_verdict_is_not_discriminated():
    assert not discrimination_decision("PASS", "PASS")["discriminated"]
    assert not discrimination_decision("FAIL", "FAIL")["discriminated"]


def test_discrimination_better_is_not_discriminated():
    # corrupted rated BETTER than clean -> not a catch
    assert not discrimination_decision("WARN", "PASS")["discriminated"]


# ---- finding-level (secondary) criterion -----------------------------


def test_localized_gap_finding_detected():
    norm = {"findings": [
        {"type": "missing_wall_continuation", "location": "top center of the image",
         "evidence": "visible gaps"},
    ]}
    assert len(localized_gap_findings(norm)) == 1


def test_non_gap_type_is_ignored():
    norm = {"findings": [
        {"type": "floating_door", "location": "top center", "evidence": "gap"},
    ]}
    assert localized_gap_findings(norm) == []


def test_gap_type_without_region_or_evidence_is_ignored():
    norm = {"findings": [
        {"type": "wall_stub", "location": "somewhere", "evidence": "looks fine"},
    ]}
    assert localized_gap_findings(norm) == []


def test_localized_gap_handles_empty_and_none():
    assert localized_gap_findings(None) == []
    assert localized_gap_findings({}) == []


# ---- planta_74 recipe still targets a wall ---------------------------


def test_planta_74_recipe_targets_a_wall():
    """Guards against render-palette drift: the rect center must sit on a
    dark wall, and ref_point on light background, else the injected defect is
    not a missing-wall."""
    recipe = CORRUPTION_RECIPES["planta_74"]
    src = REPO_ROOT / "artifacts" / "planta_74" / recipe["source_render"]
    if not src.exists():
        pytest.skip("planta_74 canonical render not present")
    from PIL import Image
    im = Image.open(src).convert("RGB")
    x0, y0, x1, y1 = recipe["rect"]
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    wall = im.getpixel((cx, cy))
    bg = im.getpixel(tuple(recipe["ref_point"]))
    assert sum(wall) / 3 < 130, f"rect center not on a dark wall: {wall}"
    assert sum(bg) / 3 > 160, f"ref_point not on light background: {bg}"
