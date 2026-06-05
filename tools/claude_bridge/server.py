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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

REPO_ROOT = Path(__file__).resolve().parents[2]

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
        "endpoints": advertised_endpoints(),
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
# Estado das ACOES corretivas em andamento (process-consults roda em background).
_ACTIONS: dict = {}
_ACTIONS_LOCK = threading.Lock()


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
.docs details{border:1px solid var(--line);border-radius:6px;margin-bottom:6px;background:#0d1117;}
.docs summary{cursor:pointer;padding:8px 12px;font-weight:600;font-size:12px;color:var(--accent);}
.docs .d{padding:3px 14px 3px 26px;font-size:12px;border-top:1px solid #21262d;}
.docs .d code{color:var(--warn);background:rgba(210,153,34,.08);padding:1px 6px;border-radius:4px;margin-right:7px;}
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
<div class="card full"><h2>Diretorio .claude/ — o cerebro do projeto (clique pra expandir)</h2>
<div class="docs">
<details><summary>raiz</summary>
<div class="d"><code>CLAUDE.md</code>bootloader: missao, Hard Rules, ordem de carregamento</div>
<div class="d"><code>constitution.md</code>principios nao-negociaveis (#1 o .skp e o artefato; #8 no-skp-no-progress)</div>
<div class="d"><code>README.md</code>orientacao/indice do diretorio</div>
</details>
<details><summary>memory/ — memoria persistente (estado + regras vivas)</summary>
<div class="d"><code>project_context.md</code>o que e o projeto e onde esta</div>
<div class="d"><code>current_state.md</code>estado atual (feito / em andamento)</div>
<div class="d"><code>operational_rules.md</code>loop GREEN/YELLOW/RED e quando parar</div>
<div class="d"><code>git_workflow.md</code>develop-first; disciplina de branch/commit/PR</div>
<div class="d"><code>multi_agent_coordination.md</code>coordenacao entre sessoes/worktrees (nao clobberar)</div>
<div class="d"><code>artifact_policy.md</code>hierarquia runs/ vs artifacts/ vs fixtures/ + promotion</div>
<div class="d"><code>lessons_learned.md</code>licoes LL-NNN acumuladas (releia antes de repetir)</div>
<div class="d"><code>deprecated_context.md</code>o que ficou obsoleto (nao seguir)</div>
</details>
<details><summary>specs/ — especificacoes (o "como deve ser")</summary>
<div class="d"><code>product_goal.md</code>o objetivo: .skp fiel ao PDF</div>
<div class="d"><code>fidelity_gate.md</code>o que conta como fiel (campos do geometry_report)</div>
<div class="d"><code>skp_artifact_layout.md</code>paths/naming/metadata do .skp canonico</div>
<div class="d"><code>skp_proof_of_progress_gate.md</code>Constitution #8: sem SKP+evidencia, nao e progresso</div>
<div class="d"><code>gate_framework_and_audit.md</code>o gate de decisao §6 (oraculo/redteam/file-fetch/confidence/audit)</div>
<div class="d"><code>generalize_builder_constants.md</code>blueprint pra generalizar as constantes do builder</div>
<div class="d"><code>perfect_reference_strategy.md</code>PDF como ground truth</div>
<div class="d"><code>sdd_and_harness_engineering.md</code>spec-driven dev + engenharia do harness</div>
<div class="d"><code>repository_hygiene.md</code>higiene do repo (arquivar obsoletos)</div>
<div class="d"><code>templates/</code>4 templates: artifact_contract, feature_spec, fidelity_spec, regression_summary</div>
</details>
<details><summary>skills/ — 10 capacidades auto-descobertas (cada uma um SKILL.md)</summary>
<div class="d"><code>pdf-to-skp-pipeline</code>build do .skp a partir do consensus</div>
<div class="d"><code>fidelity-review</code>checklist SKP vs PDF (humano)</div>
<div class="d"><code>generate-and-compare-skp-after-change</code>gera SKP + compara before/after</div>
<div class="d"><code>skp-visual-self-correction</code>Visual Oracle Gate: floating door / orphan glass / etc</div>
<div class="d"><code>skp-artifact-management</code>promocao runs/ -&gt; artifacts/</div>
<div class="d"><code>gpt-auto-consult-gate</code>consulta o oraculo :8765 nas decisoes reais (9 triggers)</div>
<div class="d"><code>gh-autopilot</code>commit -&gt; PR -&gt; merge -&gt; cleanup via gh</div>
<div class="d"><code>repo-governance</code>PR/branch/merge/hygiene</div>
<div class="d"><code>multi-agent-handoff</code>coordenacao multi-agent/worktrees</div>
<div class="d"><code>autonomous-fidelity-loop</code>loop continuo de fidelidade (log por ciclo + heartbeat)</div>
</details>
<details><summary>evals/ — avaliacao</summary>
<div class="d"><code>eval_strategy.md</code>estrategia de avaliacao</div>
<div class="d"><code>fidelity_rubric.md</code>rubrica de fidelidade (eixos)</div>
<div class="d"><code>regression_matrix.md</code>matriz de regressao</div>
</details>
<details><summary>plans/ — planejamento</summary>
<div class="d"><code>active_work.md</code>trabalho ativo</div>
<div class="d"><code>next_actions.md</code>proximas acoes</div>
<div class="d"><code>roadmap.md</code>roadmap</div>
<div class="d"><code>stopped_work.md</code>trabalho pausado</div>
</details>
<details><summary>docs/ — documentacao + historico</summary>
<div class="d"><code>index.md</code>indice dos docs</div>
<div class="d"><code>2026-05-31_agentic_system_retro_roadmap.md</code>retro do sistema agentico + roadmap</div>
<div class="d"><code>adr/0001-...</code>ADR da arquitetura (gate + pipeline) — este sistema</div>
<div class="d"><code>audits/</code>3 auditorias (estrutura .claude, friction review, proof-of-progress)</div>
</details>
<details><summary>scratch/ — local-only (gitignored)</summary>
<div class="d">rascunhos descartaveis; nada importante vive aqui</div>
</details>
</div></div>
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


def dashboard_html() -> str:
    """Serve the multi-page SPA from dashboard.html (sibling file). Falls back to
    the inline single-page DASHBOARD_HTML if the file is missing."""
    try:
        return (Path(__file__).parent / "dashboard.html").read_text("utf-8")
    except OSError:
        return DASHBOARD_HTML


def skp_inventory() -> dict:
    """Scan the repo for .skp and classify by location so the 'Lixao' page can
    govern what is a deliverable vs evidence vs scratch vs orphan."""
    cats = {"deliverable": [], "review_evidence": [], "runs_scratch": [],
            "fixtures": [], "other": []}
    total_bytes = 0
    try:
        paths = list(REPO_ROOT.rglob("*.skp"))
    except OSError:
        paths = []
    for p in paths:
        try:
            rel = p.relative_to(REPO_ROOT).as_posix()
            size = p.stat().st_size
        except OSError:
            continue
        total_bytes += size
        item = {"path": rel, "mb": round(size / 1e6, 2)}
        if rel.startswith("artifacts/review/"):
            cats["review_evidence"].append(item)
        elif rel.startswith("artifacts/"):
            cats["deliverable"].append(item)
        elif rel.startswith("runs/"):
            cats["runs_scratch"].append(item)
        elif rel.startswith("fixtures/"):
            cats["fixtures"].append(item)
        else:
            cats["other"].append(item)
    for v in cats.values():
        v.sort(key=lambda it: it["mb"], reverse=True)
    return {"total": sum(len(v) for v in cats.values()),
            "total_mb": round(total_bytes / 1e6, 1), "categories": cats}


def plant_info() -> dict:
    """Canonical plants + their render PNGs (for the Planta page)."""
    art = REPO_ROOT / "artifacts"
    plants = {}
    if art.is_dir():
        for d in sorted(art.iterdir()):
            if d.is_dir() and d.name != "review":
                pngs = sorted(f"artifacts/{d.name}/{x.name}" for x in d.glob("*.png"))
                if pngs:
                    plants[d.name] = pngs
    return {"plants": plants}


def safe_artifact(rel: str):
    """Resolve `rel` to a real image UNDER artifacts/ or None. Read-only,
    allowlisted (image suffix), no traversal / no escape."""
    try:
        p = (REPO_ROOT / rel).resolve()
        p.relative_to((REPO_ROOT / "artifacts").resolve())
    except (ValueError, OSError):
        return None
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        return None
    return p if p.is_file() else None


def _first_user_text(jsonl: Path) -> str:
    """Best-effort: the first user input in a transcript (a human-readable descriptor)."""
    try:
        with jsonl.open("r", encoding="utf-8", errors="replace") as f:
            for _ in range(10):
                line = f.readline()
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") == "queue-operation" and obj.get("content"):
                    return str(obj["content"])[:140]
                m = obj.get("message")
                if isinstance(m, dict) and m.get("role") == "user":
                    c = m.get("content")
                    if isinstance(c, str):
                        return c[:140]
                    if isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and part.get("type") == "text":
                                return str(part.get("text", ""))[:140]
    except OSError:
        pass
    return ""


def claude_sessions() -> dict:
    """Real Claude Code sessions (~/.claude/projects) + derived state, so we can see
    if e.g. 'GPT bridge integration' is ACTIVE/IDLE/STOPPED, plus any consult that is
    still waiting on the gate (a question with no recorded response)."""
    proj = Path.home() / ".claude" / "projects"
    out = []
    if proj.is_dir():
        for d in proj.iterdir():
            if not d.is_dir():
                continue
            for js in d.glob("*.jsonl"):
                try:
                    age = time.time() - js.stat().st_mtime
                except OSError:
                    continue
                state = ("ACTIVE" if age < 300 else
                         "IDLE" if age < 3600 else "STOPPED")
                reason = ("rodando agora" if age < 300 else
                          "ociosa (sem escrita recente)" if age < 3600 else
                          "parada / encerrada")
                out.append({"id": js.stem[:8], "project": d.name,
                            "desc": _first_user_text(js), "reason": reason,
                            "idle_sec": round(age), "state": state})
    out.sort(key=lambda s: s["idle_sec"])
    qd = REPO_ROOT / ".ai_bridge" / "questions"
    rd = REPO_ROOT / ".ai_bridge" / "responses"
    pending = []
    if qd.is_dir():
        answered = {p.stem for p in rd.glob("*.md")} if rd.is_dir() else set()
        for q in sorted(qd.glob("*.md")):
            if q.stem not in answered:
                try:
                    a = round(time.time() - q.stat().st_mtime)
                except OSError:
                    a = 0
                pending.append({"q": q.stem, "age_sec": a})
    return {"sessions": out[:60], "total": len(out), "pending_gate": pending}


def ecosystem() -> dict:
    """Top-level of E:\\Claude (the machine ecosystem) for the docs page."""
    root = REPO_ROOT.parent
    items = []
    try:
        for p in sorted(root.iterdir()):
            items.append({"name": p.name, "dir": p.is_dir()})
    except OSError:
        pass
    return {"root": str(root), "items": items}


def recent_commits(n: int = 12) -> dict:
    """Recent develop commits so the dashboard shows the project is alive."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "--oneline", "-n", str(n),
             "origin/develop"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10)
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        lines = []
    return {"commits": lines}


def _read_jsonl(path: Path) -> list:
    """Tolerant JSONL read: skips blank/corrupt lines, never raises."""
    out = []
    try:
        for ln in path.read_text("utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


# Seed of the living difficulties backlog. The .ai_bridge/creator_difficulties.jsonl
# (if present) overrides this; otherwise this built-in seed is served. Every entry
# MUST carry why_not_fixed_yet — the field that turns "known problem" into "actionable".
_DEFAULT_DIFFICULTIES = [
    {"id": "DIFF-001", "titulo": "Consensus é autoria humana (sem extrator PDF→consensus)",
     "sintoma": "não há pipeline que extraia walls/openings de um PDF novo; raster+Hough fabricava parede falsa",
     "severidade": "HIGH", "status": "DEFERRED", "review_by": "2026-07-15",
     "why_not_fixed_yet": "extrator vetorial confiável é grande e arriscado; decidiu-se provar o loop manual em >=2 plantas antes de investir",
     "attempts": ["raster+Hough (abandonado: fabricava falsos)", "build_vector_consensus (abandonado)"],
     "gate_helped": "parcial", "next_hypothesis": "walls = filled paths do PDF, validado contra a planta_74 já anotada",
     "acceptance_criteria": "uma 2a planta gera consensus sem anotação manual e passa os gates determinísticos"},
    {"id": "DIFF-002", "titulo": "Escala precisa de âncora física",
     "sintoma": "PDF→metros sem uma dimensão real conhecida vira chute",
     "severidade": "HIGH", "status": "MITIGATED",
     "why_not_fixed_yet": "depende de input humano por planta (uma cota/espessura real) — é requisito de dado, não bug",
     "attempts": ["PT_TO_M = wall_thickness_pts/0.19 (planta_74)"],
     "gate_helped": "nao", "next_hypothesis": "plant.json carrega wall_thickness_m por planta; sem âncora = BLOCKED",
     "acceptance_criteria": "toda planta nova declara a âncora; nunca usar default 0.0254/72"},
    {"id": "DIFF-003", "titulo": "Fidelidade de abertura de janela (peitoril/verga)",
     "sintoma": "janela carved full-height ou vidro órfão/fora do lugar (ex.: banho 2)",
     "severidade": "MED", "status": "FIXED",
     "why_not_fixed_yet": "corrigido recentemente (528e302 usa espessura da wall hospedeira) — manter sob watch p/ regressão",
     "attempts": ["3D aperture path preservando peitoril+verga", "host-wall thickness fix (banho 2)"],
     "gate_helped": "sim", "next_hypothesis": "-",
     "acceptance_criteria": "window_apertures_3d == count(kind=window), sem vidro órfão"},
    {"id": "DIFF-004", "titulo": "Colisão de worktree multi-agent",
     "sintoma": "sessões dividindo 1 worktree movem o branch sob a outra; quase clobber",
     "severidade": "MED", "status": "OPEN",
     "why_not_fixed_yet": "o orquestrador só DETECTA (heartbeat/PARALYZED); o fix-raiz (lock/isolamento de worktree) é follow-up aberto, não implementado",
     "attempts": ["orquestrador de liveness (detecção)", "worktrees isolados (wt-dash/wt-gh)"],
     "gate_helped": "sim", "next_hypothesis": "/lock keyed por session_id + ownership de branch",
     "acceptance_criteria": "duas sessões rodam sem clobber; lock visível no painel"},
    {"id": "DIFF-005", "titulo": "Julgamento visual não é auto-confiável",
     "sintoma": "oracle de visão deu PASS em planta com parede externa apagada (negative_dogfood)",
     "severidade": "HIGH", "status": "MITIGATED",
     "why_not_fixed_yet": "LLM visual não pode ser ground truth — é decisão de design (só humano/GPT-Chrome valida), não bug a consertar",
     "attempts": ["visual oracle rebaixado a conselheiro", "overlay_diff determinístico decide"],
     "gate_helped": "sim", "next_hypothesis": "determinístico decide; visual só aconselha + VISUAL_REVIEW humano",
     "acceptance_criteria": "nenhum PASS visual auto-promove fixture; VISUAL_REVIEW obrigatório"},
    {"id": "DIFF-006", "titulo": "Constantes do builder hardcoded p/ planta_74",
     "sintoma": "alturas (2.70/0.90/2.10/1.10) e crop/escala fixos no build_plan_shell_skp",
     "severidade": "LOW", "status": "OPEN",
     "why_not_fixed_yet": "é o arquivo mais QUENTE (fidelidade em voo) e a config não tem consumidor até existir 2a planta = seria infra-pela-infra; blueprint pronto esperando a árvore esfriar",
     "attempts": ["blueprint generalize_builder_constants.md (groundwork não-colidente)"],
     "gate_helped": "sim", "next_hypothesis": "plant.json com heights/crop, defaults não-quebra, swap-in quando quieto",
     "acceptance_criteria": "planta_74 inalterada sem plant.json; 2a planta respeita os valores dela"},
]


def difficulties() -> dict:
    """Living difficulties backlog. Reads .ai_bridge/creator_difficulties.jsonl if
    present (appendable by sessions), else the built-in seed. Normalizes so EVERY
    entry has why_not_fixed_yet."""
    items = _read_jsonl(REPO_ROOT / ".ai_bridge" / "creator_difficulties.jsonl")
    src = "jsonl" if items else "builtin-seed"
    if not items:
        items = _DEFAULT_DIFFICULTIES
    norm = []
    for d in items:
        norm.append({
            "id": d.get("id", "DIFF-???"),
            "titulo": d.get("titulo") or d.get("title") or "?",
            "sintoma": d.get("sintoma", ""),
            "severidade": d.get("severidade", "MED"),
            "status": d.get("status", "OPEN"),
            "why_not_fixed_yet": d.get("why_not_fixed_yet") or "UNKNOWN — campo ausente, investigar",
            "attempts": d.get("attempts", []),
            "gate_helped": d.get("gate_helped", "?"),
            "next_hypothesis": d.get("next_hypothesis", "-"),
            "acceptance_criteria": d.get("acceptance_criteria", "-"),
            "review_by": d.get("review_by", ""),
        })
    return {"difficulties": norm, "total": len(norm), "source": src}


# Learning Loop seed — failure patterns turned into operational memory so the
# system stops repeating the same mistake. Every entry MUST have como_prevenir_regressao.
_DEFAULT_LEARNINGS = [
    {"id": "FP-031", "falha_observada": "visual oracle deu PASS em planta com parede externa apagada",
     "causa_provavel": "LLM de visão não distingue ausência estrutural sutil + viés de concordância",
     "como_detectamos": "negative_dogfood (fixtures corrompidas de propósito + teste de discriminação)",
     "como_corrigimos": "rebaixar o oracle visual a conselheiro; overlay_diff determinístico vira o juiz",
     "como_prevenir_regressao": "detector DETERMINÍSTICO decide; visual só aconselha; VISUAL_REVIEW humano pra promover",
     "artefato": "tools/overlay_diff.py + tools/negative_dogfood.py + LL nos memory", "status": "APPLIED"},
    {"id": "LL-034", "falha_observada": "gate framework §6 (multi-oracle/redteam/confidence) landou VERDE mas DESPLUGADO do caller real",
     "causa_provavel": "módulos + testes unitários, sem teste de integração que prove o wiring no ask_gpt_gate",
     "como_detectamos": "review cético + grep (ask_gpt_gate não importava parse_verdict/oracle_router/redteam)",
     "como_corrigimos": "plugar parse_verdict no run_gate; wirar redteam nos triggers pesados; deletar o 6.1 (independência falsa)",
     "como_prevenir_regressao": "todo módulo de gate exige teste de INTEGRAÇÃO que prove o caller usando — verde unitário != live",
     "artefato": "test_run_gate_online_parses_verdict + test_run_gate_sends_redteam", "status": "APPLIED"},
    {"id": "LL-035", "falha_observada": "claude -p rodado de dentro do repo dispararia o SessionStart hook que sobe o próprio bridge = recursão",
     "causa_provavel": "claude -p carrega CLAUDE.md/hooks do cwd",
     "como_detectamos": "análise ao consolidar o bridge no repo (antes de subir)",
     "como_corrigimos": "rodar claude -p com cwd=tempfile.gettempdir() (fora do repo)",
     "como_prevenir_regressao": "qualquer claude -p headless do gate usa cwd NEUTRO fora do repo",
     "artefato": "server.py ask_claude (cwd=workdir)", "status": "APPLIED"},
    {"id": "LL-021", "falha_observada": "escala PDF→metros chutada (0.0254/72) gera SKP fora de proporção",
     "causa_provavel": "usar DPI default em vez de uma âncora física real da planta",
     "como_detectamos": "comparação visual com a planta + regra de extração honesta",
     "como_corrigimos": "PT_TO_M = wall_thickness_pts / 0.19 (dimensão real conhecida)",
     "como_prevenir_regressao": "plant.json declara wall_thickness_m; sem âncora = BLOCKED, nunca chutar default",
     "artefato": "PT_TO_M anchor + spec generalize_builder_constants", "status": "APPLIED"},
    {"id": "LL-036", "falha_observada": "sessões Claude dividindo um worktree movem o branch sob a outra (quase clobber)",
     "causa_provavel": "falta de isolamento/lock entre agentes no mesmo checkout",
     "como_detectamos": "o branch mudou ~5x sob a sessão durante o build do cockpit",
     "como_corrigimos": "trabalhar em worktrees isolados (wt-dash etc.) + rebase antes do push",
     "como_prevenir_regressao": "cada sessão no SEU worktree + lock por session_id (follow-up aberto)",
     "artefato": "orquestrador /sessions (detecção) + chip worktree-lock", "status": "LEARNED"},
]


def learnings() -> dict:
    """Learning Loop: failure patterns (falha→causa→correção→prevenção→artefato).
    Reads .ai_bridge/learning_log.jsonl if present, else the built-in seed.
    Normalizes so EVERY entry has como_prevenir_regressao."""
    items = _read_jsonl(REPO_ROOT / ".ai_bridge" / "learning_log.jsonl")
    src = "jsonl" if items else "builtin-seed"
    if not items:
        items = _DEFAULT_LEARNINGS
    norm = []
    for x in items:
        norm.append({
            "id": x.get("id", "FP-???"),
            "falha_observada": x.get("falha_observada") or x.get("failure") or "?",
            "causa_provavel": x.get("causa_provavel", ""),
            "como_detectamos": x.get("como_detectamos", ""),
            "como_corrigimos": x.get("como_corrigimos", ""),
            "como_prevenir_regressao": x.get("como_prevenir_regressao") or "UNKNOWN — preencher",
            "artefato": x.get("artefato", "-"),
            "status": x.get("status", "LEARNED"),
        })
    return {"learnings": norm, "total": len(norm), "source": src}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    try:
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _git_skp_sets(repo: Path) -> dict:
    """tracked / ignored / untracked .skp sets for a repo (relative paths), via
    git ls-files (read-only)."""
    def ls(*flags):
        try:
            r = subprocess.run(["git", "-C", str(repo), "ls-files", *flags, "--", "*.skp"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=15)
            return {ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()}
        except (OSError, subprocess.SubprocessError):
            return set()
    return {"tracked": ls(),
            "ignored": ls("--others", "--ignored", "--exclude-standard"),
            "untracked": ls("--others", "--exclude-standard")}


_SKP_ACTION = {"CANONICAL_DELIVERABLE": "KEEP", "REVIEW_ARTIFACT": "ARCHIVE",
               "GENERATED_SCRATCH": "DELETE_CANDIDATE", "DUPLICATE": "DELETE_CANDIDATE",
               "UNKNOWN": "INVESTIGATE"}
_SKP_RANK = {"CANONICAL_DELIVERABLE": 0, "REVIEW_ARTIFACT": 1,
             "GENERATED_SCRATCH": 2, "UNKNOWN": 3}


def _classify_skp(rel: str, git: str) -> str:
    if "artifacts/review/" in rel:
        return "REVIEW_ARTIFACT"
    if "artifacts/" in rel:
        return "CANONICAL_DELIVERABLE"
    if "runs/" in rel or git == "ignored":
        return "GENERATED_SCRATCH"
    return "UNKNOWN"


def _dedup_and_classify(files: list) -> list:
    """Group by sha256 (REAL dedup, not by name/path) + classify + suggest action.
    Within a hash group of >1, the most-canonical copy is the keeper; rest = DUPLICATE."""
    groups = {}
    for f in files:
        groups.setdefault(f["sha"], []).append(f)
    for grp in groups.values():
        for f in grp:
            f["category"] = _classify_skp(f["path"], f.get("git", ""))
            f["dup_count"] = len(grp)
        if len(grp) > 1:
            keeper = min(grp, key=lambda f: _SKP_RANK.get(f["category"], 9))
            for f in grp:
                f["dup_of"] = None if f is keeper else keeper["path"]
                if f is not keeper:
                    f["category"] = "DUPLICATE"
        else:
            grp[0]["dup_of"] = None
    for f in files:
        f["action"] = _SKP_ACTION.get(f["category"], "INVESTIGATE")
    return files


def skp_inventory_v2() -> dict:
    """Lixao v2: every .skp under E:\\Claude, sha256-deduped, with git status
    (tracked/untracked/ignored), classification + suggested action. Read-only."""
    root = REPO_ROOT.parent
    gitsets = {}
    try:
        for p in root.iterdir():
            if p.is_dir() and (p / ".git").exists():
                gitsets[p.name] = _git_skp_sets(p)
    except OSError:
        pass
    skps = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in
                  (".git", "node_modules", "__pycache__", ".pytest_cache", ".venv")]
        for fn in fns:
            if fn.lower().endswith(".skp"):
                skps.append(Path(dp) / fn)
        if len(skps) >= 400:
            break
    files = []
    for sp in skps:
        try:
            rel = sp.relative_to(root).as_posix()
            size = sp.stat().st_size
        except OSError:
            continue
        repo = rel.split("/", 1)[0]
        inrepo = rel.split("/", 1)[1] if "/" in rel else ""
        sets = gitsets.get(repo)
        git = "no-git"
        if sets and inrepo:
            git = ("tracked" if inrepo in sets["tracked"] else
                   "ignored" if inrepo in sets["ignored"] else "untracked")
        files.append({"path": rel, "mb": round(size / 1e6, 2),
                      "sha": _sha256(sp)[:12], "git": git,
                      "has_meta": (sp.parent / "geometry_report.json").exists()
                      or (sp.parent / (sp.name + ".metadata.json")).exists()})
    _dedup_and_classify(files)
    counts = {}
    for f in files:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    dup_groups = len({f["sha"] for f in files if f["dup_count"] > 1})
    return {"total": len(files), "total_mb": round(sum(f["mb"] for f in files), 1),
            "dup_groups": dup_groups, "by_category": counts,
            "files": sorted(files, key=lambda f: (f["category"], -f["mb"]))}


def _dir_size_mb(p: Path, cap: int = 8000):
    """Best-effort dir size in MB, bounded by `cap` files so big trees (.git) don't
    hang the endpoint. Returns (mb, capped)."""
    total = n = 0
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
                    n += 1
                    if n >= cap:
                        return round(total / 1e6, 1), True
            except OSError:
                pass
    except OSError:
        pass
    return round(total / 1e6, 1), False


def _classify_dir(p: Path) -> dict:
    """Human classification of a top-level E:\\Claude directory."""
    name = p.name
    known = {
        "sketchup-mcp": ("CANONICAL_REPO", "repo principal canônico (pipeline PDF→SKP + gate + .claude/)", "baixo", "não"),
        "claude-bridge": ("BRIDGE_SERVICE", "bridge standalone original (broker + server + .oauth_token + LIGAR-BRIDGE) — fallback/legado", "médio (contém o token)", "não — guarda o .oauth_token"),
        ".claude": ("CONFIG", "config/memória do projeto E:\\Claude (onde o chat roda)", "baixo", "não"),
    }
    if name in known:
        t, expl, risk, dele = known[name]
    elif name.startswith("wt-"):
        t, expl, risk, dele = ("WORKTREE", "git worktree (checkout isolado de um branch)", "baixo", "sim (git worktree remove)")
    elif name in (".venv", "venv", "env"):
        t, expl, risk, dele = ("VENV", "ambiente virtual Python", "baixo", "sim (recriável)")
    elif name == ".git":
        t, expl, risk, dele = ("GIT_INTERNAL", "interno do git", "ALTO", "NÃO")
    elif name in ("runs", "__pycache__", ".pytest_cache", "node_modules"):
        t, expl, risk, dele = ("RUNS_SCRATCH", "scratch / build output (gitignored)", "baixo", "sim")
    elif name == "artifacts":
        t, expl, risk, dele = ("ARTIFACTS", "deliverables versionados", "médio", "não")
    else:
        t, expl, risk, dele = ("UNKNOWN", "não classificado — investigar", "?", "?")
    return {"type": t, "expl": expl, "risk": risk, "can_delete": dele}


def system_map() -> dict:
    """Scan E:\\Claude top-level and explain each dir (the Explorer page)."""
    root = REPO_ROOT.parent
    items = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        entries = []
    for p in entries:
        if not p.is_dir():
            continue
        mb, capped = _dir_size_mb(p)
        try:
            mod = round(time.time() - p.stat().st_mtime)
        except OSError:
            mod = None
        items.append({"name": p.name, **_classify_dir(p), "mb": mb,
                      "mb_capped": capped, "modified_sec": mod,
                      "has_git": (p / ".git").exists(),
                      "is_worktree": (p / ".git").is_file()})
    return {"root": str(root), "items": items,
            "unknown": [i["name"] for i in items if i["type"] == "UNKNOWN"]}


def git_inventory() -> dict:
    """Read-only git state for every repo/worktree under E:\\Claude. Mutates nothing."""
    root = REPO_ROOT.parent

    def g(p, *args):
        try:
            r = subprocess.run(["git", "-C", str(p), *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=10)
            return (r.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    repos = []
    try:
        candidates = sorted(x for x in root.iterdir() if x.is_dir())
    except OSError:
        candidates = []
    for p in candidates:
        if not (p / ".git").exists():
            continue
        lines = [ln for ln in g(p, "status", "--porcelain").splitlines() if ln.strip()]
        untracked = sum(1 for ln in lines if ln.startswith("??"))
        repos.append({"path": p.name, "is_worktree": (p / ".git").is_file(),
                      "branch": g(p, "rev-parse", "--abbrev-ref", "HEAD"),
                      "head": g(p, "rev-parse", "--short", "HEAD"),
                      "remote": g(p, "remote", "get-url", "origin"),
                      "last_commit": g(p, "log", "-1", "--oneline"),
                      "dirty": len(lines) > 0, "untracked": untracked,
                      "changed": len(lines) - untracked})
    return {"repos": repos, "dirty": [r["path"] for r in repos if r["dirty"]]}


def _classify_processes(procs: list) -> dict:
    """Separa os processos 'claude.exe' em APP DESKTOP (Electron: renderer/gpu/utility —
    so RAM) vs SESSOES CLI (claude-code, stream-json — as que PODEM custar, e so quando
    geram). Logica pura pra ser testavel sem enumerar processos de verdade."""
    desktop_ram = desktop_n = 0
    cli = []
    for p in procs:
        cl = p.get("CommandLine") or ""
        ram = int((p.get("WorkingSetSize") or 0) / (1024 * 1024))
        if "claude-code" in cl or "stream-json" in cl:
            cpu = int(((p.get("KernelModeTime") or 0) + (p.get("UserModeTime") or 0)) / 1e7)
            cli.append({"pid": p.get("ProcessId"), "ram_mb": ram, "cpu_sec": cpu,
                        "effort": "max" if "--effort max" in cl else "?"})
        else:
            desktop_ram += ram
            desktop_n += 1
    cli.sort(key=lambda x: x.get("cpu_sec", 0), reverse=True)
    return {"cli_sessions": cli, "cli_count": len(cli),
            "desktop_app": {"processes": desktop_n, "ram_mb": desktop_ram}}


def live_processes() -> dict:
    """A VERDADE sobre 'esta gastando dinheiro?'. Token so queima durante geracao ativa:
    sessao CLI idle = R$0; app desktop aberto = so RAM; transcript parado no disco =
    historico, R$0. Read-only — nao mata nada."""
    ps = ("Get-CimInstance Win32_Process -Filter \"name='claude.exe'\" | "
          "Select-Object ProcessId,WorkingSetSize,KernelModeTime,UserModeTime,CommandLine | "
          "ConvertTo-Json -Compress")
    procs = []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15)
        data = json.loads(r.stdout or "[]")
        procs = data if isinstance(data, list) else [data]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        procs = []
    out = _classify_processes(procs)
    n = out["cli_count"]
    out["verdict"] = ("Nenhuma sessao CLI viva — nada pode estar custando."
                      if n == 0 else
                      f"{n} sessao(oes) CLI viva(s), todas idle = R$0. Token so queima gerando.")
    out["nota"] = ("App Desktop aberto usa RAM (~{} MB), nao dinheiro. Sessao parada e "
                   "transcript no disco = historico, R$0."
                   ).format(out["desktop_app"]["ram_mb"])
    return out


_VERDICT_TL = re.compile(r"(?im)(?:verdict|veredito|overall)\s*[:=]?\s*\**\s*"
                         r"(IMPROVED|SAME|WORSE|PASS|FAIL|WARN)")
_VERDICT_ANY = re.compile(r"\b(IMPROVED|SAME|WORSE)\b")


def _find_verdict(d: Path):
    """Best-effort verdict for a SKP run dir: prefer a 'VERDICT:'/'veredito:' line in
    regression_summary.md / verdict.md / decision.md; else any IMPROVED/SAME/WORSE."""
    for name in ("regression_summary.md", "verdict.md", "decision.md"):
        try:
            hits = list(d.rglob(name))
        except OSError:
            hits = []
        for f in hits:
            try:
                txt = f.read_text("utf-8", errors="replace")
            except OSError:
                continue
            m = _VERDICT_TL.search(txt) or _VERDICT_ANY.search(txt)
            if m:
                return m.group(1).upper()
    return None


def skp_timeline() -> dict:
    """Current canonical SKP(s) + the timeline of review cycles (renders + verdict),
    for before/after analysis. Paths are REPO_ROOT-relative (served via /artifact)."""
    art = REPO_ROOT / "artifacts"
    out = {"canonical": {}, "timeline": []}
    if not art.is_dir():
        return out
    for d in sorted(art.iterdir()):
        if d.is_dir() and d.name != "review":
            pngs = sorted(f"artifacts/{d.name}/{x.name}" for x in d.glob("*.png"))
            skps = sorted(f"artifacts/{d.name}/{x.name}" for x in d.glob("*.skp"))
            if pngs or skps:
                out["canonical"][d.name] = {"pngs": pngs,
                                            "skp": skps[0] if skps else None,
                                            "skps": skps,
                                            "has_skp": bool(skps),
                                            "verdict": _find_verdict(d)}
    review = art / "review"
    runs = []
    if review.is_dir():
        for plant in sorted(review.iterdir()):
            if not plant.is_dir():
                continue
            for run in sorted(plant.iterdir()):
                if not run.is_dir():
                    continue
                try:
                    mt = run.stat().st_mtime
                except OSError:
                    mt = 0
                pngs = []
                try:
                    for f in sorted(run.rglob("*.png")):
                        try:
                            pngs.append(f.relative_to(REPO_ROOT).as_posix())
                        except (ValueError, OSError):
                            pass
                except OSError:
                    pass
                runs.append({"plant": plant.name, "run": run.name,
                             "mtime": round(mt), "age_sec": round(time.time() - mt),
                             "verdict": _find_verdict(run),
                             "pngs": pngs[:4], "n_pngs": len(pngs)})
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    out["timeline"] = runs[:40]
    return out


_VERDICT_RE = re.compile(r"(?im)verdict\s*[:\-]\s*(GO|NO-GO|MORE-INFO|VISUAL_REVIEW)")


def _extract_verdict(txt: str):
    m = _VERDICT_RE.search(txt or "")
    return m.group(1).upper() if m else None


def gate_ledger() -> dict:
    """The gate Q&A history: question/response pairs, which are still pending
    (waiting on the gate), latency, and the verdict the gate gave. Answers 'o
    gate ajudou ou só virou teatro?'."""
    qd = REPO_ROOT / ".ai_bridge" / "questions"
    rd = REPO_ROOT / ".ai_bridge" / "responses"
    rmap = {p.stem: p for p in rd.glob("*.md")} if rd.is_dir() else {}
    entries = []
    if qd.is_dir():
        for q in sorted(qd.glob("*.md"), key=lambda p: p.name, reverse=True):
            try:
                qt = q.stat().st_mtime
            except OSError:
                qt = 0
            r = rmap.get(q.stem)
            verdict = latency = None
            if r is not None:
                try:
                    latency = max(0, round(r.stat().st_mtime - qt))
                    verdict = _extract_verdict(r.read_text("utf-8", errors="replace"))
                except OSError:
                    pass
            trig = q.stem.split("_", 1)[-1] if "_" in q.stem else q.stem
            entries.append({"id": q.stem, "trigger": trig,
                            "answered": r is not None, "verdict": verdict,
                            "latency_sec": latency, "age_sec": round(time.time() - qt)})
    answered = sum(1 for e in entries if e["answered"])
    return {"entries": entries[:80], "total": len(entries),
            "answered": answered, "pending": len(entries) - answered}


_DEFER_TRIPLET = ("why_not_fixed_yet", "next_hypothesis", "acceptance_criteria")


def _validly_deferred(d: dict) -> bool:
    """DEFERRED so conta como divida-aceita/roadmap (YELLOW, nunca RED) sob guardas
    (decisao do gate :8765, 2026-06-03 — anti-mute-button): exige o triplet completo
    (why_not_fixed_yet + next_hypothesis + acceptance_criteria) E uma review_by ainda
    nao-vencida. Sem isso NAO se esconde atras de DEFERRED — reabre e volta a contar
    como travado (RED se HIGH). Re-open trigger: passou a review_by -> reabre."""
    if d.get("status") != "DEFERRED":
        return False
    for k in _DEFER_TRIPLET:
        v = str(d.get(k) or "").strip()
        if v in ("", "-") or v.startswith("UNKNOWN"):
            return False
    rb = str(d.get("review_by") or "").strip()
    if rb and time.strftime("%Y-%m-%d") >= rb:
        return False
    return True


def status() -> dict:
    """Command Center: aggregate everything into a GREEN/YELLOW/RED project score.
    RED se houver HIGH+OPEN ou consult pendente; YELLOW se houver OPEN/dirty/DEFERRED
    (roadmap/divida aceita); senao GREEN. DEFERRED so vale com triplet + review_by valida
    (anti-gaming, gate :8765 2026-06-03) — senao reabre como OPEN."""
    sess = claude_sessions()
    gl = gate_ledger()
    gi = git_inventory()
    tl = skp_timeline()
    dif = difficulties()
    all_diffs = dif["difficulties"]
    deferred = [d for d in all_diffs if _validly_deferred(d)]
    # DEFERRED vencido / sem o triplet NAO se esconde: reabre e volta a contar como travado.
    reopened = [d for d in all_diffs if d.get("status") == "DEFERRED" and not _validly_deferred(d)]
    open_diffs = [d for d in all_diffs if d.get("status") == "OPEN"] + reopened
    high_open = [d for d in open_diffs if d.get("severidade") == "HIGH"]
    pending = gl.get("pending", 0)
    dirty = gi.get("dirty", [])
    stopped = sum(1 for s in sess.get("sessions", []) if s.get("state") == "STOPPED")
    if high_open or pending > 0:
        score = "RED"
    elif open_diffs or dirty or deferred:
        score = "YELLOW"
    else:
        score = "GREEN"
    reasons = []
    if high_open:
        reasons.append(f"{len(high_open)} dificuldade(s) HIGH OPEN")
    if pending:
        reasons.append(f"{pending} consult(s) esperando o gate")
    if dirty:
        reasons.append(f"{len(dirty)} repo(s) dirty")
    if open_diffs and not high_open:
        reasons.append(f"{len(open_diffs)} dificuldade(s) OPEN")
    if deferred:
        reasons.append(f"{len(deferred)} adiada(s) (roadmap/aceita)")
    if not reasons:
        reasons.append("tudo limpo")
    return {"score": score, "reason": "; ".join(reasons), "gate": "UP",
            "sessions": {"total": sess.get("total", 0), "stopped": stopped},
            "pending_gate": pending, "dirty_repos": dirty,
            "open_difficulties": len(open_diffs), "high_open": [d["id"] for d in high_open],
            "deferred": [d["id"] for d in deferred],
            "canonical_skp": {k: {"skp": v.get("skp"), "has_skp": v.get("has_skp", False),
                                  "verdict": v.get("verdict")}
                              for k, v in tl.get("canonical", {}).items()}}


_NBA_SEED = [
    {"titulo": "Auto-extrator vetorial PDF->consensus (walls = filled paths)", "tipo": "produto",
     "impacto": 5, "esforco": 5, "proxima_acao": "só após 2a planta no loop manual; validar contra a planta_74 anotada"},
    {"titulo": "2a planta real como forcing function", "tipo": "produto",
     "impacto": 5, "esforco": 3, "proxima_acao": "Felipe fornece PDF + âncora física; anotar consensus juntos"},
    {"titulo": "Worktree-lock (fix-raiz da colisão multi-agent)", "tipo": "infra",
     "impacto": 3, "esforco": 2, "proxima_acao": "/lock keyed por session_id + ownership de branch"},
    {"titulo": "Consolidar serving pro launcher canônico + remover wt-dash", "tipo": "infra",
     "impacto": 3, "esforco": 2, "proxima_acao": "quando feat/banho2-glass sincronizar develop, repointar + remover wt-dash"},
    {"titulo": "Watchdog do gate (auto-restart se /health cair)", "tipo": "infra",
     "impacto": 2, "esforco": 2, "proxima_acao": "scheduled task (admin) ou loop de health-check"},
    {"titulo": "Tier do oráculo (Opus pesado / Sonnet rotina)", "tipo": "gate",
     "impacto": 2, "esforco": 3, "proxima_acao": "rotear por peso da decisão no multi-oracle"},
]


def next_best_actions() -> dict:
    """Prioritized backlog by ROI = impacto/esforço (OPEN difficulties + opportunity seed)."""
    items = []
    for d in difficulties()["difficulties"]:
        if d.get("status") == "OPEN":
            imp = {"HIGH": 5, "MED": 3, "LOW": 2}.get(d.get("severidade"), 3)
            items.append({"titulo": "[DIFF] " + d["titulo"], "tipo": "dificuldade",
                          "impacto": imp, "esforco": 3,
                          "proxima_acao": d.get("next_hypothesis", "-")})
    items += [dict(x) for x in _NBA_SEED]
    for x in items:
        x["roi"] = round(x["impacto"] / max(1, x["esforco"]), 2)
    items.sort(key=lambda x: x["roi"], reverse=True)
    return {"actions": items}


# --- Acoes corretivas: os PRIMEIROS endpoints de WRITE do cockpit -------------
# Sancionado pelo Felipe ("cria um botao pra corrigir quando identificado"). Cada
# acao e ESCOPADA + SEGURA: sem push, sem main, sem mexer em fixtures, sem path
# controlado pelo cliente. So toca a fila de consults do proprio repo e loga tudo
# no audit. O que NAO da pra auto-corrigir com seguranca (ex.: dirty na branch de
# outro agente) vira DIAGNOSTICO read-only — nunca commit cego.

def _orphan_consults() -> list:
    """Consults (perguntas) sem resposta — a fila que 'espera o gate'."""
    qd = REPO_ROOT / ".ai_bridge" / "questions"
    rd = REPO_ROOT / ".ai_bridge" / "responses"
    if not qd.is_dir():
        return []
    answered = {p.stem for p in rd.glob("*.md")} if rd.is_dir() else set()
    out = []
    for q in sorted(qd.glob("*.md"), key=lambda p: p.name):
        if q.stem in answered:
            continue
        try:
            text = q.read_text("utf-8", errors="replace")
        except OSError:
            continue
        out.append({"id": q.stem, "text": text})
    return out


def _process_consults_worker(items: list) -> None:
    """Thread daemon: cada consult orfao -> gate -> grava resposta. Atualiza _ACTIONS
    pra a UI acompanhar ao vivo (3->2->1->0). Best-effort por item: um erro nao
    derruba a fila."""
    rd = REPO_ROOT / ".ai_bridge" / "responses"
    try:
        rd.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    for it in items:
        verdict = err = None
        t0 = time.time()
        try:
            answer = ask_claude(it["text"])
            verdict = _extract_verdict(answer)
            (rd / f"{it['id']}.md").write_text(answer, encoding="utf-8")
            _audit_append({"t": time.time(), "kind": "consult", "mode": "backfill",
                           "q_chars": len(it["text"]), "a_chars": len(answer),
                           "dur_sec": round(time.time() - t0, 1)})
        except Exception as e:  # nao derruba a fila por um item
            err = f"{type(e).__name__}: {e}"
        with _ACTIONS_LOCK:
            st = _ACTIONS.setdefault("process_consults", {})
            st["done"] = st.get("done", 0) + 1
            st.setdefault("results", []).append(
                {"id": it["id"], "verdict": verdict, "error": err,
                 "dur_sec": round(time.time() - t0, 1)})
    with _ACTIONS_LOCK:
        st = _ACTIONS.setdefault("process_consults", {})
        st["running"] = False
        st["finished_at"] = time.time()


def process_consults_start() -> dict:
    """Dispara o processamento da fila pendente em background. Idempotente: se ja
    esta rodando, devolve o estado sem disparar de novo."""
    with _ACTIONS_LOCK:
        st = _ACTIONS.get("process_consults")
        if st and st.get("running"):
            return {"already_running": True, **st}
    items = _orphan_consults()
    state = {"running": len(items) > 0, "total": len(items), "done": 0,
             "results": [], "started_at": time.time(),
             "finished_at": None if items else time.time()}
    with _ACTIONS_LOCK:
        _ACTIONS["process_consults"] = state
    if items:
        threading.Thread(target=_process_consults_worker, args=(items,),
                         daemon=True).start()
    return {"started": len(items), **state}


def process_consults_state() -> dict:
    """Estado corrente da acao (UI faz polling enquanto roda)."""
    with _ACTIONS_LOCK:
        st = dict(_ACTIONS.get("process_consults") or
                  {"running": False, "total": 0, "done": 0, "results": []})
    st["pending_now"] = len(_orphan_consults())
    return st


def dirty_detail() -> dict:
    """DIAGNOSTICO read-only dos repos dirty: o que mudou + recomendacao honesta.
    NAO commita nada — em especial nao toca branch de outro agente (regra multi-agent)."""
    gi = git_inventory()
    own = REPO_ROOT.name
    out = []
    for r in gi.get("repos", []):
        if not r.get("dirty"):
            continue
        p = REPO_ROOT.parent / r["path"]
        try:
            res = subprocess.run(["git", "-C", str(p), "status", "--porcelain"],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=10)
            lines = [ln for ln in (res.stdout or "").splitlines() if ln.strip()]
        except (OSError, subprocess.SubprocessError):
            lines = []
        runtime = [ln for ln in lines if ".ai_bridge/" in ln]
        real = [ln for ln in lines if ".ai_bridge/" not in ln]
        is_own = r["path"] == own
        if real:
            kind, rec = "review", "mudancas reais fora de runtime — revisar e commitar na branch"
        elif not is_own:
            kind, rec = "guarded", f"so runtime do .ai_bridge, mas na branch '{r.get('branch')}' de outro agente — NAO commito automatico"
        else:
            kind, rec = "ignorable", "so runtime do .ai_bridge no repo do cockpit — seguro gitignorar"
        out.append({"repo": r["path"], "branch": r.get("branch"), "is_own": is_own,
                    "runtime": len(runtime), "real": len(real),
                    "sample": lines[:12], "kind": kind, "recommendation": rec})
    return {"dirty": out}


def actions_overview() -> dict:
    """Liga cada problema do placard a uma acao concreta: o que e auto-corrigivel num
    clique vs o que e diagnostico/manual. Drena o painel 'Acoes' da UI."""
    st = status()
    pend = gate_ledger().get("pending", 0)
    dirty = st.get("dirty_repos", [])
    high = st.get("high_open", [])
    acts = [
        {"key": "process-consults", "label": f"Processar {pend} consult(s) pendente(s)",
         "kind": "auto", "runnable": pend > 0, "method": "POST",
         "endpoint": "/api/actions/process-consults",
         "detail": "Manda cada pergunta orfa pro gate (UP) e grava a resposta. Limpa o RED de fila."},
        {"key": "dirty-detail", "label": f"Diagnosticar {len(dirty)} repo(s) dirty",
         "kind": "diagnose", "runnable": len(dirty) > 0, "method": "GET",
         "endpoint": "/api/actions/dirty-detail",
         "detail": "Mostra o que mudou + recomendacao. Nao commita branch de outro agente."},
        {"key": "open-difficulty",
         "label": (f"Abrir trilha: {high[0]}" if high else "Backlog de dificuldades"),
         "kind": "manual", "runnable": False, "method": None,
         "endpoint": "/api/difficulties",
         "detail": "Trabalho de produto (SKP/fidelidade) — sem fix de 1 clique; ver abas Dificuldades + Oportunidades."},
    ]
    return {"score": st.get("score"), "reason": st.get("reason"), "actions": acts}


# --- Route table (Command pattern) -------------------------------------------
# Replaces a ~28-branch if/elif in do_GET/do_POST: each path maps to a small
# command `handler(req, url)`. Adding an endpoint is now ONE entry here instead of
# editing the dispatch chain AND the /health docs separately (Open/Closed + DRY).
# `advertised_endpoints()` derives /health's `endpoints` from these tables so the
# advertised contract can never drift from what is actually routed (it had: the
# old hardcoded list named 6 of ~26 real routes).

def _json_route(fn):
    """Adapt a zero-arg data function into a GET handler that sends it as JSON 200."""
    def handler(req, _url):
        req._send(200, fn())
    return handler


def _html_route(fn):
    """Adapt a zero-arg HTML producer into a GET handler that sends text/html."""
    def handler(req, _url):
        req._send_html(fn())
    return handler


def _artifact_route(req, url):
    """Serve a whitelisted artifact image (path validated by safe_artifact)."""
    f = safe_artifact((parse_qs(url.query).get("path") or [""])[0])
    if not f:
        req._send(404, {"error": "not an allowed artifact image"})
        return
    sfx = f.suffix.lower()
    ctype = ("image/svg+xml" if sfx == ".svg" else
             "image/jpeg" if sfx in (".jpg", ".jpeg") else
             "image/webp" if sfx == ".webp" else "image/png")
    req._send_bytes(f.read_bytes(), ctype)


def _ask_route(req, _url):
    """POST /ask — the oracle consult. Honest 500 on failure; never fabricates."""
    try:
        n = int(req.headers.get("Content-Length") or 0)
        body = req.rfile.read(n) if n else b""
        prompt = parse_ask_payload(body)
        if not prompt:
            req._send(400, {"error": "empty question (send 'prompt' or 'question')"})
            return
        mode = parse_ask_mode(body)
        question = apply_mode(prompt, mode)
        t0 = time.time()
        answer = ask_claude(question)
        _audit_append({"t": time.time(), "kind": "consult",
                       "mode": mode or "default", "q_chars": len(prompt),
                       "a_chars": len(answer), "dur_sec": round(time.time() - t0, 1)})
        req._send(200, {"response": answer})
    except Exception as e:  # devolve erro honesto; nao fabrica resposta
        req._send(500, {"error": f"{type(e).__name__}: {e}"})


def _heartbeat_route(req, _url):
    req._heartbeat()


def _process_consults_start_route(req, _url):
    try:
        req._send(200, process_consults_start())
    except Exception as e:
        req._send(500, {"error": f"{type(e).__name__}: {e}"})


# path (rstrip'd of trailing "/") -> command. "" is the form "/" and "/dashboard"
# reduce to. GET strips the query (urlparse); POST matches the raw path, as before.
GET_ROUTES = {
    "": _html_route(dashboard_html),
    "/dashboard": _html_route(dashboard_html),
    "/health": _json_route(health_payload),
    "/sessions": _json_route(sessions_view),
    "/events": _json_route(recent_events),
    "/api/skp-inventory": _json_route(skp_inventory),
    "/api/plant": _json_route(plant_info),
    "/api/claude-sessions": _json_route(claude_sessions),
    "/api/ecosystem": _json_route(ecosystem),
    "/api/recent-commits": _json_route(recent_commits),
    "/api/gate-ledger": _json_route(gate_ledger),
    "/api/system-map": _json_route(system_map),
    "/api/git-inventory": _json_route(git_inventory),
    "/api/processes": _json_route(live_processes),
    "/api/skp-inventory-v2": _json_route(skp_inventory_v2),
    "/api/difficulties": _json_route(difficulties),
    "/api/skp-timeline": _json_route(skp_timeline),
    "/api/learnings": _json_route(learnings),
    "/api/status": _json_route(status),
    "/api/next-best-actions": _json_route(next_best_actions),
    "/api/actions": _json_route(actions_overview),
    "/api/actions/process-consults": _json_route(process_consults_state),
    "/api/actions/dirty-detail": _json_route(dirty_detail),
    "/artifact": _artifact_route,
}

POST_ROUTES = {
    "/ask": _ask_route,
    "/heartbeat": _heartbeat_route,
    "/api/actions/process-consults": _process_consults_start_route,
}


def advertised_endpoints() -> list[str]:
    """Single source of truth for /health's `endpoints`: every served path, derived
    from the route tables so it can never drift from what do_GET/do_POST route."""
    gets = {("/" if p == "" else p) for p in GET_ROUTES}
    return sorted(gets | set(POST_ROUTES))


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

    def _send_bytes(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        handler = GET_ROUTES.get(u.path.rstrip("/"))
        if handler is None:
            self._send(404, {"error": "not found"})
            return
        handler(self, u)

    def do_POST(self):
        handler = POST_ROUTES.get(self.path.rstrip("/"))
        if handler is None:
            self._send(404, {"error": "not found"})
            return
        handler(self, None)

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
