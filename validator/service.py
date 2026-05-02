"""FastAPI service exposing the planta validator on port 8770 by default.

Endpoints
---------
GET  /health                         {"ok": true, "scorers": [...]}
GET  /entries                        list every manifest entry
GET  /entries/pending                list manifest entries with validation == null
GET  /entries/{entry_id}             one entry as stored
POST /validate/{entry_id}            run scorer for one entry, persist
POST /validate-pending               validate all pending; ?vision=true to enable
GET  /metrics                        manifest stats (counts, mean score, etc.)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .pipeline import validate_entry, validate_pending

REPO_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="planta-validator",
    version="0.1.0",
    description="Scores PNGs in runs/png_history/manifest.jsonl",
)


def _load_manifest():
    from tools.png_history import list_entries
    return list_entries()


def _find(entry_id: str) -> dict[str, Any] | None:
    for e in _load_manifest():
        if e["id"] == entry_id:
            return e
    return None


@app.get("/health")
def health():
    from .scorers import REGISTRY
    return {
        "ok": True,
        "scorers": sorted({fn.__module__.split(".")[-1] for fn in REGISTRY.values()}),
        "registered_kinds": sorted(REGISTRY.keys()),
        "manifest_entries": len(_load_manifest()),
        "pending": len([e for e in _load_manifest() if e.get("validation") is None]),
    }


@app.get("/entries")
def list_all():
    return _load_manifest()


@app.get("/entries/pending")
def list_pending():
    return [e for e in _load_manifest() if e.get("validation") is None]


@app.get("/entries/{entry_id}")
def get_entry(entry_id: str):
    e = _find(entry_id)
    if not e:
        raise HTTPException(404, f"entry not found: {entry_id}")
    return e


@app.post("/validate/{entry_id}")
def validate_one(entry_id: str, vision: bool = Query(False)):
    from tools.png_history import apply_validation
    e = _find(entry_id)
    if not e:
        raise HTTPException(404, f"entry not found: {entry_id}")
    v = validate_entry(e, REPO_ROOT, vision=vision)
    apply_validation(entry_id, v)
    return {"id": entry_id, "validation": v}


@app.post("/validate-pending")
def validate_all_pending(vision: bool = Query(False),
                         limit: int | None = Query(None, ge=1)):
    out = validate_pending(REPO_ROOT, vision=vision, limit=limit)
    return {"validated": len(out), "results": out}


@app.get("/metrics")
def metrics():
    entries = _load_manifest()
    scored = [e for e in entries if e.get("validation")]
    if not scored:
        return {"total": len(entries), "scored": 0}
    scores = [e["validation"]["score"] for e in scored if e["validation"].get("score") is not None]
    by_kind: dict[str, list[float]] = {}
    for e in scored:
        s = e["validation"].get("score")
        if s is None:
            continue
        by_kind.setdefault(e.get("kind", "?"), []).append(s)
    return {
        "total":   len(entries),
        "scored":  len(scored),
        "pending": len(entries) - len(scored),
        "mean_score": round(sum(scores) / len(scores), 4) if scores else None,
        "min_score":  round(min(scores), 4) if scores else None,
        "max_score":  round(max(scores), 4) if scores else None,
        "by_kind": {
            k: {
                "n": len(v),
                "mean": round(sum(v) / len(v), 4),
                "min":  round(min(v), 4),
                "max":  round(max(v), 4),
            }
            for k, v in by_kind.items()
        },
    }
