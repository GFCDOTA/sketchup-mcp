#!/usr/bin/env python3
"""Extrai texto dos PDFs em páginas JSONL.

Uso:
  python scripts/ingest_pdfs.py --manifest config/pdf_manifest.yml --out output/pdf_pages.jsonl

Notas:
- O output é artefato local. Não commitar se contiver texto extraído de livro.
- Mantém página, título e hash do arquivo para rastreabilidade.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Instale pyyaml: pip install pyyaml") from exc

try:
    from pypdf import PdfReader
except ImportError as exc:
    raise SystemExit("Instale pypdf: pip install pypdf") from exc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path)
    records = 0

    with out_path.open("w", encoding="utf-8") as out:
        for item in manifest.get("pdfs", []):
            pdf_path = Path(item["path"])
            if not pdf_path.exists():
                print(f"[WARN] PDF não encontrado: {pdf_path}")
                continue

            reader = PdfReader(str(pdf_path))
            file_hash = sha256_file(pdf_path)

            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                text = " ".join(text.split())

                rec = {
                    "pdf_id": item["id"],
                    "title": item["title"],
                    "path": str(pdf_path),
                    "sha256": file_hash,
                    "page": i,
                    "text": text,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                records += 1

    print(f"[OK] páginas indexadas: {records}")
    print(f"[OK] output: {out_path}")


if __name__ == "__main__":
    main()
