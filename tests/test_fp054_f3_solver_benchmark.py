"""FP-054 F3 (#453): o benchmark mede, nao julga — estatistica correta, caso unico reprodutivel, sem meta inventada."""
from __future__ import annotations

import json

import pytest

from tools.validation import solver_benchmark as sb


def test_percentile_and_summary_follow_linear_interpolation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sb.percentile(xs, 0) == 1.0 and sb.percentile(xs, 100) == 5.0 and sb.percentile(xs, 50) == 3.0
    assert sb.percentile(xs, 95) == pytest.approx(4.8)
    s = sb.summarize([0.5, 0.1, 0.3])
    assert s == {"n": 3, "min_s": 0.1, "p50_s": 0.3, "p95_s": 0.48, "max_s": 0.5}
    assert sb.percentile([7.0], 95) == 7.0


def test_peak_memory_is_measured_on_the_supported_platforms():
    v = sb.peak_rss_mb()
    assert v is not None and v > 1.0                                  # Windows (psapi) e POSIX (ru_maxrss) sao suportados


def test_benchmark_scope_is_explicit_and_declares_what_it_does_not_measure(tmp_path):
    src = (sb.ROOT / "tools/validation/solver_benchmark.py").read_text(encoding="utf-8")
    assert "geometria adversarial" in src and "nenhum: so a linha de base" in src
    assert "obstaculos 10/100/1000" in src and "--obstacles" in src            # a dimensao existe e a corrida sem ela diz o que falta
    assert sb.OBSTACLES == (0, 10, 100, 1000) and sb.OBSTACLE_CAP == 10        # so o numero de caixas varia nessa dimensao


def _cell():
    from shapely.geometry import box
    return box(100.0, 100.0, 160.0, 150.0)


def test_obstacle_positions_are_deterministic_and_have_the_requested_count():
    for mode in sb.OBSTACLE_MODES:
        for n in (0, 1, 10, 100, 1000):
            a, b = sb.obstacle_positions(_cell(), n, mode), sb.obstacle_positions(_cell(), n, mode)
            assert a == b and len(a) == n


def test_far_obstacles_are_outside_the_solver_neighborhood_and_near_ones_inside_the_ring():
    from shapely.geometry import Point
    cell, zone = _cell(), _cell().buffer(39.37)
    assert all(not zone.contains(Point(x, y)) for x, y in sb.obstacle_positions(cell, 100, "far"))
    near = sb.obstacle_positions(cell, 100, "near")
    assert all(zone.contains(Point(x, y)) and not cell.contains(Point(x, y)) for x, y in near)


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        sb.obstacle_positions(_cell(), 5, "adversarial")


def test_synthetic_obstacles_copy_the_template_without_touching_it():
    tpl = {"room": "R", "module": "M", "kind": "k", "corners": [[0, 0]], "h_in": 99.0, "extra": 1}
    boxes = sb.synthetic_obstacles(tpl, [(1.0, 2.0), (5.0, 6.0)])
    assert [b["module"] for b in boxes] == ["SynthObstacle0", "SynthObstacle1"] and all(b["room"] == "SYNTH" for b in boxes)
    assert boxes[1]["corners"][0] == [5.0, 6.0] and boxes[1]["extra"] == 1 and tpl == {
        "room": "R", "module": "M", "kind": "k", "corners": [[0, 0]], "h_in": 99.0, "extra": 1}


def test_call_counter_counts_shapely_calls_including_a_name_bound_unary_union_and_restores_everything():
    import shapely.ops
    from shapely.geometry import box
    from shapely.geometry.base import BaseGeometry
    before = {n: getattr(BaseGeometry, n) for n in sb.COUNTED_METHODS}
    uu_before = shapely.ops.unary_union
    a, b = box(0, 0, 2, 2), box(1, 1, 3, 3)
    with sb.CallCounter() as c:
        a.intersection(b)
        a.buffer(1.0)
        a.buffer(2.0)
        shapely.ops.unary_union([a, b])
    assert c.counts["intersection"] == 1 and c.counts["buffer"] == 2 and c.counts["unary_union"] == 1
    assert all(getattr(BaseGeometry, n) is f for n, f in before.items()) and shapely.ops.unary_union is uu_before
    a.intersection(b)
    assert c.counts["intersection"] == 1                                      # fora do contexto nao conta mais


def test_call_counter_restores_even_when_the_body_raises():
    from shapely.geometry.base import BaseGeometry
    orig = BaseGeometry.buffer
    with pytest.raises(RuntimeError):
        with sb.CallCounter():
            raise RuntimeError("falha no corpo")
    assert BaseGeometry.buffer is orig


@pytest.mark.planta74_scale
def test_single_case_runs_on_the_real_lavabo_and_reports_candidates_and_status():
    res = sb.run_case("r007", 1, repeats=2)
    assert res["room"] == "r007" and res["max_candidates"] == 1 and res["candidates_total"] > 100
    assert res["time"]["n"] == 2 and res["time"]["p50_s"] > 0 and res["status"] in ("FEASIBLE", "INFEASIBLE", "UNKNOWN")
    json.dumps(res)


@pytest.mark.planta74_scale
def test_obstacle_case_on_the_real_lavabo_adds_boxes_reports_calls_and_never_touches_the_plant():
    base = sb.run_case("r007", 10, repeats=1, count_calls=True)
    res = sb.run_case("r007", 10, repeats=1, obstacles=100, mode="near", count_calls=True)
    assert res["boxes_real"] == base["boxes_real"] == res["boxes_total"] - 100
    assert res["obstacle_mode"] == "near" and set(res["shapely_calls"]) >= {"buffer", "intersection", "unary_union"}
    assert res["candidates_total"] == base["candidates_total"]               # o problema do solver nao muda; so as caixas
    json.dumps(res)
