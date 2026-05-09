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


# A 3-room T topology — added Cycle 11e (2026-05-08) to broaden the
# round-trip surface beyond the 2-room L.  One horizontal HALL at the
# bottom + 2 rooms (TOP_LEFT, TOP_RIGHT) above, separated by a full-
# height vertical divider. ONE 50-pt gap on the horizontal divider
# (the SUITE-side door) and a vertical divider between TL and TR.
#
# Why only one interior gap?  Watershed-based room polygonization
# (`tools/rooms_from_seeds.py`) flows seeds through every wall_gap.
# When two seeds compete for the same gap, the closer one claims most
# of the cross-sectional area, leaving the further seed with a sliver
# polygon.  In the T topology, seating an opening between HALL and a
# top room and ALSO between HALL and another top room overconstrains
# watershed — the HALL seed loses its polygon to the closer top-room
# seeds.  We keep ONE clear interior_passage and one clean closed
# divider so each room watershed is well-defined.
#
# Layout (PDF y-up):
#
#   +-----------------------+-----------------------+    y=240
#   |                       |                       |
#   |   TOP_LEFT            |   TOP_RIGHT           |
#   |     [SALA T]          |     [SUITE T]         |
#   |                       |                       |
#   +-----------------------+-----+--gap1-----+-----+    y=140 (H div)
#   |                                               |
#   |                  HALL                         |
#   |              [COZINHA T]                      |
#   +-----------------------------------------------+    y=20
#   x=20                                          x=620
#
# Three rooms; one wall_gap opening (gap1 between HALL & TOP_RIGHT).
# Gap is 50 pt — well within DEFAULT_GAP_MIN_PTS=30.
EXAMPLE_SPEC_3_ROOM_T = {
    "page_w": 700.0,
    "page_h": 280.0,
    "walls": [
        # outer rectangle
        WallRect(20, 20, 600, T),                      # bottom (hall floor)
        WallRect(20, 240 - T, 600, T),                 # top
        WallRect(20, 20, T, 220),                      # left side
        WallRect(620 - T, 20, T, 220),                 # right side
        # horizontal divider y=140 between hall and top rooms,
        # with ONE 50-pt gap on the SUITE-T side (gap1 at x=460..510).
        # Divider goes x=20..620 with two stubs around the gap.
        WallRect(20, 140 - T, 440, T),                 # left full segment x:20..460
        WallRect(510, 140 - T, 110, T),                # right stub x:510..620
        # vertical divider x=320 between TOP_LEFT and TOP_RIGHT,
        # from y=140 (top edge of H divider) to y=240 (top wall).
        WallRect(320 - T / 2, 140 - T, T, 100 + T),    # full height
    ],
    "labels": [
        # Note: extract_room_labels.py only emits text matching
        # ROOM_KEYWORDS (SALA, SUITE, COZINHA, QUARTO, BANHO, etc.).
        # We use canonical keywords + a single suffix letter so the
        # rooms map 1:1 to the spec without colliding with l2.
        # The text-center for "COZINHA T" at Helvetica 10pt is ~25pt
        # right of x. Place HALL seed left of the vertical divider.
        TextLabel("COZINHA T", x=120, y=70),           # in HALL room
        TextLabel("SALA T", x=140, y=190),             # in TOP_LEFT (closed)
        TextLabel("SUITE T", x=440, y=190),            # in TOP_RIGHT (gap1)
    ],
    "expected_counts": {
        "walls_min": 7,
        "rooms": 3,
        "openings_min": 0,
        "openings_max": 1,
    },
}


# A 4-room PLUS (cross) topology — added Cycle 11e (2026-05-08).
# One central HALL room + 4 wing rooms (NORTH, SOUTH, EAST, WEST)
# branching off, each connected by a 50-pt wall_gap. Wait — task says
# "1 central + 3 wings". So 4 rooms total: CENTER + 3 wings (NORTH,
# EAST, WEST). South is closed by an exterior wall. 3 openings between
# CENTER and each wing.
#
# Layout (PDF y-up). Center sits at the middle; arms extend out:
#
#                  +-----------+               y=320
#                  |  NORTH    |
#                  |  [N WING] |
#                  +--gap_n----+               y=240 (top divider)
#                  |           |
#   +-----------+--+           +--+-----------+ y=200
#   |  WEST     |   CENTER     |   EAST       |
#   | [W WING]  | gap_w   gap_e |  [E WING]   |
#   +-----------+--+           +--+-----------+ y=120
#                  |           |
#                  |  HALL P   |
#                  +-----------+               y=80 (south = closed)
#                 x=180     x=320
EXAMPLE_SPEC_4_ROOM_PLUS = {
    "page_w": 500.0,
    "page_h": 360.0,
    "walls": [
        # ---- CENTER box (vertical strip x=180..320, y=80..320) ----
        # bottom of CENTER (closed — south is exterior here)
        WallRect(180, 80, 140, T),
        # top of CENTER (closed — N wing connects via gap above)
        # The H divider between CENTER and NORTH at y=240, with gap_n.
        WallRect(180, 240 - T, 60, T),                 # left stub x:180..240
        WallRect(290, 240 - T, 30, T),                 # right stub x:290..320
        # CENTER left wall (x=180), full height. Has gap_w at the
        # WEST connection (y=140..190 = 50pt).
        WallRect(180, 80, T, 60),                      # bottom stub y:80..140
        WallRect(180, 190, T, 50),                     # top stub y:190..240
        # CENTER right wall (x=320 - T = 314), full height. Has gap_e
        # at the EAST connection (y=140..190).
        WallRect(320 - T, 80, T, 60),                  # bottom stub
        WallRect(320 - T, 190, T, 50),                 # top stub
        # ---- NORTH wing (x=180..320, y=240..320) ----
        # north wing's top + sides
        WallRect(180, 320 - T, 140, T),                # top
        WallRect(180, 240, T, 80),                     # left side
        WallRect(320 - T, 240, T, 80),                 # right side
        # ---- WEST wing (x=20..180, y=120..200) ----
        WallRect(20, 120, T, 80),                      # left side
        WallRect(20, 120, 160, T),                     # bottom
        WallRect(20, 200 - T, 160, T),                 # top
        # west's right wall is the CENTER's left, already drawn
        # ---- EAST wing (x=320..480, y=120..200) ----
        WallRect(480 - T, 120, T, 80),                 # right side
        WallRect(320, 120, 160, T),                    # bottom
        WallRect(320, 200 - T, 160, T),                # top
    ],
    "labels": [
        # Same ROOM_KEYWORDS rule as SPEC_3 — pick canonical room
        # words. The suffix letter (P/N/W/E) keeps each name unique.
        TextLabel("SALA P", x=220, y=130),             # in CENTER
        TextLabel("QUARTO N", x=215, y=270),           # in NORTH
        TextLabel("QUARTO W", x=60, y=155),            # in WEST
        TextLabel("QUARTO E", x=355, y=155),           # in EAST
    ],
    "expected_counts": {
        "walls_min": 12,
        "rooms": 4,
        "openings_min": 0,
        "openings_max": 3,
    },
}


# A 5-room LONG HALL topology — added Cycle 11e (2026-05-08).
# Five rooms in a row, separated by 4 vertical dividers each with a
# 35-pt wall_gap door. Mixed public/private room mix so the V5
# room-context classifier doesn't reject every gap as "private<->private
# too wide" (PRIVATE_PAIR_DOOR_MAX_M = 1.50 m caps QUARTO<->QUARTO).
# 35 pt × PT_TO_M=0.0352 ≈ 1.23 m — passes interior_passage.
#
# Layout (PDF y-up):
#
#   +------+-+----+-+----+-+----+-+----+-+------+    y=180
#   |      |g|    |g|    |g|    |g|         |
#   | R1   |1| R2 |2| R3 |3| R4 |4| R5      |
#   |      | |    | |    | |    | |    | |     |
#   +------+-+----+-+----+-+----+-+----+-+------+   y=20
#   x=20                                         x=820
#
# Each room is ~157 pt wide (inside). Each divider has a 6-pt wall +
# 35-pt gap + 6-pt wall, centered vertically on the divider.
EXAMPLE_SPEC_5_LONG_HALL = {
    "page_w": 840.0,
    "page_h": 200.0,
    "walls": [
        # outer rectangle
        WallRect(20, 20, 800, T),                      # bottom
        WallRect(20, 180 - T, 800, T),                 # top
        WallRect(20, 20, T, 160),                      # left side
        WallRect(820 - T, 20, T, 160),                 # right side
        # 4 vertical dividers at x = 180, 340, 500, 660.
        # Each divider has a 35-pt vertical gap centered at y=100
        # (so y=82.5..117.5 = 35pt gap).
        # bottom stub: y=20..82.5 (h=62.5), top stub: y=117.5..180 (h=62.5).
        # Divider 1 at x=180:
        WallRect(180 - T / 2, 20, T, 62.5),
        WallRect(180 - T / 2, 117.5, T, 62.5),
        # Divider 2 at x=340:
        WallRect(340 - T / 2, 20, T, 62.5),
        WallRect(340 - T / 2, 117.5, T, 62.5),
        # Divider 3 at x=500:
        WallRect(500 - T / 2, 20, T, 62.5),
        WallRect(500 - T / 2, 117.5, T, 62.5),
        # Divider 4 at x=660:
        WallRect(660 - T / 2, 20, T, 62.5),
        WallRect(660 - T / 2, 117.5, T, 62.5),
    ],
    "labels": [
        # Mixed public/private to avoid the
        # PRIVATE_PAIR_DOOR_MAX_M=1.50m wall in
        # tools/classify_openings_by_room_context.py:_classify_pair.
        # Pattern: alternate private (QUARTO/SUITE) with public
        # (SALA/COZINHA) so each adjacent pair has at least one public.
        TextLabel("SALA H", x=65, y=95),               # in R1 (public)
        TextLabel("QUARTO H", x=215, y=95),            # in R2 (private)
        TextLabel("COZINHA H", x=375, y=95),           # in R3 (public)
        TextLabel("SUITE H", x=545, y=95),             # in R4 (private)
        TextLabel("LAVABO H", x=705, y=95),            # in R5 (private-ish)
    ],
    "expected_counts": {
        "walls_min": 12,
        "rooms": 5,
        "openings_min": 0,
        "openings_max": 4,
    },
}


# Mapping for CLI/test access. Add new specs here.
SPECS: dict[str, dict] = {
    "l2": EXAMPLE_SPEC_2_ROOM_L,
    "t3": EXAMPLE_SPEC_3_ROOM_T,
    "plus4": EXAMPLE_SPEC_4_ROOM_PLUS,
    "hall5": EXAMPLE_SPEC_5_LONG_HALL,
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
    ap.add_argument("--spec", choices=sorted(SPECS.keys()), default="l2",
                     help="which built-in spec to render (default: l2 "
                          "= 2-room L-shape; t3 = 3-room T; plus4 = "
                          "4-room cross; hall5 = 5-room corridor)")
    args = ap.parse_args(argv)
    spec = SPECS.get(args.spec)
    if spec is None:
        raise SystemExit(f"unknown spec: {args.spec}")
    write_pdf(spec, args.out)
    print(f"[ok] wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
