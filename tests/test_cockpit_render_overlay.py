"""Unit tests for the Validation Cockpit's SVG overlay renderer.

Cycle 12 (2026-05-08). The renderer is pure Python (no streamlit
import), so it can run in the standard test suite. The Streamlit
app itself (`cockpit/app.py`) is not unit-tested here — its
behaviour is exercised by manual `streamlit run cockpit/app.py`
session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cockpit.render_overlay import (
    PT_TO_M_DEFAULT,
    OverlayToggles,
    PdfUnderlay,
    diff_summary,
    expected_match_summary,
    opening_summary_rows,
    pdf_page_to_data_url,
    render_overlay_svg,
    room_summary_rows,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---- Fixtures ----------------------------------------------------------

def _toy_consensus() -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [100, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [0, 100], "end": [100, 100],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w2", "start": [0, 0], "end": [0, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w3", "start": [100, 0], "end": [100, 100],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w4", "start": [50, 0], "end": [50, 100],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA", "seed_pt": [25, 50],
             "polygon_pts": [[0, 0], [50, 0], [50, 100], [0, 100]],
             "area_pts2": 5000},
            {"id": "r1", "name": "COZINHA", "seed_pt": [75, 50],
             "polygon_pts": [[50, 0], [100, 0], [100, 100], [50, 100]],
             "area_pts2": 5000},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w4",
             "kind_v5": "interior_door", "decision": "clean",
             "center": [50.0, 50.0],
             "evidence": {"room_left": "SALA",
                          "room_right": "COZINHA",
                          "room_left_id": "r0",
                          "room_right_id": "r1"}},
        ],
        "soft_barriers": [],
    }


# ---- render_overlay_svg ------------------------------------------------

def test_render_overlay_returns_self_contained_svg():
    svg = render_overlay_svg(_toy_consensus())
    assert svg.startswith("<svg "), svg[:60]
    assert svg.endswith("</svg>"), svg[-60:]
    assert "viewBox=" in svg
    assert "preserveAspectRatio" in svg


def test_render_overlay_includes_walls_when_toggled_on():
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(walls=True, rooms=False, labels=False,
                                 openings=False),
    )
    # Wall fill color (#3b3326) appears in wall polygons
    assert "#3b3326" in svg


def test_render_overlay_omits_walls_when_toggled_off():
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(walls=False, rooms=True, labels=False,
                                 openings=False),
    )
    assert "#3b3326" not in svg


def test_render_overlay_includes_room_labels_when_toggled():
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(walls=True, rooms=True, labels=True,
                                 openings=False),
    )
    assert "SALA" in svg
    assert "COZINHA" in svg
    assert "m²" in svg  # area annotation


def test_render_overlay_includes_openings_when_toggled():
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(walls=False, rooms=False, labels=False,
                                 openings=True),
    )
    # Orange interior_door fill present
    assert "#f59e0b" in svg


def test_render_overlay_handles_empty_consensus():
    """Renderer must not crash on a consensus with empty walls + rooms."""
    svg = render_overlay_svg(
        {"walls": [], "rooms": [], "openings": []})
    assert svg.startswith("<svg ")
    assert svg.endswith("</svg>")


def test_render_overlay_special_chars_in_label_are_escaped():
    """Label rendering uppercases the name AND escapes XML chars."""
    c = _toy_consensus()
    c["rooms"][0]["name"] = "<sala> & cia"
    svg = render_overlay_svg(c)
    # The renderer uppercases the room name in the label.
    assert "&lt;SALA&gt;" in svg
    assert "&amp;" in svg
    # Raw `<sala>` (or any unescaped `<` followed by alpha) must
    # not slip through. Check for the lowercase variant since the
    # uppercased one is escaped.
    assert "<sala>" not in svg
    assert "<SALA>" not in svg


# ---- room_summary_rows / opening_summary_rows -------------------------

def test_room_summary_rows_returns_one_row_per_room():
    rows = room_summary_rows(_toy_consensus(), pt_to_m=PT_TO_M_DEFAULT)
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"SALA", "COZINHA"}
    sala = next(r for r in rows if r["name"] == "SALA")
    assert sala["polygon_verts"] == 4
    assert sala["openings_touching"] == 1
    assert sala["area_m2"] > 0


def test_opening_summary_rows_returns_one_row_per_opening():
    rows = opening_summary_rows(_toy_consensus())
    assert len(rows) == 1
    op = rows[0]
    assert op["kind"] == "interior_door"
    assert op["decision"] == "clean"
    assert op["room_left"] == "SALA"
    assert op["room_right"] == "COZINHA"
    assert op["host_wall"] == "w4"


# ---- PDF underlay (Cycle 12b) ----------------------------------------

def _toy_underlay() -> PdfUnderlay:
    """Hand-crafted PdfUnderlay so the renderer tests stay free of
    pypdfium2 + filesystem (the helper itself is exercised by the
    real-PDF smoke test below)."""
    # 1x1 transparent PNG, base64-encoded
    transparent_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
        "QVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    return PdfUnderlay(
        data_url=f"data:image/png;base64,{transparent_png}",
        page_w_pt=595.0,
        page_h_pt=842.0,
        opacity=0.55,
    )


def test_render_overlay_with_pdf_underlay_emits_image():
    """When a PdfUnderlay is supplied, the SVG must include the
    raster <image> element with the page bounds and the data URL."""
    svg = render_overlay_svg(_toy_consensus(), pdf_underlay=_toy_underlay())
    assert "<image " in svg
    assert "data:image/png;base64," in svg
    # Page bounds applied as image dimensions
    assert 'width="595.00"' in svg
    assert 'height="842.00"' in svg
    # opacity passed through
    assert 'opacity="0.55"' in svg


def test_render_overlay_without_pdf_underlay_omits_image():
    """Default path is unchanged — no `<image>` when no underlay."""
    svg = render_overlay_svg(_toy_consensus())
    assert "<image " not in svg
    assert "data:image/png;base64," not in svg


def test_render_overlay_pdf_underlay_overrides_viewbox():
    """When the underlay is on, the viewBox must be the PDF page
    bounds (0 0 page_w page_h), NOT the auto-fit bounds of the
    consensus polygons. This guarantees the bitmap and the vector
    overlay share the same coord system."""
    svg = render_overlay_svg(_toy_consensus(), pdf_underlay=_toy_underlay())
    assert 'viewBox="0.00 0.00 595.00 842.00"' in svg
    # And the y-flip group reflects the page-height anchor:
    # translate(0 {y0+y1}) scale(1 -1) where y0=0, y1=842
    assert 'transform="translate(0 842.0) scale(1 -1)"' in svg


def test_pdf_page_to_data_url_returns_png_data_uri(tmp_path):
    """Round-trip the helper against a real PDF candidate. Skip on
    stripped checkout. Asserts the data URL is well-formed and the
    page dims are positive."""
    candidates = [
        REPO_ROOT / "planta_74.pdf",
        REPO_ROOT / "runs" / "cycle11c" / "synth_l2.pdf",
    ]
    pdf_path = next((p for p in candidates if p.exists()), None)
    if pdf_path is None:
        pytest.skip("no PDF available to round-trip")
    underlay = pdf_page_to_data_url(pdf_path)
    assert underlay.data_url.startswith("data:image/png;base64,")
    assert underlay.page_w_pt > 0
    assert underlay.page_h_pt > 0
    # PNG decode sanity: base64 payload must decode without error
    import base64
    payload = underlay.data_url.split(",", 1)[1]
    raw = base64.b64decode(payload)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "data URL is not a PNG"


# ---- Expected-model overlay (Cycle 12d) ------------------------------

def _toy_expected_model() -> dict:
    """Two expected rooms: SALA (matches observed area), COZINHA
    (observed area is below expected_min so should be flagged
    out_of_range_low). One PHANTOM expected room with no observed
    counterpart (should appear as missing_polygon)."""
    return {
        "schema_version": "1.0",
        "rooms": [
            # _toy_consensus has SALA at 5000 pts^2.
            # 5000 * (0.19/5.4)^2 = 5000 * 0.001238 = 6.19 m^2.
            # Pick a range that contains 6.19 → in_range.
            {"id": "sala", "label": "SALA",
             "expected_area_m2_range": [3.0, 12.0]},
            # COZINHA also at 5000 pts^2 = 6.19 m^2. Range starts at
            # 8 → out_of_range_low.
            {"id": "cozinha", "label": "COZINHA",
             "expected_area_m2_range": [8.0, 14.0]},
            # Phantom — no observed match.
            {"id": "lavabo_phantom", "label": "LAVABO",
             "expected_area_m2_range": [2.0, 5.0]},
        ],
    }


def test_expected_match_summary_categorizes_rooms():
    rows = expected_match_summary(_toy_consensus(), _toy_expected_model())
    by_label = {r["expected_label"] or r["observed_name"]: r for r in rows}
    assert by_label["SALA"]["status"] == "in_range"
    assert by_label["SALA"]["observed_id"] == "r0"
    assert by_label["COZINHA"]["status"] == "out_of_range_low"
    assert by_label["COZINHA"]["observed_id"] == "r1"
    assert by_label["LAVABO"]["status"] == "missing_polygon"
    assert by_label["LAVABO"]["observed_id"] is None
    # 3 expected rooms; 0 unmatched_observed (both observed rooms
    # are in the expected list)
    assert len(rows) == 3


def test_expected_match_summary_returns_empty_without_expected_model():
    assert expected_match_summary(_toy_consensus(), None) == []
    assert expected_match_summary(_toy_consensus(), {}) == []


def test_render_overlay_with_gt_toggle_recolors_room_outlines():
    """When ground_truth_overlay is ON and expected_model has data,
    each observed room gets a thicker outline in the status color
    instead of the default '#7a7a7a' grey."""
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(ground_truth_overlay=True),
        expected_model=_toy_expected_model(),
    )
    # Status colors must appear as outline strokes
    assert 'stroke="#16a34a"' in svg, "in_range green not present"
    assert 'stroke="#f59e0b"' in svg, "out_of_range_low orange not present"
    # Outline thickened to 2.0
    assert 'stroke-width="2.0"' in svg


def test_render_overlay_with_gt_toggle_off_keeps_default_outlines():
    """Default toggle is off — the SVG must stay byte-equivalent to
    the baseline path even if `expected_model` is supplied."""
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(ground_truth_overlay=False),
        expected_model=_toy_expected_model(),
    )
    # Status palette colors must NOT appear
    assert 'stroke="#16a34a"' not in svg
    assert 'stroke="#f59e0b"' not in svg
    # Default room stroke present
    assert 'stroke="#7a7a7a"' in svg


# ---- Hover highlight (Cycle 12c) -------------------------------------

def test_render_overlay_emits_hover_style_block():
    """The SVG must include the inline `<style>` block that defines
    `.hover-room:hover` and `.hover-opening:hover` so browsers (and
    GitHub's inline SVG renderer) get hover feedback for free."""
    svg = render_overlay_svg(_toy_consensus())
    assert "<style>" in svg
    assert ".hover-room:hover" in svg
    assert ".hover-opening:hover" in svg


def test_render_overlay_emits_title_per_room():
    """Each rendered room polygon carries a `<title>` child with the
    room name, area, and id — browsers show this as a native
    tooltip on hover, no JS needed."""
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(walls=False, rooms=True, labels=False,
                                 openings=False),
    )
    assert "<title>SALA · " in svg
    assert "<title>COZINHA · " in svg
    # Tooltip carries the m² annotation + id
    assert "m² · id=" in svg
    # And the polygon class is applied so CSS hover fires
    assert 'class="hover-room"' in svg


def test_render_overlay_emits_title_per_opening():
    """Each opening circle carries a `<title>` with kind + decision
    + room context (room_left ↔ room_right) + id."""
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(walls=False, rooms=False, labels=False,
                                 openings=True),
    )
    # Toy fixture has one interior_door between SALA and COZINHA
    assert "<title>interior_door · decision=clean · SALA ↔ COZINHA" in svg
    assert 'class="hover-opening"' in svg


def test_render_overlay_title_text_xml_escaped():
    """Tooltip text MUST be XML-escaped so a room name containing
    `<`, `>`, or `&` doesn't break the SVG. Mirrors the existing
    label-escape contract."""
    c = _toy_consensus()
    c["rooms"][0]["name"] = "<bad> & evil"
    svg = render_overlay_svg(c)
    # Raw `<bad>` must NOT slip through (it would terminate the title
    # element and inject markup). Note: the renderer does NOT
    # uppercase the tooltip text — names pass through as-is.
    assert "<title><bad>" not in svg
    assert "<title>&lt;bad&gt; &amp; evil ·" in svg


# ---- Diff view (Cycle 12e) -------------------------------------------

def _toy_consensus_b() -> dict:
    """Variant of `_toy_consensus`: SALA shifted slightly + COZINHA
    enlarged + a brand-new BANHO room. Used to exercise the diff
    overlay (matched / only_in_a / only_in_b paths)."""
    base = _toy_consensus()
    base["rooms"] = [
        # SALA shifted x+10
        {"id": "rb0", "name": "SALA",
         "polygon_pts": [[10, 0], [60, 0], [60, 100], [10, 100]],
         "area_pts2": 5000},
        # COZINHA wider — area_pts2 is bigger
        {"id": "rb1", "name": "COZINHA",
         "polygon_pts": [[50, 0], [120, 0], [120, 100], [50, 100]],
         "area_pts2": 7000},
        # New room only in B
        {"id": "rb2", "name": "BANHO",
         "polygon_pts": [[0, 100], [50, 100], [50, 150], [0, 150]],
         "area_pts2": 2500},
    ]
    return base


def test_render_overlay_with_diff_overlay_emits_dashed_polygons():
    """When `consensus_b` is provided AND `diff_overlay=True`, the
    SVG must include `<polygon ... stroke-dasharray="3,2" ...>` for
    each B room — drawn over the A render."""
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(diff_overlay=True),
        consensus_b=_toy_consensus_b(),
    )
    assert 'stroke-dasharray="3,2"' in svg
    # Magenta is the diff stroke color
    assert 'stroke="#c026d3"' in svg
    # B has 3 rooms → 3 dashed polygons (one per room)
    assert svg.count('stroke-dasharray="3,2"') == 3


def test_render_overlay_diff_overlay_off_omits_dashed():
    """Default toggle is off; even if `consensus_b` is supplied the
    SVG must stay byte-equivalent to the no-diff path."""
    svg = render_overlay_svg(
        _toy_consensus(),
        toggles=OverlayToggles(diff_overlay=False),
        consensus_b=_toy_consensus_b(),
    )
    assert 'stroke-dasharray="3,2"' not in svg
    assert 'stroke="#c026d3"' not in svg


def test_diff_summary_categorises_matched_and_unique_rooms():
    rows = diff_summary(_toy_consensus(), _toy_consensus_b())
    by_name = {r["name"]: r for r in rows}
    # 3 rooms total: SALA, COZINHA (matched) + BANHO (only_in_b)
    assert set(by_name.keys()) == {"SALA", "COZINHA", "BANHO"}
    assert by_name["SALA"]["status"] == "matched"
    assert by_name["SALA"]["in_a"] and by_name["SALA"]["in_b"]
    # Both have area_pts2 = 5000, same PT_TO_M → delta = 0
    assert by_name["SALA"]["delta_m2"] == 0.0
    assert by_name["COZINHA"]["status"] == "matched"
    # B's COZINHA is bigger (7000 vs 5000 pts^2) → positive delta
    assert by_name["COZINHA"]["delta_m2"] > 0
    assert by_name["BANHO"]["status"] == "only_in_b"
    assert by_name["BANHO"]["in_b"] and not by_name["BANHO"]["in_a"]
    assert by_name["BANHO"]["delta_m2"] is None


def test_diff_summary_handles_only_in_a_rooms():
    """When B is missing a room that A has, status is `only_in_a`."""
    a = _toy_consensus()
    b = {"rooms": [a["rooms"][0]]}  # only SALA
    rows = diff_summary(a, b)
    by_name = {r["name"]: r for r in rows}
    assert by_name["COZINHA"]["status"] == "only_in_a"
    assert by_name["COZINHA"]["in_a"] and not by_name["COZINHA"]["in_b"]
    assert by_name["COZINHA"]["delta_m2"] is None


# ---- Real consensus smoke test (skip if missing) ----------------------

# ---- overrides_view annotation (Cycle 12h) ---------------------------

def _toy_overrides_view_room_label() -> dict:
    """Apply-view shape that flips room `r1` (COZINHA → KITCHEN) via
    a `room_label_override`. Mirrors what
    `cockpit.overrides.overrides_apply_view` produces."""
    return {
        "schema_version": "review_overrides_view_v1",
        "rooms": [
            {"id": "r0", "name": "SALA", "source": "detected"},
            {
                "id": "r1",
                "name": "KITCHEN",
                "_name_original": "COZINHA",
                "source": "manual",
            },
        ],
        "openings": [
            {"id": "o0", "source": "detected"},
        ],
    }


def _toy_overrides_view_opening_kind() -> dict:
    """Apply-view shape that flips opening `o0`'s kind_v5 via an
    `opening_kind_override` and rejects opening `o0` (use only one
    of these in the same test, but the helper covers both)."""
    return {
        "schema_version": "review_overrides_view_v1",
        "rooms": [
            {"id": "r0", "name": "SALA", "source": "detected"},
            {"id": "r1", "name": "COZINHA", "source": "detected"},
        ],
        "openings": [
            {
                "id": "o0",
                "kind_v5": "window",
                "_kind_v5_original": "interior_door",
                "source": "manual",
            },
        ],
    }


def test_render_overlay_with_overrides_view_annotates_title():
    """When `overrides_view` is supplied, room/opening tooltips gain
    a ` · override (...)` suffix listing the active override
    short-name. Default v1.x tooltip text remains intact.

    Note: the renderer reads room/opening field values (name, kind)
    from the source `consensus`, not from `overrides_view`. The view
    is consulted purely to look up the override status by id and
    append the annotation suffix. Apply-time rewriting of values
    is the job of `tools/apply_overrides.py` (Slice 3).
    """
    svg = render_overlay_svg(
        _toy_consensus(),
        overrides_view=_toy_overrides_view_room_label(),
    )
    # COZINHA's tooltip carries the original (consensus-side) name
    # AND picks up the `override (label)` annotation suffix.
    cozinha_chunk = (
        svg.split("<title>COZINHA · ", 1)[1].split("</title>", 1)[0]
    )
    assert "override (label)" in cozinha_chunk
    # SALA was not overridden → no annotation, baseline tooltip only.
    assert "<title>SALA · " in svg
    sala_chunk = svg.split("<title>SALA · ", 1)[1].split("</title>", 1)[0]
    assert "override" not in sala_chunk, (
        "Room without an active override must not gain the suffix"
    )

    # Now an opening_kind_override on o0 → tooltip gains
    # `override (kind)` for the opening
    svg2 = render_overlay_svg(
        _toy_consensus(),
        overrides_view=_toy_overrides_view_opening_kind(),
    )
    # Opening tooltip carries the override annotation
    o0_chunk = (
        svg2.split("<title>interior_door · decision=clean · "
                   "SALA ↔ COZINHA · ", 1)[1]
            .split("</title>", 1)[0]
    )
    assert "override (kind)" in o0_chunk


def test_render_overlay_without_overrides_view_unchanged():
    """Default `overrides_view=None` is byte-equivalent to the v1.x
    renderer — no annotations leak into the SVG even when override
    short-names appear elsewhere in the toy fixture."""
    svg_default = render_overlay_svg(_toy_consensus())
    svg_explicit_none = render_overlay_svg(
        _toy_consensus(), overrides_view=None,
    )
    # Default-vs-explicit-None: identical bytes
    assert svg_default == svg_explicit_none

    # No ` · override` suffix anywhere
    assert " · override" not in svg_default
    # Existing v1.x tooltips still present (regression check on
    # Cycle 12c contract)
    assert "<title>SALA · " in svg_default
    assert "<title>COZINHA · " in svg_default
    assert ("<title>interior_door · decision=clean · "
            "SALA ↔ COZINHA · ") in svg_default


def test_render_overlay_on_planta_74_baseline_smoke():
    """Smoke: renderer produces a non-empty SVG on the canonical
    `planta_74` run dir if it exists. Skipped on stripped CI checkout."""
    canonical = (REPO_ROOT / "runs" / "feature_room_context_2026_05_06"
                 / "consensus_with_room_context.json")
    if not canonical.exists():
        pytest.skip("canonical planta_74 c3 missing")
    consensus = json.loads(canonical.read_text(encoding="utf-8"))
    svg = render_overlay_svg(consensus)
    assert svg.startswith("<svg ")
    assert svg.endswith("</svg>")
    # Must contain at least one of the planta_74 room names
    assert "SUITE" in svg or "SALA" in svg
