"""gpt_review.py — GATE de GPT_REVIEW (Modo B) para mudancas de APARENCIA.

Felipe: o GPT e o VALIDADOR. Toda mudanca visual (render/SKP) PASSA por este gate antes de
ser promovida. O gate NUNCA autojulga (proibido IMPROVED/SAME/WORSE local). A volta do GPT
(texto no schema Modo B) e a UNICA fonte do veredito.

Fluxo (agent-in-the-loop — o round-trip usa a sessao ChatGPT autenticada no Chrome do Felipe,
nao da p/ ser 100% headless; o resto e deterministico e logado):

  1. prepare  -> seta o clipboard com a imagem (setclip.ps1 -STA) + imprime o PROMPT Modo B
                 canonico + grava um review PENDING no ledger.
  2. (o agente cola no ChatGPT via Chrome MCP, captura o texto do veredito, salva num .txt)
  3. record   -> parseia o texto do schema -> structured -> append no ledger JSONL + gpt_verdicts.md;
                 decide o GATE: PASS|WARN -> promove (WARN vira backlog); FAIL -> BLOCK (nao promove).

Ledger (append-only): artifacts/review/interior/gpt_review_ledger.jsonl
Espelho humano:        artifacts/review/interior/gpt_verdicts.md

Uso:
  python tools/gpt_review.py prepare --id sala_eyefill3 --image <png> --context "..." [--dims A,B,C]
  python tools/gpt_review.py record  --id sala_eyefill3 --verdict-file <txt>
  python tools/gpt_review.py show     [--id <id>]            # lista o ledger
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "artifacts/review/interior/gpt_review_ledger.jsonl"
VERDICTS_MD = ROOT / "artifacts/review/interior/gpt_verdicts.md"
SETCLIP = ROOT / ".claude/scratch/setclip.ps1"

# Dimensoes default do schema Modo B (premium de interiores). Override com --dims.
DEFAULT_DIMS = ["PREMIUM_REALISM", "MATERIALS", "LIGHTING", "CAMERA", "FURNITURE_DETAIL"]
GATE_VALUES = ("PASS", "WARN", "FAIL")


def build_prompt(context: str, dims) -> str:
    """Prompt canonico Modo B: TEXTO puro, schema fixo, SEM gerar imagem/redesenhar."""
    dim_line = " // ".join(f"{d}:" for d in dims)
    return (
        "MODO B, SO TEXTO, SEM IMAGEM, SEM REDESENHAR, SEM FERRAMENTA DE IMAGEM. "
        f"Avalie a imagem (render) que envio. CONTEXTO: {context} "
        "Responda SO neste schema, em texto puro: "
        f"VERDICT: PASS|WARN|FAIL // {dim_line} // "
        "TOP_3_ISSUES: 1) 2) 3) // NEXT_ACTION: a UNICA acao de maior ROI."
    )


def _val(token: str) -> str:
    """Extrai PASS|WARN|FAIL de um trecho (primeiro que aparecer)."""
    m = re.search(r"\b(PASS|WARN|FAIL)\b", token.upper())
    return m.group(1) if m else "?"


def parse_verdict(text: str, dims) -> dict:
    """Parseia o texto do schema Modo B -> {verdict, dims:{}, top_issues:[], next_action}.
    Robusto a '//' OU quebras de linha como separador."""
    norm = text.replace("\r", "\n")
    norm = re.sub(r"\s*//\s*", "\n", norm)            # '//' -> newline
    keys = ["VERDICT"] + list(dims) + ["TOP_3_ISSUES", "TOP_ISSUES", "NEXT_ACTION"]
    # captura KEY: valor (ate a proxima KEY conhecida ou fim)
    out = {"verdict": "?", "dims": {}, "top_issues": [], "next_action": ""}
    key_alt = "|".join(re.escape(k) for k in keys)
    for m in re.finditer(rf"(?im)^\s*({key_alt})\s*[:\-]\s*(.+?)(?=\n\s*(?:{key_alt})\s*[:\-]|\Z)",
                         norm, re.S):
        k, v = m.group(1).upper(), m.group(2).strip()
        if k == "VERDICT":
            out["verdict"] = _val(v)
        elif k in ("TOP_3_ISSUES", "TOP_ISSUES"):
            issues = re.split(r"\s*\d\)\s*", v)
            out["top_issues"] = [s.strip(" .;\n") for s in issues if s.strip(" .;\n")][:3]
        elif k == "NEXT_ACTION":
            out["next_action"] = v.strip()
        else:
            out["dims"][k] = {"status": _val(v), "note": v.strip()}
    return out


def gate_decision(parsed: dict) -> dict:
    """Decisao do GATE a partir do veredito do GPT (NUNCA local).
    gate = VERDICT do GPT. FAIL ou qualquer dimensao FAIL -> BLOCK (nao promove).
    WARN -> promove mas registra backlog. PASS -> promove."""
    verdict = parsed.get("verdict", "?")
    dim_fail = [d for d, x in parsed.get("dims", {}).items() if x.get("status") == "FAIL"]
    if verdict == "FAIL" or dim_fail:
        return {"gate": "FAIL", "promote": False,
                "reason": f"VERDICT={verdict}" + (f"; dims FAIL={dim_fail}" if dim_fail else "")}
    if verdict == "WARN":
        warns = [d for d, x in parsed.get("dims", {}).items() if x.get("status") == "WARN"]
        return {"gate": "WARN", "promote": True, "reason": f"WARN (backlog: {warns})"}
    if verdict == "PASS":
        return {"gate": "PASS", "promote": True, "reason": "PASS"}
    return {"gate": "UNKNOWN", "promote": False, "reason": "VERDICT nao parseado — revisar manualmente"}


def _append_ledger(entry: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def cmd_prepare(a):
    img = Path(a.image)
    if not img.exists():
        print(f"ERRO: imagem nao existe: {img}"); return 2
    dims = a.dims.split(",") if a.dims else DEFAULT_DIMS
    # seta o clipboard com a imagem (powershell -STA), p/ colar no ChatGPT
    clip_ok = False
    if SETCLIP.exists():
        r = subprocess.run(["powershell", "-STA", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", str(SETCLIP), "-Path", str(img)], capture_output=True, text=True)
        clip_ok = (r.returncode == 0)
        print(r.stdout.strip() or r.stderr.strip())
    _append_ledger({"ts": _ts(), "id": a.id, "status": "PENDING", "artifact": str(img),
                    "context": a.context, "dims": dims, "clip_ok": clip_ok})
    print("\n=== GPT_REVIEW :: PROMPT MODO B (cole no ChatGPT junto da imagem) ===")
    print(build_prompt(a.context, dims))
    print("=== (clipboard " + ("OK" if clip_ok else "FALHOU") + f") id={a.id} ===")
    return 0


def cmd_record(a):
    text = Path(a.verdict_file).read_text("utf-8", "ignore") if a.verdict_file else (a.text or "")
    if not text.strip():
        print("ERRO: sem texto de veredito (--verdict-file ou --text)"); return 2
    dims = a.dims.split(",") if a.dims else DEFAULT_DIMS
    parsed = parse_verdict(text, dims)
    gate = gate_decision(parsed)
    entry = {"ts": _ts(), "id": a.id, "status": "REVIEWED", "artifact": a.image or "",
             "verdict": parsed["verdict"], "dims": parsed["dims"],
             "top_issues": parsed["top_issues"], "next_action": parsed["next_action"],
             "gate": gate["gate"], "promote": gate["promote"], "reason": gate["reason"],
             "raw": text.strip()}
    _append_ledger(entry)
    _mirror_md(entry)
    print(f"\n=== GPT_REVIEW :: GATE = {gate['gate']} (promote={gate['promote']}) ===")
    print(f"id={a.id}  VERDICT={parsed['verdict']}")
    for d, x in parsed["dims"].items():
        print(f"  {d}: {x['status']}")
    if parsed["next_action"]:
        print(f"NEXT_ACTION: {parsed['next_action']}")
    print(f"reason: {gate['reason']}")
    if not gate["promote"]:
        print(">>> GATE BLOQUEIA promocao: corrigir antes de promover o artefato.")
    return 0 if gate["promote"] else 1


def _mirror_md(entry: dict):
    if not VERDICTS_MD.exists():
        return
    dims = " · ".join(f"{d}:{x['status']}" for d, x in entry["dims"].items())
    block = (f"\n### GPT_REVIEW [{entry['ts']}] id={entry['id']} → GATE **{entry['gate']}**\n"
             f"- artifact: `{Path(entry['artifact']).name if entry['artifact'] else '?'}`\n"
             f"- VERDICT: **{entry['verdict']}** · {dims}\n"
             f"- NEXT_ACTION: {entry['next_action']}\n")
    with VERDICTS_MD.open("a", encoding="utf-8") as f:
        f.write(block)


def cmd_show(a):
    if not LEDGER.exists():
        print("(ledger vazio)"); return 0
    for line in LEDGER.read_text("utf-8").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if a.id and e.get("id") != a.id:
            continue
        st = e.get("gate") or e.get("status")
        print(f"[{e.get('ts')}] {e.get('id'):<22} {st:<8} {e.get('verdict','')}  "
              f"{Path(e.get('artifact','')).name}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="GATE GPT_REVIEW (Modo B) p/ mudancas de aparencia")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="seta clipboard + imprime prompt + grava PENDING")
    p.add_argument("--id", required=True); p.add_argument("--image", required=True)
    p.add_argument("--context", default=""); p.add_argument("--dims", default="")
    p.set_defaults(fn=cmd_prepare)
    r = sub.add_parser("record", help="parseia veredito do GPT + decide gate + loga")
    r.add_argument("--id", required=True)
    r.add_argument("--verdict-file"); r.add_argument("--text"); r.add_argument("--image", default="")
    r.add_argument("--dims", default="")
    r.set_defaults(fn=cmd_record)
    s = sub.add_parser("show", help="lista o ledger")
    s.add_argument("--id", default=""); s.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
