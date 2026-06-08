"""Testes do calculo PURO de peso+velocidade dos Marcos (marcos_metrics.compute_metrics).
Fixture sintetica — sem rede, sem gh, sem snapshot real."""
from tools.claude_bridge.marcos_metrics import compute_metrics


def _pr(n, add=10, dele=5, state="MERGED", title="feat: x", date="2026-05-03"):
    return {"number": n, "title": title, "state": state,
            "additions": add, "deletions": dele, "mergedAt": f"{date}T10:00:00Z"}


def _fixture():
    prs = [
        # era N1 = PRs [1,5): 4 PRs (semana 1)
        _pr(1, title="chore: repo hardening", date="2026-05-03"),
        _pr(2, date="2026-05-03"),
        _pr(3, title="docs(diagnostic): FP-013 plateau analysis", date="2026-05-04"),
        _pr(4, date="2026-05-04"),
        # era N2 = PRs [5,10): 5 PRs (semana 2)
        _pr(5, date="2026-05-11"),
        _pr(6, title="fix(walls): junction", date="2026-05-11"),
        _pr(7, title="feat(fp-030): negative-dogfood oracle misses wall", date="2026-05-12"),
        _pr(8, date="2026-05-12"),
        _pr(9, date="2026-05-13"),
        # era N3 = PRs [10, max+1): 3 PRs; #10 com LOC enorme (noisy)
        _pr(10, add=19000, dele=2000, title="feat(artifacts): canonical .skp", date="2026-05-18"),
        _pr(11, date="2026-05-18"),
        _pr(12, date="2026-05-19"),
        # nao-merged: excluido
        _pr(99, state="OPEN", date="2026-05-20"),
    ]
    marcos = [
        {"nivel": 3, "anchor": 10}, {"nivel": 2, "anchor": 5},
        {"nivel": 1, "anchor": 1}, {"nivel": 9, "anchor": None},  # N9 sem anchor
    ]
    return prs, marcos


def test_empty_unavailable():
    assert compute_metrics([], [])["available"] is False
    assert compute_metrics([{"number": 1, "state": "OPEN"}], [])["available"] is False


def test_totals_exclude_non_merged():
    prs, marcos = _fixture()
    m = compute_metrics(prs, marcos)
    assert m["available"] is True
    assert m["total_prs"] == 12          # #99 OPEN fora
    assert m["max_pr"] == 12             # max ENTRE os merged


def test_weights_per_era():
    prs, marcos = _fixture()
    w = compute_metrics(prs, marcos)["weights"]
    assert w["1"]["prs"] == 4            # [1,5)
    assert w["2"]["prs"] == 5            # [5,10)
    assert w["3"]["prs"] == 3            # [10,13)
    assert "9" not in w                  # marco sem anchor nao entra no peso


def test_loc_noisy_flag():
    prs, marcos = _fixture()
    w = compute_metrics(prs, marcos)["weights"]
    assert w["3"]["loc_noisy"] is True   # 21K LOC / 3 PRs > 5000
    assert w["1"]["loc_noisy"] is False
    assert w["2"]["loc_noisy"] is False


def test_velocity_and_weekly():
    prs, marcos = _fixture()
    m = compute_metrics(prs, marcos)
    assert m["avg_per_day"] is not None and m["avg_per_day"] > 0
    assert m["avg_per_week"] is not None
    weeks = {b["week"] for b in m["weekly"]}
    assert len(weeks) >= 2               # PRs espalhados em >1 semana ISO
    assert sum(b["prs"] for b in m["weekly"]) == 12


def test_learning_and_pivots():
    prs, marcos = _fixture()
    learn = compute_metrics(prs, marcos)["learning"]
    assert learn["count"] >= 3           # FP-013, fix(walls), negative-dogfood
    assert 0 < learn["ratio"] <= 1
    titles = " ".join(p["title"] for p in learn["pivots"]).lower()
    assert "negative-dogfood" in titles  # pivot detectado
    assert "plateau" in titles


def test_nothing_hardcoded_reacts_to_data():
    # remover PRs muda os numeros (prova que e' derivado, nao fixo)
    prs, marcos = _fixture()
    full = compute_metrics(prs, marcos)
    fewer = compute_metrics(prs[:6] + [prs[-1]], marcos)  # so #1..#6 (+ OPEN)
    assert fewer["total_prs"] < full["total_prs"]
    assert fewer["weights"]["1"]["prs"] != full["weights"]["1"]["prs"] or \
        fewer["weights"]["2"]["prs"] != full["weights"]["2"]["prs"]
