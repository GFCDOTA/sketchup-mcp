"""knowledge_ingest.py — chunk + embed + indexa docs numa coleção Qdrant
`knowledge_base`, separada da `felipe_preferences` (gosto pessoal) e do
`rag_chunks` (RAG de fidelidade do pipeline sketchup-mcp).

Fontes hoje: decisões anteriores do projeto (ITERATIONS.md, HANDOFF.md),
regras técnicas (felipe_visual_judge_rules.json, skills de audit/ergonomia).
PDFs de arquitetura/normas/ergonomia AINDA NÃO EXISTEM no repo (só o
manifest-modelo em tools/pdf_knowledge/pdf_manifest.template.yml, sem PDF
real) — quando existirem em references/pdfs/, rodar
`tools/pdf_knowledge/ingest_pdfs.py` primeiro (PDF -> JSONL por página) e
depois `index_jsonl()` daqui pra jogar no Qdrant.

Uso:
    python -m knowledge_ingest index-file <path> --category <cat> --source <nome>
    python -m knowledge_ingest index-jsonl <pdf_pages.jsonl>
"""
from __future__ import annotations

import argparse
import json
import sys
import zlib
from pathlib import Path

import rag_chat as rc

KB_COLLECTION = "knowledge_base"
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150


def _chunks(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= size:
        return [text] if text.strip() else []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


def _ensure_kb_collection() -> None:
    try:
        rc._http("GET", f"{rc.QDRANT_URL}/collections/{KB_COLLECTION}", timeout=5)
    except rc.InfraUnavailable:
        rc._http("PUT", f"{rc.QDRANT_URL}/collections/{KB_COLLECTION}",
                 {"vectors": {"size": rc.EMBED_DIM, "distance": "Cosine"}}, timeout=15)


def index_text(text: str, *, source: str, category: str, extra: dict | None = None) -> int:
    """Chunka+embeda+upserta um texto. Retorna nº de chunks indexados."""
    _ensure_kb_collection()
    points = []
    for i, ch in enumerate(_chunks(text)):
        if not ch.strip():
            continue
        vec = rc.embed(ch, prefix="search_document: ")
        pid = zlib.crc32(f"{source}:{i}".encode("utf-8")) & 0x7FFFFFFF
        payload = {"text": ch, "source": source, "category": category, "chunk_idx": i}
        if extra:
            payload.update(extra)
        points.append({"id": pid, "vector": vec, "payload": payload})
    if points:
        rc._http("PUT", f"{rc.QDRANT_URL}/collections/{KB_COLLECTION}/points?wait=true",
                 {"points": points}, timeout=60)
    return len(points)


def index_file(path: str, *, category: str, source: str | None = None) -> int:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    return index_text(text, source=source or p.name, category=category)


def index_jsonl(path: str) -> int:
    """Indexa um pdf_pages.jsonl (saída do tools/pdf_knowledge/ingest_pdfs.py) —
    1 chunk por página, source=titulo do PDF, category='pdf'."""
    total = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        total += index_text(
            rec.get("text", ""),
            source=f"{rec.get('title', rec.get('pdf_id', 'pdf'))} p.{rec.get('page')}",
            category="pdf",
            extra={"pdf_id": rec.get("pdf_id"), "page": rec.get("page")})
    return total


def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    try:
        _ensure_kb_collection()
        vec = rc.embed(query, prefix="search_query: ")
        out = rc._http("POST", f"{rc.QDRANT_URL}/collections/{KB_COLLECTION}/points/search",
                       {"vector": vec, "limit": top_k, "with_payload": True}, timeout=15)
        results = out.get("result", [])
        rc._emit_chunks(KB_COLLECTION, results, threshold=0.28, top_k=top_k,
                        query=query)
        return [r["payload"] for r in results if r.get("score", 0) > 0.28]
    except rc.InfraUnavailable as e:
        rc._emit_retrieval_degraded(KB_COLLECTION, f"InfraUnavailable: {e}")
        return []


def count_knowledge() -> int:
    try:
        out = rc._http("GET", f"{rc.QDRANT_URL}/collections/{KB_COLLECTION}", timeout=5)
        return int(out.get("result", {}).get("points_count", 0))
    except rc.InfraUnavailable:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("index-file")
    f.add_argument("path")
    f.add_argument("--category", required=True)
    f.add_argument("--source")
    j = sub.add_parser("index-jsonl")
    j.add_argument("path")
    ns = ap.parse_args()
    if ns.cmd == "index-file":
        n = index_file(ns.path, category=ns.category, source=ns.source)
        print(f"{n} chunks indexados de {ns.path}")
    elif ns.cmd == "index-jsonl":
        n = index_jsonl(ns.path)
        print(f"{n} chunks indexados de {ns.path}")


if __name__ == "__main__":
    sys.exit(main())
