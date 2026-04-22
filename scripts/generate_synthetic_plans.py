"""Generate synthetic architectural floor plans as SVG + openings GT YAML.

Produces 7 diverse layouts to validate the SVG pipeline end-to-end without
over-fitting on ``planta_74m2.pdf``:

* ``studio``      - 3-room studio apartment (800x600)
* ``2br``         - 2 bedrooms + living + kitchen + bathroom (5 rooms, 800x600)
* ``3br``         - 3x3 grid-based layout with 3 bedrooms + 2 bathrooms (800x600)
* ``lshape``      - L-shaped apartment (4 rooms, irregular outer perimeter, 800x600)
* ``tiny``        - 2-room small plan (400x300), stress test small viewBox
* ``large``       - 10-room multi-bedroom apartment (1000x800), stress scale
* ``multistory``  - two-floor plan with disconnected components (800x1200)

Each layout emits two files in ``--out``:

* ``<name>.svg`` - parseable by ``ingest/svg_service.py::ingest_svg``
  (stroke #000000, stroke-width 6.25, axis-aligned paths only, per-layout
  viewBox recorded in ``LAYOUTS``).
* ``<name>_openings_gt.yaml`` - ground-truth openings with
  ``center``, ``width``, ``orientation`` and ``kind`` per entry.

Walls are *split* around each door/window/passage so the SVG contains
exactly the gaps the opening detector relies on. The generator owns both
wall layout and the opening spec, so the YAML is guaranteed consistent
with the emitted SVG.

The generator does not adapt to the pipeline (no thresholds tweaked to
make detection pass). Any mismatch between the GT list and the detector's
output is a signal about the detector, not the fixture.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import yaml


STROKE_COLOR = "#000000"
STROKE_WIDTH = 6.25  # match planta_74m2 stroke width range [6.0, 6.5]
VIEW_W = 800
VIEW_H = 600


@dataclass(frozen=True)
class Wall:
    """Axis-aligned wall segment in user-units."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def orientation(self) -> str:
        if self.y1 == self.y2:
            return "horizontal"
        if self.x1 == self.x2:
            return "vertical"
        raise ValueError(
            f"non-axis-aligned wall: ({self.x1},{self.y1})->({self.x2},{self.y2})"
        )

    @property
    def length(self) -> float:
        return abs(self.x2 - self.x1) + abs(self.y2 - self.y1)


@dataclass(frozen=True)
class Opening:
    """Ground-truth opening annotation (door/window/passage)."""
    id: str
    center: tuple[float, float]
    width: float
    orientation: str  # "horizontal" | "vertical"
    kind: str  # "door" | "window" | "passage"
    notes: str = ""


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _is_wall_horizontal(w: Wall) -> bool:
    return w.y1 == w.y2


@dataclass(frozen=True)
class _SplitResult:
    walls: list[Wall]
    applied: bool  # True when a gap was actually carved out
    touched: bool  # True when the opening landed on this wall (even if clipped to edge)


def _split_wall_at_opening(wall: Wall, opening: Opening) -> _SplitResult:
    """If `opening` intersects `wall`, carve a gap out of it.

    - Returns ``applied=True`` when the opening falls strictly inside the wall
      (two half-walls emitted, a detectable gap between them).
    - Returns ``applied=False, touched=True`` when the opening lies on the
      wall's line but abuts or crosses a wall endpoint (corner window):
      the wall is *trimmed* back to the edge of the gap instead of split in
      two. The SVG then carries a missing segment at the corner but no
      interior gap, which mirrors how a corner-adjacent window would
      actually look in a real plan.
    - Returns ``applied=False, touched=False`` when the opening is elsewhere
      and the wall is emitted unchanged.
    """
    cx, cy = opening.center
    half = opening.width / 2.0

    if _is_wall_horizontal(wall):
        if opening.orientation != "horizontal":
            return _SplitResult([wall], False, False)
        if abs(wall.y1 - cy) > 0.5:
            return _SplitResult([wall], False, False)
        x_min = min(wall.x1, wall.x2)
        x_max = max(wall.x1, wall.x2)
        gap_lo = cx - half
        gap_hi = cx + half
        # Opening must be within [x_min, x_max] horizontally; otherwise skip.
        if gap_hi <= x_min or gap_lo >= x_max:
            return _SplitResult([wall], False, False)
        if gap_lo > x_min and gap_hi < x_max:
            # Standard case: split.
            return _SplitResult(
                [
                    Wall(x_min, wall.y1, gap_lo, wall.y1),
                    Wall(gap_hi, wall.y1, x_max, wall.y1),
                ],
                True,
                True,
            )
        # Corner-abutting gap: trim the wall to what remains.
        left_piece = None if gap_lo <= x_min else Wall(x_min, wall.y1, gap_lo, wall.y1)
        right_piece = None if gap_hi >= x_max else Wall(gap_hi, wall.y1, x_max, wall.y1)
        remaining = [w for w in (left_piece, right_piece) if w is not None]
        return _SplitResult(remaining if remaining else [], False, True)

    # vertical wall
    if opening.orientation != "vertical":
        return _SplitResult([wall], False, False)
    if abs(wall.x1 - cx) > 0.5:
        return _SplitResult([wall], False, False)
    y_min = min(wall.y1, wall.y2)
    y_max = max(wall.y1, wall.y2)
    gap_lo = cy - half
    gap_hi = cy + half
    if gap_hi <= y_min or gap_lo >= y_max:
        return _SplitResult([wall], False, False)
    if gap_lo > y_min and gap_hi < y_max:
        return _SplitResult(
            [
                Wall(wall.x1, y_min, wall.x1, gap_lo),
                Wall(wall.x1, gap_hi, wall.x1, y_max),
            ],
            True,
            True,
        )
    top_piece = None if gap_lo <= y_min else Wall(wall.x1, y_min, wall.x1, gap_lo)
    bottom_piece = None if gap_hi >= y_max else Wall(wall.x1, gap_hi, wall.x1, y_max)
    remaining = [w for w in (top_piece, bottom_piece) if w is not None]
    return _SplitResult(remaining if remaining else [], False, True)


def _apply_openings(walls: list[Wall], openings: list[Opening]) -> list[Wall]:
    """Produce a new wall list with door/window/passage gaps cut out."""
    current = list(walls)
    for opening in openings:
        nxt: list[Wall] = []
        touched = False
        for w in current:
            result = _split_wall_at_opening(w, opening)
            if result.touched:
                touched = True
            nxt.extend(result.walls)
        if not touched and opening.kind != "passage":
            # A door or window in the GT that does not land on any wall is
            # almost always a fixture authoring bug (wrong coordinates).
            # Passages may legitimately sit in open space where no wall
            # exists.
            raise ValueError(
                f"opening {opening.id!r} (center={opening.center}) does "
                f"not lie on any wall; cannot cut a gap."
            )
        current = nxt
    return current


def _outer_rect(x1: float, y1: float, x2: float, y2: float) -> list[Wall]:
    return [
        Wall(x1, y1, x2, y1),  # top
        Wall(x2, y1, x2, y2),  # right
        Wall(x1, y2, x2, y2),  # bottom
        Wall(x1, y1, x1, y2),  # left
    ]


# ---------------------------------------------------------------------------
# layouts
# ---------------------------------------------------------------------------

def layout_studio() -> tuple[list[Wall], list[Opening]]:
    """Studio (3 rooms): bedroom+living, kitchen, bathroom."""
    walls: list[Wall] = []
    walls.extend(_outer_rect(50, 50, 750, 550))
    # horizontal wall y=300 from x=450 to x=750 (kitchen below, bedroom above)
    walls.append(Wall(450, 300, 750, 300))
    # vertical wall x=450 from y=300 to y=550 (bathroom separator)
    walls.append(Wall(450, 300, 450, 550))

    openings = [
        Opening(
            id="main_entrance",
            center=(150.0, 50.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="front door on top outer wall",
        ),
        Opening(
            id="bathroom_door",
            center=(450.0, 420.0),
            width=50.0,
            orientation="vertical",
            kind="door",
            notes="door between living and bathroom",
        ),
        Opening(
            id="window_bedroom",
            center=(640.0, 50.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="window on top outer wall, bedroom side (moved from 700 to avoid corner-snap collapse)",
        ),
    ]
    return walls, openings


def layout_2br() -> tuple[list[Wall], list[Opening]]:
    """2 bedrooms + central corridor + living + kitchen + bathroom (5-6 rooms)."""
    walls: list[Wall] = []
    walls.extend(_outer_rect(50, 50, 750, 550))
    # living/kitchen side of the corridor at y=300
    walls.append(Wall(50, 300, 400, 300))
    walls.append(Wall(450, 300, 750, 300))
    # corridor walls (two parallel verticals at x=400 and x=450)
    walls.append(Wall(400, 50, 400, 300))
    walls.append(Wall(450, 50, 450, 300))
    walls.append(Wall(400, 300, 400, 550))
    walls.append(Wall(450, 300, 450, 550))
    # divide the two bedrooms horizontally at y=170
    walls.append(Wall(50, 170, 400, 170))

    openings = [
        Opening(
            id="entrance",
            center=(150.0, 50.0),
            width=70.0,
            orientation="horizontal",
            kind="door",
            notes="front door to corridor",
        ),
        Opening(
            id="bedroom1_door",
            center=(400.0, 100.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        Opening(
            id="bedroom2_door",
            center=(400.0, 230.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        Opening(
            id="bathroom_door",
            center=(400.0, 420.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        Opening(
            id="kitchen_door",
            center=(450.0, 420.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        Opening(
            id="living_passage",
            center=(225.0, 300.0),
            width=70.0,
            orientation="horizontal",
            kind="passage",
            notes="wide living-to-corridor passage",
        ),
        Opening(
            id="corridor_cross",
            center=(425.0, 300.0),
            width=50.0,
            orientation="horizontal",
            kind="passage",
            notes="corridor threshold between upper and lower corridor halves (analogous to 3br.corridor_cross); the 50u gap at y=300 between the two vertical corridor walls x=400/x=450 is an architectural passage, not a spurious colinear gap",
        ),
        Opening(
            id="window_br1",
            center=(50.0, 140.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, bedroom 1",
        ),
        Opening(
            id="window_br2",
            center=(50.0, 260.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, bedroom 2",
        ),
    ]
    return walls, openings


def layout_3br() -> tuple[list[Wall], list[Opening]]:
    """3 bedrooms + 2 bathrooms + living + kitchen = 7 rooms in a 3x3 grid.

    Layout (800x600 canvas, outer rect 50..750 x 50..550):

      row 1 (y=50..220):  br1   | corridor | br2
      row 2 (y=220..390): bath1 | corridor | bath2
      row 3 (y=390..550): living| kitchen  |  kitchen (merged)

    Vertical corridor columns: x=340..420 and x=430..510 (split).
    Each room has at least 1 door. 2 external windows.

    Row dividers (y=220, y=390) cross the corridor as short stubs of
    length 35, leaving a 50-wide central gap at x=400. Those stubs anchor
    the two interior passages (corridor_cross, br3_passage) as detectable
    colinear gaps instead of empty-space virtual openings that the
    gap-based detector cannot see. Stub length is intentionally greater
    than the corner-snap tolerance (thickness*5 = 31.25) so
    _extend_to_perpendicular in the opening detector does not collapse
    the stubs onto the corridor verticals at x=340 / x=460.
    """
    # Cells: cols 50..340, 340..460 (corridor), 460..750. Rows: 50..220,
    # 220..390, 390..550.
    x_col1_end = 340.0
    x_col2_start = 460.0  # corridor walls at x=340 and x=460
    y_row1_end = 220.0
    y_row2_end = 390.0
    # Corridor stubs at row dividers: 35 long, leaving a 50-wide gap at x=400.
    stub_len = 35.0

    walls: list[Wall] = []
    walls.extend(_outer_rect(50, 50, 750, 550))
    # corridor left & right (x=340, x=460) from top to bottom
    walls.append(Wall(x_col1_end, 50, x_col1_end, 550))
    walls.append(Wall(x_col2_start, 50, x_col2_start, 550))
    # row divider y=220: main spans + corridor stubs (central 50-wide gap)
    walls.append(Wall(50, y_row1_end, x_col1_end, y_row1_end))
    walls.append(
        Wall(x_col1_end, y_row1_end, x_col1_end + stub_len, y_row1_end)
    )
    walls.append(
        Wall(x_col2_start - stub_len, y_row1_end, x_col2_start, y_row1_end)
    )
    walls.append(Wall(x_col2_start, y_row1_end, 750, y_row1_end))
    # row divider y=390: main spans + corridor stubs (central 50-wide gap)
    walls.append(Wall(50, y_row2_end, x_col1_end, y_row2_end))
    walls.append(
        Wall(x_col1_end, y_row2_end, x_col1_end + stub_len, y_row2_end)
    )
    walls.append(
        Wall(x_col2_start - stub_len, y_row2_end, x_col2_start, y_row2_end)
    )
    walls.append(Wall(x_col2_start, y_row2_end, 750, y_row2_end))

    openings = [
        # Front entrance onto the corridor from the bottom.
        Opening(
            id="entrance",
            center=(400.0, 550.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="front door opens onto corridor from bottom wall",
        ),
        # Bedroom 1 door (corridor side, left column, top row)
        Opening(
            id="br1_door",
            center=(x_col1_end, 135.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Bedroom 2 door (corridor side, right column, top row)
        Opening(
            id="br2_door",
            center=(x_col2_start, 135.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Bathroom 1 door (corridor side, left column, middle row)
        Opening(
            id="bath1_door",
            center=(x_col1_end, 305.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Bathroom 2 door (corridor side, right column, middle row)
        Opening(
            id="bath2_door",
            center=(x_col2_start, 305.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Living room door (corridor side, left column, bottom row)
        Opening(
            id="living_door",
            center=(x_col1_end, 470.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Kitchen door (corridor side, right column, bottom row)
        Opening(
            id="kitchen_door",
            center=(x_col2_start, 470.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Third bedroom / den sits mid-corridor — passage into corridor.
        # Width is the 50-wide central gap left by the row-divider stubs
        # at y=390 (see docstring: stubs 35 long on either side of x=400).
        Opening(
            id="br3_passage",
            center=(400.0, 390.0),
            width=50.0,
            orientation="horizontal",
            kind="passage",
            notes="passage from corridor to bottom-middle space (50-wide gap between y=390 row-divider stubs)",
        ),
        # Openings between the two bathrooms via the corridor (internal).
        # Same geometry as br3_passage but at y=220.
        Opening(
            id="corridor_cross",
            center=(400.0, 220.0),
            width=50.0,
            orientation="horizontal",
            kind="passage",
            notes="opening across corridor at row boundary (50-wide gap between y=220 row-divider stubs)",
        ),
        # External windows on side walls
        Opening(
            id="window_br1",
            center=(50.0, 135.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, bedroom 1",
        ),
        Opening(
            id="window_br2",
            center=(750.0, 135.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, bedroom 2",
        ),
        Opening(
            id="window_living",
            center=(150.0, 550.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="external window, living room",
        ),
    ]
    return walls, openings


def layout_lshape() -> tuple[list[Wall], list[Opening]]:
    """L-shaped apartment (4 rooms): living, bedroom, bathroom, laundry.

    Outer perimeter follows an L traced clockwise from (50,50):
      (50,50) -> (500,50) -> (500,350) -> (750,350) -> (750,550) -> (50,550) -> (50,50)
    """
    walls: list[Wall] = [
        # Outer L perimeter, split into the 6 axis-aligned segments.
        Wall(50, 50, 500, 50),     # top (upper arm)
        Wall(500, 50, 500, 350),   # right side of upper arm (inner corner)
        Wall(500, 350, 750, 350),  # top of lower arm
        Wall(750, 350, 750, 550),  # right side
        Wall(50, 550, 750, 550),   # bottom
        Wall(50, 50, 50, 550),     # left side
        # Interior partitions
        # Split upper arm vertically: bedroom (left) + bathroom (right)
        Wall(300, 50, 300, 350),
        # Separate laundry from living in lower arm.
        # Partition at x=600 (not 620): with the outer east wall at x=750
        # the living-room south span is 150 units, enough to fit the
        # 70-wide window_living with stubs >= 31.25 on both sides (the
        # pipeline corner-snap threshold = 5 * thickness = 31.25). At
        # x=620 the span was only 130 units and the right stub (15 units)
        # collapsed to the east-wall corner, destroying the gap.
        Wall(600, 350, 600, 550),
        # Hall wall between upper-arm and living area (below 350)
        # to avoid one giant room; connects left wall to upper-arm's
        # south wall at y=350.
        Wall(50, 350, 300, 350),
    ]

    openings = [
        Opening(
            id="entrance",
            center=(150.0, 550.0),
            width=70.0,
            orientation="horizontal",
            kind="door",
            notes="front door on south wall, living room",
        ),
        Opening(
            id="bedroom_door",
            center=(300.0, 150.0),
            width=50.0,
            orientation="vertical",
            kind="door",
            notes="bedroom to hallway (interior wall)",
        ),
        Opening(
            id="bathroom_door",
            center=(300.0, 275.0),
            width=50.0,
            orientation="vertical",
            kind="door",
            notes="bathroom to hallway (interior wall)",
        ),
        Opening(
            id="laundry_door",
            center=(600.0, 470.0),
            width=50.0,
            orientation="vertical",
            kind="door",
            notes="laundry off living room (on partition at x=600)",
        ),
        Opening(
            id="hall_passage",
            center=(150.0, 350.0),
            width=70.0,
            orientation="horizontal",
            kind="passage",
            notes="open passage between upper-arm hallway and living room",
        ),
        Opening(
            id="window_living",
            center=(675.0, 550.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes=(
                "external window, living room south. Center moved 700->675 "
                "so both stubs (40 and 40 units) exceed corner_snap (31.25) "
                "and the pipeline detects the colinear gap. Paired with the "
                "laundry partition moved from x=620 to x=600."
            ),
        ),
        Opening(
            id="window_bedroom",
            center=(150.0, 50.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="external window, bedroom (top wall)",
        ),
        Opening(
            id="window_bathroom",
            center=(400.0, 50.0),
            width=50.0,
            orientation="horizontal",
            kind="window",
            notes="external window, bathroom (top wall)",
        ),
    ]
    return walls, openings


def layout_tiny() -> tuple[list[Wall], list[Opening]]:
    """Tiny plan (2 rooms): 1 main room + 1 bathroom.

    viewBox 0 0 400 300. Outer rect 30..370 x 30..270. Vertical divider
    at x=240 splits main room (left) from bathroom (right). Stress test
    for small plans with few walls.
    """
    walls: list[Wall] = []
    walls.extend(_outer_rect(30, 30, 370, 270))
    # vertical divider between main room and bathroom
    walls.append(Wall(240, 30, 240, 270))

    openings = [
        Opening(
            id="main_entrance",
            center=(130.0, 30.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="front door on top outer wall, main room",
        ),
        Opening(
            id="bathroom_door",
            center=(240.0, 150.0),
            width=50.0,
            orientation="vertical",
            kind="door",
            notes="door between main room and bathroom",
        ),
        Opening(
            id="window_main",
            center=(130.0, 270.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="window on bottom wall, main room",
        ),
    ]
    return walls, openings


def layout_large() -> tuple[list[Wall], list[Opening]]:
    """Large multi-bedroom apartment (10 rooms).

    viewBox 0 0 1000 800. Outer rect 50..950 x 50..750 (900x700 interior).

    Grid layout:
      rows: y=50..260, 260..470, 470..610, 610..750
      cols: x=50..260, 260..470, 470..630, 630..800, 800..950

      row 1 (bedrooms):       br1 | br2 | br3   (br4 spans cols 4-5)
      row 2 (corridor row):   bath1 | corridor (row) | bath2 | storage
      row 3 (common):         living ............................ | kitchen
      row 4 (service):        laundry | dining | kitchen (cont) | pantry

    Stress test for scale and many interior walls.

    Instead of a strict grid, use a central horizontal corridor at y=260..310
    joining rooms from top to bottom.
    """
    walls: list[Wall] = []
    walls.extend(_outer_rect(50, 50, 950, 750))

    # --- Top band: 4 bedrooms side by side, y=50..260 ---
    # Vertical dividers between bedrooms
    walls.append(Wall(280, 50, 280, 260))   # br1 | br2
    walls.append(Wall(510, 50, 510, 260))   # br2 | br3
    walls.append(Wall(740, 50, 740, 260))   # br3 | br4
    # South wall of bedrooms (horizontal corridor north side)
    walls.append(Wall(50, 260, 950, 260))

    # --- Central corridor band: y=260..310 (50 px wide hall) ---
    walls.append(Wall(50, 310, 950, 310))  # south side of corridor

    # --- Bathroom/utility band: y=310..470 ---
    walls.append(Wall(200, 310, 200, 470))   # bath1 east wall
    walls.append(Wall(420, 310, 420, 470))   # bath1 | office divider
    walls.append(Wall(640, 310, 640, 470))   # office | bath2 divider
    walls.append(Wall(820, 310, 820, 470))   # bath2 | storage divider
    walls.append(Wall(50, 470, 950, 470))    # south wall of this band

    # --- Bottom band: y=470..750: living + kitchen ---
    # Vertical divider between living and kitchen
    walls.append(Wall(620, 470, 620, 750))

    openings = [
        # Main entrance from south into living/kitchen
        Opening(
            id="entrance",
            center=(300.0, 750.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="front door on south outer wall, living room",
        ),
        # Bedroom doors (onto corridor's north wall y=260)
        Opening(
            id="br1_door",
            center=(165.0, 260.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        Opening(
            id="br2_door",
            center=(395.0, 260.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        Opening(
            id="br3_door",
            center=(625.0, 260.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        Opening(
            id="br4_door",
            center=(845.0, 260.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        # Utility row doors onto corridor's south wall y=310
        Opening(
            id="bath1_door",
            center=(125.0, 310.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        Opening(
            id="office_door",
            center=(525.0, 310.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        Opening(
            id="bath2_door",
            center=(735.0, 310.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        Opening(
            id="storage_door",
            center=(885.0, 310.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        # Passage from utility band to living/kitchen band
        Opening(
            id="living_passage",
            center=(300.0, 470.0),
            width=70.0,
            orientation="horizontal",
            kind="passage",
            notes="open passage from utility band to living room",
        ),
        Opening(
            id="kitchen_passage",
            center=(800.0, 470.0),
            width=70.0,
            orientation="horizontal",
            kind="passage",
            notes="open passage from utility band to kitchen",
        ),
        # Door between living and kitchen (vertical interior wall)
        Opening(
            id="kitchen_door",
            center=(620.0, 610.0),
            width=50.0,
            orientation="vertical",
            kind="door",
            notes="door between living and kitchen",
        ),
        # External windows on side walls
        Opening(
            id="window_br1",
            center=(50.0, 155.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, bedroom 1 west wall",
        ),
        Opening(
            id="window_br4",
            center=(950.0, 155.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, bedroom 4 east wall",
        ),
        Opening(
            id="window_living",
            center=(200.0, 750.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="external window, living room south wall",
        ),
        Opening(
            id="window_kitchen",
            center=(800.0, 750.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="external window, kitchen south wall",
        ),
        Opening(
            id="window_kitchen_east",
            center=(950.0, 610.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="external window, kitchen east wall",
        ),
    ]
    return walls, openings


def layout_multistory() -> tuple[list[Wall], list[Opening]]:
    """Two-floor plan stacked vertically with a disconnected gap.

    viewBox 0 0 800 1200. Two independent floor rectangles:
      floor 1: y=50..560   (outer rect 50..750 x 50..560)
      floor 2: y=640..1170 (outer rect 50..750 x 640..1170)

    An 80-px gap at y=560..640 keeps the floors as two separate connected
    components. The gap is intentionally wider than the opening detector's
    ``max_opening`` (~75 px at thickness 6.25) so the detector does not
    spuriously bridge the colinear west/east walls between floors. This
    validates that the pipeline handles disconnected ``main_component``
    candidates without crashing and without over-detecting openings.

    Each floor has 4 rooms. 13 openings total.
    """
    walls: list[Wall] = []
    # --- Floor 1 ---
    walls.extend(_outer_rect(50, 50, 750, 560))
    # horizontal divider at y=305 splits top/bottom bands on floor 1
    walls.append(Wall(50, 305, 750, 305))
    # vertical divider at x=400 on top band (br1 | br2)
    walls.append(Wall(400, 50, 400, 305))
    # vertical divider at x=400 on bottom band (living | kitchen)
    walls.append(Wall(400, 305, 400, 560))

    # --- Floor 2 ---
    walls.extend(_outer_rect(50, 640, 750, 1170))
    # horizontal divider at y=895 splits top/bottom bands on floor 2
    walls.append(Wall(50, 895, 750, 895))
    # vertical divider at x=400 on top band (br3 | br4)
    walls.append(Wall(400, 640, 400, 895))
    # vertical divider at x=400 on bottom band (office | dining)
    walls.append(Wall(400, 895, 400, 1170))

    openings = [
        # Floor 1 entrance from south
        Opening(
            id="f1_entrance",
            center=(200.0, 560.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="floor 1 front door, living room south wall",
        ),
        # Floor 1: br1 door (horizontal wall y=305)
        Opening(
            id="f1_br1_door",
            center=(200.0, 305.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="floor 1 bedroom 1 door onto central hallway",
        ),
        # Floor 1: br2 door (horizontal wall y=305)
        Opening(
            id="f1_br2_door",
            center=(600.0, 305.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        # Floor 1: living | kitchen door (vertical at x=400, bottom band)
        Opening(
            id="f1_kitchen_door",
            center=(400.0, 435.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Floor 1: bedroom 1 external window (north wall)
        Opening(
            id="f1_window_br1",
            center=(200.0, 50.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="floor 1 br1 window on north wall",
        ),
        # Floor 1: bedroom 2 external window (north wall)
        Opening(
            id="f1_window_br2",
            center=(600.0, 50.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="floor 1 br2 window on north wall",
        ),
        # Floor 1: kitchen external window (east wall)
        Opening(
            id="f1_window_kitchen",
            center=(750.0, 435.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="floor 1 kitchen east window",
        ),

        # Floor 2 entrance from south (independent entry, maybe stairwell)
        Opening(
            id="f2_entrance",
            center=(200.0, 1170.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
            notes="floor 2 front door, office south wall",
        ),
        # Floor 2: br3 door (horizontal wall y=895)
        Opening(
            id="f2_br3_door",
            center=(200.0, 895.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        # Floor 2: br4 door (horizontal wall y=895)
        Opening(
            id="f2_br4_door",
            center=(600.0, 895.0),
            width=50.0,
            orientation="horizontal",
            kind="door",
        ),
        # Floor 2: office | dining door (vertical at x=400, bottom band)
        Opening(
            id="f2_dining_door",
            center=(400.0, 1025.0),
            width=50.0,
            orientation="vertical",
            kind="door",
        ),
        # Floor 2: br3 external window (north wall)
        Opening(
            id="f2_window_br3",
            center=(200.0, 640.0),
            width=70.0,
            orientation="horizontal",
            kind="window",
            notes="floor 2 br3 window on north wall",
        ),
        # Floor 2: dining external window (east wall)
        Opening(
            id="f2_window_dining",
            center=(750.0, 1025.0),
            width=70.0,
            orientation="vertical",
            kind="window",
            notes="floor 2 dining east window",
        ),
    ]
    return walls, openings


# ---------------------------------------------------------------------------
# SVG + YAML writers
# ---------------------------------------------------------------------------

def walls_to_svg(
    walls: list[Wall],
    openings: list[Opening],
    view_w: int = VIEW_W,
    view_h: int = VIEW_H,
) -> str:
    """Render walls (with door/window/passage gaps cut) to an SVG string.

    The pipeline's SVG ingest expects:
      * stroke == ``#000000`` (exact match)
      * stroke-width within [6.0, 6.5]
      * axis-aligned paths only, no curves
      * a valid viewBox

    Each wall becomes a ``<path d="M x1,y1 L x2,y2" />`` element. Keeping
    one path per segment preserves the gaps at openings exactly.
    """
    cut_walls = _apply_openings(walls, openings)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {view_w} {view_h}">',
        '  <g>',
    ]
    for w in cut_walls:
        lines.append(
            f'    <path d="M {w.x1},{w.y1} L {w.x2},{w.y2}" '
            f'style="fill:none;stroke:{STROKE_COLOR};stroke-width:{STROKE_WIDTH}" />'
        )
    lines.append('  </g>')
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def write_gt_yaml(
    openings: list[Opening],
    source_name: str,
    path: Path,
    thickness: float = STROKE_WIDTH,
) -> None:
    data = {
        "meta": {
            "source": f"{source_name}.svg",
            "thickness": thickness,
            "annotator": "programmatic (generate_synthetic_plans.py)",
        },
        "openings": [
            {
                "id": o.id,
                "center": list(o.center),
                "width": o.width,
                "orientation": o.orientation,
                "kind": o.kind,
                "notes": o.notes,
            }
            for o in openings
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

# Each entry: (name, layout_fn, view_w, view_h). view_w/view_h default to
# the 800x600 canvas used by the original four layouts but can be extended
# per-layout to stress-test small/large/tall plans.
LAYOUTS: list[tuple[str, Callable[[], tuple[list[Wall], list[Opening]]], int, int]] = [
    ("studio", layout_studio, VIEW_W, VIEW_H),
    ("2br", layout_2br, VIEW_W, VIEW_H),
    ("3br", layout_3br, VIEW_W, VIEW_H),
    ("lshape", layout_lshape, VIEW_W, VIEW_H),
    ("tiny", layout_tiny, 400, 300),
    ("large", layout_large, 1000, 800),
    ("multistory", layout_multistory, 800, 1200),
]


def generate_all(out_dir: Path) -> list[tuple[str, int, int]]:
    """Write all (svg, yaml) pairs into ``out_dir``.

    Returns a list of ``(name, n_walls_after_cut, n_openings)`` tuples so
    the CLI (and tests) can report wall counts.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: list[tuple[str, int, int]] = []
    for name, layout_fn, view_w, view_h in LAYOUTS:
        walls, openings = layout_fn()
        svg = walls_to_svg(walls, openings, view_w=view_w, view_h=view_h)
        (out_dir / f"{name}.svg").write_text(svg, encoding="utf-8")
        write_gt_yaml(openings, name, out_dir / f"{name}_openings_gt.yaml")
        cut_walls = _apply_openings(walls, openings)
        summary.append((name, len(cut_walls), len(openings)))
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic SVG plans and opening GT YAMLs."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/svg/synthetic"),
        help="Output directory for .svg + _openings_gt.yaml pairs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = generate_all(args.out)
    for name, n_walls, n_openings in summary:
        print(f"wrote {name}.svg ({n_walls} walls, {n_openings} openings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
