"""ingest.py — converte a resposta do Consult GPT em APRENDIZADO persistente e versionável.

answer -> (1) regras novas no felipe_style_dna.md (dedupe) · (2) anti-patterns no
felipe_visual_judge_rules.json (dedupe) · (3) próxima microtarefa em next_microtasks.md ·
(4) feedback por veredito em .ai_bridge/interior_feedback/ · (5) record em ingested/.

NUNCA move geometria / NUNCA toca PDF/golden — só escreve aprendizado de LINGUAGEM. Idempotente:
ingerir a mesma resposta 2× não duplica regra nem anti-pattern.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from tools.interior_studio.consult_gpt_bridge import answer_parser, contracts, store

ROOT = Path(__file__).resolve().parents[3]
FELIPE_DNA = ROOT / ".claude" / "memory" / "felipe_style_dna.md"
JUDGE_RULES = ROOT / "references" / "design_rules" / "felipe_visual_judge_rules.json"
FEEDBACK = ROOT / ".ai_bridge" / "interior_feedback"
NEXT_MT = ROOT / ".ai_bridge" / "interior_consult" / "next_microtasks.md"
DNA_SECTION = "## Aprendido via Consult GPT"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def ingest(question_id: str | None = None) -> dict:
    """Carrega a resposta (a mais recente, ou por question_id), parseia e aplica o aprendizado."""
    ans = store.latest_answer()
    if not ans:
        return {"ok": False, "error": "nenhuma resposta no inbox — cole a resposta primeiro"}
    raw = ans["raw"]
    parsed = answer_parser.parse_answer(raw)
    qid = question_id or parsed.get("question_id") or "sem_id"
    parsed["question_id"] = qid
    warns = contracts.validate_answer(parsed) + (parsed.get("_warnings") or [])
    return apply_learning(parsed, qid, raw, warns)


def apply_learning(parsed: dict, question_id: str, raw_md: str | None, warns: list[str] | None = None) -> dict:
    """Aplica o aprendizado já parseado (IO). Separado de ingest() para testar com paths injetáveis."""
    rules_added = _apply_dna(parsed.get("dna_updates") or [], question_id)
    aps_added = _apply_anti_patterns(parsed.get("anti_patterns") or [], question_id)
    nm = parsed.get("next_microtask") or {}
    if nm.get("title"):
        _append_microtask(nm, parsed.get("verdict"), question_id)
    fb_path = _write_feedback(parsed, question_id)
    record = {
        "question_id": question_id,
        "verdict": parsed.get("verdict"),
        "summary": parsed.get("summary"),
        "top_fix": parsed.get("top_fix"),
        "question_answers": parsed.get("question_answers"),
        "rules_added": rules_added,
        "anti_patterns_added": aps_added,
        "next_microtask": nm,
        "next_render_prompt": parsed.get("next_render_prompt"),
        "feedback_path": fb_path,
        "warnings": warns or [],
    }
    store.mark_ingested(question_id, record, raw_md)
    return {"ok": True, **record}


def _apply_dna(updates: list[str], question_id: str) -> list[str]:
    if not updates:
        return []
    FELIPE_DNA.parent.mkdir(parents=True, exist_ok=True)
    text = FELIPE_DNA.read_text("utf-8") if FELIPE_DNA.exists() else ""
    existing = _norm(text)
    added = [u for u in updates if _norm(u) and _norm(u) not in existing]
    if not added:
        return []
    if DNA_SECTION not in text:
        text = text.rstrip() + f"\n\n{DNA_SECTION}\n"
    extra = "".join(f"- {u.strip()} _(Consult GPT · {question_id})_\n" for u in added)
    # insere logo após o header da seção (mantém o resto do arquivo)
    idx = text.index(DNA_SECTION) + len(DNA_SECTION)
    nl = text.find("\n", idx)
    text = text[:nl + 1] + extra + text[nl + 1:]
    FELIPE_DNA.write_text(text, "utf-8")
    return added


def _apply_anti_patterns(aps: list[str], question_id: str) -> list[str]:
    if not aps or not JUDGE_RULES.exists():
        if aps and not JUDGE_RULES.exists():
            return []  # judge file ausente; não fabrica
        return []
    data = json.loads(JUDGE_RULES.read_text("utf-8"))
    arr = data.setdefault("anti_patterns", [])
    have = {_norm(a.get("what", "")) for a in arr}
    added = []
    n = len(arr)
    for ap in aps:
        if _norm(ap) and _norm(ap) not in have:
            n += 1
            arr.append({"id": f"ap_consult_{n}", "what": ap.strip(), "why": "Consult GPT", "from": question_id})
            have.add(_norm(ap))
            added.append(ap.strip())
    if added:
        JUDGE_RULES.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return added


def _append_microtask(nm: dict, verdict: str | None, question_id: str) -> None:
    NEXT_MT.parent.mkdir(parents=True, exist_ok=True)
    if not NEXT_MT.exists():
        NEXT_MT.write_text("# Próximas microtarefas (do Consult GPT)\n\n", "utf-8")
    block = [f"\n## {nm.get('id') or 'MT'} — {nm.get('title','').strip()}",
             f"- origem: Consult GPT · {question_id} · veredito {verdict or '?'}"]
    if nm.get("description"):
        block.append(f"- descrição: {nm['description'].strip()}")
    for a in nm.get("acceptance") or []:
        block.append(f"- aceite: {a}")
    for f in nm.get("likely_files") or []:
        block.append(f"- arquivo provável: {f}")
    with NEXT_MT.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(block) + "\n")


def _write_feedback(parsed: dict, question_id: str) -> str:
    verdict = (parsed.get("verdict") or "").upper()
    bucket = {"PASS": "approved", "FAIL": "rejected"}.get(verdict, "corrections")
    d = FEEDBACK / bucket
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{store._slug(question_id)}.md"
    lines = [f"# Feedback — {question_id}", f"- veredito: {verdict or '?'}",
             f"- resumo: {parsed.get('summary','')}", f"- correção nº1: {parsed.get('top_fix','')}", ""]
    if parsed.get("anti_patterns"):
        lines += ["## Anti-patterns"] + [f"- {a}" for a in parsed["anti_patterns"]] + [""]
    if parsed.get("dna_updates"):
        lines += ["## DNA updates"] + [f"- {a}" for a in parsed["dna_updates"]]
    p.write_text("\n".join(lines), "utf-8")
    return store._rel(p)
