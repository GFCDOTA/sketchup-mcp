"""cycles.py — entidade CYCLE de primeira classe do Interior Studio (stdlib, offline).

Cada ciclo = uma microtarefa rastreável em `.ai_bridge/interior_cycles/CYCLE-NNN.json`, com a
timeline canônica de etapas: PM → Team Lead → Reference Scout → Felipe(curadoria) → Architect →
Gates → Consult Liaison → Learning. O dashboard :8782 lê isto pra mostrar a VERDADE DO PROCESSO
(não chat solto). NUNCA toca o oráculo :8765 nem geometria congelada — só rastreia o processo.

Determinismo: a única dependência de clock é o `ts` dos eventos, INJETÁVEL (handlers passam o real;
testes passam fixo). O resto é I/O puro e idempotente.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CYCLES_DIR = ROOT / ".ai_bridge" / "interior_cycles"

# As 8 etapas canônicas da esteira (ordem fixa). Cada ciclo carrega o status real de cada uma.
STEP_ORDER = ["PM", "Team Lead", "Reference Scout", "Felipe", "Architect",
              "Gates", "Consult Liaison", "Learning"]
STEP_FACE = {"PM": "🦙", "Team Lead": "🤖", "Reference Scout": "🔭", "Felipe": "🧑",
             "Architect": "🐳", "Gates": "✅", "Consult Liaison": "🔌", "Learning": "📚"}
# status visuais: done · doing · waiting · blocked · pending · na (não aplicável)
STATUS_ICON = {"done": "✓", "doing": "⚙", "waiting": "⏳", "blocked": "⛔",
               "pending": "—", "na": "·"}


def _dir() -> Path:
    CYCLES_DIR.mkdir(parents=True, exist_ok=True)
    return CYCLES_DIR


def _now(ts: float | None) -> float:
    return ts if ts is not None else time.time()


def list_cycles() -> list[dict]:
    out = []
    for p in sorted(_dir().glob("CYCLE-*.json")):
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def get_cycle(cid: str) -> dict | None:
    p = _dir() / f"{cid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cycle(c: dict) -> dict:
    (_dir() / f"{c['cycle_id']}.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), "utf-8")
    return c


def next_id() -> str:
    n = 0
    for c in list_cycles():
        m = re.search(r"(\d+)", c.get("cycle_id", ""))
        if m:
            n = max(n, int(m.group(1)))
    return f"CYCLE-{n + 1:03d}"


def current_cycle() -> dict | None:
    """O ciclo ATIVO: o de maior número que não está fechado; senão o último."""
    cs = list_cycles()
    if not cs:
        return None
    closed = {"done", "frozen", "archived"}
    active = [c for c in cs if c.get("status") not in closed]
    pool = active or cs
    return sorted(pool, key=lambda c: c.get("cycle_id", ""))[-1]


def new_cycle(*, asset: str, microtask: str, mode: str, title: str = "", room: str = "living",
              project: str = "planta_74", status: str = "running", next_action: str = "",
              cycle_id: str | None = None, ts: float | None = None) -> dict:
    cid = cycle_id or next_id()
    c = {
        "cycle_id": cid, "project": project, "room": room, "asset": asset,
        "microtask": microtask, "title": title, "mode": mode, "status": status,
        "next_action": next_action, "created_at": _now(ts),
        "steps": [], "references": {"pack_id": None, "approved": [], "rejected": [], "main": [], "anti": []},
        "gates": {}, "consult": {"question_id": None, "answer_id": None, "ingested": False},
        "learning": {"new_rules": [], "anti_patterns": [], "golden_samples": []},
    }
    return save_cycle(c)


def set_step(cid: str, agent: str, status: str, summary: str = "", *, model: str | None = None,
             files: list | None = None, ts: float | None = None) -> dict | None:
    """Registra/atualiza uma etapa do ciclo (idempotente por agente)."""
    c = get_cycle(cid)
    if not c:
        return None
    step = next((s for s in c["steps"] if s.get("agent") == agent), None)
    if step is None:
        step = {"agent": agent}
        c["steps"].append(step)
    step.update({"status": status, "summary": summary[:400], "ts": _now(ts)})
    if model is not None:
        step["model"] = model
    if files is not None:
        step["files"] = files
    return save_cycle(c)


def set_status(cid: str, status: str, next_action: str | None = None) -> dict | None:
    c = get_cycle(cid)
    if not c:
        return None
    c["status"] = status
    if next_action is not None:
        c["next_action"] = next_action
    return save_cycle(c)


def architect_blocked(c: dict) -> bool:
    """Regra-trava: o Arquiteto NÃO constrói sem referência ⭐ principal curada pelo Felipe."""
    refs = c.get("references") or {}
    return not (refs.get("main") or [])


def timeline(c: dict) -> list[dict]:
    """As 8 etapas canônicas com o status real do ciclo (merge do que foi registrado + regras)."""
    recorded = {s.get("agent"): s for s in c.get("steps", [])}
    blocked = architect_blocked(c)
    out = []
    for agent in STEP_ORDER:
        s = dict(recorded.get(agent, {}))
        st = s.get("status")
        if not st:
            # default por etapa quando ainda não registrada
            if agent == "Felipe":
                refs = c.get("references") or {}
                curated = (refs.get("approved") or []) + (refs.get("main") or []) + (refs.get("anti") or [])
                st = "done" if refs.get("main") else ("doing" if curated else "waiting")
            elif agent == "Architect":
                st = "blocked" if blocked else "pending"
            elif agent == "Gates":
                st = "na"
            elif agent == "Consult Liaison":
                st = "done" if (c.get("consult") or {}).get("ingested") else "pending"
            elif agent == "Learning":
                lr = c.get("learning") or {}
                st = "done" if (lr.get("new_rules") or lr.get("anti_patterns") or lr.get("golden_samples")) else "pending"
            else:
                st = "pending"
        out.append({"agent": agent, "face": STEP_FACE.get(agent, "•"),
                    "status": st, "icon": STATUS_ICON.get(st, "•"),
                    "summary": s.get("summary", ""), "model": s.get("model", ""),
                    "files": s.get("files", [])})
    return out


def next_step(c: dict) -> dict:
    """A PRÓXIMA ETAPA CORRETA do ciclo (não um 'rodar ciclo' genérico). `actionable`=tem botão;
    senão é ação do Felipe (curar)."""
    refs = c.get("references") or {}
    consult = c.get("consult") or {}
    if not refs.get("pack_id"):
        return {"kind": "scout", "label": "🔭 Rodar Scout (buscar referências)", "actionable": True}
    if not refs.get("main"):
        return {"kind": "curate", "label": "⭐ Você: escolher 1–2 referências PRINCIPAIS no Reference Pack",
                "actionable": False}
    if not consult.get("ingested"):
        return {"kind": "consult", "label": "🔌 Gerar pergunta pro Consult GPT → SOFA_BUILD_SPEC",
                "actionable": True}
    return {"kind": "build", "label": "▶ Gerar Build Spec / construir (pós-curadoria)", "actionable": True}


def factory_state() -> dict:
    """Resumo pro topo do dashboard (barra de fábrica) + timeline do ciclo atual."""
    c = current_cycle()
    if not c:
        return {"has_cycle": False, "cycles": []}
    cards = [{"cycle_id": x.get("cycle_id"), "asset": x.get("asset"), "microtask": x.get("microtask"),
              "title": x.get("title"), "status": x.get("status")}
             for x in sorted(list_cycles(), key=lambda y: y.get("cycle_id", ""), reverse=True)]
    return {
        "has_cycle": True,
        "cycle_id": c.get("cycle_id"), "project": c.get("project"), "room": c.get("room"),
        "asset": c.get("asset"), "microtask": c.get("microtask"), "title": c.get("title"),
        "mode": c.get("mode"), "status": c.get("status"), "next_action": c.get("next_action"),
        "architect_blocked": architect_blocked(c),
        "references": c.get("references") or {}, "timeline": timeline(c),
        "consult": c.get("consult") or {}, "learning": c.get("learning") or {},
        "next_step": next_step(c), "cycles": cards,
    }
