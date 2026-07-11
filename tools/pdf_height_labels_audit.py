#!/usr/bin/env python3
"""Auditoria de LABELS DE ALTURA do PDF vs consensus (peitoril/mureta).

O PDF da planta escreve alturas como TEXTO vetorial ("PEITORIL H=1,10M",
"MURETA H=0,70M"). Este audit extrai cada label com posição, associa ao
soft_barrier sourced mais próximo e verifica o ``height_m`` do consensus
contra a medida do PDF — a direção REVERSA (PDF → consensus) que o review
clínico 2026-07-11 apontou como cega: elemento que o PDF nomeia e o
consensus não renderiza era invisível a todos os gates.

Vereditos por label:
- ``MATCH``      — barreira sourced próxima com height_m ≈ altura do label.
- ``MISMATCH``   — barreira sourced próxima com altura DIFERENTE.
- ``UNRENDERED`` — nenhuma barreira sourced perto: o PDF nomeia um elemento
  que não existe no .skp (ex.: MURETA H=0,70M do terraço técnico). Lista
  as polylines órfãs candidatas pra CURADORIA — nunca promove sozinho
  (linework órfão é ambíguo; associar por palpite = fabricar geometria).

Janelas: este PDF não carrega texto de peitoril de janela — alturas de
janela seguem convenção NBR documentada no builder (honesto: sem medida,
sem invenção).

Uso:
    python -m tools.pdf_height_labels_audit            # planta_74
    python -m tools.pdf_height_labels_audit --json
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# label ↔ barreira: distância máx do centro do texto até a polyline (pts).
# Labels ficam ADJACENTES ao elemento (fora dele); 40pt ≈ 1m na planta_74.
LABEL_MATCH_MAX_PT = 40.0
HEIGHT_TOL_M = 0.05
# sourced vence uma órfã quase-empatada: linework órfão frequentemente
# DUPLICA a borda que uma barreira sourced já cobre (ex. sb004 vs
# h_sb000 na borda leste do terraço técnico, diferença de 0.5pt).
SOURCED_TIEBREAK_PT = 3.0

LABEL_RE = re.compile(r"(PEITORIL|MURETA|GUARDA[- ]?CORPO)?\s*H\s*=\s*([\d]+[.,]\d+)\s*M")


def _consensus(fix: str) -> dict:
    p = REPO / "fixtures" / fix / "consensus_with_human_walls_and_soft_barriers.json"
    return json.loads(p.read_text("utf-8"))


def height_labels_from_pdf(pdf_path: Path) -> list[dict]:
    """[(kind, height_m, cx, cy)] de cada label 'X H=n,nnM' do PDF."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    tp = pdf[0].get_textpage()
    text = tp.get_text_bounded()
    out = []
    for m in LABEL_RE.finditer(text.upper()):
        kind = (m.group(1) or "ALTURA").replace("-", "_").replace(" ", "_")
        height = float(m.group(2).replace(",", "."))
        # posição: bbox dos chars do match
        boxes = [tp.get_charbox(i) for i in range(m.start(), m.end())]
        xs = [c for b in boxes for c in (b[0], b[2])]
        ys = [c for b in boxes for c in (b[1], b[3])]
        if not xs:
            continue
        out.append({
            "kind": kind, "height_m": height,
            "center": [round((min(xs) + max(xs)) / 2, 1),
                       round((min(ys) + max(ys)) / 2, 1)],
        })
    return out


def _dist_to_polyline(pt, pts) -> float:
    """Distância ponto→polyline por SEGMENTO (vértice engana em polyline
    esparsa: h_sb000 tem 3 vértices cobrindo 4m de borda)."""
    if len(pts) == 1:
        return math.hypot(pts[0][0] - pt[0], pts[0][1] - pt[1])
    from shapely.geometry import LineString, Point
    return float(LineString(pts).distance(Point(pt)))


def audit(fix: str = "planta_74") -> list[dict]:
    con = _consensus(fix)
    labels = height_labels_from_pdf(REPO / f"{fix}.pdf")
    barriers = [sb for sb in con.get("soft_barriers", [])
                if sb.get("polyline_pts")]
    rows = []
    for lb in labels:
        row = dict(lb)
        # vizinho mais próximo GLOBAL (sourced OU órfã): se o elemento
        # real do label for uma polyline órfã, casar com a sourced "mais
        # próxima" seria associação errada.
        ranked = sorted(
            ((sb, _dist_to_polyline(lb["center"], sb["polyline_pts"]))
             for sb in barriers),
            key=lambda t: t[1],
        )
        near = [(sb, d) for sb, d in ranked if d < LABEL_MATCH_MAX_PT]
        sourced_near = next(
            ((sb, d) for sb, d in near if sb.get("barrier_type")), None)
        orphan_near = next(
            ((sb, d) for sb, d in near if not sb.get("barrier_type")), None)
        # sourced vence se for o mais próximo ou quase-empatado (órfã
        # costuma duplicar a mesma borda); órfã CLARAMENTE mais próxima
        # = elemento não-renderizado distinto.
        if sourced_near and (orphan_near is None
                             or sourced_near[1] <= orphan_near[1]
                             + SOURCED_TIEBREAK_PT):
            sb, d = sourced_near
            row["barrier_id"] = sb["id"]
            row["consensus_height_m"] = sb.get("height_m")
            ok = (sb.get("height_m") is not None
                  and abs(sb["height_m"] - lb["height_m"]) <= HEIGHT_TOL_M)
            row["verdict"] = "MATCH" if ok else "MISMATCH"
            row["dist_pt"] = round(d, 1)
        else:
            row["verdict"] = "UNRENDERED"
            row["candidates"] = [
                {"id": sb["id"], "dist_pt": round(d, 1)}
                for sb, d in ranked[:3] if not sb.get("barrier_type")
            ]
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", default="planta_74")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = audit(args.fix)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            extra = (f"barrier={r.get('barrier_id')} "
                     f"consensus_h={r.get('consensus_height_m')}"
                     if "barrier_id" in r else
                     f"candidatas={[c['id'] for c in r.get('candidates', [])]}")
            print(f"{r['kind']:14} H={r['height_m']:.2f}m @ {r['center']} "
                  f"=> {r['verdict']} ({extra})")
    bad = [r for r in rows if r["verdict"] == "MISMATCH"]
    unrendered = [r for r in rows if r["verdict"] == "UNRENDERED"]
    status = "FAIL" if bad else ("WARN" if unrendered else "PASS")
    print(f"pdf_height_labels_audit => {status} "
          f"(match={sum(1 for r in rows if r['verdict']=='MATCH')} "
          f"mismatch={len(bad)} unrendered={len(unrendered)})")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
