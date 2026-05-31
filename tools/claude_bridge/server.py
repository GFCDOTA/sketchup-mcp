#!/usr/bin/env python3
r"""
claude-bridge — oracle CLAUDE via HTTP, drop-in do ChatGPT bridge (:8765).

Contexto: `tools/ask_gpt_gate.py` consulta um bridge por HTTP:
    GET  localhost:8765/health
    POST localhost:8765/ask {"prompt": "..."}  -> {"response": "..."}
Este server atende esse MESMO contrato usando `claude -p` (headless) como motor — ou
seja, o CLAUDE responde as consultas de decisão da sessão automaticamente, na
ASSINATURA (sem API key). Suba na 8765 (parando o ChatGPT bridge antes) e o gate passa
a falar com o Claude sem nenhuma mudança.

Auth: `claude -p` headless precisa de um token OAuth. Rode `claude setup-token` e
exporte CLAUDE_CODE_OAUTH_TOKEN (o start.ps1 carrega de um `.oauth_token` local, que é
gitignorado — NUNCA commitar o token).

Política (no system prompt): MODO B — autonomia delegada. O oracle decide sozinho
(técnico / fixture / merges) com base em evidência determinística; o ÚNICO gate humano
é Verdict: VISUAL_REVIEW, quando a APARÊNCIA da planta muda e só o olho do humano valida
vs o PDF. Nunca dá veredito visual IMPROVED/SAME/WORSE sozinho.

Uso:
    python server.py                 # serve em 127.0.0.1:8765
    python server.py --port 8766     # outra porta
    python server.py --selftest      # testa a chamada ao claude e sai (sem servir)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLAUDE_TIMEOUT = 240  # segundos por resposta; estoura -> erro 500, nunca trava infinito

SYSTEM = """You are the CLAUDE ORACLE for the sketchup-mcp fidelity project. The human (Felipe)
delegated FULL AUTONOMY to you for everything EXCEPT the visual look of the plant ("modo B").
DECIDE — never punt to the human except for VISUAL_REVIEW.

Answer ONLY in this format, no fences, no fluff:
- Verdict: GO / NO-GO / MORE-INFO / VISUAL_REVIEW
- Confidence: high / medium / low
- Reasoning: 2-4 sentences, technical, critical
- Assumptions: bullets — what you ASSUMED or could NOT verify from the prompt
- Risks: bullets
- Suggested next action: 1-2 lines, highest-leverage first

Confidence + Assumptions are MANDATORY (gate framework §6.4): the asker uses your
`assumptions` to decide what to re-check deterministically vs accept. A factual
claim about something you cannot see in the prompt belongs in `assumptions`
(low/medium confidence), never stated as fact.

FILE-FETCH (§6.3): when a decision hinges on a file you were NOT given (a
consensus.json, geometry_report.json, a test), do NOT guess its contents — answer
Verdict: MORE-INFO and add a line `Need-files: <comma-separated repo paths>`. The
asker re-sends the prompt with those files (read-only) so you can decide on facts.

DECIDE AUTONOMOUSLY (no human): technical / architectural / A-B-C / refactor / gates /
consensus & fixture regeneration / merges -- based on the DETERMINISTIC evidence given
(overlay_diff vs PDF, opening_host_audit, pytest). Prefer fixing root causes over workarounds.

THE ONLY HUMAN GATE = VISUAL_REVIEW: use it ONLY when a change alters the plant's APPEARANCE such
that only a human eye can validate it vs the PDF (geometry/render/representation changed, or a
regenerated fixture is about to be PROMOTED to canonical). Then Verdict: VISUAL_REVIEW and state
exactly what before/after-vs-PDF to show Felipe. Do NOT give IMPROVED/SAME/WORSE yourself
(proven unreliable -- negative_dogfood); that is Felipe's call once summoned.
"""


def claude_bin() -> str:
    return shutil.which("claude") or shutil.which("claude.cmd") or "claude"


def ask_claude(question: str) -> str:
    """Roda `claude -p` headless com SYSTEM + a pergunta. Devolve o texto ou levanta."""
    prompt = SYSTEM + "\n\n=== QUESTION ===\n\n" + question
    # cwd NEUTRO (temp, FORA do repo): claude -p nao carrega o CLAUDE.md/hooks deste
    # projeto -> sem prompt de permissao e, critico, sem disparar o SessionStart hook
    # que sobe ESTE bridge (recursao). Model+effort pinados: Opus 4.8 + xhigh (o JUIZ).
    workdir = tempfile.gettempdir()
    if sys.platform == "win32":
        # npm instala claude como .CMD -> precisa de shell; prompt vai por STDIN (sem quoting)
        cmd = (f'"{claude_bin()}" -p --model claude-opus-4-8 --effort xhigh '
               f'--output-format text')
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_TIMEOUT, shell=True, cwd=workdir)
    else:
        proc = subprocess.run([claude_bin(), "-p", "--model", "claude-opus-4-8",
                               "--effort", "xhigh", "--output-format", "text"],
                              input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_TIMEOUT, cwd=workdir)
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(f"resposta vazia (stderr: {(proc.stderr or '')[:300]})")
    low = out.lower()
    if "not logged in" in low or "please run /login" in low:
        raise RuntimeError("claude headless NAO autenticado — rode `claude setup-token` "
                           "e exporte CLAUDE_CODE_OAUTH_TOKEN")
    return out


# ---- /ask + /health contract (spec gate_framework §6.5) ------------
ASK_FIELDS = ("prompt", "question")
VERDICT_ENUM = ("GO", "NO-GO", "MORE-INFO", "VISUAL_REVIEW")


def parse_ask_payload(raw: bytes) -> str:
    """Extract the question text from a raw /ask body.

    - UTF-8 TOLERANT: ``errors="replace"`` — a stray non-ASCII byte (the bridge
      once 500'd on the "ã" in "NÃO") must never crash the request.
    - FLEXIBLE FIELD: accepts ``prompt`` OR ``question`` so the caller does not
      have to guess (the consuming session discovered the field by trial/error).
    Returns the stripped text, or "" if absent/blank.
    """
    if not raw:
        return ""
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        return ""
    for field in ASK_FIELDS:
        val = data.get(field)
        if val:
            return str(val).strip()
    return ""


REDTEAM_PREFIX = (
    "RED-TEAM MODE (gate framework §6.2). The asker probably already leans toward "
    "one option — do NOT just rank. First argue the STRONGEST case AGAINST the "
    "option that looks preferred and name the failure mode that would make it "
    "wrong; only then give your Verdict. If the preferred option still wins after "
    "you steelman the opposition, say so explicitly. This exists to counter the "
    "agreement bias of one Claude consulting another."
)


def parse_ask_mode(raw: bytes) -> str:
    """Extract the optional `mode` from an /ask body (e.g. 'redteam'). '' if none."""
    if not raw:
        return ""
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("mode") or "").strip().lower()


def apply_mode(prompt: str, mode: str) -> str:
    """Wrap the question per mode. `redteam` prepends a steelman-the-opposition
    instruction; any other / empty mode is a no-op."""
    if mode == "redteam" and prompt:
        return f"{REDTEAM_PREFIX}\n\n=== DECISION ===\n\n{prompt}"
    return prompt


def health_payload() -> dict:
    """Self-documenting /health: exposes the /ask contract (which field to send,
    what verdicts come back) so the caller never reverse-engineers it."""
    return {
        "status": "ok",
        "oracle": "claude",
        "ask_field": list(ASK_FIELDS),
        "verdict_enum": list(VERDICT_ENUM),
        "modes": ["default", "redteam"],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._send(200, health_payload())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            prompt = parse_ask_payload(body)
            if not prompt:
                self._send(400, {"error": "empty question (send 'prompt' or 'question')"})
                return
            question = apply_mode(prompt, parse_ask_mode(body))
            self._send(200, {"response": ask_claude(question)})
        except Exception as e:  # devolve erro honesto; nao fabrica resposta
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass  # silencia o log default do http.server


class Server(ThreadingHTTPServer):
    # allow_reuse_address=False: no Windows o SO_REUSEADDR deixaria 2+ servers bindarem
    # o mesmo :8765 (zumbis empilhados respondendo com SYSTEM velho). Com False, um
    # segundo start FALHA ALTO (OSError) em vez de empilhar silenciosamente.
    allow_reuse_address = False


def main():
    ap = argparse.ArgumentParser(description="Claude oracle HTTP (drop-in do :8765)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--selftest", action="store_true",
                    help="testa ask_claude e sai (sem subir o servidor)")
    args = ap.parse_args()

    if args.selftest:
        try:
            print(f"selftest OK | resposta={ask_claude('Reply ONLY with the single word: PONG')[:160]!r}")
        except Exception as e:
            print(f"selftest FALHOU: {e}")
        return

    try:
        srv = Server((args.host, args.port), Handler)
    except OSError as e:
        print(f"NAO subiu em {args.host}:{args.port} (ja em uso? outro server no ar): {e}")
        return
    print(f"claude-bridge HTTP em http://{args.host}:{args.port} (/health, POST /ask) | claude={claude_bin()}")
    print("Ctrl+C pra parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nparando.")
        srv.shutdown()


if __name__ == "__main__":
    main()
