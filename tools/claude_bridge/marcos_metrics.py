"""Calculo PURO de peso + velocidade dos Marcos a partir do historico de PRs.

Funcao sem I/O (testavel): recebe a lista de PRs (do snapshot pr_history.json,
gerado por pr_history.py via `gh pr list`) + os marcos (com campo `anchor` = nº do
PR que abre a era) e deriva:
  - peso por marco = PRs + LOC entre ancoras consecutivas;
  - velocidade: PRs/dia, PRs/semana (media) e buckets semanais;
  - aprendizado: % de PRs de failure-pattern/licao/fix + pivots (hipotese refutada).

NADA e' hardcoded: tudo sai dos dados. LOC pode ser ruidoso (assets/binarios) — a
era e' FLAGADA quando LOC/PR passa de LOC_NOISY_RATIO (heuristica honesta, nao oculta).
Datas dos PRs (mergedAt) sao best-effort (o repo teve clock-skew); a ANCORA confiavel
de ordem e' o numero do PR.
"""
import re
from collections import Counter
from datetime import datetime

LOC_NOISY_RATIO = 5000   # LOC/PR acima disto -> era provavelmente inflada por assets

_LEARN_RE = re.compile(r"FP-\d|LL-\d|refute|redirect|not viable|negative.?dogfood|"
                       r"diagnostic|plateau|spike|\bfix\(", re.IGNORECASE)
_PIVOT_RE = re.compile(r"refute|redirect|not viable|negative.?dogfood|plateau",
                       re.IGNORECASE)


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _loc(p):
    return (p.get("additions") or 0) + (p.get("deletions") or 0)


def compute_metrics(prs, marcos):
    """prs: list[dict] (number,title,mergedAt,additions,deletions,state).
    marcos: list[dict] com `nivel` e (opcional) `anchor` (int = 1o PR da era).
    Retorna dict serializavel. available=False se nao houver PR merged."""
    merged = [p for p in (prs or [])
              if p.get("state") == "MERGED" and isinstance(p.get("number"), int)]
    merged.sort(key=lambda p: p["number"])
    if not merged:
        return {"available": False, "note": "sem PRs merged no snapshot"}

    max_pr = merged[-1]["number"]
    dts = [d for d in (_parse_dt(p.get("mergedAt")) for p in merged) if d]
    span_days = ((max(dts) - min(dts)).days or 1) if dts else None
    loc_total = sum(_loc(p) for p in merged)

    # --- peso por marco (entre ancoras consecutivas, por nº de PR) ---
    anchored = sorted((m for m in marcos if isinstance(m.get("anchor"), int)),
                      key=lambda m: m["anchor"])
    weights = {}
    for i, m in enumerate(anchored):
        a = m["anchor"]
        nxt = anchored[i + 1]["anchor"] if i + 1 < len(anchored) else max_pr + 1
        era = [p for p in merged if a <= p["number"] < nxt]
        loc = sum(_loc(p) for p in era)
        n = len(era)
        weights[str(m["nivel"])] = {
            "prs": n, "loc": loc,
            "loc_noisy": bool(n and loc / n > LOC_NOISY_RATIO),
        }
    max_prs = max((w["prs"] for w in weights.values()), default=0)

    # --- velocidade semanal (ISO week) ---
    weekly = Counter()
    for p in merged:
        d = _parse_dt(p.get("mergedAt"))
        if d:
            y, w, _ = d.isocalendar()
            weekly[f"{y}-W{w:02d}"] += 1
    weekly_list = [{"week": k, "prs": weekly[k]} for k in sorted(weekly)]

    # --- aprendizado / pivots ---
    learn = [p for p in merged if _LEARN_RE.search(p.get("title", ""))]
    pivots = [{"number": p["number"], "title": p.get("title", "")}
              for p in merged if _PIVOT_RE.search(p.get("title", ""))]

    return {
        "available": True,
        "total_prs": len(merged),
        "max_pr": max_pr,
        "span_days": span_days,
        "date_range": ([min(dts).date().isoformat(), max(dts).date().isoformat()]
                       if dts else None),
        "avg_per_day": round(len(merged) / span_days, 1) if span_days else None,
        "avg_per_week": round(len(merged) * 7 / span_days, 1) if span_days else None,
        "loc_total": loc_total,
        "weights": weights,
        "max_prs_era": max_prs,
        "weekly": weekly_list,
        "learning": {
            "count": len(learn),
            "ratio": round(len(learn) / len(merged), 2),
            "pivots": pivots,
        },
        "loc_noisy_ratio": LOC_NOISY_RATIO,
    }
