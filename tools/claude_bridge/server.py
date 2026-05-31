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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CLAUDE_TIMEOUT = 240  # segundos por resposta; estoura -> erro 500, nunca trava infinito
MODEL = "claude-opus-4-8"   # o JUIZ do modo B (Opus 4.8)
EFFORT = "xhigh"            # effort maximo
STARTED_AT = time.time()    # para o uptime no painel operacional

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
        cmd = (f'"{claude_bin()}" -p --model {MODEL} --effort {EFFORT} '
               f'--output-format text')
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_TIMEOUT, shell=True, cwd=workdir)
    else:
        proc = subprocess.run([claude_bin(), "-p", "--model", MODEL,
                               "--effort", EFFORT, "--output-format", "text"],
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
        "model": MODEL,
        "effort": EFFORT,
        "uptime_sec": round(time.time() - STARTED_AT, 1),
        "ask_field": list(ASK_FIELDS),
        "verdict_enum": list(VERDICT_ENUM),
        "modes": ["default", "redteam"],
        "endpoints": ["/", "/ask", "/health", "/heartbeat", "/sessions", "/events"],
    }


# --- session liveness orchestrator (gate spec section-5 audit-core, OBSERVE-ONLY) ---
# The gate is the chokepoint every session consults; sessions also POST a per-cycle
# heartbeat so we can tell PROGRESS from SILENCE (a session working hard but not
# consulting looks identical to a dead one). NO actor that kills/restarts peers.
# Collision PREVENTION is worktree isolation — a separate follow-up, not this.
STALL_SECONDS = 600     # no heartbeat in 10 min -> STALLED (liveness / wall clock)
PARALYZED_M = 3         # `cycle` unchanged across this many beats -> PARALYZED
AUDIT_PATH = Path(__file__).resolve().parents[2] / ".ai_bridge" / "audit" / "audit.jsonl"
_SESSIONS: dict = {}
_SESSIONS_LOCK = threading.Lock()


def _audit_append(event: dict) -> None:
    """Best-effort append to the audit-core log; never break a request on a log write."""
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def record_heartbeat(session_id: str, cycle, last_action: str = "") -> dict:
    """Record a per-cycle heartbeat. `cycle` is the monotonic PROGRESS token — the one
    signal that tells alive-and-progressing apart from alive-but-stuck."""
    now = time.time()
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(session_id, {"cycle": None, "unchanged": 0})
        s["unchanged"] = s["unchanged"] + 1 if s["cycle"] == cycle else 0
        s["cycle"] = cycle
        s["last_seen"] = now
        s["last_action"] = last_action  # human-readability only, never a flag input
        _SESSIONS[session_id] = s
    _audit_append({"t": now, "kind": "heartbeat", "session_id": session_id,
                   "cycle": cycle, "last_action": last_action})
    return {"recorded": session_id, "cycle": cycle}


def sessions_view() -> dict:
    """Read model: each session + derived flags. STALLED = silent too long;
    PARALYZED = still beating but `cycle` frozen (the case passive logging is blind to)."""
    now = time.time()
    out = {}
    with _SESSIONS_LOCK:
        for sid, s in _SESSIONS.items():
            flags = []
            if (now - s.get("last_seen", 0)) > STALL_SECONDS:
                flags.append("STALLED")
            if s.get("unchanged", 0) >= PARALYZED_M:
                flags.append("PARALYZED")
            out[sid] = {
                "cycle": s.get("cycle"),
                "age_sec": round(now - s.get("last_seen", now), 1),
                "unchanged_beats": s.get("unchanged", 0),
                "last_action": s.get("last_action", ""),
                "flags": flags or ["OK"],
            }
    return out


def recent_events(limit: int = 80) -> list:
    """Tail of the audit-core log (heartbeats + consults), oldest-to-newest.
    Powers the operational dashboard 'when was it called' feed."""
    try:
        lines = AUDIT_PATH.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


# Operational dashboard served by the gate itself (no external stack): polls
# /health + /sessions + /events every 5s. If this page won't load, the gate is down.
DASHBOARD_HTML = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Claude Gate - Operacional</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--txt:#e6edf3;--dim:#8b949e;
--ok:#3fb950;--bad:#f85149;--warn:#d29922;--accent:#58a6ff;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
header{display:flex;align-items:center;gap:16px;padding:16px 24px;border-bottom:1px solid var(--line);flex-wrap:wrap;}
h1{font-size:18px;margin:0;font-weight:600;}
.badge{padding:6px 14px;border-radius:20px;font-weight:700;letter-spacing:.5px;}
.badge.on{background:rgba(63,185,80,.15);color:var(--ok);border:1px solid var(--ok);}
.badge.off{background:rgba(248,81,73,.15);color:var(--bad);border:1px solid var(--bad);}
.wrap{padding:24px;display:grid;gap:20px;grid-template-columns:1fr 1fr;max-width:1100px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin:0 0 12px;}
.kv{display:flex;justify-content:space-between;padding:3px 0;gap:12px;}
.kv span:first-child{color:var(--dim);}
table{width:100%;border-collapse:collapse;font-size:13px;}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);}
th{color:var(--dim);font-weight:500;}
.flag{padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;}
.flag.OK{background:rgba(63,185,80,.15);color:var(--ok);}
.flag.STALLED{background:rgba(210,153,34,.15);color:var(--warn);}
.flag.PARALYZED{background:rgba(248,81,73,.15);color:var(--bad);}
.feed{max-height:280px;overflow:auto;}
.ev{display:flex;gap:10px;padding:4px 0;border-bottom:1px solid #21262d;font-size:12px;}
.ev .t{color:var(--dim);white-space:nowrap;}
.ev .k{font-weight:700;}
.ev .k.consult{color:var(--accent);}
.ev .k.heartbeat{color:var(--dim);}
.timeline{display:flex;gap:3px;flex-wrap:wrap;}
.dot{width:12px;height:12px;border-radius:3px;background:var(--line);}
.dot.up{background:var(--ok);}
.dot.down{background:var(--bad);}
.full{grid-column:1 / -1;}
.pipe{display:flex;align-items:stretch;gap:6px;flex-wrap:wrap;}
.stg{flex:1;min-width:84px;background:#0d1117;border:1px solid var(--line);border-radius:8px;padding:10px 6px;text-align:center;font-size:12px;font-weight:600;display:flex;flex-direction:column;justify-content:center;}
.stg small{display:block;color:var(--dim);font-weight:400;margin-top:4px;font-size:10px;}
.stg.pdf{border-color:#6e7681;}
.stg.human{border-color:var(--warn);background:rgba(210,153,34,.08);}
.stg.auto{border-color:var(--accent);background:rgba(88,166,255,.07);}
.stg.gate{border-color:var(--ok);background:rgba(63,185,80,.07);}
.stg.ok{border-color:var(--ok);background:rgba(63,185,80,.15);}
.arr{display:flex;align-items:center;color:var(--dim);font-size:18px;}
.legend{margin-top:12px;display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--dim);align-items:center;}
.lg{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:middle;}
.lg.auto{background:rgba(88,166,255,.6);}
.lg.human{background:rgba(210,153,34,.7);}
.lg.gate{background:rgba(63,185,80,.6);}
.lg.ok{background:var(--ok);}
footer{padding:0 24px 24px;color:var(--dim);font-size:12px;}
</style></head><body>
<header><h1>&#127899; Claude Gate - Operacional</h1>
<span id="status" class="badge off">CHECANDO...</span>
<span id="updated" style="color:var(--dim);font-size:12px;"></span></header>
<div class="wrap">
<div class="card full"><h2>Pipeline PDF -&gt; SKP (como o sketchup-mcp processa)</h2>
<div class="pipe">
<div class="stg pdf">PDF<small>planta</small></div><div class="arr">&#8594;</div>
<div class="stg human">anotacao<small>HUMANO</small></div><div class="arr">&#8594;</div>
<div class="stg auto">consensus.json<small>walls/openings/rooms</small></div><div class="arr">&#8594;</div>
<div class="stg auto">build_shell<small>.py shapely</small></div><div class="arr">&#8594;</div>
<div class="stg auto">.skp + renders<small>.rb SketchUp</small></div><div class="arr">&#8594;</div>
<div class="stg gate">gates det.<small>opening_host/overlay</small></div><div class="arr">&#8594;</div>
<div class="stg human">VISUAL_REVIEW<small>HUMANO vs PDF</small></div><div class="arr">&#8594;</div>
<div class="stg ok">artifacts/<small>deliverable</small></div>
</div>
<div class="legend"><span><span class="lg auto"></span>automatico</span><span><span class="lg human"></span>gate humano</span><span><span class="lg gate"></span>deterministico (ground truth)</span><span><span class="lg ok"></span>entrega</span></div>
<div style="margin-top:10px;color:var(--dim);font-size:12px;">O oraculo :8765 (modo B, Opus 4.8) decide as bifurcacoes tecnicas ao longo do fluxo. So o VISUAL_REVIEW sobe pro humano.</div></div>
<div class="card"><h2>Health</h2><div id="health"></div></div>
<div class="card"><h2>Health timeline</h2><div id="timeline" class="timeline"></div>
<div style="margin-top:10px;color:var(--dim);font-size:12px;">verde=online | vermelho=offline | refresh 5s</div></div>
<div class="card full"><h2>Sessoes (orquestrador)</h2>
<table><thead><tr><th>session</th><th>cycle</th><th>idade</th><th>beats iguais</th><th>ultima acao</th><th>flags</th></tr></thead>
<tbody id="sessions"></tbody></table></div>
<div class="card full"><h2>Atividade (consults + heartbeats)</h2><div id="feed" class="feed"></div></div>
</div>
<footer>Servido pelo proprio gate em :8765 - sem stack externa</footer>
<script>
const hist=[];
function fmtAge(s){if(s==null)return '-';if(s<90)return s+'s';if(s<5400)return Math.round(s/60)+'m';return Math.round(s/3600)+'h';}
function fmtTime(t){try{return new Date(t*1000).toLocaleTimeString('pt-br');}catch(e){return '';}}
function kv(k,v){return '<div class="kv"><span>'+k+'</span><span>'+v+'</span></div>';}
async function tick(){
let online=false,health=null;
try{const r=await fetch('/health',{cache:'no-store'});health=await r.json();online=r.ok;}catch(e){online=false;}
const b=document.getElementById('status');
b.className='badge '+(online?'on':'off');b.textContent=online?'ONLINE':'OFFLINE';
document.getElementById('updated').textContent='atualizado '+new Date().toLocaleTimeString('pt-br');
hist.push(online);if(hist.length>60)hist.shift();
document.getElementById('timeline').innerHTML=hist.map(u=>'<div class="dot '+(u?'up':'down')+'"></div>').join('');
if(health){document.getElementById('health').innerHTML=
kv('oracle',health.oracle)+kv('model',health.model||'-')+kv('effort',health.effort||'-')+
kv('uptime',fmtAge(health.uptime_sec))+kv('modes',(health.modes||[]).join(', '))+
kv('endpoints',(health.endpoints||[]).join(' '));}
else{document.getElementById('health').innerHTML='<div style="color:var(--bad)">sem resposta do /health</div>';}
if(!online)return;
try{const s=await (await fetch('/sessions',{cache:'no-store'})).json();
const rows=Object.entries(s).map(function(e){var id=e[0],v=e[1];
return '<tr><td>'+id+'</td><td>'+(v.cycle==null?'-':v.cycle)+'</td><td>'+fmtAge(v.age_sec)+'</td><td>'+(v.unchanged_beats||0)+'</td><td>'+(v.last_action||'')+'</td><td>'+(v.flags||[]).map(f=>'<span class="flag '+f+'">'+f+'</span>').join(' ')+'</td></tr>';}).join('');
document.getElementById('sessions').innerHTML=rows||'<tr><td colspan=6 style="color:var(--dim)">nenhuma sessao batendo ponto ainda</td></tr>';}catch(e){}
try{const ev=await (await fetch('/events',{cache:'no-store'})).json();
document.getElementById('feed').innerHTML=ev.slice().reverse().map(function(e){
var extra=e.kind==='consult'?('mode='+(e.mode||'default')+' | '+(e.dur_sec==null?'?':e.dur_sec)+'s | q'+(e.q_chars==null?'?':e.q_chars)):('cycle='+(e.cycle==null?'?':e.cycle)+' | '+(e.session_id||'')+' '+(e.last_action||''));
return '<div class="ev"><span class="t">'+fmtTime(e.t)+'</span><span class="k '+e.kind+'">'+e.kind+'</span><span>'+extra+'</span></div>';}).join('')||'<div style="color:var(--dim)">sem atividade ainda</div>';}catch(e){}
}
tick();setInterval(tick,5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.rstrip("/")
        if p == "" or p == "/dashboard":
            self._send_html(DASHBOARD_HTML)
        elif p == "/health":
            self._send(200, health_payload())
        elif p == "/sessions":
            self._send(200, sessions_view())
        elif p == "/events":
            self._send(200, recent_events())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path == "/heartbeat":
            self._heartbeat()
            return
        if path != "/ask":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            prompt = parse_ask_payload(body)
            if not prompt:
                self._send(400, {"error": "empty question (send 'prompt' or 'question')"})
                return
            mode = parse_ask_mode(body)
            question = apply_mode(prompt, mode)
            t0 = time.time()
            answer = ask_claude(question)
            _audit_append({"t": time.time(), "kind": "consult",
                           "mode": mode or "default", "q_chars": len(prompt),
                           "a_chars": len(answer), "dur_sec": round(time.time() - t0, 1)})
            self._send(200, {"response": answer})
        except Exception as e:  # devolve erro honesto; nao fabrica resposta
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def _heartbeat(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8", "replace")) if n else {}
            sid = str((data or {}).get("session_id") or "").strip()
            if not sid:
                self._send(400, {"error": "heartbeat needs session_id"})
                return
            self._send(200, record_heartbeat(
                sid, data.get("cycle"), str(data.get("last_action") or "")))
        except Exception as e:
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
