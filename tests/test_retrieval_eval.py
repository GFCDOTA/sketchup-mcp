"""FP-035 — testes do harness de avaliação de retrieval (o oráculo que faltava).

Duas camadas:
  1. MATEMÁTICA das métricas (recall@k / MRR / nDCG order-sensitive) sobre vetores
     sintéticos com valores exatos conhecidos — determinístico, sem I/O.
  2. Harness sobre o golden-set REAL rodando reference_db.retrieve no caminho
     faceted (sempre-on no CI, zero infra): roda 2× byte-idêntico e é bem-formado.

Não asserta um LIMIAR de qualidade absoluto sobre o ranking de hoje (que é
degenerado de propósito — style ignorado, empate alfabético); isso é o que a
mudança de ranking vai medir. Aqui provamos que o RÉGUA está correta e estável.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import retrieval_eval as re

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "references/eval/retrieval_golden.jsonl"


# --- 1. matemática das métricas (valores exatos) ----------------------------

def test_recall_at_k_counts_only_top_k():
    predicted = ["a", "b", "c", "d"]
    relevant = ["a", "c", "x"]
    # top-2 = [a, b] -> só 'a' dos 3 relevantes
    assert re.recall_at_k(predicted, relevant, 2) == pytest.approx(1 / 3)
    # top-4 = [a, b, c, d] -> 'a' e 'c'
    assert re.recall_at_k(predicted, relevant, 4) == pytest.approx(2 / 3)


def test_recall_empty_relevant_is_one_when_nothing_predicted():
    # hard-negative: relevante vazio -> perfeito só se o predito também é vazio.
    assert re.recall_at_k([], [], 6) == 1.0
    # vazou algo onde não devia -> 0.0 (precisão do hard-negative)
    assert re.recall_at_k(["kitchen_tok"], [], 6) == 0.0


def test_mrr_is_reciprocal_of_first_hit_rank():
    # primeiro predito relevante é 'a' na posição 2 (1-indexed) -> 1/2
    assert re.mrr(["b", "a", "c"], ["a"]) == pytest.approx(0.5)
    # primeiro predito na posição 1 -> 1.0
    assert re.mrr(["a", "b"], ["a", "b"]) == 1.0
    # nenhum relevante encontrado -> 0.0
    assert re.mrr(["x", "y"], ["a"]) == 0.0


def test_ndcg_is_order_sensitive():
    relevant = ["a", "b"]           # ganho graduado: a=2, b=1 (ordem importa)
    # ordem ideal -> 1.0
    assert re.ndcg_at_k(["a", "b"], relevant, 2) == pytest.approx(1.0)
    # ordem invertida -> penalizada, valor exato conhecido
    assert re.ndcg_at_k(["b", "a"], relevant, 2) == pytest.approx(0.8597, abs=1e-4)
    # relevante ausente do topo -> < ordem ideal
    assert re.ndcg_at_k(["x", "a", "b"], relevant, 2) < 1.0


def test_ndcg_empty_relevant_is_one():
    assert re.ndcg_at_k([], [], 6) == 1.0


# --- 2. harness sobre o golden-set real (faceted, sempre-on) ----------------

def test_golden_set_exists_and_wellformed():
    assert GOLDEN.exists(), "golden-set de retrieval não encontrado"
    rows = re.load_golden(GOLDEN)
    assert rows, "golden-set vazio"
    for r in rows:
        assert r["room"], "linha sem room"
        assert isinstance(r["relevant"], list)


def test_golden_token_names_are_real():
    # rótulos referem tokens que EXISTEM (pega typo no golden-set).
    real = {p.stem for p in (ROOT / "references/tokens").glob("*.json")}
    for r in re.load_golden(GOLDEN):
        for name in r["relevant"]:
            assert name in real, f"token inexistente no golden-set: {name!r}"


def test_eval_runs_deterministic_on_faceted():
    # roda o harness 2× no caminho faceted (sem infra) -> agregado byte-idêntico.
    a = re.evaluate(GOLDEN, k=6, backend="faceted")
    b = re.evaluate(GOLDEN, k=6, backend="faceted")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert 0.0 <= a["aggregate"]["mrr"] <= 1.0
    assert 0.0 <= a["aggregate"]["recall_at_k"] <= 1.0
    assert 0.0 <= a["aggregate"]["ndcg_at_k"] <= 1.0
    assert a["k"] == 6
    assert len(a["rows"]) == len(re.load_golden(GOLDEN))


def test_hard_negative_room_returns_no_kitchen_tokens():
    # bedroom/bathroom não podem vazar token de cozinha -> recall (precisão) = 1.0
    rows = {(r["query"]["room"], r["query"]["style"]): r
            for r in re.evaluate(GOLDEN, k=6, backend="faceted")["rows"]}
    for (room, _style), row in rows.items():
        if room in ("bedroom", "bathroom"):
            assert row["predicted"] == [], f"vazou token em {room}"
            assert row["recall_at_k"] == 1.0
