#!/usr/bin/env python3
"""Busca simples em índice JSONL gerado por ingest_pdfs.py.

Não é RAG pesado. É uma ferramenta rápida para achar páginas candidatas.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", s.lower())


def score(text: str, query_terms: list[str]) -> int:
    tokens = tokenize(text)
    counts = {t: tokens.count(t) for t in set(query_terms)}
    return sum(counts.values())


def snippet(text: str, terms: list[str], size: int = 500) -> str:
    lower = text.lower()
    pos = min([lower.find(t) for t in terms if lower.find(t) >= 0] or [0])
    start = max(0, pos - size // 2)
    end = min(len(text), start + size)
    return text[start:end].strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    terms = tokenize(args.query)
    rows = []

    with Path(args.index).open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            s = score(rec.get("text", ""), terms)
            if s > 0:
                rows.append((s, rec))

    rows.sort(key=lambda x: (-x[0], x[1]["title"], x[1]["page"]))

    for rank, (s, rec) in enumerate(rows[: args.limit], start=1):
        print(f"\n## {rank}. score={s} | {rec['title']} | p.{rec['page']}")
        print(snippet(rec["text"], terms))


if __name__ == "__main__":
    main()
