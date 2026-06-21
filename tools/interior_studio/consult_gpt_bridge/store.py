"""store.py — persistência local do Consult GPT Bridge (stdlib only, offline).

Árvore (`.ai_bridge/interior_consult/`):
  outbox/   <ts>_<slug>.json + .md   — perguntas geradas pelo Arquiteto
  inbox/    <ts>_<slug>_answer.md    — respostas coladas pelo Felipe (cru)
  answered/ <question_id>.md         — respostas já ingeridas (arquivadas)
  ingested/ <question_id>.json       — aprendizado extraído (record)
  failed/   <ts>_<slug>.md           — respostas que falharam o parse
  logs/     events.jsonl             — trilha append-only

Determinismo: a única dependência de clock é o prefixo de timestamp dos arquivos, INJETÁVEL via `ts`
(os handlers passam o tempo real; os testes passam fixo). O resto é I/O puro.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONSULT = ROOT / ".ai_bridge" / "interior_consult"
SUBDIRS = ("outbox", "inbox", "answered", "ingested", "failed", "logs")


def ensure_dirs() -> None:
    for d in SUBDIRS:
        (CONSULT / d).mkdir(parents=True, exist_ok=True)


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (s or "q").strip())
    return (s.strip("_") or "q")[:48]


def _rel(p: Path) -> str:
    """Caminho relativo à raiz do repo p/ logs/respostas amigáveis. Robusto se CONSULT for redirecionado
    pra fora do repo (testes)."""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _ts(ts: str | None) -> str:
    return ts or time.strftime("%Y%m%dT%H%M%S")


def _log(event: str, **kw) -> None:
    ensure_dirs()
    rec = {"event": event, **kw}
    with (CONSULT / "logs" / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def save_question(contract: dict, *, ts: str | None = None) -> dict:
    """Grava a pergunta no outbox como .json (canônico) + .md (pra copiar)."""
    from tools.interior_studio.consult_gpt_bridge import contracts as C
    ensure_dirs()
    qid = contract.get("question_id") or "q"
    stem = f"{_ts(ts)}_{_slug(qid)}"
    jp = CONSULT / "outbox" / f"{stem}.json"
    mp = CONSULT / "outbox" / f"{stem}.md"
    jp.write_text(json.dumps(contract, ensure_ascii=False, indent=2), "utf-8")
    mp.write_text(C.render_question_md(contract), "utf-8")
    _log("question_saved", question_id=qid, json=_rel(jp))
    return {"question_id": qid, "json_path": _rel(jp), "md_path": _rel(mp)}


def save_answer(question_id: str, raw_md: str, *, ts: str | None = None) -> dict:
    """Grava a resposta crua (colada pelo Felipe) no inbox."""
    ensure_dirs()
    stem = f"{_ts(ts)}_{_slug(question_id)}_answer"
    p = CONSULT / "inbox" / f"{stem}.md"
    p.write_text(raw_md or "", "utf-8")
    _log("answer_saved", question_id=question_id, path=_rel(p))
    return {"question_id": question_id, "path": _rel(p)}


def _newest(dir_name: str, pattern: str) -> Path | None:
    d = CONSULT / dir_name
    if not d.is_dir():
        return None
    files = sorted(d.glob(pattern))   # nomes começam com ts ordenável
    return files[-1] if files else None


def latest_question() -> dict | None:
    p = _newest("outbox", "*.json")
    if not p:
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def latest_answer() -> dict | None:
    p = _newest("inbox", "*_answer.md")
    if not p:
        return None
    raw = p.read_text("utf-8")
    return {"path": _rel(p), "raw": raw}


def pending_questions() -> list[dict]:
    """Perguntas no outbox que ainda não têm record ingerido."""
    out = []
    done = {p.stem for p in (CONSULT / "ingested").glob("*.json")} if (CONSULT / "ingested").is_dir() else set()
    for p in sorted((CONSULT / "outbox").glob("*.json")) if (CONSULT / "outbox").is_dir() else []:
        try:
            c = json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if c.get("question_id") not in done:
            out.append({"question_id": c.get("question_id"), "mode": c.get("mode"),
                        "room": c.get("room"), "phase": c.get("phase"), "created_at": c.get("created_at")})
    return out


def counts() -> dict:
    def _n(d, pat):
        return len(list((CONSULT / d).glob(pat))) if (CONSULT / d).is_dir() else 0
    return {"ingested": _n("ingested", "*.json"), "failed": _n("failed", "*.md")}


def mark_ingested(question_id: str, record: dict, raw_md: str | None = None) -> dict:
    """Salva o aprendizado extraído em ingested/<id>.json e arquiva a resposta em answered/<id>.md."""
    ensure_dirs()
    ip = CONSULT / "ingested" / f"{_slug(question_id)}.json"
    ip.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    if raw_md is not None:
        (CONSULT / "answered" / f"{_slug(question_id)}.md").write_text(raw_md, "utf-8")
    _log("ingested", question_id=question_id, verdict=record.get("verdict"))
    return {"path": _rel(ip)}


def mark_failed(question_id: str, raw_md: str, reason: str, *, ts: str | None = None) -> dict:
    ensure_dirs()
    p = CONSULT / "failed" / f"{_ts(ts)}_{_slug(question_id)}.md"
    p.write_text(f"<!-- parse failed: {reason} -->\n\n{raw_md or ''}", "utf-8")
    _log("failed", question_id=question_id, reason=reason)
    return {"path": _rel(p)}
