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
import re
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Run-as-script bootstrap: `python server.py` (the docstring's own example, and
# how start.ps1 / .claude/launch.json launch it) puts only THIS file's dir on
# sys.path, so `from tools.claude_bridge...` -> ModuleNotFoundError. The watchdog
# works around it by exporting PYTHONPATH; do it here too so every launch path
# (script, module, PYTHONPATH-less preview) resolves the package.
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from tools.claude_bridge.knowledge_log import difficulties, learnings
from tools.claude_bridge.skp_inventory import skp_inventory, skp_inventory_v2
from tools.claude_bridge.system_inventory import git_inventory, live_processes, system_map

REPO_ROOT = Path(__file__).resolve().parents[2]
try:  # raiz do workspace E:\Claude — fonte unica, robusta a apps/ (2026-06-09)
    from tools.claude_bridge._paths import WORKSPACE_ROOT  # noqa: E402
except ImportError:  # execucao standalone sem PYTHONPATH
    from _paths import WORKSPACE_ROOT  # noqa: E402

CLAUDE_TIMEOUT = 240  # segundos por resposta; estoura -> erro 500, nunca trava infinito
MODEL = "claude-opus-4-8"   # o JUIZ do modo B (Opus 4.8)
EFFORT = "xhigh"            # effort maximo

# Tiers do oraculo: 'fast' (rotina/triagem, segundos) vs 'deep' (A/B/C pesado, o JUIZ).
# Modelo por ALIAS (claude resolve 'sonnet'/'opus' pro mais recente) + effort. deep =
# comportamento atual (zero regressao). Sem isso, usar o gate em mais cenarios vira
# pedagio de 60s por chamada (a latencia e' o effort xhigh, nao o I/O).
TIERS = {
    "fast": {"model": "sonnet", "effort": "low"},
    "deep": {"model": MODEL, "effort": EFFORT},
}
DEFAULT_TIER = "deep"       # back-compat: sem 'tier' no /ask -> deep (nao muda quem ja chama)


def resolve_tier(tier: str):
    """tier -> (model, effort). Desconhecido/vazio -> DEFAULT_TIER. Pura, testavel."""
    t = TIERS.get(str(tier or "").strip().lower()) or TIERS[DEFAULT_TIER]
    return t["model"], t["effort"]


def consult_audit_fields(tier: str, mode: str = "") -> dict:
    """Campos de tier/model/effort do evento de audit do /ask. Pura, testavel.
    Garante que o audit registra tier + model + EFFORT de cada consulta."""
    model, effort = resolve_tier(tier)
    return {
        "mode": mode or "default",
        "tier": tier or DEFAULT_TIER,
        "model": model,
        "effort": effort,
    }
STARTED_AT = time.time()    # para o uptime no painel operacional

# Identidade do BUILD servido (FP-040): sha+mtime DESTE arquivo, calculados no
# startup. Deixa /health distinguir "vivo mas rodando código velho" de saudável —
# o watchdog relança o server.py do working tree do MAIN, e sem isto um deploy
# não-aplicado é invisível (o gotcha real: /health ok com rota nova ausente).
def _build_identity() -> dict:
    import hashlib
    p = Path(__file__).resolve()
    try:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        mtime = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))
    except OSError:
        digest, mtime = "unknown", "unknown"
    return {"server_sha12": digest, "server_mtime": mtime}


BUILD_IDENTITY = _build_identity()

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


def ask_claude(question: str, tier: str = DEFAULT_TIER) -> str:
    """Roda `claude -p` headless com SYSTEM + a pergunta. `tier` escolhe model+effort:
    'fast' (rotina/triagem, segundos) vs 'deep' (Opus xhigh, o JUIZ). Texto ou levanta."""
    model, effort = resolve_tier(tier)
    prompt = SYSTEM + "\n\n=== QUESTION ===\n\n" + question
    # cwd NEUTRO (temp, FORA do repo): claude -p nao carrega o CLAUDE.md/hooks deste
    # projeto -> sem prompt de permissao e, critico, sem disparar o SessionStart hook
    # que sobe ESTE bridge (recursao).
    workdir = tempfile.gettempdir()
    if sys.platform == "win32":
        # npm instala claude como .CMD -> precisa de shell; prompt vai por STDIN (sem quoting)
        cmd = (f'"{claude_bin()}" -p --model {model} --effort {effort} '
               f'--output-format text')
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_TIMEOUT, shell=True, cwd=workdir)
    else:
        proc = subprocess.run([claude_bin(), "-p", "--model", model,
                               "--effort", effort, "--output-format", "text"],
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


def ask_claude_vision(question: str, image_paths, tier: str = DEFAULT_TIER) -> str:
    """Como ask_claude, mas concede LEITURA dos diretorios das imagens (--add-dir) pro
    claude -p ABRIR os renders com a ferramenta Read — a VISAO vem dai. E o unico olho
    confiavel do sistema: os modelos locais de visao (qwen2.5vl/moondream) NAO discriminam
    defeito (negative_dogfood provou). O prompt do chamador instrui a leitura + o formato
    de saida (visual_findings). Sem --add-dir, o claude -p (cwd neutro) e' bloqueado por
    permissao ao ler paths fora do cwd e HONESTAMENTE se recusa a chutar."""
    model, effort = resolve_tier(tier)
    prompt = SYSTEM + "\n\n=== QUESTION ===\n\n" + question
    workdir = tempfile.gettempdir()
    dirs = []
    for p in (image_paths or []):
        d = os.path.dirname(os.path.abspath(str(p)))
        if d and d not in dirs:
            dirs.append(d)
    if sys.platform == "win32":
        adg = " ".join(f'--add-dir "{d}"' for d in dirs)
        cmd = (f'"{claude_bin()}" -p --model {model} --effort {effort} '
               f'--output-format text {adg}')
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_TIMEOUT, shell=True, cwd=workdir)
    else:
        add_args = []
        for d in dirs:
            add_args += ["--add-dir", d]
        proc = subprocess.run([claude_bin(), "-p", "--model", model, "--effort", effort,
                               "--output-format", "text", *add_args],
                              input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=CLAUDE_TIMEOUT, cwd=workdir)
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError(f"resposta vazia (stderr: {(proc.stderr or '')[:300]})")
    low = out.lower()
    if "not logged in" in low or "please run /login" in low:
        raise RuntimeError("claude headless NAO autenticado")
    return out


# ---- painel colaborativo de 3 juizes (vision panel) ------------------------
# Decisao do Felipe: o /ask-vision deixa de ser 1 chamada `claude -p` e vira um
# PAINEL de 3: "estrutura" (5 eixos geometricos existentes) + "material_luz"
# (eixo NOVO, textura/cor/reflectancia/sombra/exposicao — o que os 6 eixos
# antigos NAO cobrem) RODAM EM PARALELO (ThreadPoolExecutor — stdlib, cada
# chamada e' um subprocess bloqueante `claude -p`, threads bastam pra IO-bound);
# o 3o ("sintese") roda DEPOIS, recebe os DOIS relatorios como TEXTO (nao
# rele imagens — custo) e produz (a) o top_level_verdict FINAL (resolve
# conflito honesto, nunca inventa o que um juiz nao viu) e (b)
# design_patterns_observed — a colaboracao dos 3 vira conhecimento de design
# REUSAVEL (FP-035-prep), nao so um PASS/FAIL isolado.
#
# Degradacao honesta: falha/timeout de QUALQUER uma das 3 chamadas NAO fabrica
# veredito nem padroes daquele juiz — confidence cai, o 3o decide com o que tem
# (nunca inventa o que falta). "FAIL so se DISCRIMINATED" continua regra de
# PROMOCAO no run_skp_visual_review.py — o painel nao mexe nisso.
VISION_PANEL_TIMEOUT_SEC = CLAUDE_TIMEOUT + 60  # cada juiz roda dentro do CLAUDE_TIMEOUT do ask_claude_vision; folga pro ThreadPoolExecutor.result()

_STRUCTURE_JUDGE_PROMPT = """You are judge 1/3 of a collaborative visual-fidelity panel — ESTRUTURA.
Focus ONLY on these 5 geometric fidelity axes (PDF-vs-SKP correctness, NOT aesthetics):
wall_fidelity, door_fidelity, window_fidelity, room_fidelity, scale_rotation.
Ignore material/color/light/texture entirely — that is judge 2's job, not yours.

OPEN each render below with the Read tool and LOOK at it: your judgment MUST come from the
pixels, not from geometry numbers alone.

Renders (absolute paths, readable via --add-dir):
{img_lines}

Return ONLY a JSON object (no prose, no code fences):
{{
  "top_level_verdict": "PASS|WARN|FAIL",
  "confidence": "low|medium|high",
  "axes": {{
    "wall_fidelity":  {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "door_fidelity":  {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "window_fidelity":{{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "room_fidelity":  {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "scale_rotation": {{"verdict":"PASS|WARN|FAIL","evidence":"..."}}
  }},
  "findings": [ {{"id":"vf_001","severity":"FAIL|WARN","axis":"<one of the 5 axes above>",
  "type":"<type>","location":"...","evidence_image":"<render file name>","evidence":"..."}} ]
}}

Finding types: floating_door, wall_stub, missing_wall_continuation, misplaced_window,
full_height_window_void, floor_leak, misplaced_soft_barrier. Report ONLY what you SEE.

{extra_context}
"""

_MATERIAL_LIGHT_JUDGE_PROMPT = """You are judge 2/3 of a collaborative visual-fidelity panel — MATERIAL & LUZ.
Focus ONLY on this axis: material_light — texture, color, reflectance, shadow, exposure. This is
what differentiates a real V-Ray render from a wireframe/flat-shaded placeholder; it is NOT
covered by the 5 geometric axes (wall/door/window/room/scale_rotation), which judge 1 already owns.
Ignore wall/door/window/room placement and scale entirely — that is judge 1's job, not yours.

OPEN each render below with the Read tool and LOOK at it: your judgment MUST come from the
pixels.

Renders (absolute paths, readable via --add-dir):
{img_lines}

Return ONLY a JSON object (no prose, no code fences):
{{
  "top_level_verdict": "PASS|WARN|FAIL",
  "confidence": "low|medium|high",
  "axes": {{
    "material_light": {{"verdict":"PASS|WARN|FAIL","evidence":"..."}}
  }},
  "findings": [ {{"id":"vf_001","severity":"FAIL|WARN","axis":"material_light",
  "type":"<type>","location":"...","evidence_image":"<render file name>","evidence":"..."}} ],
  "design_patterns_observed": [
    {{"pattern":"<short label, e.g. paleta/material/luz/proporcao/layout choice>",
      "verdict":"works|fails|neutral","why":"<what you SAW that supports this>"}}
  ]
}}

Finding types: orphan_glass_panel, flat_shading_no_texture, blown_out_exposure,
missing_shadow, wrong_material_hue, global_visual_fail. design_patterns_observed is OPTIONAL —
leave it [] if you did not see enough to name a reusable pattern; NEVER invent one. Report ONLY
what you SEE.

{extra_context}
"""

_SYNTHESIS_JUDGE_PROMPT = """You are judge 3/3 of a collaborative visual-fidelity panel — SINTESE.
You do NOT re-read the renders (that is expensive and already done). You receive the two reports
below, written by judge 1 (ESTRUTURA — the 5 geometric fidelity axes) and judge 2 (MATERIAL & LUZ
— texture/color/light). Either report may be MISSING (judge failed/timed out) — if so, decide with
what you have and say so honestly; NEVER invent what a missing judge would have said.

Your job has two parts:
1. Resolve the FINAL top_level_verdict for this render, combining both reports honestly (FAIL if
   either report FAILs; WARN if either WARNs and neither FAILs; PASS only if both PASS). If a
   report is missing, do not silently default to PASS — say so in a finding and reflect it in
   confidence.
2. Produce design_patterns_observed: a list of REUSABLE design-pattern observations (palette,
   material, lighting, proportion, layout) that this variant demonstrates working well OR badly —
   this is accumulated design knowledge, not a fidelity verdict. Merge/dedupe patterns already
   named by judge 2 with anything you can additionally infer from BOTH reports together (e.g. a
   geometric proportion issue from judge 1 combined with a material choice from judge 2). Leave
   the list EMPTY if there is not enough signal — never fabricate a pattern.

=== JUDGE 1 REPORT (ESTRUTURA) ===
{structure_report}

=== JUDGE 2 REPORT (MATERIAL & LUZ) ===
{material_light_report}

Return ONLY a JSON object (no prose, no code fences) matching visual_findings.v1:
{{
  "schema_version": "visual_findings.v1",
  "top_level_verdict": "PASS|WARN|FAIL",
  "confidence": "low|medium|high",
  "axes": {{
    "wall_fidelity":   {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "door_fidelity":   {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "window_fidelity": {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "room_fidelity":   {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "scale_rotation":  {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "material_light":  {{"verdict":"PASS|WARN|FAIL","evidence":"..."}},
    "global_visual":   {{"verdict":"PASS|WARN|FAIL","evidence":"..."}}
  }},
  "findings": [ {{"id":"vf_001","severity":"FAIL|WARN","axis":"<one of the 7 axes above>",
  "type":"<type>","location":"...","evidence_image":"<render file name>","evidence":"..."}} ],
  "design_patterns_observed": [
    {{"pattern":"...","verdict":"works|fails|neutral","why":"..."}}
  ]
}}

If a report above is literally the text "MISSING (judge failed/timed out)", copy through the
axes/findings you DO have from the other report, mark the missing axes' verdict as "WARN" with
evidence "judge unavailable — not evaluated", cap confidence at "low", and add a finding
{{"severity":"WARN","axis":"global_visual","type":"panel_degraded", ...}} documenting which judge
was missing. Never claim PASS for an axis nobody evaluated.
"""


def _vision_panel_img_lines(image_paths) -> str:
    return "\n".join(f"  - {Path(p).resolve()}" for p in (image_paths or []))


def _run_vision_judge(prompt_template: str, image_paths, extra_context: str,
                      tier: str) -> tuple[str | None, str | None]:
    """Roda 1 juiz do painel (`ask_claude_vision`). Retorna (texto, None) em
    sucesso ou (None, motivo) em falha — NUNCA fabrica texto de juiz que falhou
    (o chamador precisa distinguir 'juiz respondeu' de 'juiz caiu')."""
    prompt = prompt_template.format(
        img_lines=_vision_panel_img_lines(image_paths),
        extra_context=extra_context or "")
    try:
        return ask_claude_vision(prompt, image_paths, tier=tier), None
    except Exception as e:  # noqa: BLE001 — degradacao honesta, nunca propaga
        return None, f"{type(e).__name__}: {e}"


def ask_claude_vision_panel(question: str, image_paths, tier: str = DEFAULT_TIER) -> str:
    """Painel COLABORATIVO de 3 juizes (substitui a chamada unica ao
    ask_claude_vision pro /ask-vision). `question` e' o contexto extra que o
    chamador passaria (ex.: pending findings do vision_queue_consumer) —
    repassado aos juizes 1 e 2 como contexto secundario.

    1. "estrutura" + "material_luz" RODAM EM PARALELO (ThreadPoolExecutor,
       2 workers — cada chamada e' 1 subprocess `claude -p` bloqueante de
       ~50-110s medido em producao; paralelizar os 2 primeiros corta a
       latencia total de ~3x para ~2x uma chamada).
    2. "sintese" roda DEPOIS, recebendo os 2 relatorios como TEXTO (nunca
       relê as imagens — custo). Produz o veredito FINAL + design_patterns.

    Retorna o TEXTO do juiz de sintese (mesmo formato de string que
    ask_claude_vision devolvia) — o chamador (_ask_vision_route) empacota em
    {"response": "<texto>"} EXATAMENTE como antes; nenhuma mudanca de contrato
    HTTP. Nunca fabrica: se um juiz falha, o prompt de sintese INSTRUI o 3o a
    marcar os eixos daquele juiz como WARN honesto (nunca PASS por omissao)."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_structure = ex.submit(_run_vision_judge, _STRUCTURE_JUDGE_PROMPT,
                                  image_paths, question, tier)
        fut_material = ex.submit(_run_vision_judge, _MATERIAL_LIGHT_JUDGE_PROMPT,
                                 image_paths, question, tier)
        structure_text, structure_err = fut_structure.result(timeout=VISION_PANEL_TIMEOUT_SEC)
        material_text, material_err = fut_material.result(timeout=VISION_PANEL_TIMEOUT_SEC)

    structure_report = structure_text or "MISSING (judge failed/timed out)"
    material_report = material_text or "MISSING (judge failed/timed out)"
    if structure_err:
        structure_report += f"\n[judge 1 error, honestly surfaced: {structure_err}]"
    if material_err:
        material_report += f"\n[judge 2 error, honestly surfaced: {material_err}]"

    synthesis_prompt = _SYNTHESIS_JUDGE_PROMPT.format(
        structure_report=structure_report, material_light_report=material_report)
    # sintese NAO le imagem (custo) -> ask_claude (texto), nao ask_claude_vision;
    # sem imagens no bridge, --add-dir fica vazio e o dir do cwd neutro basta.
    return ask_claude(synthesis_prompt, tier=tier)


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


def parse_ask_tier(raw: bytes) -> str:
    """Extract the optional `tier` (fast|deep) from an /ask body. '' if none."""
    if not raw:
        return ""
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("tier") or "").strip().lower()


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
        "tiers": {k: dict(v) for k, v in TIERS.items()},
        "default_tier": DEFAULT_TIER,
        "uptime_sec": round(time.time() - STARTED_AT, 1),
        **BUILD_IDENTITY,
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
# Thresholds de visibilidade operacional (configuraveis). UP/DOWN nao basta:
GATE_IDLE_WARN_SEC = 24 * 3600   # gate UP sem consulta ha > 24h -> ONLINE_IDLE (warn)
GATE_IDLE_BAD_SEC = 72 * 3600    # > 72h -> ocioso/stale (bad)
SOURCE_STALE_MARGIN_SEC = 3600   # legacy .md mais velho que o audit por > 1h -> STALE_SOURCE
_AIB = REPO_ROOT / ".ai_bridge"
QUESTIONS_DIR = _AIB / "questions"   # consults legacy (pergunta)
RESPONSES_DIR = _AIB / "responses"   # consults legacy (resposta)


def _questions_dir() -> Path:
    """Resolve em call-time (nao no import) pra honrar um REPO_ROOT monkeypatchado
    em teste; em producao REPO_ROOT nao muda, entao e' identico a QUESTIONS_DIR."""
    return REPO_ROOT / ".ai_bridge" / "questions"


def _responses_dir() -> Path:
    return REPO_ROOT / ".ai_bridge" / "responses"
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


# --- Visibilidade operacional: ultima atividade + fonte REAL do gate ----------
# O painel nao pode parecer vivo quando esta ocioso, nem mostrar a aba Gate com
# fonte velha como se fosse atual. audit.jsonl e a fonte PRIMARIA de consults
# recentes; questions/responses .md sao LEGACY/fallback. UNKNOWN explicito quando
# nao ha fonte — nunca inventa.

def _fmt_dt(t):
    try:
        return time.strftime("%d/%m %H:%M", time.localtime(t))
    except Exception:
        return "?"


def _newest_mtime(*iters):
    newest = None
    for it in iters:
        try:
            for p in it:
                try:
                    m = p.stat().st_mtime
                except OSError:
                    continue
                if newest is None or m > newest:
                    newest = m
        except OSError:
            pass
    return newest


def _audit_scan() -> dict:
    """Varre TODO o audit.jsonl (nao so o tail): t do evento mais novo (qualquer kind),
    t do consult mais novo, e os consults recentes (dado REAL pra aba Gate)."""
    last_event = last_consult = None
    consults = []
    try:
        lines = AUDIT_PATH.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        t = e.get("t")
        if not isinstance(t, (int, float)):
            continue
        if last_event is None or t > last_event:
            last_event = t
        if e.get("kind") == "consult":
            if last_consult is None or t > last_consult:
                last_consult = t
            consults.append(e)
    consults.sort(key=lambda e: e.get("t", 0), reverse=True)
    return {"last_event": last_event, "last_consult": last_consult, "consults": consults}


def _classify_gate_source(audit_consult_at, legacy_q_at, margin=SOURCE_STALE_MARGIN_SEC):
    """PURA (testavel): qual a fonte do gate e se a legacy esta stale vs o audit."""
    has_a = audit_consult_at is not None
    has_l = legacy_q_at is not None
    if has_a and has_l:
        source = "mixed"
    elif has_a:
        source = "audit.jsonl"
    elif has_l:
        source = "questions/responses legacy"
    else:
        source = "unavailable"
    stale = bool(has_a and has_l and (audit_consult_at - legacy_q_at) > margin)
    return source, stale


def _classify_gate_state(up, last_consult_at, now, pending, stalled, source_stale,
                         warn=GATE_IDLE_WARN_SEC, bad=GATE_IDLE_BAD_SEC):
    """PURA (testavel): estado honesto do gate. UP/DOWN sozinho nao basta."""
    if not up:
        return "DOWN", "bad"
    if last_consult_at is None:
        return "UNKNOWN", "warn"
    if pending > 0 or stalled > 0:
        return "BLOCKED", "bad"
    if source_stale:
        return "STALE_SOURCE", "warn"
    idle = now - last_consult_at
    if idle > bad:
        return "ONLINE_IDLE", "bad"
    if idle > warn:
        return "ONLINE_IDLE", "warn"
    return "ONLINE_ACTIVE", "ok"


def _gate_source_info() -> dict:
    """Fonte real do gate + staleness + consults recentes do audit (pra aba Gate)."""
    now = time.time()
    aud = _audit_scan()
    qd = _questions_dir()
    rd = _responses_dir()
    legacy_q = _newest_mtime(qd.glob("*.md")) if qd.is_dir() else None
    legacy_r = _newest_mtime(rd.glob("*.md")) if rd.is_dir() else None
    audit_c = aud["last_consult"]
    source, stale = _classify_gate_source(audit_c, legacy_q)
    reason = None
    if stale:
        reason = ("fonte legacy stale: questions/responses ultimo em " + _fmt_dt(legacy_q)
                  + ", mas audit tem consult em " + _fmt_dt(audit_c))
    return {
        "source": source, "source_stale": stale, "stale_reason": reason,
        "audit_last_consult_at": audit_c, "audit_last_event_at": aud["last_event"],
        "legacy_last_question_at": legacy_q, "legacy_last_response_at": legacy_r,
        "audit_consults": [{"age_sec": round(now - e.get("t", now)), "mode": e.get("mode", "default"),
                            "dur_sec": e.get("dur_sec"), "q_chars": e.get("q_chars"),
                            "a_chars": e.get("a_chars")} for e in aud["consults"][:20]],
    }


def activity_summary() -> dict:
    """Visibilidade operacional honesta: ultima atividade, ociosidade do gate, fonte
    real + staleness, sessoes vivas/paradas, ultimo artifact. UNKNOWN explicito."""
    now = time.time()
    up = True  # se /api/activity responde, ESTE gate esta servindo (o watchdog cobre o DOWN)
    src = _gate_source_info()
    audit_c = src["audit_last_consult_at"]
    legacy_q = src["legacy_last_question_at"]
    legacy_r = src["legacy_last_response_at"]

    cand_consult = [x for x in (audit_c, legacy_q) if x]
    cand_resp = [x for x in (audit_c, legacy_r) if x]
    last_consult = max(cand_consult) if cand_consult else None
    last_response = max(cand_resp) if cand_resp else None
    gate_idle = (now - last_consult) if last_consult else None

    sv = sessions_view()
    active = sum(1 for v in sv.values() if v.get("flags") == ["OK"])
    stalled = sum(1 for v in sv.values()
                  if "STALLED" in v.get("flags", []) or "PARALYZED" in v.get("flags", []))

    live_last = None
    with _SESSIONS_LOCK:
        for s in _SESSIONS.values():
            ls = s.get("last_seen")
            if ls and (live_last is None or ls > live_last):
                live_last = ls
    cand_act = [x for x in (src["audit_last_event_at"], live_last) if x]
    last_activity = max(cand_act) if cand_act else None

    art = REPO_ROOT / "artifacts"
    last_artifact = _newest_mtime(art.glob("**/*.skp"), art.glob("**/*.png")) if art.is_dir() else None

    try:
        pending = len(_orphan_consults())
    except Exception:
        pending = 0

    state, sev = _classify_gate_state(up, last_consult, now, pending, stalled, src["source_stale"])

    def age(t):
        return round(now - t) if t else None

    return {
        "now": now, "up": up,
        "gate_state": state, "gate_state_sev": sev,
        "last_activity_at": last_activity, "last_activity_age_sec": age(last_activity),
        "last_gate_consult_at": last_consult, "last_gate_consult_age_sec": age(last_consult),
        "last_gate_response_at": last_response, "last_gate_response_age_sec": age(last_response),
        "gate_idle_age_sec": (round(gate_idle) if gate_idle is not None else None),
        "gate_source": src["source"], "gate_source_stale": src["source_stale"],
        "stale_reason": src["stale_reason"],
        "active_sessions_now": active, "stalled_sessions_now": stalled,
        "last_artifact_at": last_artifact, "last_artifact_age_sec": age(last_artifact),
        "pending_gate": pending,
        "thresholds": {"idle_warn_sec": GATE_IDLE_WARN_SEC, "idle_bad_sec": GATE_IDLE_BAD_SEC,
                       "source_stale_margin_sec": SOURCE_STALE_MARGIN_SEC},
    }


# Operational dashboard RETIRED 2026-07-03 (unified-cockpit landed) — the page now lives
# at :8782 (sketchup-mcp-bff), reading this gate by FILE via bridge_mirror.py. This gate
# stays headless: root/`/dashboard` just redirect a lost bookmark to the real page.
def _redirect_to_cockpit(req, _url):
    req.send_response(302)
    req.send_header("Location", "http://localhost:8782/")
    req.send_header("Content-Length", "0")
    req.end_headers()


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
    qd = _questions_dir()
    rd = _responses_dir()
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
    root = WORKSPACE_ROOT
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
    qd = _questions_dir()
    rd = _responses_dir()
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
    out = {"entries": entries[:80], "total": len(entries),
           "answered": answered, "pending": len(entries) - answered}
    out.update(_gate_source_info())  # fonte REAL (audit vs legacy) + staleness + consults recentes
    return out


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
    {"titulo": "Tier do oráculo (Opus pesado / Sonnet rotina)", "tipo": "gate",
     "impacto": 2, "esforco": 3, "proxima_acao": "rotear por peso da decisão no multi-oracle"},
    {"titulo": "Swap-in das constantes do builder (generalize_builder_constants)", "tipo": "generalização",
     "impacto": 3, "esforco": 4, "proxima_acao": "executar o blueprint quando a árvore esfriar; precisa build SU + consumidor real (DIFF-006 foi revertido)"},
    {"titulo": "RAG indexado das fontes (file-fetch §6.3 é o RAG-bebê)", "tipo": "enhancement",
     "impacto": 2, "esforco": 4, "proxima_acao": "indexar fontes depois do pipeline generalizar"},
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
    qd = _questions_dir()
    rd = _responses_dir()
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
    rd = _responses_dir()
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
    try:
        own = REPO_ROOT.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        own = REPO_ROOT.name
    out = []
    for r in gi.get("repos", []):
        if not r.get("dirty"):
            continue
        p = WORKSPACE_ROOT / r["path"]
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

_FILES_EXCLUDE = (".venv", "__pycache__", ".git", "node_modules", "runs", ".pytest_cache", ".mypy_cache")


def _py_desc(path) -> str:
    """Descricao HONESTA de um .py: docstring do modulo (1a linha). Vazio se nao houver."""
    import ast
    try:
        doc = ast.get_docstring(ast.parse(path.read_text("utf-8", errors="replace")))
        if doc:
            return doc.strip().splitlines()[0].strip()[:160]
    except Exception:
        pass
    return ""


def _md_desc(path) -> str:
    """Descricao HONESTA de um .md: 1o heading/linha nao-vazia (sem #). Vazio se nada."""
    try:
        for ln in path.read_text("utf-8", errors="replace").splitlines():
            s = ln.strip()
            if not s or s == "---":
                continue
            s = s.lstrip("#").strip()
            if s:
                return s[:160]
    except Exception:
        pass
    return ""


def recent_files(limit: int = 80) -> dict:
    """Inventario de .py/.md modificados recentemente — proxy de 'o que foi mexido nos
    ultimos processamentos'. mtime = ultima atualizacao; descricao EXTRAIDA do proprio
    arquivo (docstring/heading), nunca inventada. NAO e rastreamento de execucao."""
    now = time.time()
    globs = [
        REPO_ROOT.glob("*.py"), REPO_ROOT.glob("*.md"),
        (REPO_ROOT / "tools").glob("**/*.py"), (REPO_ROOT / "tools").glob("**/*.md"),
        (REPO_ROOT / ".claude").glob("**/*.md"),
        (REPO_ROOT / "docs").glob("**/*.md"),
    ]
    out: dict = {}
    for g in globs:
        try:
            for p in g:
                parts = str(p).replace("\\", "/").split("/")
                if any(x in parts for x in _FILES_EXCLUDE):
                    continue
                key = str(p)
                if key in out or not p.is_file():
                    continue
                try:
                    mt = p.stat().st_mtime
                except OSError:
                    continue
                kind = p.suffix.lstrip(".")
                out[key] = {
                    "path": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "kind": kind, "mtime": mt, "age_sec": round(now - mt),
                    "desc": _py_desc(p) if kind == "py" else _md_desc(p),
                }
        except OSError:
            pass
    rows = sorted(out.values(), key=lambda r: r["mtime"], reverse=True)[:limit]
    return {"files": rows, "total": len(out), "shown": len(rows),
            "scanned_roots": ["(raiz)", "tools/", ".claude/", "docs/"],
            "note": "ordenado por mtime (proxy de uso recente, nao execucao); descricao do proprio arquivo"}


def cognitive_doc() -> dict:
    """Serve o CLAUDE_COGNITIVE_ARCHITECTURE.md (raiz do repo) como texto, pra aba
    'Cerebro' renderizar. Fonte UNICA de verdade — a aba nao duplica o conteudo."""
    p = REPO_ROOT / "CLAUDE_COGNITIVE_ARCHITECTURE.md"
    try:
        txt = p.read_text("utf-8", errors="replace")
        mt = p.stat().st_mtime
        return {"exists": True, "text": txt, "mtime": mt, "age_sec": round(time.time() - mt)}
    except OSError:
        return {"exists": False, "text": "",
                "note": "CLAUDE_COGNITIVE_ARCHITECTURE.md nao encontrado na raiz do repo"}


# === ESTADO VIVO DO CEREBRO (aba Cerebro) ====================================
# Transforma a aba Cerebro de "doc vivo" em cockpit: o que a sessao carrega (do
# CLAUDE.md) e quao FRESCO esta, o gate atual, o artefato canonico e a proxima
# acao. TUDO derivado de arquivos/endpoints REAIS — nada fabricado (Hard Rule
# nao-fabricar). O que NAO da pra saber em runtime (qual skill esta acionada
# AGORA) e reportado como tal, nunca chutado.

_STATE_AGING_SEC = 2 * 24 * 3600    # arquivo de estado > 2 dias -> AGING
_STATE_STALE_SEC = 5 * 24 * 3600    # > 5 dias -> STALE
_MANDATORY_SKILLS = {"generate-and-compare-skp-after-change"}  # Constitution #8: pos-mudanca


def _git_out(args, timeout=4):
    """Best-effort `git -C REPO_ROOT <args>` -> stdout stripado, ou None se git/repo
    indisponivel. Mesmo padrao do system_inventory (nunca derruba o request)."""
    try:
        p = subprocess.run(["git", "-C", str(REPO_ROOT)] + list(args),
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode == 0:
            return p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _file_state(rel: str) -> dict:
    """Presenca + frescor (mtime) de um arquivo cognitivo (REPO_ROOT-relativo).
    Ausente = badge MISSING (um @import pendurado e' sinal honesto, nao erro mudo)."""
    p = REPO_ROOT / rel
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {"path": rel, "exists": False, "badge": "MISSING", "age_sec": None}
    return {"path": rel, "exists": True, "age_sec": round(time.time() - mt), "badge": "LIVE"}


def _loaded_from_claude_md() -> list:
    """A ordem de auto-load REAL: parseia as linhas `@.claude/...` do .claude/CLAUDE.md
    (fonte viva). Cada item = presenca + frescor. Auto-atualiza se o CLAUDE.md mudar."""
    md = REPO_ROOT / ".claude" / "CLAUDE.md"
    try:
        txt = md.read_text("utf-8", errors="replace")
    except OSError:
        return []
    seen, out = set(), []
    for m in re.finditer(r"(?m)^@(\.claude/\S+)", txt):
        rel = m.group(1)
        if rel not in seen:
            seen.add(rel)
            out.append(_file_state(rel))
    return out


def _current_state_freshness() -> dict:
    """current_state.md e' o 'snapshot do dia' (decai rapido — o doc cognitivo diz isso).
    Staleness HONESTA = commits-behind no git desde o ultimo commit do arquivo + idade
    local (mtime). Sem git -> so mtime (commits_behind=None)."""
    rel = ".claude/memory/current_state.md"
    st = _file_state(rel)
    behind = None
    last = _git_out(["log", "-1", "--format=%H", "--", rel])
    if last:
        cnt = _git_out(["rev-list", "--count", f"{last}..HEAD"])
        if cnt and cnt.isdigit():
            behind = int(cnt)
    st["commits_behind"] = behind
    age = st.get("age_sec")
    if not st["exists"]:
        st["badge"], st["why"] = "MISSING", "arquivo ausente"
    elif (behind is not None and behind > 5) or (age is not None and age > _STATE_STALE_SEC):
        st["badge"], st["why"] = "STALE", (f"{behind} commits atras" if behind else "muito velho — reconferir vs git")
    elif (behind is not None and behind > 0) or (age is not None and age > _STATE_AGING_SEC):
        st["badge"], st["why"] = "AGING", (f"{behind} commit(s) atras" if behind else "envelhecendo")
    else:
        st["badge"], st["why"] = "LIVE", "fresco"
    return st


def _skill_cards() -> list:
    """Painel de capacidades: cada .claude/skills/*/SKILL.md -> nome + descricao, lidos
    do proprio arquivo (frontmatter `description:` ou 1o heading). Nao fabricado."""
    base = REPO_ROOT / ".claude" / "skills"
    cards = []
    if not base.is_dir():
        return cards
    for d in sorted(base.iterdir()):
        sk = d / "SKILL.md"
        if not sk.is_file():
            continue
        try:
            txt = sk.read_text("utf-8", errors="replace")
        except OSError:
            txt = ""
        desc = ""
        m = re.search(r"(?m)^description:\s*(.+)$", txt)
        if m:
            desc = m.group(1).strip().strip("\"'")
        else:
            h = re.search(r"(?m)^#\s+(.+)$", txt)
            if h:
                desc = h.group(1).strip()
        try:
            age = round(time.time() - sk.stat().st_mtime)
        except OSError:
            age = None
        cards.append({"name": d.name, "desc": desc[:170], "age_sec": age,
                      "mandatory": d.name in _MANDATORY_SKILLS})
    return cards


def brain_state() -> dict:
    """Estado VIVO da aba Cerebro: o que a sessao carrega (do CLAUDE.md) + frescor,
    o gate atual, o artefato canonico e a proxima acao (ROI). Reusa os endpoints
    existentes (gate_ledger/skp_timeline/next_best_actions) — fonte unica, sem
    duplicar logica. Cada sub-call e' guardada: uma falha vira sinal, nao 500."""
    claude_md = _file_state(".claude/CLAUDE.md")
    loaded = _loaded_from_claude_md()
    current_state = _current_state_freshness()

    # gate atual: livre / esperando consults / oraculo offline (reusa o ledger)
    try:
        pending = gate_ledger().get("pending", 0)
    except Exception:
        pending = 0
    claude_ok = bool(shutil.which("claude") or shutil.which("claude.cmd"))
    if not claude_ok:
        gate = {"badge": "DEPRECATED", "label": "oraculo offline (claude nao no PATH)"}
    elif pending > 0:
        gate = {"badge": "STALE", "label": f"{pending} consult(s) esperando o gate"}
    else:
        gate = {"badge": "LIVE", "label": f"livre · oraculo {MODEL} (modo B)"}

    # artefato canonico atual (reusa o timeline): o 1o com .skp; senao o 1o que exista
    artifact = None
    try:
        canon = skp_timeline().get("canonical", {})
    except Exception:
        canon = {}
    for plant, info in canon.items():
        if info.get("has_skp"):
            artifact = {"plant": plant, "skp": info.get("skp"), "verdict": info.get("verdict"),
                        "badge": "LIVE" if info.get("verdict") else "DRAFT"}
            break
    if artifact is None and canon:
        plant = next(iter(canon))
        artifact = {"plant": plant, "skp": None,
                    "verdict": canon[plant].get("verdict"), "badge": "DRAFT"}

    # proxima acao recomendada (reusa o backlog por ROI — top item)
    try:
        acts = next_best_actions().get("actions", [])
    except Exception:
        acts = []
    next_action = acts[0] if acts else None

    skills = _skill_cards()
    return {
        "claude_md": claude_md,
        "loaded": loaded,
        "current_state": current_state,
        "gate": gate,
        "artifact": artifact,
        "next_action": next_action,
        "skills": skills,
        "mandatory_skills": sorted(_MANDATORY_SKILLS),
        "skill_runtime_note": ("qual skill esta acionada AGORA nao e' rastreavel em runtime — "
                               "so a DISPONIBILIDADE e' honesta; a skill 'acende' pelo gatilho da task"),
        "counts": {"loaded": len(loaded),
                   "loaded_missing": sum(1 for x in loaded if not x.get("exists")),
                   "skills": len(skills)},
    }


def noc_actions() -> dict:
    """Estado do ATUADOR (NOC dispatcher) pra aba do dashboard: acoes recentes (ledger),
    fila pendente e se ha um dispatcher segurando o lock AGORA. So LEITURA — o cockpit
    nao atua; quem atua e o tools/claude_bridge/noc_dispatcher.py (processo a parte).
    Nada fabricado: tudo vem de .ai_bridge/noc/{actions.jsonl,queue.jsonl,dispatcher.lock}."""
    noc = REPO_ROOT / ".ai_bridge" / "noc"
    _TERMINAL = {"COMMITTED", "VISUAL_REVIEW_QUEUED", "NOOP", "VERIFY_FAILED"}

    def _jsonl(p):
        rows = []
        try:
            for ln in p.read_text("utf-8", errors="replace").splitlines():
                ln = ln.strip()
                if ln:
                    try:
                        rows.append(json.loads(ln))
                    except ValueError:
                        pass
        except OSError:
            pass
        return rows

    actions = _jsonl(noc / "actions.jsonl")
    for a in actions:
        a["age_sec"] = round(time.time() - float(a.get("t", time.time())))
    recent = list(reversed(actions))[:30]

    counts = {}
    for a in actions:
        counts[a.get("status", "?")] = counts.get(a.get("status", "?"), 0) + 1

    done = {a.get("task_id") for a in actions if a.get("status") in _TERMINAL}
    pending = [{"id": t.get("id"), "title": t.get("title"), "appearance": bool(t.get("appearance"))}
               for t in _jsonl(noc / "queue.jsonl")
               if t.get("id") not in done and t.get("safe") is not False]

    lock = {"held": False}
    try:
        d = json.loads((noc / "dispatcher.lock").read_text("utf-8"))
        age = round(time.time() - float(d.get("ts", 0)))
        lock = {"held": age <= 900, "owner": d.get("owner"), "pid": d.get("pid"), "age_sec": age}
    except (OSError, ValueError):
        pass

    return {"exists": (noc / "actions.jsonl").exists() or (noc / "queue.jsonl").exists(),
            "actions": recent, "counts": counts, "total_actions": len(actions),
            "pending": pending, "lock": lock,
            "visual_review_pending": [a for a in recent if a.get("status") == "VISUAL_REVIEW_QUEUED"],
            "note": "atuador = noc_dispatcher.py (processo a parte); este card so observa o ledger"}


def marcos() -> dict:
    """Marcos / subidas de nivel do projeto (timeline curada, versionada em
    tools/claude_bridge/marcos.json). Ordena por nivel desc (mais recente no topo).
    So leitura — a curadoria vive no JSON, nada fabricado aqui."""
    p = REPO_ROOT / "tools" / "claude_bridge" / "marcos.json"
    try:
        data = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError) as e:
        return {"exists": False, "marcos": [], "note": f"marcos.json indisponivel: {type(e).__name__}"}
    if not isinstance(data, list):
        data = []
    data = sorted(data, key=lambda m: m.get("nivel", 0), reverse=True)

    # metricas AUTO-COMPUTADAS do snapshot de PRs (peso/era + velocidade). Nada
    # hardcoded: o calculo roda ao vivo sobre pr_history.json (gerado por pr_history.py).
    metrics = {"available": False,
               "note": "pr_history.json ausente — rode tools/claude_bridge/pr_history.py"}
    snap = REPO_ROOT / "tools" / "claude_bridge" / "pr_history.json"
    try:
        s = json.loads(snap.read_text("utf-8"))
        from tools.claude_bridge.marcos_metrics import compute_metrics
        metrics = compute_metrics(s.get("prs", []), data)
        metrics["generated_at"] = s.get("generated_at")
        metrics["source"] = f"{s.get('source', 'gh pr list')} -> pr_history.json (snapshot)"
    except (OSError, ValueError) as e:
        metrics = {"available": False, "note": f"pr_history.json indisponivel: {type(e).__name__}"}
    except Exception as e:  # calculo nunca derruba o endpoint
        metrics = {"available": False, "note": f"erro no calculo: {type(e).__name__}: {e}"}

    return {"exists": True, "marcos": data, "count": len(data),
            "current_level": max((m.get("nivel", 0) for m in data), default=0),
            "metrics": metrics}


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


def _memory_search_route(req, url):
    """GET /api/memory/search?q=...&k=6 — RAG #2 (memória do projeto), read-only.
    Busca semântica na project_memory.db pra os agentes consultarem 'o que já
    fizemos e aprendemos'. Honesto em 400/500; nunca fabrica. NÃO toca o /ask."""
    try:
        params = parse_qs(url.query)
        query = (params.get("q") or params.get("query") or [""])[0].strip()
        if not query:
            req._send(400, {"error": "empty query (send ?q=...)"})
            return
        try:
            k = int((params.get("k") or ["6"])[0])
        except ValueError:
            k = 6
        k = max(1, min(k, 20))
        from tools.project_memory_db import search as _memory_search
        results = _memory_search(query, k)
        req._send(200, {"query": query, "count": len(results), "results": results})
    except Exception as e:  # índice ausente / Ollama offline -> erro honesto
        req._send(500, {"error": f"{type(e).__name__}: {e}"})


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
        tier = parse_ask_tier(body)
        question = apply_mode(prompt, mode)
        t0 = time.time()
        answer = ask_claude(question, tier=tier)
        _audit_append({"t": time.time(), "kind": "consult",
                       **consult_audit_fields(tier, mode),
                       "q_chars": len(prompt),
                       "a_chars": len(answer), "dur_sec": round(time.time() - t0, 1)})
        req._send(200, {"response": answer})
    except Exception as e:  # devolve erro honesto; nao fabrica resposta
        req._send(500, {"error": f"{type(e).__name__}: {e}"})


def _ask_vision_route(req, _url):
    """POST /ask-vision — painel COLABORATIVO de 3 juizes (estrutura + material_luz
    em paralelo -> sintese). Mesmo contrato HTTP de sempre: 'images' [paths abs]
    que o claude -p pode LER (--add-dir); devolve {"response": "<json/texto>"} —
    o cliente (oracle_providers.ClaudeBridgeVisionProvider) parseia igual, campos
    novos sao aditivos. Honest 500; painel nunca fabrica veredito/padrao de juiz
    que falhou (ver ask_claude_vision_panel)."""
    try:
        n = int(req.headers.get("Content-Length") or 0)
        body = req.rfile.read(n) if n else b""
        data = json.loads(body.decode("utf-8", errors="replace")) if body else {}
        prompt = (data.get("prompt") or data.get("question") or "").strip()
        images = data.get("images") or []
        if not prompt:
            req._send(400, {"error": "empty prompt"})
            return
        if not images:
            req._send(400, {"error": "no images (send 'images': [abs paths])"})
            return
        tier = data.get("tier") or DEFAULT_TIER
        t0 = time.time()
        answer = ask_claude_vision_panel(prompt, images, tier=tier)
        _audit_append({"t": time.time(), "kind": "consult_vision_panel",
                       "n_images": len(images), "a_chars": len(answer),
                       "dur_sec": round(time.time() - t0, 1)})
        req._send(200, {"response": answer})
    except Exception as e:
        req._send(500, {"error": f"{type(e).__name__}: {e}"})


def _heartbeat_route(req, _url):
    req._heartbeat()


def _process_consults_start_route(req, _url):
    try:
        req._send(200, process_consults_start())
    except Exception as e:
        req._send(500, {"error": f"{type(e).__name__}: {e}"})


def local_llms() -> dict:
    """Local LLM fleet (Ollama on :11434): which models are installed and which are
    loaded in memory right now. Best-effort; returns up=False if the daemon is down.
    Powers the NOC 'Fleet local' card."""
    import urllib.request

    base = "http://127.0.0.1:11434"
    out = {"up": False, "version": "", "count": 0, "models": [], "running": []}

    def _get(path):
        with urllib.request.urlopen(base + path, timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        tags = _get("/api/tags")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    out["up"] = True

    running = set()
    try:
        running = {m.get("name", "") for m in (_get("/api/ps").get("models") or [])}
    except Exception:
        pass
    try:
        out["version"] = _get("/api/version").get("version", "")
    except Exception:
        pass

    models = []
    for m in (tags.get("models") or []):
        det = m.get("details") or {}
        name = m.get("name", "?")
        icon, role = _llm_role(name)
        models.append({
            "name": name,
            "gb": round((m.get("size") or 0) / (1024 ** 3), 1),
            "params": det.get("parameter_size", ""),
            "quant": det.get("quantization_level", ""),
            "family": det.get("family", ""),
            "running": name in running,
            "icon": icon,
            "role": role,
        })
    # carregados em memoria primeiro, depois alfabetico
    models.sort(key=lambda x: (not x["running"], x["name"]))
    out["models"] = models
    out["count"] = len(models)
    out["running"] = sorted(n for n in running if n)
    return out


# --- Fleet local: papel de cada modelo + acionamentos (parse do log Ollama) --
LLM_ROLES = {
    "planta-assistant": ("\U0001F3E0", "Decisões de planta / arquitetura"),
    "coder-assistant": ("\U0001F4BB", "Código SketchUp / Ruby"),
    "qwen2.5-coder": ("\U0001F4BB", "Código (geral)"),
    "deepseek-r1": ("\U0001F9E0", "Raciocínio / decisão técnica"),
    "qwen2.5vl": ("\U0001F441️", "Visão — review visual (FP-030)"),
    "moondream": ("\U0001F441️", "Visão leve / caption"),
    "interior-designer": ("\U0001F6CB️", "Mobiliar / design de interiores"),
    "llama3.1": ("\U0001F4AC", "Geral / fallback"),
}


def _llm_role(name: str):
    base = (name or "").split(":")[0]
    return LLM_ROLES.get(base, ("\U0001F916", "—"))


def llm_usage() -> dict:
    """Acionamentos por modelo, reconstruídos do log do Ollama (server*.log).
    Pareia cada `POST /api/(generate|chat|embeddings)` (linha GIN) com o
    último `template selection model=<nome>` (modelo carregado naquele
    instante). O Ollama não expõe contador por modelo via API; a janela
    é o que os logs rotacionados ainda guardam. 0 = sem registro na janela."""
    import os

    out = {"up": False, "total_calls": 0, "log_files": 0, "models": []}
    appdata = os.environ.get("LOCALAPPDATA", "")
    logdir = Path(appdata) / "Ollama" if appdata else None

    stats = {}
    total = 0
    files = []
    if logdir and logdir.is_dir():
        files = sorted(logdir.glob("server*.log"), key=lambda p: p.stat().st_mtime)
    sel_re = re.compile(r'msg="template selection" model=\S*/([^/\s]+)')
    gin_re = re.compile(r'\[GIN\]\s+([\d/]+ - [\d:]+).*?\|\s*POST\s+"/api/(?:generate|chat|embeddings|embed)"')
    dur_re = re.compile(r'\|\s*([\d.]+)(ms|µs|μs|us|s|m)\s*\|')
    cur = None
    for f in files:
        try:
            text = f.read_text("utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = sel_re.search(line)
            if m:
                cur = m.group(1)
                continue
            g = gin_re.search(line)
            if not g:
                continue
            model = cur or "(desconhecido)"
            st = stats.setdefault(model, {"calls": 0, "last_ts": "", "ms_total": 0.0})
            st["calls"] += 1
            st["last_ts"] = g.group(1)
            total += 1
            d = dur_re.search(line)
            if d:
                v, u = float(d.group(1)), d.group(2)
                st["ms_total"] += (v / 1000 if u in ("µs", "μs", "us")
                                   else v if u == "ms"
                                   else v * 60000 if u == "m"
                                   else v * 1000)

    base = local_llms()
    out["up"] = base.get("up", False)
    running = set(base.get("running") or [])
    seen, rows = set(), []
    for mm in base.get("models") or []:
        name = mm["name"]
        st = stats.get(name) or {}
        calls = st.get("calls", 0)
        rows.append({
            "name": name, "icon": mm.get("icon", "\U0001F916"), "role": mm.get("role", "—"),
            "installed": True, "running": name in running,
            "calls": calls, "last_ts": st.get("last_ts", ""),
            "avg_ms": round(st["ms_total"] / calls) if calls else 0,
            "gb": mm.get("gb", 0),
        })
        seen.add(name)
    for name, st in stats.items():
        if name in seen:
            continue
        icon, role = _llm_role(name)
        rows.append({
            "name": name, "icon": icon, "role": role,
            "installed": False, "running": False,
            "calls": st["calls"], "last_ts": st["last_ts"],
            "avg_ms": round(st["ms_total"] / st["calls"]) if st["calls"] else 0, "gb": 0,
        })
    rows.sort(key=lambda r: (-r["calls"], r["name"]))
    out["total_calls"] = total
    out["log_files"] = len(files)
    out["models"] = rows
    return out


# path (rstrip'd of trailing "/") -> command. "" is the form "/" and "/dashboard"
# reduce to. GET strips the query (urlparse); POST matches the raw path, as before.
GET_ROUTES = {
    "": _redirect_to_cockpit,
    "/dashboard": _redirect_to_cockpit,
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
    "/api/local-llms": _json_route(local_llms),
    "/api/llm-usage": _json_route(llm_usage),
    "/api/activity": _json_route(activity_summary),
    "/api/files": _json_route(recent_files),
    "/api/cognitive": _json_route(cognitive_doc),
    "/api/brain-state": _json_route(brain_state),
    "/api/noc-actions": _json_route(noc_actions),
    "/api/marcos": _json_route(marcos),
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
    "/api/memory/search": _memory_search_route,
}

POST_ROUTES = {
    "/ask": _ask_route,
    "/ask-vision": _ask_vision_route,
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
