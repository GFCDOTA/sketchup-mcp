"""reference_packs.py — Reference Pack como entidade de 1ª classe + CURADORIA do Felipe (stdlib).

O Felipe não cura texto solto: cura REFERÊNCIA VISUAL. Cada ação (👍 aprovar · 👎 rejeitar ·
⭐ principal · 🚫 anti-pattern) persiste em `references/felipe/<bucket>/<ref_id>.json` (verdito durável,
fonte = pack), atualiza o status no pack JSON e sincroniza `references` do ciclo ligado. Idempotente.

Regra-trava: enquanto não houver referência ⭐ principal, o Arquiteto fica bloqueado (ver cycles.py).
NUNCA toca geometria nem :8765 — só registra gosto curado.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tools.interior_studio import cycles

ROOT = Path(__file__).resolve().parents[2]
PACKS_DIR = ROOT / ".ai_bridge" / "reference_packs"
FELIPE_DIR = ROOT / "references" / "felipe"

# ação de curadoria -> status no pack
ACTIONS = {"approve": "approved", "reject": "rejected", "main": "main", "anti": "anti", "clear": "pending"}
# status -> pasta durável em references/felipe/
BUCKET = {"approved": "approved", "main": "approved", "rejected": "rejected", "anti": "anti_patterns"}


def _now(ts: float | None) -> float:
    return ts if ts is not None else time.time()


def pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def load_pack(pack_id: str) -> dict | None:
    p = pack_path(pack_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_pack(pack: dict) -> dict:
    pack_path(pack["pack_id"]).write_text(json.dumps(pack, ensure_ascii=False, indent=2), "utf-8")
    return pack


def _counts(pack: dict) -> dict:
    refs = pack.get("references", [])
    out = {"total": len(refs), "approved": 0, "rejected": 0, "main": 0, "anti": 0, "pending": 0}
    for r in refs:
        st = r.get("status", "pending")
        out[st] = out.get(st, 0) + 1
    return out


def pack_state(pack_id: str) -> dict:
    """Estado do pack pro dashboard (refs + status + contagens)."""
    pack = load_pack(pack_id)
    if not pack:
        return {"ok": False, "pack_id": pack_id, "references": [], "counts": {}}
    return {"ok": True, "pack_id": pack_id, "asset": pack.get("asset"), "theme": pack.get("theme"),
            "honesty": pack.get("honesty"), "direction": pack.get("direction"),
            "references": pack.get("references", []), "counts": _counts(pack)}


def _write_verdict(ref: dict, status: str, ts: float | None) -> str | None:
    bucket = BUCKET.get(status)
    if not bucket:  # pending/clear: remove verditos antigos
        for b in set(BUCKET.values()):
            old = FELIPE_DIR / b / f"{ref['id']}.json"
            if old.exists():
                old.unlink()
        return None
    d = FELIPE_DIR / bucket
    d.mkdir(parents=True, exist_ok=True)
    # ao reclassificar, limpa o bucket anterior pra não duplicar
    for b in set(BUCKET.values()):
        if b != bucket:
            old = FELIPE_DIR / b / f"{ref['id']}.json"
            if old.exists():
                old.unlink()
    rec = {"id": ref["id"], "title": ref.get("title"), "link": ref.get("link"),
           "type": ref.get("type"), "status": status, "is_main": status == "main",
           "comment": ref.get("comment", ""), "curated_at": _now(ts),
           "copy": ref.get("copy"), "avoid": ref.get("avoid")}
    p = d / f"{ref['id']}.json"
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), "utf-8")
    return str(p.relative_to(ROOT))


def _sync_cycle(pack_id: str, pack: dict, cycle_id: str | None) -> None:
    """Reescreve cycle.references a partir do status real do pack (idempotente)."""
    if not cycle_id:
        c = cycles.current_cycle()
        cycle_id = c.get("cycle_id") if c else None
    if not cycle_id:
        return
    c = cycles.get_cycle(cycle_id)
    if not c:
        return
    refs = pack.get("references", [])
    by = {"approved": [], "rejected": [], "main": [], "anti": []}
    for r in refs:
        st = r.get("status", "pending")
        if st == "main":
            by["main"].append(r["id"])
            by["approved"].append(r["id"])
        elif st in ("approved", "rejected", "anti"):
            by[st].append(r["id"])
    c["references"] = {"pack_id": pack_id, **by}
    cycles.save_cycle(c)


def curate(pack_id: str, ref_id: str, action: str, comment: str | None = None,
           cycle_id: str | None = None, ts: float | None = None) -> dict:
    """Aplica uma ação de curadoria do Felipe a uma referência."""
    status = ACTIONS.get(action)
    if status is None:
        return {"ok": False, "error": f"ação inválida: {action}"}
    pack = load_pack(pack_id)
    if not pack:
        return {"ok": False, "error": f"pack não encontrado: {pack_id}"}
    ref = next((r for r in pack.get("references", []) if r.get("id") == ref_id), None)
    if not ref:
        return {"ok": False, "error": f"referência não encontrada: {ref_id}"}
    # ⭐ principal é exclusivo: zera o main anterior
    if status == "main":
        for r in pack["references"]:
            if r.get("status") == "main" and r["id"] != ref_id:
                r["status"] = "approved"
                _write_verdict(r, "approved", ts)
    ref["status"] = status
    if comment is not None:
        ref["comment"] = comment.strip()[:300]
    verdict_path = _write_verdict(ref, status, ts)
    save_pack(pack)
    _sync_cycle(pack_id, pack, cycle_id)
    return {"ok": True, "pack_id": pack_id, "ref_id": ref_id, "status": status,
            "verdict_path": verdict_path, "counts": _counts(pack)}


def ensure_felipe_dirs() -> None:
    for b in ("approved", "rejected", "anti_patterns", "golden_samples"):
        (FELIPE_DIR / b).mkdir(parents=True, exist_ok=True)
