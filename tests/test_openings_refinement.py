from __future__ import annotations

import pytest

from model.types import Wall
from openings.pruning import (
    dedup_collinear_openings,
    filter_min_width_openings,
    prune_orphan_openings,
)
from openings.service import Opening


def _wall(wall_id: str, start: tuple[float, float], end: tuple[float, float]) -> Wall:
    return Wall(
        wall_id=wall_id,
        page_index=0,
        start=start,
        end=end,
        thickness=6.25,
        orientation="horizontal" if start[1] == end[1] else "vertical",
        source="svg",
        confidence=1.0,
    )


def _opening(
    opening_id: str,
    wall_a: str,
    wall_b: str,
    width: float = 50.0,
    center: tuple[float, float] = (100.0, 100.0),
    orientation: str = "horizontal",
) -> Opening:
    return Opening(
        opening_id=opening_id,
        page_index=0,
        orientation=orientation,
        center=center,
        width=width,
        wall_a=wall_a,
        wall_b=wall_b,
        kind="door",
    )


def test_prune_orphan_openings_drops_when_both_walls_missing() -> None:
    kept = [_wall("wall-1", (0, 0), (100, 0))]
    openings = [
        _opening("opening-1", "wall-2", "wall-3"),  # both missing -> drop
        _opening("opening-2", "wall-1", "wall-4"),  # one kept -> keep (boundary)
    ]

    result, report = prune_orphan_openings(openings, kept)

    assert [o.opening_id for o in result] == ["opening-2"]
    assert report.input_count == 2
    assert report.dropped_orphan == 1
    assert report.kept == 1


def test_prune_keeps_opening_when_both_walls_in_main() -> None:
    kept = [
        _wall("wall-1", (0, 0), (50, 0)),
        _wall("wall-2", (60, 0), (100, 0)),
    ]
    openings = [_opening("opening-1", "wall-1", "wall-2")]

    result, report = prune_orphan_openings(openings, kept)

    assert len(result) == 1
    assert result[0].opening_id == "opening-1"
    assert report.dropped_orphan == 0
    assert report.kept == 1


def test_prune_keeps_boundary_opening_conservative() -> None:
    """Preserva porta onde apenas uma wall sobreviveu.

    Caso tipico: porta externa onde um lado e fachada separada em
    componente distinto. Filtro conservador nao descarta esse vao para
    evitar falso negativo.
    """
    kept = [_wall("wall-1", (0, 0), (100, 0))]
    openings = [_opening("opening-1", "wall-1", "wall-999")]

    result, report = prune_orphan_openings(openings, kept)

    assert len(result) == 1
    assert report.dropped_orphan == 0


def test_prune_empty_inputs() -> None:
    result, report = prune_orphan_openings([], [])
    assert result == []
    assert report.input_count == 0
    assert report.dropped_orphan == 0
    assert report.kept == 0


def test_prune_does_not_mutate_kept_walls_list() -> None:
    """Filtro nao deve alterar a lista de walls — ela vai pra build_topology."""
    kept = [_wall("wall-1", (0, 0), (100, 0))]
    openings = [_opening("opening-1", "wall-999", "wall-998")]

    before = list(kept)
    prune_orphan_openings(openings, kept)

    assert kept == before


def test_filter_min_width_drops_below_threshold() -> None:
    """Default 3.5 x thickness threshold: 6.25 x 3.5 = 21.875 px."""
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=15.0),  # below -> drop
        _opening("opening-2", "wall-3", "wall-4", width=21.0),  # below -> drop
        _opening("opening-3", "wall-5", "wall-6", width=22.0),  # above -> keep
        _opening("opening-4", "wall-7", "wall-8", width=60.0),  # above -> keep
    ]

    result, report = filter_min_width_openings(openings, wall_thickness=6.25)

    assert [o.opening_id for o in result] == ["opening-3", "opening-4"]
    assert report.input_count == 4
    assert report.dropped_below_min == 2
    assert report.kept == 2
    assert report.threshold_px == pytest.approx(21.875)


def test_filter_min_width_respects_explicit_mul() -> None:
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=40.0),
        _opening("opening-2", "wall-3", "wall-4", width=60.0),
    ]

    # mul=8 -> threshold = 50 px; drops the 40 px opening
    result, report = filter_min_width_openings(openings, wall_thickness=6.25, min_width_mul=8.0)

    assert [o.opening_id for o in result] == ["opening-2"]
    assert report.threshold_px == pytest.approx(50.0)


def test_filter_min_width_env_var_override(monkeypatch) -> None:
    openings = [_opening("opening-1", "wall-1", "wall-2", width=40.0)]
    monkeypatch.setenv("OPENINGS_MIN_WIDTH_MUL", "10.0")

    # threshold = 62.5, opening 40 dropped
    _, report = filter_min_width_openings(openings, wall_thickness=6.25)
    assert report.dropped_below_min == 1
    assert report.threshold_px == pytest.approx(62.5)


def test_filter_min_width_empty() -> None:
    result, report = filter_min_width_openings([], wall_thickness=6.25)
    assert result == []
    assert report.input_count == 0
    assert report.threshold_px == pytest.approx(21.875)


def test_dedup_merges_very_close_colinear_pair() -> None:
    """Parede dupla em vertical: dois openings em ~mesmo x, centros
    separados por 5px (< 4xt=25), overlap completo. Deve fundir."""
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=54.0, center=(437.0, 309.0), orientation="vertical"),
        _opening("opening-2", "wall-3", "wall-4", width=40.0, center=(441.0, 313.0), orientation="vertical"),
    ]

    result, report = dedup_collinear_openings(openings, wall_thickness=6.25)

    assert len(result) == 1
    # Keeps the wider opening
    assert result[0].opening_id == "opening-1"
    assert result[0].width == pytest.approx(54.0)
    assert report.merged == 1
    assert report.kept == 1


def test_dedup_keeps_distant_colinear_pair() -> None:
    """Mesma parede, centros separados por 150px (muito > 4xt=25).
    Duas portas reais distintas — nao devem fundir."""
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=60.0, center=(100.0, 100.0), orientation="horizontal"),
        _opening("opening-2", "wall-1", "wall-2", width=60.0, center=(250.0, 100.0), orientation="horizontal"),
    ]

    result, report = dedup_collinear_openings(openings, wall_thickness=6.25)

    assert len(result) == 2
    assert report.merged == 0


def test_dedup_skips_different_orientation() -> None:
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=50.0, center=(100.0, 100.0), orientation="horizontal"),
        _opening("opening-2", "wall-3", "wall-4", width=50.0, center=(100.0, 100.0), orientation="vertical"),
    ]

    result, report = dedup_collinear_openings(openings, wall_thickness=6.25)

    assert len(result) == 2
    assert report.merged == 0


def test_dedup_skips_pair_without_overlap() -> None:
    """Dois openings colineares com overlap insuficiente: nao sao duplicatas.

    centros a 20px, ambos com width=10 (ranges nao se tocam): overlap=0,
    gate de 0.30 falha, mantidos os 2.
    """
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=10.0, center=(100.0, 100.0), orientation="horizontal"),
        _opening("opening-2", "wall-3", "wall-4", width=10.0, center=(120.0, 100.0), orientation="horizontal"),
    ]

    result, report = dedup_collinear_openings(openings, wall_thickness=6.25)

    assert len(result) == 2
    assert report.merged == 0


def test_dedup_skips_different_perpendicular_axis() -> None:
    """Mesma orientacao mas eixos perp diferentes (> 1xt): paredes paralelas,
    nao mesma parede dupla. Mantidos os 2."""
    openings = [
        _opening("opening-1", "wall-1", "wall-2", width=50.0, center=(100.0, 100.0), orientation="horizontal"),
        _opening("opening-2", "wall-3", "wall-4", width=50.0, center=(100.0, 120.0), orientation="horizontal"),
    ]

    # delta perp = 20 > thickness (6.25)
    result, report = dedup_collinear_openings(openings, wall_thickness=6.25)

    assert len(result) == 2
    assert report.merged == 0


def test_dedup_empty_input() -> None:
    result, report = dedup_collinear_openings([], wall_thickness=6.25)
    assert result == []
    assert report.input_count == 0
    assert report.merged == 0


def test_dedup_single_input() -> None:
    openings = [_opening("opening-1", "wall-1", "wall-2")]
    result, report = dedup_collinear_openings(openings, wall_thickness=6.25)
    assert len(result) == 1
    assert report.merged == 0
