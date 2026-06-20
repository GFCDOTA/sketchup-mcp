"""studio_log.py — barramento de ATIVIDADE do INTERIOR_STUDIO (feed pro dashboard vivo).

Cada agente (nossos: orchestrator/pm/designer/scout; locais: ollama/deepseek/qwen) posta o que
está fazendo aqui; a dashboard :8782 lê o tail e mostra carinha + status + última fala, estilo chat.
Quem orquestra (a sessão principal) posta em volta de cada dispatch/consulta — visibilidade honesta
do que está rolando enquanto se programa.

Uso:
    python tools/studio_log.py post designer working "decidindo a paleta da cozinha"
    python tools/studio_log.py post designer done "parede [60,58,54] quente, mata a caverna"
    python tools/studio_log.py tail 20
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY = ROOT / "artifacts/reference_lab/studio_activity.jsonl"
VALID_STATUS = {"idle", "working", "thinking", "done", "blocked", "error", "waiting"}


def post(agent: str, status: str, message: str, to: str | None = None,
         ts: float | None = None) -> dict:
    ACTIVITY.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": ts if ts is not None else time.time(), "agent": agent,
           "status": status if status in VALID_STATUS else "working", "message": message}
    if to:
        rec["to"] = to   # destinatário -> a dashboard desenha a seta de conversa
    with ACTIVITY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def talk(frm: str, to: str, message: str) -> dict:
    """Atalho: um agente FALANDO com outro (status=working + campo `to`)."""
    return post(frm, "working", message, to=to)


def tail(n: int = 40) -> list[dict]:
    if not ACTIVITY.exists():
        return []
    lines = ACTIVITY.read_text("utf-8", "ignore").splitlines()[-n:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def latest_by_agent() -> dict:
    """Último status/fala de cada agente (pra o card de status na dashboard)."""
    last = {}
    for rec in tail(400):
        last[rec["agent"]] = rec
    return last


def main(argv=None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if not a:
        print(__doc__)
        return 0
    if a[0] == "post" and len(a) >= 4:
        rec = post(a[1], a[2], " ".join(a[3:]))
        print("posted:", rec["agent"], rec["status"])
    elif a[0] == "talk" and len(a) >= 4:
        rec = talk(a[1], a[2], " ".join(a[3:]))
        print("talk:", rec["agent"], "->", rec.get("to"))
    elif a[0] == "tail":
        n = int(a[1]) if len(a) > 1 else 40
        for r in tail(n):
            print(f"[{r['agent']:<22}] {r['status']:<8} {r['message']}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
