"""Tests for classify_openings_by_room_context — caminho B.

Covers:
- room rules: indoor x indoor / indoor x open_air / both rules-out
- width thresholds: interior_door / passage / window / glazed_balcony
- dedup of phantom-double openings on same wall (svg_arc raio + corda)
- robustness when room polygons overlap (nearest-seed fallback)
- self-adjacent disambiguation
- preservation of geometry_origin and hinge fields
"""
from __future__ import annotations

from tools.classify_openings_by_room_context import (
    DEDUP_DISTANCE_PT,
    PT_TO_M_DEFAULT,
    _classify_pair,
    _cluster_openings_by_proximity,
    classify_openings_by_room_context,
    find_rooms_flanking_wall,
    is_open_air_room,
)

# ---- Helpers ----

def _square_polygon(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _two_room_consensus(width_pt=29.0, geometry_origin="svg_arc",
                         room_a="SUITE 01", room_b="BANHO 01",
                         opening_id="o000",
                         kind_v5="door_arc"):
    """Two indoor rooms separated by a single horizontal wall, with
    one opening at the wall midpoint."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w000", "start": [0.0, 100.0],
             "end": [200.0, 100.0], "thickness": 5.4,
             "orientation": "h"},
        ],
        "rooms": [
            {"id": "r000", "name": room_a,
             "seed_pt": [100.0, 50.0],
             "polygon_pts": _square_polygon(0, 0, 200, 95)},
            {"id": "r001", "name": room_b,
             "seed_pt": [100.0, 150.0],
             "polygon_pts": _square_polygon(0, 105, 200, 200)},
        ],
        "openings": [
            {"id": opening_id, "wall_id": "w000",
             "center": [100.0, 100.0],
             "opening_width_pts": float(width_pt),
             "geometry_origin": geometry_origin,
             "kind_v5": kind_v5,
             "hinge": "left"},
        ],
        "soft_barriers": [],
    }


# ---- is_open_air_room ----

def test_open_air_room_terraco():
    assert is_open_air_room("TERRACO SOCIAL")
    assert is_open_air_room("Terraço Técnico")
    assert is_open_air_room("SACADA")
    assert is_open_air_room("VARANDA GOURMET")


def test_open_air_room_indoor():
    assert not is_open_air_room("SALA DE ESTAR")
    assert not is_open_air_room("COZINHA")
    assert not is_open_air_room("BANHO 01")
    assert not is_open_air_room("SUITE 02")
    assert not is_open_air_room(None)
    assert not is_open_air_room("")


# ---- _classify_pair: pure rule table ----

def _r(name):
    return {"id": "r0", "name": name, "seed_pt": [0, 0],
            "polygon_pts": []}


def test_classify_indoor_indoor_door():
    assert _classify_pair(_r("SUITE"), _r("BANHO"), 0.85) == "interior_door"


def test_classify_indoor_indoor_passage():
    assert _classify_pair(_r("SALA"), _r("JANTAR"), 1.80) == "interior_passage"


def test_classify_indoor_indoor_too_wide_dropped():
    assert _classify_pair(_r("SUITE"), _r("BANHO"), 3.20) is None


def test_classify_indoor_open_air_window():
    assert _classify_pair(_r("BANHO"), _r("TERRACO TECNICO"), 0.90) == "window"


def test_classify_indoor_open_air_glazed_balcony():
    out = _classify_pair(_r("SALA"), _r("TERRACO SOCIAL"), 2.50)
    assert out == "glazed_balcony"


def test_classify_indoor_exterior_window():
    """Indoor + None (exterior outside building) -> window."""
    assert _classify_pair(_r("BANHO"), None, 0.90) == "window"


def test_classify_indoor_exterior_glazed():
    assert _classify_pair(_r("SALA"), None, 2.20) == "glazed_balcony"


def test_classify_both_open_air_dropped():
    """Two open_air rooms shouldn't share a partition; drop."""
    assert _classify_pair(_r("TERRACO SOCIAL"),
                            _r("TERRACO TECNICO"), 1.20) is None


def test_classify_both_none_dropped():
    assert _classify_pair(None, None, 1.0) is None


# ---- private-room rule ----

def test_classify_private_pair_force_door():
    """Two private rooms (suite/banho) ALWAYS render as door even
    when width is up to PRIVATE_PAIR_DOOR_MAX_M (1.50m)."""
    assert _classify_pair(_r("SUITE 01"), _r("BANHO 01"), 1.36) == \
        "interior_door"
    assert _classify_pair(_r("LAVABO"), _r("BANHO 02"), 1.40) == \
        "interior_door"


def test_classify_private_pair_too_wide_dropped():
    """Private pair with width > 1.50m is detector noise, not a real
    passage between bedroom and bathroom."""
    assert _classify_pair(_r("BANHO 01"), _r("SUITE 01"), 1.88) is None
    assert _classify_pair(_r("BANHO 02"), _r("SUITE 01"), 2.20) is None


def test_classify_private_plus_public_uses_default_rules():
    """SUITE -> SALA DE ESTAR is a corridor connection. Default
    interior_door / interior_passage rules apply (not the strict
    private-pair rule)."""
    assert _classify_pair(_r("SUITE 02"), _r("SALA DE ESTAR"), 0.95) == \
        "interior_door"
    assert _classify_pair(_r("SUITE 02"), _r("SALA DE ESTAR"), 1.80) == \
        "interior_passage"


# ---- chord recovery from arc bbox ----

def test_chord_recovery_horizontal_wall_uses_x_span():
    """Horizontal wall: chord is bbox X-span. Earlier bug used
    max(W,H) which equals the swing depth."""
    cons = _two_room_consensus(width_pt=55.0)  # legacy wide width
    op = cons["openings"][0]
    op["arc_bbox_pts"] = [50.0, 100.0, 80.0, 155.0]  # 30 x 55
    classify_openings_by_room_context(cons)
    op = cons["openings"][0]
    # chord recovered = 30pt = 1.06m, room pair is SUITE 01 / BANHO 01
    # (private pair) -> door
    assert op["kind_v5"] == "interior_door"
    assert op["opening_width_pts_legacy"] == 55.0
    assert abs(op["opening_width_pts"] - 30.0) < 0.5


def test_chord_recovery_vertical_wall_uses_y_span():
    cons = _two_room_consensus()
    cons["walls"][0]["start"] = [100.0, 0.0]
    cons["walls"][0]["end"] = [100.0, 200.0]
    cons["walls"][0]["orientation"] = "v"
    op = cons["openings"][0]
    op["center"] = [100.0, 100.0]
    op["opening_width_pts"] = 55.0
    op["arc_bbox_pts"] = [85.0, 90.0, 140.0, 120.0]  # 55 x 30
    # Need to set up rooms on either side of vertical wall
    cons["rooms"] = [
        {"id": "rA", "name": "SUITE 01", "seed_pt": [50.0, 100.0],
         "polygon_pts": _square_polygon(0, 0, 95, 200)},
        {"id": "rB", "name": "BANHO 01", "seed_pt": [150.0, 100.0],
         "polygon_pts": _square_polygon(105, 0, 200, 200)},
    ]
    classify_openings_by_room_context(cons)
    op = cons["openings"][0]
    assert op["kind_v5"] == "interior_door"
    # y-span = 30pt = 1.06m
    assert abs(op["opening_width_pts"] - 30.0) < 0.5


def test_chord_recovery_skipped_for_wall_gap():
    """wall_gap openings have no arc_bbox; recovery is a no-op and the
    existing opening_width_pts (real gap width) is used as-is."""
    cons = _two_room_consensus(width_pt=82.0,
                                geometry_origin="wall_gap",
                                kind_v5="open_passage",
                                room_a="SALA DE ESTAR",
                                room_b="TERRACO SOCIAL")
    classify_openings_by_room_context(cons)
    op = cons["openings"][0]
    assert "opening_width_pts_legacy" not in op
    assert op["opening_width_pts"] == 82.0
    assert op["kind_v5"] == "glazed_balcony"


# ---- find_rooms_flanking_wall ----

def test_flanking_wall_two_rooms_polygon_hit():
    cons = _two_room_consensus()
    rm, rp = find_rooms_flanking_wall(cons["walls"][0], cons["rooms"],
                                      thickness_pt=5.4)
    assert {rm["id"], rp["id"]} == {"r000", "r001"}


def test_flanking_wall_polygon_overlap_falls_back_to_seed():
    """If both polygons claim both sides of the wall, the hybrid lookup
    must fall back to nearest-seed and still return DIFFERENT rooms."""
    cons = _two_room_consensus()
    # Inflate r000 polygon to cover the wall + r001 area too
    cons["rooms"][0]["polygon_pts"] = _square_polygon(0, 0, 200, 200)
    rm, rp = find_rooms_flanking_wall(cons["walls"][0], cons["rooms"],
                                      thickness_pt=5.4)
    assert rm is not None and rp is not None
    assert rm["id"] != rp["id"]


def test_flanking_wall_no_rooms_returns_none():
    cons = _two_room_consensus()
    cons["rooms"] = []
    rm, rp = find_rooms_flanking_wall(cons["walls"][0], cons["rooms"],
                                      thickness_pt=5.4)
    assert (rm, rp) == (None, None)


# ---- Dedup ----

def test_cluster_openings_close_centers_clustered():
    ops = [
        {"id": "a", "center": [100.0, 100.0]},
        {"id": "b", "center": [115.0, 100.0]},  # 15 pt away
        {"id": "c", "center": [200.0, 100.0]},  # far
    ]
    clusters = _cluster_openings_by_proximity(ops, threshold_pt=30.0)
    assert len(clusters) == 2
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]


def test_dedup_arc_radius_phantom_kept_corda():
    """Real bug from planta_74: svg_arc emits both the chord (~1.0m,
    real door) and the radius (~2.15m, phantom). After classification
    the chord should win (interior_door fits 1.0m snugly; passage
    fits 2.15m tighter, BUT chord wins because rooms_populated is
    equal and interior_door has higher kind_priority)."""
    cons = _two_room_consensus(width_pt=29.0, opening_id="real")
    cons["openings"].append({
        "id": "phantom", "wall_id": "w000",
        "center": [110.0, 100.0],  # within 30pt of the real
        "opening_width_pts": 61.0,  # raio = 2.15m
        "geometry_origin": "svg_arc",
        "kind_v5": "door_arc",
        "hinge": "left",
    })
    classify_openings_by_room_context(cons)
    ids = [op["id"] for op in cons["openings"]]
    assert "real" in ids
    assert "phantom" not in ids
    real = cons["openings"][0]
    assert real["kind_v5"] == "interior_door"


def test_dedup_does_not_merge_far_centers():
    cons = _two_room_consensus(width_pt=29.0, opening_id="a")
    cons["openings"].append({
        "id": "b", "wall_id": "w000",
        "center": [180.0, 100.0],  # 80 pt away from "a"
        "opening_width_pts": 29.0,
        "geometry_origin": "svg_arc",
        "kind_v5": "door_arc",
        "hinge": "right",
    })
    classify_openings_by_room_context(cons)
    ids = sorted(op["id"] for op in cons["openings"])
    assert ids == ["a", "b"]


# ---- End-to-end on representative cases ----

def test_e2e_apartment_door_interior():
    cons = _two_room_consensus(width_pt=29.0,
                                room_a="SUITE 02", room_b="BANHO 02")
    classify_openings_by_room_context(cons)
    assert len(cons["openings"]) == 1
    op = cons["openings"][0]
    assert op["kind_v5"] == "interior_door"
    assert op["geometry_origin"] == "svg_arc"  # preserved
    assert op["hinge"] == "left"  # preserved


def test_e2e_apartment_glazed_balcony():
    cons = _two_room_consensus(width_pt=82.0,  # 2.88m
                                room_a="SALA DE ESTAR",
                                room_b="TERRACO SOCIAL",
                                geometry_origin="wall_gap",
                                kind_v5="open_passage")
    classify_openings_by_room_context(cons)
    op = cons["openings"][0]
    assert op["kind_v5"] == "glazed_balcony"
    assert op["geometry_origin"] == "wall_gap"  # preserved


def test_e2e_drops_metadata_recorded():
    cons = _two_room_consensus(width_pt=29.0, opening_id="real")
    cons["openings"].append({
        "id": "phantom", "wall_id": "w000",
        "center": [110.0, 100.0],
        "opening_width_pts": 61.0,
        "geometry_origin": "svg_arc",
        "kind_v5": "door_arc",
        "hinge": "left",
    })
    classify_openings_by_room_context(cons)
    md = cons["metadata"]["openings_room_context_classifier"]
    assert md["kept"] == 1
    assert md["dropped"] == 1
    assert md["dedup_distance_pt"] == DEDUP_DISTANCE_PT
    assert md["pt_to_m"] == PT_TO_M_DEFAULT
