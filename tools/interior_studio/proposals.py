"""proposals.py — fila de PROPOSALS dos workers locais (GPT: 'nada entra direto; Felipe aprova').

Cada proposta de um agente local (programa de mobiliário do Arquiteto, gap do Auditor, etc.) vira um arquivo
em .ai_bridge/proposals/{pending,approved,rejected}/. requires_approval=True sempre. id determinístico
(idempotente: re-propor sobrescreve o pending). stdlib only; sem clock/random na lógica.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PDIR = ROOT / ".ai_bridge/proposals"
STATUSES = ("pending", "approved", "rejected")


def _dir(status: str) -> Path:
    p = PDIR / status
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(proposal: dict) -> dict:
    """Salva (ou sobrescreve) uma proposta como PENDING. Exige 'id'."""
    pid = proposal["id"]
    proposal.setdefault("requires_approval", True)
    (_dir("pending") / f"{pid}.json").write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2), "utf-8")
    return proposal


def _load(status: str) -> list[dict]:
    out = []
    d = PDIR / status
    if d.exists():
        for f in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(f.read_text("utf-8")))
            except Exception:  # noqa: BLE001
                pass
    return out


def state() -> dict:
    return {s: _load(s) for s in STATUSES}


def _move(pid: str, frm: str, to: str) -> dict | None:
    src = PDIR / frm / f"{pid}.json"
    if not src.exists():
        return None
    data = json.loads(src.read_text("utf-8"))
    data["status"] = to
    (_dir(to) / f"{pid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    src.unlink()
    return data


def approve(pid: str) -> dict | None:
    return _move(pid, "pending", "approved")


def reject(pid: str) -> dict | None:
    return _move(pid, "pending", "rejected")


def approved_program(environment: str) -> dict | None:
    """O furniture_program APROVADO de um cômodo (pro inventário dinâmico ler)."""
    for p in _load("approved"):
        if p.get("type") == "furniture_program" and p.get("environment") == environment:
            return p
    return None
