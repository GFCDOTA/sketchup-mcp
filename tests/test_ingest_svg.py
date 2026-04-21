from __future__ import annotations

from pathlib import Path

import pytest

from ingest.svg_service import IngestSvgError, ingest_svg


FIXTURE = Path(__file__).parent / "fixtures" / "svg" / "minimal_room.svg"


def test_parses_minimal_room() -> None:
    doc = ingest_svg(FIXTURE.read_bytes(), "minimal_room.svg")
    assert len(doc.walls) == 5
    assert doc.viewbox_width == 200.0
    assert doc.viewbox_height == 100.0
    assert doc.stroke_width_median == pytest.approx(6.25)
    assert 6.25 in doc.stroke_width_samples


def test_skips_curve_paths() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<path d="M 0,0 C 10,10 20,20 30,30" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'<path d="M 10,10 H 80" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'</svg>'
    )
    doc = ingest_svg(svg, "curve.svg")
    # Only the straight path should remain; the curve one is rejected wholesale.
    assert len(doc.walls) == 1
    assert doc.walls[0].orientation == "horizontal"


def test_filters_non_black_stroke() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<path d="M 10,10 H 80" '
        b'style="fill:none;stroke:#ff0000;stroke-width:6.25" />'
        b'<path d="M 10,20 H 80" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'</svg>'
    )
    doc = ingest_svg(svg, "color.svg")
    # Red path dropped, black path kept.
    assert len(doc.walls) == 1
    assert doc.walls[0].start[1] == 20.0


def test_filters_wrong_stroke_width() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<path d="M 10,10 H 80" '
        b'style="fill:none;stroke:#000000;stroke-width:3.0" />'
        b'<path d="M 10,20 H 80" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'</svg>'
    )
    doc = ingest_svg(svg, "width.svg")
    assert len(doc.walls) == 1
    assert doc.walls[0].start[1] == 20.0


def test_transform_flattening() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">'
        b'<g transform="translate(100,50)">'
        b'<path d="M 10,10 H 90" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'</g>'
        b'</svg>'
    )
    doc = ingest_svg(svg, "xform.svg")
    assert len(doc.walls) == 1
    wall = doc.walls[0]
    # translate(100,50) shifts the segment: x in [10..90] -> [110..190]; y=10 -> 60.
    assert wall.start == (110.0, 60.0)
    assert wall.end == (190.0, 60.0)


def test_raises_on_invalid_xml() -> None:
    with pytest.raises(IngestSvgError):
        ingest_svg(b"not xml", "x.svg")


def test_raises_on_missing_viewbox() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<path d="M 10,10 H 80" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'</svg>'
    )
    with pytest.raises(IngestSvgError):
        ingest_svg(svg, "no_vb.svg")


def test_raises_when_no_walls() -> None:
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<path d="M 0,0 C 10,10 20,20 30,30" '
        b'style="fill:none;stroke:#000000;stroke-width:6.25" />'
        b'</svg>'
    )
    with pytest.raises(IngestSvgError):
        ingest_svg(svg, "curves_only.svg")
