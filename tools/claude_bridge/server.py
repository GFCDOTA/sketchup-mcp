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

Limites (reforçados no system prompt): NUNCA aprovar mutação de fixture canônica
(Hard Rule #3) nem dar veredito visual IMPROVED/SAME/WORSE -> Verdict: NEEDS-HUMAN.

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CLAUDE_TIMEOUT = 240  # segundos por resposta; estoura -> erro 500, nunca trava infinito

SYSTEM = """You are the CLAUDE ORACLE answering a decision question from a Claude Code \
session working on the repo `sketchup-mcp` (PDF floorplan -> faithful SketchUp .skp).
Answer ONLY in this format, no markdown fences, no fluff:

- Verdict: GO / NO-GO / NEEDS-HUMAN / MORE-INFO
- Reasoning: 2-4 sentences, technical, critical (no rubber-stamping)
- Risks: bullets
- Suggested next action: 1-2 lines, start with the single highest-leverage step

HARD BOUNDARIES (never cross — the asker's project rules):
- NEVER approve mutating a canonical fixture (fixtures/quadrado, fixtures/planta_74,
  consensus.json). That needs the human's explicit OK -> answer Verdict: NEEDS-HUMAN.
- NEVER give a visual fidelity verdict (IMPROVED/SAME/WORSE) — that is the human's or
  GPT-via-Chrome's call -> Verdict: NEEDS-HUMAN.
- Prefer fixing root causes (data/extraction) over piling workarounds in the builder.
"""


def claude_bin() -> str:
    return shutil.which("claude") or shutil.which("claude.cmd") or "claude"


def ask_claude(question: str) -> str:
    """Roda `claude -p` headless com SYSTEM + a pergunta. Devolve o texto ou levanta."""
    prompt = SYSTEM + "\n\n=== QUESTION ===\n\n" + question
    if sys.platform == "win32":
        # npm instala claude como .CMD -> precisa de shell; prompt vai por STDIN (sem quoting)
        cmd = f'"{claude_bin()}" -p --output-format text'
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              timeout=CLAUDE_TIMEOUT, shell=True)
    else:
        proc = subprocess.run([claude_bin(), "-p", "--output-format", "text"],
                              input=prompt, capture_output=True, text=True,
                              timeout=CLAUDE_TIMEOUT)
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(f"resposta vazia (stderr: {(proc.stderr or '')[:300]})")
    low = out.lower()
    if "not logged in" in low or "please run /login" in low:
        raise RuntimeError("claude headless NAO autenticado — rode `claude setup-token` "
                           "e exporte CLAUDE_CODE_OAUTH_TOKEN")
    return out


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
            self._send(200, {"status": "ok", "oracle": "claude"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            prompt = (payload.get("prompt") or "").strip()
            if not prompt:
                self._send(400, {"error": "campo 'prompt' vazio"})
                return
            self._send(200, {"response": ask_claude(prompt)})
        except Exception as e:  # devolve erro honesto; nao fabrica resposta
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass  # silencia o log default do http.server


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

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"claude-bridge HTTP em http://{args.host}:{args.port} (/health, POST /ask) | claude={claude_bin()}")
    print("Ctrl+C pra parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nparando.")
        srv.shutdown()


if __name__ == "__main__":
    main()
