"""answer_parser.py — parseia o ARCHITECT_ANSWER_CONTRACT (markdown do Consult GPT) em struct.

Tolerante (o GPT varia o markdown). Aceita JSON direto também. Lógica PURA e determinística.
"""
from __future__ import annotations

import json
import re

_VERDICT_RE = re.compile(r"\b(PASS|WARN|FAIL)\b")
_NUM_ITEM_RE = re.compile(r"^\s*\d+\.\s*(.+)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")


def parse_answer(raw: str) -> dict:
    """raw (md ou json) -> dict no shape do answer_contract (best-effort). Inclui `_warnings`."""
    if not raw or not raw.strip():
        return {"_warnings": ["resposta vazia"]}
    s = raw.strip()
    # JSON direto?
    if s[:1] in "{[":
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                obj.setdefault("_warnings", [])
                return obj
        except Exception:  # noqa: BLE001
            pass
    sections = _split_sections(s)
    warnings: list[str] = []

    out: dict = {
        "question_id": _meta(s, "question_id"),
        "answered_at": _meta(s, "answered_at"),
        "consultant": _meta(s, "consultant") or "Consult GPT",
        "verdict": None,
        "summary": "",
        "question_answers": [],
        "top_fix": "",
        "keep": [], "change": [], "dont_do": [],
        "dna_updates": [], "anti_patterns": [],
        "next_microtask": {}, "next_render_prompt": "",
    }

    vsec = _find(sections, "veredito")
    out["verdict"] = _first_verdict(vsec or s)
    out["summary"] = _clean_text(vsec)

    qa_sec = _find(sections, "respostas", "dúvidas", "duvidas")
    out["question_answers"] = _parse_qa(qa_sec)

    out["keep"] = _bullets(_find(sections, "manter"))
    out["change"] = _bullets(_find(sections, "alterar"))
    out["dont_do"] = _bullets(_find(sections, "não fazer", "nao fazer"))
    out["dna_updates"] = _bullets(_find(sections, "felipe style dna", "atualização", "atualizacao"))
    out["anti_patterns"] = _bullets(_find(sections, "anti-pattern", "anti pattern", "antipattern"))
    out["next_microtask"] = _parse_microtask(_find(sections, "próxima microtarefa", "proxima microtarefa", "microtarefa"))
    out["next_render_prompt"] = _first_code_or_text(_find(sections, "prompt curto", "próximo render", "proximo render"))

    # top_fix = "ajuste número 1" das dúvidas, senão a 1ª linha de change
    for qa in out["question_answers"]:
        if "ajuste" in (qa.get("id") or "").lower():
            out["top_fix"] = qa.get("note") or out["top_fix"]
    if not out["top_fix"] and out["change"]:
        out["top_fix"] = out["change"][0]

    if not out["verdict"]:
        warnings.append("veredito não encontrado")
    if not out["question_answers"]:
        warnings.append("respostas às dúvidas não encontradas")
    out["_warnings"] = warnings
    return out


# ------------------------------------------------------------------ helpers
def _split_sections(s: str) -> list[tuple[str, str]]:
    """Quebra por headers '## ...' -> [(titulo_lower, corpo)]."""
    parts = re.split(r"(?m)^\#{1,6}\s+(.+?)\s*$", s)
    out = []
    # parts = [pre, title1, body1, title2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip().lower(), parts[i + 1]))
    return out


def _find(sections: list[tuple[str, str]], *keys: str) -> str | None:
    for title, body in sections:
        if any(k in title for k in keys):
            return body
    return None


def _meta(s: str, key: str) -> str | None:
    m = re.search(rf"(?im)^[-*\s]*{re.escape(key)}\s*:\s*`?([^`\n]+?)`?\s*$", s)
    return m.group(1).strip() if m else None


def _first_verdict(text: str | None) -> str | None:
    if not text:
        return None
    m = _VERDICT_RE.search(text)
    return m.group(1) if m else None


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    lines = [ln.strip(" `") for ln in text.strip().splitlines() if ln.strip(" `>")]
    # remove uma linha que seja só o token de veredito
    lines = [ln for ln in lines if not re.fullmatch(r"(PASS|WARN|FAIL)\s*[|/\s]*", ln, re.I)]
    return " ".join(lines).strip()[:600]


def _bullets(text: str | None) -> list[str]:
    if not text:
        return []
    out = []
    for ln in text.splitlines():
        m = _BULLET_RE.match(ln)
        if m:
            v = m.group(1).strip(" `")
            if v and not v.lower().startswith(("item", "anti-pattern", "regra", "preferência", "preferencia", "token visual")):
                out.append(v)
    return out


def _label_to_id(label: str) -> str:
    low = (label or "").strip().lower()
    if "ajuste" in low:
        return "ajuste_1"
    m = re.search(r"[a-z_]+_check", low)
    if m:
        return m.group(0)
    s = re.sub(r"[^a-z0-9]+", "_", low).strip("_")
    return s[:30] or "q"


def _parse_qa(text: str | None) -> list[dict]:
    """Agrupa cada item numerado (inclui linhas de continuação — o GPT às vezes põe o veredito na
    linha seguinte) e extrai id/veredito/nota tolerante a label multi-palavra ('ajuste número 1')."""
    if not text:
        return []
    items: list[str] = []
    cur = None
    for ln in text.splitlines():
        if _NUM_ITEM_RE.match(ln):
            if cur is not None:
                items.append(cur)
            cur = ln.strip()
        elif cur is not None and ln.strip():
            cur += " " + ln.strip()
    if cur is not None:
        items.append(cur)
    out = []
    for raw in items:
        item = _NUM_ITEM_RE.match(raw).group(1).strip()
        label, sep, rest = item.partition(":")
        cid = _label_to_id(label) if sep else f"q{len(out)+1}"
        body = rest if sep else item
        verdict = _first_verdict(body)
        note = _VERDICT_RE.sub("", body).strip(" -—:`")
        out.append({"id": cid, "verdict": verdict or "N/A", "note": note})
    return out


def _parse_microtask(text: str | None) -> dict:
    if not text:
        return {}
    mt = {}
    title = _kv(text, "título", "titulo", "title")
    if title:
        mt["title"] = title
        idm = re.search(r"(MT-[\w-]+)", title)
        if idm:
            mt["id"] = idm.group(1)
    desc = _kv(text, "descrição", "descricao", "description")
    if desc:
        mt["description"] = desc
    acc = _sub_bullets(text, "critério", "criterio", "aceite")
    if acc:
        mt["acceptance"] = acc
    files = _sub_bullets(text, "arquivos")
    if files:
        mt["likely_files"] = files
    return mt


def _kv(text: str, *keys: str) -> str | None:
    """Valor de um rótulo 'k:'. Aceita inline ('Título: X') E rótulo sozinho com o valor na linha
    seguinte ('Título:\\n`X`') — formato que o ChatGPT usa bastante."""
    lines = text.splitlines()
    for k in keys:
        kp = re.escape(k)
        for i, ln in enumerate(lines):
            m = re.match(rf"(?i)^[-*\s]*{kp}\s*:\s*`?([^`\n]+?)`?\s*$", ln)
            if m and m.group(1).strip():
                return m.group(1).strip()
            if re.match(rf"(?i)^[-*\s]*{kp}\s*:?\s*$", ln):   # rótulo sozinho -> próxima linha não-vazia
                for nxt in lines[i + 1:]:
                    if nxt.strip():
                        return nxt.strip().strip("`* ")
                    continue
    return None


def _sub_bullets(text: str, *keys: str) -> list[str]:
    """Bullets que aparecem DEPOIS de uma linha-rótulo (ex.: 'Critério de aceite:')."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if any(k in ln.lower() for k in keys) and ln.rstrip().endswith(":"):
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for ln in lines[start:]:
        m = _BULLET_RE.match(ln)
        if m:
            v = m.group(1).strip(" `")
            if v.endswith(":"):   # nova sub-label (ex.: "Arquivos prováveis:") -> para aqui
                break
            out.append(v)
        elif ln.strip() and not ln.startswith((" ", "\t")):
            break
    return out


def _first_code_or_text(text: str | None) -> str:
    if not text:
        return ""
    m = re.search(r"`([^`]+)`", text)
    if m:
        return m.group(1).strip()
    return _clean_text(text)[:300]
