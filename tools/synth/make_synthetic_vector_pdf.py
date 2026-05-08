"""make_synthetic_vector_pdf.py — zero-dep vector PDF generator
for round-trip testing the planta extraction pipeline.

Why this exists (Cycle 11c, 2026-05-08):

`tools/fidelity/synth_from_expected.py` (Cycle 12) round-trips a
manual `expected_model.json` THROUGH the fidelity engine — it
never exercises the real extraction pipeline. So a bug between
the PDF parser and the consensus could pass the engine self-check
unnoticed. This module fills that gap: it generates a real
PDF-1.4 file (filled-rectangle walls + text labels) that the
existing `tools.build_vector_consensus` accepts as a vector PDF.
A test then runs the full 5-stage pipeline against the synth PDF
and verifies the extracted consensus matches what was intended.

Constraints:
- ZERO new project dependency. Hand-rolls PDF objects + content
  stream from spec (PDF 1.4). Uses only stdlib.
- Output is a SMALL planta_74-style 2-room L-shape with one door
  + 2 labels. Big enough to exercise wall + room + opening +
  classifier paths; small enough that round-trip stays under a
  second.
- Walls are FILLED rectangles (matches what
  `tools/build_vector_consensus.py:_identify_wall_paths`
  expects: `fillmode != 0 and stroke_on == 0`).
- Labels are real PDF text using the standard Type 1 base font
  Helvetica (no embedded font file needed).

Boundary:
- Does NOT generate openings (door arcs / wall gaps) on its own.
  An "opening" in this synthetic PDF is a *wall gap* — i.e. a
  break in the wall row achieved by leaving a 1-2 wall-thickness
  gap between two filled rectangles. The pipeline's
  `--detect-wall-gaps` flag picks that up. No Bezier arcs.
- Does NOT generate soft_barriers (peitoris). Skip.
- Does NOT model real m^2 — synth's purpose is structural, not
  metric. PT_TO_M is conservative-default.

Public API:
- ``write_pdf(spec: dict, out_path: pathlib.Path) -> None``
  - ``spec``: see ``EXAMPLE_SPEC_2_ROOM_L`` for the schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


# ---------- Spec dataclasses (the "input") ---------------------------

@dataclass(frozen=True)
class WallRect:
    """A wall represented as a filled rectangle in PDF user space.

    All coordinates in PDF points (1/72 inch). The wall is *filled*
    only — never stroked — to match the pipeline's wall detector.
    """
    x: float  # bottom-left x
    y: float  # bottom-left y
    w: float  # width
    h: float  # height


@dataclass(frozen=True)
class TextLabel:
    """A room seed label (e.g. 'COZINHA') placed in PDF user space."""
    text: str
    x: float  # text origin (baseline left)
    y: float
    size_pt: float = 10.0


# ---------- Example spec ---------------------------------------------

# A 2-room L-shape, ~10x6 wall units. Walls are 6 pt thick (matches
# planta_74's wall_thickness ~5.4 pt; rounded up for a hair more
# stability against the detector's median-thickness clustering).
#
# Layout (bottom-left origin, PDF y-up):
#
#                  +------------------+    y=200
#                  | room_a (right)   |
#                  |    [SUITE]       |
#  +---------------+--------+         |
#  |   room_b      DOOR     |         |
#  |   (left)      | dummy  |         |
#  | [SALA DE...]  +--------+---------+    y=100
#  |                                  |
#  +----------------------------------+    y=20
#  x=20                            x=520
#
# The door is a wall-gap: two L-shaped wall stubs flanking a 30-pt
# opening on the dividing wall. Pipeline's --detect-wall-gaps will
# pick it up.

T = 6.0  # wall thickness pt
EXAMPLE_SPEC_2_ROOM_L = {
    "page_w": 600.0,
    "page_h": 240.0,
    "walls": [
        # outer rectangle (4 walls)
        WallRect(20, 20, 500, T),                   # bottom
        WallRect(20, 200 - T, 500, T),              # top-right segment
        WallRect(20, 100 - T, 200, T),              # top of left wing
        WallRect(20, 20, T, 80),                    # left of left wing (low)
        WallRect(20, 100, T, 100),                  # left of right wing (high)
        WallRect(520 - T, 20, T, 180),              # right side
        # ridge wall between left wing top and right wing bottom
        # (the L shoulder; goes from 220 to 220+? actually closes the
        # L's notch: from (220, 100) to (220, 200))
        WallRect(220 - T / 2, 100 - T, T, 100 + T), # vertical between rooms
        # divider with door gap (horizontal between rooms at x=20 to 220).
        # Cycle 11d: gap widened to 50 pt (was 20 pt, below
        # DEFAULT_GAP_MIN_PTS=30 in tools/detect_wall_gaps.py so the
        # detector silently dropped it). Now 130..180 = 50 pt — well
        # within the [30, 250] band that the wall-gap detector
        # accepts as a door-shaped opening.
        WallRect(20, 100 - T, 110, T),               # left stub  (x: 20..130)
        WallRect(180, 100 - T, 40, T),               # right stub (x: 180..220)
    ],
    "labels": [
        TextLabel("SALA SYNTH", x=80, y=60),         # in left/lower room (room_b)
        TextLabel("SUITE SYNTH", x=320, y=140),      # in right room (room_a)
    ],
    # Companion expected_counts the test will compare against.
    "expected_counts": {
        "walls_min": 7,         # detector may merge / dedupe
        "rooms": 2,
        "openings_min": 0,      # wall_gap may or may not get carved
        "openings_max": 2,
    },
}


# ---------- PDF writer (hand-rolled PDF 1.4) -------------------------

def _content_stream(walls: Sequence[WallRect],
                     labels: Sequence[TextLabel]) -> bytes:
    """Build the page-content stream. Walls = filled rectangles
    (`re` + `f`); labels = text in Helvetica."""
    parts: list[str] = ["q"]
    # Black fill color for walls.
    parts.append("0 0 0 rg")
    for w in walls:
        # `x y w h re` then `f` to fill without stroke.
        parts.append(f"{w.x:.3f} {w.y:.3f} {w.w:.3f} {w.h:.3f} re")
        parts.append("f")
    # Text labels: Helvetica via Tf, Td, Tj.
    for lbl in labels:
        parts.append("BT")
        parts.append(f"/F1 {lbl.size_pt:.3f} Tf")
        parts.append(f"{lbl.x:.3f} {lbl.y:.3f} Td")
        # Escape ()\\ in text per PDF spec.
        safe = (lbl.text.replace("\\", "\\\\")
                          .replace("(", "\\(")
                          .replace(")", "\\)"))
        parts.append(f"({safe}) Tj")
        parts.append("ET")
    parts.append("Q")
    return ("\n".join(parts) + "\n").encode("latin-1")


def _pdf_obj(num: int, body: bytes) -> bytes:
    return f"{num} 0 obj\n".encode() + body + b"\nendobj\n"


def _pdf_dict(d: dict) -> bytes:
    parts = ["<<"]
    for k, v in d.items():
        parts.append(f"/{k} {v}")
    parts.append(">>")
    return ("\n".join(parts)).encode("latin-1")


def write_pdf(spec: dict, out_path: Path) -> None:
    """Write a vector PDF for ``spec`` to ``out_path``.

    The output is PDF 1.4 with one page containing filled-rectangle
    walls and Helvetica text labels. ``spec`` must contain
    ``page_w``, ``page_h``, ``walls`` (list of WallRect), and
    ``labels`` (list of TextLabel).
    """
    page_w = float(spec["page_w"])
    page_h = float(spec["page_h"])
    walls = list(spec["walls"])
    labels = list(spec["labels"])

    content = _content_stream(walls, labels)

    # Object 1: Catalog
    obj1 = _pdf_dict({"Type": "/Catalog", "Pages": "2 0 R"})
    # Object 2: Pages
    obj2 = _pdf_dict({"Type": "/Pages", "Kids": "[3 0 R]", "Count": "1"})
    # Object 3: Page
    obj3 = _pdf_dict({
        "Type": "/Page",
        "Parent": "2 0 R",
        "MediaBox": f"[0 0 {page_w:.3f} {page_h:.3f}]",
        "Contents": "4 0 R",
        "Resources": "<< /Font << /F1 5 0 R >> >>",
    })
    # Object 4: Content stream
    obj4 = (b"<< /Length " + str(len(content)).encode() + b" >>\n"
             b"stream\n" + content + b"endstream")
    # Object 5: Helvetica font (Type 1, base14)
    obj5 = _pdf_dict({
        "Type": "/Font",
        "Subtype": "/Type1",
        "BaseFont": "/Helvetica",
        "Encoding": "/WinAnsiEncoding",
    })

    objects = [obj1, obj2, obj3, obj4, obj5]
    out = bytearray()
    out += b"%PDF-1.4\n"
    out += b"%\xe2\xe3\xcf\xd3\n"  # binary marker so PDF readers detect binary mode
    offsets: list[int] = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += _pdf_obj(i, body)

    # xref + trailer
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n"
    out += _pdf_dict({"Size": str(len(objects) + 1), "Root": "1 0 R"})
    out += b"\nstartxref\n"
    out += f"{xref_pos}\n".encode()
    out += b"%%EOF\n"

    out_path.write_bytes(bytes(out))


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Generate a synthetic vector PDF for round-trip "
        "testing the planta extraction pipeline."
    )
    ap.add_argument("--out", type=Path, required=True,
                     help="output PDF path")
    ap.add_argument("--spec", choices=["l2"], default="l2",
                     help="which built-in spec to render (default: l2 "
                          "= 2-room L-shape)")
    args = ap.parse_args(argv)
    spec = EXAMPLE_SPEC_2_ROOM_L if args.spec == "l2" else None
    if spec is None:
        raise SystemExit(f"unknown spec: {args.spec}")
    write_pdf(spec, args.out)
    print(f"[ok] wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
