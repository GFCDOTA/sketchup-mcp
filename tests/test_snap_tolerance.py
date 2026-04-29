from __future__ import annotations

from model.types import Wall
from topology.service import build_topology


def _wall(
    wid: str,
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: float,
    orientation: str,
) -> Wall:
    return Wall(
        wall_id=wid,
        page_index=0,
        start=start,
        end=end,
        thickness=thickness,
        orientation=orientation,
        source="synthetic",
        confidence=1.0,
    )


def test_snap_collapses_close_endpoints_into_shared_node() -> None:
    # Two walls meeting at a corner with endpoints 1 px apart must snap
    # into the same graph node. With snap_tolerance = 1.5 x median (= 12
    # px) the H wall's right end at (300, 200) and the V wall's top at
    # (301, 200) collapse into a shared corner junction with degree 2.
    walls = [
        _wall("w-h", (200.0, 200.0), (300.0, 200.0), 8.0, "horizontal"),
        _wall("w-v", (301.0, 200.0), (301.0, 100.0), 8.0, "vertical"),
    ]
    _, junctions, _, _ = build_topology(walls)
    # Expect exactly one corner junction near (300.5, 200) with degree 2.
    corner = [j for j in junctions if 299 < j.point[0] < 302 and 199 < j.point[1] < 201]
    assert len(corner) == 1, [(j.point, j.kind) for j in junctions]
    assert corner[0].degree == 2
    assert corner[0].kind == "pass_through"
    # The H wall's left endpoint and the V wall's bottom endpoint remain
    # as legitimate ends.
    ends = [j for j in junctions if j.kind == "end"]
    assert len(ends) == 2


def test_snap_preserves_legitimate_close_endpoints_beyond_tolerance() -> None:
    # Endpoints separated by more than 1.5 x median thickness (= 12 px
    # for thickness 8) must NOT collapse. Place two walls whose closest
    # endpoints are 30 px apart.
    walls = [
        _wall("w-1", (0.0, 100.0), (100.0, 100.0), 8.0, "horizontal"),
        _wall("w-2", (130.0, 100.0), (230.0, 100.0), 8.0, "horizontal"),
    ]
    _, junctions, _, report = build_topology(walls)
    # Expect 4 end junctions (one per wall endpoint), all degree 1
    end_kinds = [j for j in junctions if j.kind == "end"]
    assert len(end_kinds) == 4, [(j.point, j.kind) for j in junctions]


def test_snap_does_not_merge_across_pages() -> None:
    # Identical coords on two different pages must not snap into one.
    walls = [
        _wall("w-0", (100.0, 100.0), (200.0, 100.0), 8.0, "horizontal"),
        Wall(
            wall_id="w-1",
            page_index=1,
            start=(100.0, 100.0),
            end=(200.0, 100.0),
            thickness=8.0,
            orientation="horizontal",
            source="synthetic",
            confidence=1.0,
        ),
    ]
    split_walls, _, _, report = build_topology(walls)
    pages = {w.page_index for w in split_walls}
    assert pages == {0, 1}
    assert report.max_components_within_page == 1  # 1 component per page
