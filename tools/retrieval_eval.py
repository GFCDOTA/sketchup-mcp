"""retrieval_eval.py — FP-035: o oráculo de qualidade de retrieval que faltava.

Mede o ranking de `reference_db.retrieve` contra um golden-set rotulado à mão
(`references/eval/retrieval_golden.jsonl`) com métricas DETERMINÍSTICAS e
SENSÍVEIS À ORDEM — recall@k, MRR, nDCG@k (ganho graduado) — em stdlib puro.

Por que existe: hoje NÃO há métrica de retrieval no repo (grep recall@|mrr|nDCG
= 0). O único check de relevância é a presença hardcoded de 2 nomes de token num
teste. Sem este oráculo, mexer no ranking (fundir o recall semântico descartado
em reference_db.py:467, adicionar facet de style, RRF) é change-without-proof:
comprovadamente DIFERENTE, nunca comprovadamente MELHOR.

Honestidade de escopo:
  - Os 12 tokens curados são todos de COZINHA e não carregam `style` -> recall@k
    satura (~1.0). Por isso o sinal primário é MRR/nDCG (ordem), + hard-negatives
    (bedroom/bathroom -> nada) que medem PRECISÃO.
  - O caminho faceted não toca infra (sempre-on no CI). backend='embed' passa
    por reference_db.retrieve, que degrada honesto pro faceted se Qdrant/Ollama
    estão off — a métrica nunca é fabricada.
  - Os RÓTULOS são julgamento de relevância do Felipe (draft inicial marcado no
    próprio golden-set). A régua é objetiva; o gabarito é curado.

CLI:
  python -m tools.retrieval_eval [--golden PATH] [--k 6] [--backend faceted|embed]
                                 [--json] [--baseline PATH]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from tools import reference_db as rdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "references/eval/retrieval_golden.jsonl"
CORPUS_SIZE = 12  # nº de tokens curados; top_n grande p/ capturar o ranking inteiro


# ---------------------------------------------------------------------------
# métricas (stdlib puro, determinístico, sem clock/random)
# ---------------------------------------------------------------------------
def recall_at_k(predicted: list[str], relevant: list[str], k: int) -> float:
    """Fração dos relevantes presentes no top-k. Relevante vazio (hard-negative):
    1.0 só se o top-k também é vazio, senão 0.0 (mede precisão do hard-negative)."""
    top = predicted[:k]
    if not relevant:
        return 1.0 if not top else 0.0
    hits = len(set(relevant) & set(top))
    return hits / len(relevant)


def mrr(predicted: list[str], relevant: list[str]) -> float:
    """Reciprocal rank do PRIMEIRO predito relevante (1-indexed). 0.0 se nenhum."""
    rel = set(relevant)
    for rank, item in enumerate(predicted, start=1):
        if item in rel:
            return 1.0 / rank
    return 0.0


def _gain(item: str, relevant: list[str]) -> float:
    """Ganho graduado: item no topo do gabarito vale mais (ordem importa)."""
    if item in relevant:
        return float(len(relevant) - relevant.index(item))
    return 0.0


def ndcg_at_k(predicted: list[str], relevant: list[str], k: int) -> float:
    """nDCG@k com ganho graduado pela posição esperada — sensível à ORDEM.
    Relevante vazio -> 1.0 (nada a ordenar)."""
    if not relevant:
        return 1.0
    dcg = sum(_gain(item, relevant) / math.log2(i + 2)
              for i, item in enumerate(predicted[:k]))
    # ideal: gabarito na ordem esperada
    idcg = sum(_gain(item, relevant) / math.log2(i + 2)
               for i, item in enumerate(relevant[:k]))
    return dcg / idcg if idcg else 0.0


# ---------------------------------------------------------------------------
# golden-set
# ---------------------------------------------------------------------------
def load_golden(path: Path | str = DEFAULT_GOLDEN) -> list[dict]:
    """Lê o golden JSONL. Ignora linhas em branco e comentários (`#`).
    Cada linha: {room, style?, budget?, relevant:[...], note?}."""
    rows: list[dict] = []
    for line in Path(path).read_text("utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        d = json.loads(s)
        rows.append({
            "room": (d.get("room") or "").strip().lower(),
            "style": d.get("style"),
            "budget": d.get("budget"),
            "relevant": list(d.get("relevant") or []),
            "note": d.get("note", ""),
        })
    # ordem determinística e estável, independente da ordem do arquivo
    rows.sort(key=lambda r: (r["room"], r["style"] or "", str(r["budget"])))
    return rows


# ---------------------------------------------------------------------------
# avaliação
# ---------------------------------------------------------------------------
def evaluate(golden: Path | str = DEFAULT_GOLDEN, *, k: int = 6,
             backend: str = "faceted") -> dict:
    """Roda reference_db.retrieve pra cada linha do golden e agrega as métricas.
    Determinístico no caminho faceted. Retorna um relatório serializável."""
    rows_in = load_golden(golden)
    out_rows: list[dict] = []
    for r in rows_in:
        bundle = rdb.retrieve(r["room"], r["style"], r["budget"],
                              top_n=CORPUS_SIZE, backend=backend)
        predicted = [t["name"] for t in bundle["tokens"]]
        out_rows.append({
            "query": {"room": r["room"], "style": r["style"], "budget": r["budget"]},
            "relevant": r["relevant"],
            "predicted": predicted,
            "recall_at_k": round(recall_at_k(predicted, r["relevant"], k), 4),
            "mrr": round(mrr(predicted, r["relevant"]), 4),
            "ndcg_at_k": round(ndcg_at_k(predicted, r["relevant"], k), 4),
            "confidence": bundle.get("confidence"),
            "note": r["note"],
        })

    def _mean(vals: list[float]) -> float:
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    # MRR agrega só sobre linhas COM relevantes (indefinido p/ hard-negative);
    # recall/ndcg agregam sobre todas (hard-negative bem-definido = 1.0 perfeito).
    with_rel = [row for row in out_rows if row["relevant"]]
    aggregate = {
        "n": len(out_rows),
        "n_with_relevant": len(with_rel),
        "recall_at_k": _mean([row["recall_at_k"] for row in out_rows]),
        "mrr": _mean([row["mrr"] for row in with_rel]),
        "ndcg_at_k": _mean([row["ndcg_at_k"] for row in out_rows]),
    }
    return {
        "k": k,
        "backend": backend,
        "aggregate": aggregate,
        "style_discrimination": _style_discrimination(out_rows),
        "rows": out_rows,
    }


def _style_discrimination(rows: list[dict]) -> list[dict]:
    """Diagnóstico-chave: cômodos onde estilos DIFERENTES devolvem o MESMO ranking
    (prova de que o ranking ignora style — reference_db.py:476-477). Determinístico."""
    # agrupa por (room, budget) — comparar estilos HOLDING budget constante, senão
    # uma linha de budget diferente mascara o empate de estilo.
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        if row["predicted"]:
            key = (row["query"]["room"], str(row["query"]["budget"]))
            groups.setdefault(key, []).append(row)
    flags: list[dict] = []
    for (room, _budget), rs in sorted(groups.items()):
        styles = sorted({str(row["query"]["style"]) for row in rs})
        preds = {tuple(row["predicted"]) for row in rs}
        if len(styles) >= 2 and len(preds) == 1:
            flags.append({"room": room, "styles": styles,
                          "identical_ranking": True})
    return flags


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt_report(rep: dict) -> str:
    a = rep["aggregate"]
    lines = [
        f"retrieval_eval — backend={rep['backend']}  k={rep['k']}  "
        f"n={a['n']} (com relevantes: {a['n_with_relevant']})",
        f"  recall@{rep['k']}={a['recall_at_k']:.4f}  "
        f"MRR={a['mrr']:.4f}  nDCG@{rep['k']}={a['ndcg_at_k']:.4f}",
        "",
    ]
    for row in rep["rows"]:
        q = row["query"]
        tag = f"{q['room']}/{q['style'] or '-'}" + (
            f"/{q['budget']}" if q["budget"] else "")
        lines.append(
            f"  {tag:34} recall={row['recall_at_k']:.3f} "
            f"mrr={row['mrr']:.3f} ndcg={row['ndcg_at_k']:.3f} "
            f"[{row['confidence']}]")
    if rep["style_discrimination"]:
        lines.append("")
        lines.append("  ⚠ style ignorado no ranking (mesmo ranking p/ estilos distintos):")
        for f in rep["style_discrimination"]:
            lines.append(f"      {f['room']}: {', '.join(f['styles'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Avalia o retrieval vs golden-set.")
    ap.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--backend", default="faceted", choices=("faceted", "embed"))
    ap.add_argument("--json", action="store_true", help="saída JSON crua")
    ap.add_argument("--baseline", default=None,
                    help="JSON de baseline; sai !=0 se o agregado regredir")
    a = ap.parse_args(argv)

    rep = evaluate(a.golden, k=a.k, backend=a.backend)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json
          else _fmt_report(rep))

    if a.baseline:
        base = json.loads(Path(a.baseline).read_text("utf-8"))["aggregate"]
        now = rep["aggregate"]
        regressed = [m for m in ("recall_at_k", "mrr", "ndcg_at_k")
                     if now[m] + 1e-9 < base[m]]
        if regressed:
            print(f"\nREGRESSÃO vs baseline em: {', '.join(regressed)}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
