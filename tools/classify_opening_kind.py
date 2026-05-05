"""V5 enrichment: classify each opening into a semantic ``kind_v5``.

Why
---
The current pipeline emits ``kind: door | window`` (geometric type)
plus ``geometry_origin: svg_arc | svg_segments`` (how it was detected).
That tells you what the PDF *drew*, not what the *space* is.

The visual diff against the Matterport tour
(``docs/tour/matterport_visual_findings_74m2.md`` V5 verdict) showed
that some openings on planta_74 read as thin orange strips on walls
because the SKP exporter has no way to distinguish:

* a swinging door with a real arc symbol,
* a fixed glazed sliding door at the terraço perimeter,
* a wide open passage with no door at all.

This module adds a **schema-additive** semantic classifier. It
**does not modify** the existing ``kind`` field, the ``openings``
list shape, the wall list, or the count of openings — just adds two
optional fields per opening:

* ``kind_v5``        one of: ``door_arc | open_passage | glazed_balcony | window``
* ``kind_v5_reason`` short text explaining the classifier's choice

The Ruby exporter (``tools/consume_consensus.rb``, CLAUDE.md §1.4) is
**not touched** — a future PR can branch on ``kind_v5`` to render
different opening symbols, but this PR keeps SKP behavior unchanged
per the conservative path documented in the ChatGPT review session.

Classifier
----------
Per-opening, conservative + heuristic + auditable:

* ``geometry_origin == "svg_arc"`` → ``door_arc``
  (the arc symbol is the strongest evidence of a swinging door)
* ``geometry_origin == "svg_segments"`` AND the host wall is the
  outer envelope of a room whose name matches the TERRACO/VARANDA
  pattern → ``glazed_balcony``
* ``geometry_origin == "svg_segments"`` otherwise → ``window``
* No ``geometry_origin`` set OR explicit ``wall_gap`` origin →
  ``open_passage`` (the future wall-gap detector will use this label;
  this module does NOT invent gaps from nowhere — see test
  ``test_door_arc_not_invented_without_evidence``)

The TERRACO room match uses substring search on room ``name`` (case-
insensitive), looking for the word ``TERRA`` (covers TERRACO SOCIAL,
TERRACO TECNICO, TERRAÇO, VARANDA-as-future-rename).

Usage
-----
    from tools.classify_opening_kind import classify_openings

    consensus = json.load(open("runs/v1_pipeline_after/consensus_with_rooms.json"))
    classify_openings(consensus)   # in-place, schema-additive
    json.dump(consensus, open(out, "w"), indent=2)

Or via the existing extractor's CLI: ``tools/extract_openings_vector.py``
accepts ``--classify-kind`` to run the enrichment as a post-process.
"""

from __future__ import annotations

import re
from typing import Any

# Class label vocabulary. Extend with care — any new label must be
# documented here, in the test file, and in the future Ruby render
# branch (when one is added).
KIND_DOOR_ARC = "door_arc"
KIND_OPEN_PASSAGE = "open_passage"
KIND_GLAZED_BALCONY = "glazed_balcony"
KIND_WINDOW = "window"

ALL_KINDS_V5 = (
    KIND_DOOR_ARC,
    KIND_OPEN_PASSAGE,
    KIND_GLAZED_BALCONY,
    KIND_WINDOW,
)

# Substring (case-insensitive) on room ``name`` to flag a TERRACO/VARANDA
# room. Matches "TERRACO SOCIAL", "TERRACO TECNICO", "Terraço", "VARANDA",
# "VARANDA SOCIAL", etc. The substring is intentionally short (TERRA)
# to also catch "TERRAÇO" with cedilla after a unidecode pass — but the
# input here is the consensus's own room.name, so no transliteration is
# needed.
_TERRACO_RE = re.compile(r"\b(TERRA|VARANDA)", re.IGNORECASE)


def _is_terraco_room(room: dict[str, Any]) -> bool:
    name = room.get("name", "")
    return bool(_TERRACO_RE.search(str(name)))


def _opening_room_adjacency(
    opening: dict[str, Any], rooms: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Rooms whose polygon contains the opening's center point.

    Uses a plain ray-casting point-in-polygon for stdlib-only operation.
    Returns at most 2 rooms (the opening's host wall divides them).
    """
    cx, cy = opening.get("center", [0.0, 0.0])
    out: list[dict[str, Any]] = []
    for room in rooms:
        poly = room.get("polygon_pts")
        if not poly or len(poly) < 3:
            continue
        if _point_in_polygon(cx, cy, poly):
            out.append(room)
    return out


def _point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
    """Ray-casting; ``poly`` is a list of [x, y] vertices, not closed."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _opening_near_terraco(
    opening: dict[str, Any], rooms: list[dict[str, Any]]
) -> bool:
    """True if the opening's center is inside a TERRACO/VARANDA room.

    The host wall of a glazed balcony is the boundary between the
    living/dining and the terraço; the opening's *center* sits inside
    the terraço's polygon when the polygon was drawn to include the
    glass envelope (the planta_74 case).
    """
    for r in rooms:
        if not _is_terraco_room(r):
            continue
        poly = r.get("polygon_pts")
        if not poly or len(poly) < 3:
            continue
        cx, cy = opening.get("center", [0.0, 0.0])
        if _point_in_polygon(cx, cy, poly):
            return True
        # Also accept openings within ~1 wall thickness of the
        # terraço polygon (host wall sits between two rooms).
        # We approximate "near" by checking the polygon bbox plus
        # a margin — cheap and good enough for screen-class precision.
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        margin = 8.0  # ~ wall thickness; aligns with V1 snap default
        if (min(xs) - margin <= cx <= max(xs) + margin
                and min(ys) - margin <= cy <= max(ys) + margin):
            return True
    return False


def classify_one(
    opening: dict[str, Any], rooms: list[dict[str, Any]]
) -> tuple[str, str]:
    """Return ``(kind_v5, reason)`` for one opening.

    Pure function; does not mutate ``opening``.
    """
    origin = opening.get("geometry_origin")

    if origin == "svg_arc":
        n_cubic = opening.get("arc_n_cubic", 0)
        return (
            KIND_DOOR_ARC,
            f"svg_arc with {n_cubic} cubic segments; "
            f"hinge attached to wall {opening.get('wall_id', '?')}",
        )

    if origin == "svg_segments":
        if _opening_near_terraco(opening, rooms):
            return (
                KIND_GLAZED_BALCONY,
                "svg_segments + opening center inside/near TERRACO/VARANDA room",
            )
        return (
            KIND_WINDOW,
            "svg_segments; not adjacent to a terraço/varanda room",
        )

    if origin == "wall_gap":
        return (
            KIND_OPEN_PASSAGE,
            "wall_gap origin: no arc and no glass segments, just a wall break",
        )

    # No origin set: refuse to invent a door_arc; default to open_passage
    # so the schema is filled but no false-positive door symbol is added
    # downstream. This is the conservative fallback ChatGPT specified
    # ("door_arc não inventado sem evidência").
    return (
        KIND_OPEN_PASSAGE,
        "no geometry_origin set; defaulting to open_passage "
        "(door_arc requires explicit svg_arc evidence)",
    )


def classify_openings(consensus: dict[str, Any]) -> dict[str, Any]:
    """Mutate ``consensus`` in place: add ``kind_v5`` + ``kind_v5_reason``
    to each opening. Returns the same dict for convenience.

    Schema-additive: existing ``kind``, ``geometry_origin``, etc. are
    preserved. Counts of walls / rooms / openings / soft_barriers are
    untouched.
    """
    rooms = consensus.get("rooms") or []
    openings = consensus.get("openings") or []
    n_before = len(openings)

    counts = {k: 0 for k in ALL_KINDS_V5}
    for o in openings:
        kv5, reason = classify_one(o, rooms)
        o["kind_v5"] = kv5
        o["kind_v5_reason"] = reason
        counts[kv5] += 1

    # Stamp the consensus metadata so downstream / debug can tell which
    # openings list has been classified. Does NOT replace existing
    # metadata fields.
    md = consensus.setdefault("metadata", {})
    md["opening_kind_v5_classifier"] = {
        "version": "1.0.0",
        "counts": counts,
        "n_openings_input": n_before,
        "n_openings_output": len(openings),
    }

    assert len(openings) == n_before, (
        "classify_openings must not change opening count "
        f"({n_before} -> {len(openings)})"
    )
    return consensus
