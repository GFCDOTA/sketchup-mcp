#!/usr/bin/env python3
"""Exporta contexto curto para o Claude com páginas candidatas.

O objetivo é dar ao agente uma lista de referências e trechos curtos,
não reproduzir livros.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", s.lower())


def score(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(lower.count(t) for t in terms)


def make_excerpt(text: str, terms: list[str], max_chars: int = 700) -> str:
    lower = text.lower()
    hits = [lower.find(t) for t in terms if lower.find(t) >= 0]
    pos = min(hits) if hits else 0
    start = max(0, pos - max_chars // 3)
    end = min(len(text), start + max_chars)
    return text[start:end].strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    terms = tokenize(args.query)
    rows = []

    with Path(args.index).open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            s = score(rec.get("text", ""), terms)
            if s:
                rows.append((s, rec))

    rows.sort(key=lambda x: (-x[0], x[1]["title"], x[1]["page"]))
    rows = rows[: args.limit]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Contexto curto de PDFs para Claude",
        "",
        f"Query: `{args.query}`",
        "",
        "Regra: use estes trechos só para extrair regras codificáveis. Não copie conteúdo longo para o repo.",
        "",
    ]

    for i, (s, rec) in enumerate(rows, start=1):
        lines += [
            f"## {i}. {rec['title']} — página {rec['page']} — score {s}",
            "",
            make_excerpt(rec["text"], terms),
            "",
            "Ação esperada do agente: converter o aprendizado acima em regra/teste/constante, se aplicável.",
            "",
        ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] contexto gerado: {out}")


if __name__ == "__main__":
    main()
