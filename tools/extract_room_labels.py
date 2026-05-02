"""Extract room labels from PDF text and cluster multi-line labels.

Room names in architectural plans are often laid out across two lines
(e.g. "SALA DE\nJANTAR"). The PDF stores each line as its own text rect.
We:
  1. Pull every text rect.
  2. Filter to those WITHIN the planta region (drops legend/notes).
  3. Match against a room-keyword list.
  4. Cluster rects whose centroids are within a few line-heights of
     each other and whose text reads as a continuation
     (e.g. "SALA DE" + "JANTAR" → "SALA DE JANTAR").
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pypdfium2 as pdfium


ROOM_KEYWORDS = [
    "COZINHA", "SALA DE JANTAR", "SALA DE ESTAR", "SALA",
    "JANTAR", "ESTAR",
    "SUITE", "QUARTO", "DORMITORIO",
    "BANHO", "BANHEIRO", "WC", "LAVABO",
    "A.S.", "AREA DE SERVICO", "SERVICO", "LAVANDERIA",
    "TERRACO", "VARANDA", "SACADA",
    "SOCIAL", "TECNICO", "GOURMET",
    "ESCRITORIO", "HOME", "CLOSET",
]


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.upper().strip())


def _is_room_label(text: str) -> bool:
    norm = _normalize(text)
    return any(kw in norm for kw in ROOM_KEYWORDS)


def extract_labels(pdf_path: Path,
                   planta_region: tuple[float, float, float, float] | None = None
                   ) -> list[dict]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    text_page = page.get_textpage()
    n_rects = text_page.count_rects()

    raw: list[dict] = []
    for i in range(n_rects):
        l, t, r, b = text_page.get_rect(i)
        cx, cy = (l + r) / 2.0, (t + b) / 2.0
        if planta_region is not None:
            x0, y0, x1, y1 = planta_region
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                continue
        txt = text_page.get_text_bounded(l, t, r, b).strip()
        if not _is_room_label(txt):
            continue
        raw.append({
            "text": txt,
            "norm": _normalize(txt),
            "pos": [cx, cy],
            "rect": [l, t, r, b],
            "h": abs(t - b),
        })

    # Cluster multi-line labels: same centroid x within 2*line_h and
    # centroid y within 2.5*line_h.
    clusters: list[list[dict]] = []
    used: set[int] = set()
    for i, r in enumerate(raw):
        if i in used:
            continue
        h = r["h"] or 5.0
        cluster = [r]
        used.add(i)
        for j in range(i + 1, len(raw)):
            if j in used:
                continue
            o = raw[j]
            if abs(r["pos"][0] - o["pos"][0]) > 2.0 * h:
                continue
            if abs(r["pos"][1] - o["pos"][1]) > 2.5 * h:
                continue
            cluster.append(o)
            used.add(j)
        clusters.append(cluster)

    # Reduce each cluster to a single label
    labels: list[dict] = []
    for ci, c in enumerate(clusters):
        # Sort by descending y (PDF y up; top line first when rendered)
        c.sort(key=lambda r: -r["pos"][1])
        text = " ".join(r["norm"] for r in c)
        cx = sum(r["pos"][0] for r in c) / len(c)
        cy = sum(r["pos"][1] for r in c) / len(c)
        labels.append({
            "id": f"l{ci:03d}",
            "name": text,
            "seed_pt": [cx, cy],
            "lines": [r["text"] for r in c],
        })
    return labels


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--planta-region", nargs=4, type=float,
                    help="x0 y0 x1 y1 in PDF points")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    region = tuple(args.planta_region) if args.planta_region else None
    labels = extract_labels(args.pdf, region)
    if args.out:
        args.out.write_text(json.dumps(labels, indent=2))
    print(f"[ok] {len(labels)} room labels")
    for l in labels:
        print(f"  {l['id']}: {l['name']!r} @ ({l['seed_pt'][0]:.1f},{l['seed_pt'][1]:.1f})")
