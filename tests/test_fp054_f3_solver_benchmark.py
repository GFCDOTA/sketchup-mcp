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
    assert "obstaculos 10/100/1000" in src and "geometria adversarial" in src and "nenhum: so a linha de base" in src


@pytest.mark.planta74_scale
def test_single_case_runs_on_the_real_lavabo_and_reports_candidates_and_status():
    res = sb.run_case("r007", 1, repeats=2)
    assert res["room"] == "r007" and res["max_candidates"] == 1 and res["candidates_total"] > 100
    assert res["time"]["n"] == 2 and res["time"]["p50_s"] > 0 and res["status"] in ("FEASIBLE", "INFEASIBLE", "UNKNOWN")
    json.dumps(res)
