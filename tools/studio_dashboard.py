"""studio_dashboard.py — dashboard VIVA do INTERIOR_STUDIO (:8782).

Painel em GUARDA-CHUVAS: cada líder (PM · Team Lead · Arquiteto) numa coluna, com seus
sub-agentes embaixo e o chat próprio; setas DINÂMICAS entre colunas quando um fala com o outro;
métricas (chamadas/erros por agente). Abaixo: backlog, sessões/coordenação, referências, curadoria,
galeria de renders. Servidor SEPARADO do oráculo :8765 (frágil). stdlib only.

Uso:  python tools/studio_dashboard.py [--port 8782]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ANGLES = ROOT / "artifacts/planta_74/furnished/kitchen_angles"
BACKLOG = ROOT / "artifacts/reference_lab/kitchen/spec/KITCHEN_TO_100.md"
COORD = ROOT / ".ai_bridge/SESSION_COORDINATION.md"
INBOX = ROOT / "artifacts/reference_lab/inbox/INBOX.json"
ARCH_KB = ROOT / ".ai_bridge/knowledge/architect.md"   # conhecimento que o Felipe alimenta (orientações do GPT)
FELIPE_DNA = ROOT / ".claude/memory/felipe_style_dna.md"               # identidade de estilo CANÔNICA (room-agnostic)
JUDGE_RULES = ROOT / "references/design_rules/felipe_visual_judge_rules.json"  # regras do juiz visual + erros marcados
KANBAN_FILE = ROOT / ".ai_bridge/kanban.json"          # status Trello de cada microtarefa (Felipe move)
CYCLES_FILE = ROOT / ".ai_bridge/interior_consult/cycles.jsonl"  # cada ciclo persistido (o "banco" do loop)
RELAY_FILE = ROOT / ".ai_bridge/interior_consult/relay.json"     # fila do relay Claude↔ChatGPT (Chrome)
KANBAN_COLS = ["backlog", "refinamento", "execução", "teste", "executado"]
SKIP = (".denoiser.png", ".effectsResult.png")
DEFAULT_PACK = "sofa_reference_pack_001"   # pack ativo da esteira (sofá = primeiro laboratório)

from tools.interior_studio import cycles as ic_cycles            # noqa: E402  entidade CYCLE (esteira)
from tools.interior_studio import reference_packs as ic_refpacks  # noqa: E402  Reference Pack + curadoria Felipe
from tools.interior_studio import gpt_review_bundle as ic_bundle  # noqa: E402  pacote de revisão pro Consult GPT
from tools.interior_studio import learning_patch as ic_patch      # noqa: E402  LEARNING_PATCH (resposta→patch→diff→aprova)


def _kanban_load():
    if KANBAN_FILE.exists():
        try:
            return json.loads(KANBAN_FILE.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _move_task(mt, direction):
    """Move a microtarefa entre as colunas do Kanban (Felipe arrasta com ◀ ▶)."""
    if not mt:
        return {"ok": False}
    k = _kanban_load()
    cur = k.get(mt) if k.get(mt) in KANBAN_COLS else "backlog"
    i = max(0, min(len(KANBAN_COLS) - 1, KANBAN_COLS.index(cur) + (1 if direction == "next" else -1)))
    k[mt] = KANBAN_COLS[i]
    KANBAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    KANBAN_FILE.write_text(json.dumps(k, ensure_ascii=False, indent=2), "utf-8")
    return {"ok": True, "mt": mt, "status": k[mt]}

ROSTER = [
    {"id": "interior-orchestrator", "face": "\U0001F3AF", "label": "Team Lead"},
    {"id": "interior-pm",           "face": "\U0001F4CB", "label": "PM"},
    {"id": "interior-designer",     "face": "\U0001F3A8", "label": "Arquiteto"},
    {"id": "reference-scout",       "face": "\U0001F52D", "label": "Scout"},
    {"id": "ollama-deepseek",       "face": "\U0001F433", "label": "DeepSeek"},
    {"id": "ollama-qwen",           "face": "\U0001F916", "label": "Qwen-coder"},
    {"id": "ollama-llama",          "face": "\U0001F999", "label": "Llama"},
    {"id": "gpt-visual",            "face": "\U0001F9E0", "label": "GPT (visão)"},
    {"id": "ollama-spec",           "face": "\U0001F4D0", "label": "Especialista-Spec"},
]
# Topologia: PM coordena (sem LLM); Team Lead consulta os LOCAIS (código); Arquiteto consulta GPT (visão).
UMBRELLAS = [
    {"id": "pm",        "label": "PM",        "lead": "interior-pm",           "subs": ["ollama-llama"]},
    {"id": "team_lead", "label": "Team Lead", "lead": "interior-orchestrator", "subs": ["ollama-qwen"]},
    {"id": "architect", "label": "Arquiteto", "lead": "interior-designer",     "subs": ["ollama-deepseek", "gpt-visual"]},
]


def _renders() -> list[dict]:
    if not ANGLES.is_dir():
        return []
    try:
        from tools import reference_db as rdb
        infer = rdb._infer_from_name
    except Exception:  # noqa: BLE001
        def infer(_n):
            return (None, None)
    out = []
    for p in sorted(ANGLES.glob("*.png"), key=lambda x: -x.stat().st_mtime):
        if p.name.endswith(SKIP):
            continue
        theme, sub = infer(p.name)
        out.append({"name": p.name, "theme": theme or "-", "sub": sub or "render",
                    "kb": round(p.stat().st_size / 1024), "mtime": int(p.stat().st_mtime)})
    return out


def _sessions() -> dict:
    wt = []
    try:
        r = subprocess.run(["git", "worktree", "list"], cwd=ROOT, capture_output=True,
                           text=True, timeout=10)
        wt = [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        pass
    claims = []
    if COORD.exists():
        for ln in COORD.read_text("utf-8", "ignore").splitlines():
            m = re.match(r"\|\s*(MT-[\w/]+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", ln)
            if m and m.group(1) != "MT":
                claims.append({"mt": m.group(1), "desc": m.group(2), "owner": m.group(3),
                               "status": m.group(4)})
    return {"worktrees": wt, "claims": claims}


def _backlog() -> dict:
    if not BACKLOG.exists():
        return {"total": 0, "pele": 0, "geo": 0, "done": 0, "tasks": []}
    txt = BACKLOG.read_text("utf-8", "ignore")
    mts = set(re.findall(r"MT-\d+", txt))
    geo = set(re.findall(r"(MT-\d+)\s*`?\[GEO\]", txt))
    done = set(re.findall(r"(MT-\d+)[^\n]*(?:DONE|✓|completed)", txt))
    kb = _kanban_load()
    tasks, seen = [], set()
    for ln in txt.splitlines():  # linhas de tabela: | **MT-NN** | descrição | ...
        if not ln.strip().startswith("|") or "MT-" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        for i, c in enumerate(cells):
            mm = re.search(r"(MT-\d+)", c)
            if mm and i + 1 < len(cells):
                mt = mm.group(1)
                if mt in seen:
                    break
                seen.add(mt)
                desc = re.sub(r"[*`\[\]]", "", cells[i + 1]).strip()
                status = kb.get(mt) if kb.get(mt) in KANBAN_COLS else ("executado" if mt in done else "backlog")
                tasks.append({"mt": mt, "what": desc[:90], "geo": mt in geo, "done": mt in done, "status": status})
                break
    return {"total": len(mts), "geo": len(geo), "pele": len(mts) - len(geo),
            "done": len(done), "tasks": tasks}


_REF_CACHE = {"t": 0.0, "v": None}   # cache 30s do reference_db (não reabrir SQLite a cada poll)


def _references() -> dict:
    if _REF_CACHE["v"] is not None and time.time() - _REF_CACHE["t"] < 30:
        return _REF_CACHE["v"]
    try:
        from tools import reference_db as rdb
        con = rdb.connect()
        rdb.init(con)
        if not con.execute("SELECT COUNT(*) FROM reference").fetchone()[0]:
            rdb.ingest(con)
        by_kind = dict(con.execute("SELECT kind, COUNT(*) FROM reference GROUP BY kind").fetchall())
        by_theme = dict(con.execute(
            "SELECT COALESCE(theme,'(sem tema)'), COUNT(*) FROM reference "
            "WHERE kind IN ('render','theme_preset') GROUP BY theme").fetchall())
        con.close()
        out = {"by_kind": by_kind, "by_theme": by_theme}
    except Exception as e:  # noqa: BLE001
        out = {"error": str(e)}
    _REF_CACHE.update(t=time.time(), v=out)
    return out


def _inbox() -> list[dict]:
    if not INBOX.exists():
        return []
    try:
        return json.loads(INBOX.read_text("utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return []


def _agents() -> dict:
    try:
        from tools import studio_log
        last = studio_log.latest_by_agent()
        feed = studio_log.tail(40)
        allrecs = studio_log.tail(1000)
    except Exception:  # noqa: BLE001
        last, feed, allrecs = {}, [], []
    facemap = {a["id"]: a for a in ROSTER}

    # status ONLINE dos LLMs locais (Ollama) — bolinha verde mesmo idle se o modelo está up
    try:
        from tools import ollama_bridge
        avail = set(ollama_bridge.available())
        rm = ollama_bridge.ROLE_MODEL
    except Exception:  # noqa: BLE001
        avail, rm = set(), {}
    online_map = {"ollama-deepseek": rm.get("deepseek"), "ollama-qwen": rm.get("qwen"),
                  "ollama-llama": rm.get("llama"), "ollama-spec": rm.get("designer"),
                  # o LÍDER mostra o status do modelo que ELE usa (PM=llama, Lead=qwen, Arq=deepseek)
                  "interior-pm": rm.get("llama"), "interior-orchestrator": rm.get("qwen"),
                  "interior-designer": rm.get("deepseek")}

    def card(aid):
        rec = last.get(aid)
        base = facemap.get(aid, {"face": "•", "label": aid})
        mdl = online_map.get(aid)
        return {"id": aid, "face": base["face"], "label": base["label"],
                "status": rec["status"] if rec else "idle",
                "message": rec["message"] if rec else "—",
                "ts": rec.get("ts") if rec else None,
                "to": rec.get("to") if rec else None,
                "online": bool(mdl and mdl in avail)}

    metrics = {}
    model_usage = {}   # chamadas REAIS aos LLMs (campo `via`), distinto de "mensagens no feed"
    for r in allrecs:
        m = metrics.setdefault(r["agent"], {"calls": 0, "errors": 0})
        m["calls"] += 1
        if r.get("status") == "error":
            m["errors"] += 1
        via = r.get("via")
        if via:
            model_usage[via] = model_usage.get(via, 0) + 1

    umbrellas = [{"id": u["id"], "label": u["label"], "lead": card(u["lead"]),
                  "subs": [card(s) for s in u["subs"]]} for u in UMBRELLAS]
    agent_umbrella = {}
    for u in UMBRELLAS:
        agent_umbrella[u["lead"]] = u["id"]
        for s in u["subs"]:
            agent_umbrella[s] = u["id"]
    return {"umbrellas": umbrellas, "feed": feed, "metrics": metrics,
            "agent_umbrella": agent_umbrella, "model_usage": model_usage}


def _learning_log() -> dict:
    """Agrega o aprendizado PERSISTENTE pra esteira: regras novas (Consult GPT → DNA), anti-patterns
    (juiz visual), golden samples congelados. Só LÊ — não fabrica nada."""
    new_rules: list = []
    anti_patterns: list = []
    golden: list = []
    ing_dir = ROOT / ".ai_bridge/interior_consult/ingested"
    if ing_dir.is_dir():
        for p in sorted(ing_dir.glob("*.json"))[-12:]:
            try:
                rec = json.loads(p.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            new_rules += rec.get("rules_added") or []
            anti_patterns += rec.get("anti_patterns_added") or []
    if JUDGE_RULES.exists():
        try:
            jd = json.loads(JUDGE_RULES.read_text("utf-8"))
            for a in jd.get("anti_patterns") or []:
                w = a.get("what") or a.get("id")
                if w:
                    anti_patterns.append(w)
        except (json.JSONDecodeError, OSError):
            pass
    try:
        new_rules += ic_patch.applied_rules()   # regras já aplicadas via LEARNING_PATCH aprovado
    except Exception:  # noqa: BLE001
        pass
    gs_dir = ROOT / "references/felipe/golden_samples"
    if gs_dir.is_dir():
        golden = [p.stem for p in sorted(gs_dir.glob("*")) if p.is_file()]

    def _dd(xs):
        seen, out = set(), []
        for x in xs:
            k = (x or "").strip().lower() if isinstance(x, str) else str(x)
            if k and k not in seen:
                seen.add(k)
                out.append(x.strip() if isinstance(x, str) else x)
        return out
    return {"new_rules": _dd(new_rules)[-15:], "anti_patterns": _dd(anti_patterns)[-15:],
            "golden_samples": golden}


def _state() -> dict:
    fac = ic_cycles.factory_state()
    pack_id = (fac.get("references") or {}).get("pack_id") or DEFAULT_PACK
    return {"agents": _agents(), "renders": _renders(), "sessions": _sessions(),
            "backlog": _backlog(), "references": _references(), "inbox": _inbox(),
            "knowledge": _knowledge_state(), "consult": _consult_state(), "cycles": _cycles_recent(8),
            "factory": fac, "refpack": ic_refpacks.pack_state(pack_id), "learning": _learning_log(),
            "patches": ic_patch.patches_state()}


PAGE = r"""<!doctype html><html lang=pt-BR><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>INTERIOR STUDIO — live</title>
<style>
:root{--bg:#0e0f12;--card:#16171c;--bd:#262a32;--fg:#e8e9ec;--mut:#9aa0aa;--ok:#7fd99a;--warn:#e6c069;--blu:#6ca8ff;--red:#e67c7c;--gold:#c9a86a}
*{box-sizing:border-box}
body{margin:0;color:var(--fg);font:14px/1.5 system-ui,Arial;min-height:100vh;
 background:radial-gradient(1100px 560px at 12% -8%, #1d1626 0%, #0e0f12 58%) fixed}
*::-webkit-scrollbar{width:9px;height:9px}*::-webkit-scrollbar-track{background:transparent}
*::-webkit-scrollbar-thumb{background:#2e2a3a;border-radius:6px;border:2px solid transparent;background-clip:padding-box}
*::-webkit-scrollbar-thumb:hover{background:#473d5c;background-clip:padding-box}
header{position:sticky;top:0;z-index:40;padding:12px 22px;display:flex;align-items:center;gap:16px;
 background:linear-gradient(90deg,#15131c,#121318);border-bottom:1px solid #2c2636}
h1{font-size:16px;margin:0;letter-spacing:.6px;font-weight:700;background:linear-gradient(90deg,#fff,var(--gold));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdot{width:9px;height:9px;border-radius:50%;background:var(--gold);box-shadow:0 0 9px var(--gold)}
nav{display:flex;gap:3px}nav a{color:var(--mut);text-decoration:none;font-size:12.5px;padding:4px 10px;border-radius:7px}
nav a:hover{color:var(--fg);background:#1f1b29}
.mut{color:var(--mut);font-size:12.5px}.wrap{padding:16px 20px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px;overflow:auto;resize:both;min-height:84px;min-width:300px;width:100%;max-width:100%;box-sizing:border-box;flex:0 0 auto}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:0 0 10px}
.card.collapsed{height:auto!important;resize:none}
.wbtn{cursor:pointer;color:#7a8696;font-size:12px;margin-right:5px;user-select:none}.wbtn:hover{color:var(--gold)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.thumb{border:1px solid var(--bd);border-radius:8px;overflow:hidden;background:#000}
.thumb img{width:100%;display:block;aspect-ratio:4/3;object-fit:cover}
.thumb .cap{padding:5px 7px;font-size:11px}.thumb .t{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:12.5px}td,th{border:1px solid var(--bd);padding:5px 8px;text-align:left}
th{color:var(--mut);font-weight:600}.pill{display:inline-block;padding:1px 8px;border-radius:10px;background:#20242b;font-size:11px}
.bar{height:8px;background:#20242b;border-radius:4px;overflow:hidden;margin-top:6px}.bar>i{display:block;height:100%;background:var(--ok)}
.k{display:inline-block;margin-right:14px}.k b{font-size:18px}
/* ORG / guarda-chuvas */
.org{position:relative}
.arrows{position:absolute;left:0;top:0;pointer-events:none;z-index:3;overflow:visible}
.cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:26px;position:relative;z-index:1;padding-top:30px}
@media(max-width:980px){.cols{grid-template-columns:1fr;gap:16px}}
.bub .btxt{overflow-wrap:anywhere;word-break:break-word}
.col{background:#13151a;border:1px solid var(--bd);border-radius:12px;padding:15px;display:flex;flex-direction:column}
.lead{display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--bd);padding-bottom:9px;margin-bottom:9px}
.lead .face{font-size:30px;line-height:1}.lead .nm{font-weight:700;font-size:15px}
.lead .msg{color:var(--mut);font-size:11.5px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.askto{font-size:10.5px;color:var(--gold);margin-left:6px}
.pmbox{background:#15131c;border:1px solid #2c2636;border-left:3px solid var(--gold);border-radius:8px;padding:7px 11px;margin-bottom:9px;font-size:11.5px;color:#cdb98a}.pmbox b{color:var(--gold)}
.cyc-help{margin:5px 0;padding:6px 8px;background:#0e0d14;border-radius:6px;color:#9aa0aa;font-size:11px;line-height:1.45}.cyc-help b{color:#cdb98a}
.cyc-next{margin:5px 0;font-size:12px;color:#e8e9ec}
.cycnav{cursor:pointer;background:#15131c;border:1px solid #2c2636;border-left:3px solid var(--gold);border-radius:7px;padding:6px 9px;margin-bottom:9px;font-size:11.5px;color:#cdb98a}.cycnav:hover{background:#1d1826}.cycnav b{color:var(--gold)}
.askbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.askbar select,.askbar input{background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:8px;padding:8px 11px;font:13px system-ui}
.askbar input{flex:1;min-width:220px}
.qhist{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.qchip{cursor:pointer;background:#0c0d10;border:1px solid var(--bd);border-radius:12px;padding:3px 10px;font-size:11.5px;color:#cdb98a}.qchip:hover{border-color:var(--gold);color:#fff}
.cycsec{margin-top:16px;border-top:1px solid var(--bd);padding-top:13px}
.cycsec-h{font-size:13px;color:var(--gold);font-weight:600;margin-bottom:9px}
.convbox{max-height:430px;overflow-y:auto;padding:8px 12px;background:#0c0d10;border:1px solid var(--bd);border-radius:8px;display:flex;flex-direction:column}
.bub.cons{border:1px solid var(--gold)}
.scoutlist{display:flex;flex-direction:column;gap:6px;margin-top:10px;max-height:340px;overflow-y:auto}
.scoutrow{background:#0c0d10;border:1px solid var(--bd);border-radius:7px;padding:8px 11px;font-size:12.5px}
.mtlink{cursor:pointer;border-bottom:1px dotted var(--gold)}.mtlink:hover{color:#fff}
.kc-hl{outline:2px solid var(--gold);outline-offset:1px;box-shadow:0 0 0 4px rgba(201,168,106,.18)}
.cylist{display:flex;flex-direction:column;gap:9px}
.cyrow{background:#0c0d10;border:1px solid var(--bd);border-left:3px solid var(--blu);border-radius:8px;padding:9px 12px}
.cyhd{font-size:12.5px;margin-bottom:4px}
.cydir{font-size:13px;color:#e8e9ec;line-height:1.5;margin:3px 0 6px;cursor:pointer;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.cydir.exp{-webkit-line-clamp:unset;overflow:visible}
.cymeta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:11px}
.subs{display:flex;flex-direction:row;flex-wrap:wrap;gap:6px;margin-bottom:9px}
.sub{display:flex;gap:8px;align-items:center;background:#181a1f;border:1px solid var(--bd);border-radius:8px;padding:4px 9px;flex:1 1 auto;min-width:128px}
.sub .face{font-size:15px;opacity:.55}.sub.act .face,.lead.act .face{opacity:1}
.sub .nm{font-size:12.5px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sdot{width:8px;height:8px;border-radius:50%;background:#5a606b;display:inline-block;margin-left:auto;flex:none}
.s-working .sdot,.s-thinking .sdot{background:var(--ok);box-shadow:0 0 7px var(--ok);animation:pulse 1.1s infinite}
.s-done .sdot{background:var(--blu)}.s-blocked .sdot,.s-error .sdot{background:var(--red)}.s-waiting .sdot{background:var(--warn)}
.stag{font-size:10px;color:var(--mut);margin-left:6px}
.clearbtn{margin-left:8px;background:#2a1a1a;border:1px solid #4a2a2a;color:#e6a0a0;border-radius:6px;padding:1px 8px;cursor:pointer;font-size:10.5px}.clearbtn:hover{background:#3a2222}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.chat{background:#0c0d10;border:1px solid var(--bd);border-radius:8px;padding:10px 12px;flex:1;min-height:200px;max-height:460px;overflow-y:auto;font-size:12.5px}
.chat .ln{padding:2px 0;border-bottom:1px solid #16181d}.chat .to{color:var(--ok)}.chat .t{color:var(--mut);font-size:10px;float:right}
.arrow{fill:none;stroke:var(--ok);stroke-width:1.7;stroke-dasharray:6 6;opacity:.8;animation:flow 1.1s linear infinite;filter:drop-shadow(0 0 2px var(--ok))}
@keyframes flow{to{stroke-dashoffset:-13}}
/* métricas */
.metrics{margin-top:14px}.mrow{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12px}
.mrow .nm{width:130px;color:var(--mut)}.mbar{flex:1;display:flex;gap:3px;align-items:center}
.mbar .c{height:11px;background:var(--blu);border-radius:3px;min-width:2px}.mbar .e{height:11px;background:var(--red);border-radius:3px}
.mnum{font-size:11px;color:var(--mut);width:92px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}
.chartbox{background:#13151a;border:1px solid var(--bd);border-radius:10px;padding:12px}
.pie{display:flex;gap:14px;align-items:center}.pie svg{width:118px;height:118px;flex:none}
.legend{font-size:12px}.lg{display:flex;align-items:center;gap:6px;margin:2px 0}.sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.flagrow{display:flex;gap:6px;margin-top:10px}.flagrow input{flex:1;background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:6px;padding:4px 7px;font-size:12px}
.flagrow select,.flagrow button,td button{background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:6px;padding:3px 8px;font-size:12px;cursor:pointer}
.flagrow button:hover,td button:hover{background:#1f2227}
.onl{color:var(--ok);font-size:9.5px;border:1px solid #2a4030;border-radius:8px;padding:0 5px}
.off{color:#6a6f78;font-size:9.5px;border:1px solid #2a2d34;border-radius:8px;padding:0 5px}
.sdot.on{background:var(--ok);box-shadow:0 0 7px var(--ok)}
.arrow.err{stroke:var(--red);filter:drop-shadow(0 0 4px var(--red))}
.askrow{display:flex;gap:5px;margin-top:8px}.askrow input{flex:1;background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:6px;padding:4px 7px;font-size:11.5px}
.askrow button{background:#0c0d10;border:1px solid var(--bd);color:var(--ok);border-radius:6px;padding:4px 9px;cursor:pointer}.askrow button:hover{background:#1f2227}
.uprow{display:flex;gap:8px;align-items:center;margin-bottom:6px;font-size:12px}.uprow input[type=file]{color:var(--mut);font-size:11.5px}
.uprow button{background:#0c0d10;border:1px solid var(--bd);color:var(--ok);border-radius:6px;padding:4px 9px;cursor:pointer}.uprow button:hover{background:#1f2227}
.upbtn{background:#1a1622;border:1px solid #2c2636;color:var(--gold);border-radius:7px;padding:5px 12px;cursor:pointer;font-size:12px}.upbtn:hover{background:#221c2e}
.bub{max-width:84%;padding:7px 11px;border-radius:11px;margin:6px 0;font-size:12.5px;line-height:1.45;word-break:break-word}
.bub.me{background:#1f3a4d;margin-left:auto;border-bottom-right-radius:3px}
.bub.them{background:#1d2026;border:1px solid var(--bd);margin-right:auto;border-bottom-left-radius:3px}
.bub .bt{font-size:9px;color:var(--mut);margin-top:2px}
.send{background:#192219!important;color:var(--ok)!important;border:1px solid #2c3a2c!important;font-weight:600;padding:3px 9px!important;font-size:11.5px}.send:hover{background:#21301f!important}
.critwrap{display:flex;gap:12px;align-items:flex-start;margin-bottom:8px}
.critic{width:230px;border:1px solid var(--bd);border-radius:8px;flex:none;cursor:pointer}.critic:hover{border-color:var(--gold)}
.thumb{cursor:pointer;position:relative}.lnk{color:var(--blu);cursor:pointer;text-decoration:underline}
.trash{background:#2a1a1a;border:1px solid #4a2a2a;color:#e6a0a0;border-radius:6px;padding:2px 7px;cursor:pointer;font-size:12px}.trash:hover{background:#3a2222}
.thumbtrash{position:absolute;top:5px;right:5px;padding:1px 6px;z-index:2}
.minithumb{width:46px;height:34px;object-fit:cover;border-radius:5px;cursor:pointer;border:1px solid var(--bd)}
.tklist{max-height:260px;overflow-y:auto;margin-top:10px}
.tk{padding:4px 0;font-size:12.5px;border-bottom:1px solid #181a20}
.tg{font-size:10px;padding:1px 6px;border-radius:8px}.tg.pele{background:#19281f;color:var(--ok)}.tg.geo{background:#2a2419;color:var(--warn)}
.kboard{display:flex;gap:12px;overflow-x:auto;padding-bottom:6px;margin-top:10px}
.kcol{flex:1;min-width:185px;background:#101116;border:1px solid var(--bd);border-radius:10px;padding:9px}
.kcol-h{font-size:12px;font-weight:600;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;margin-bottom:8px;border-bottom:1px solid var(--bd);padding-bottom:6px}
.kcol-b{display:flex;flex-direction:column;gap:7px;max-height:340px;overflow-y:auto}
.kcard{background:#181a20;border:1px solid var(--bd);border-radius:8px;padding:7px 9px}
.kc-top{font-size:12px;margin-bottom:3px}.kc-what{font-size:11.5px;color:var(--mut);line-height:1.35}
.kc-mv{margin-top:5px;display:flex;gap:5px;justify-content:flex-end}
.kc-mv button{background:#0c0d10;border:1px solid var(--bd);color:var(--gold);border-radius:5px;padding:1px 8px;cursor:pointer;font-size:11px}.kc-mv button:hover{background:#1f1b29}
textarea{width:100%;min-height:90px;background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:8px;padding:8px 11px;font:13px system-ui;resize:vertical}
.upbtn{display:inline-block;background:#0c0d10;border:1px solid var(--bd);color:var(--blu);border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11.5px;font-weight:600}.upbtn:hover{background:#16202e}
.kblist-h{margin:12px 0 6px;font-size:12px;color:var(--mut);font-weight:600}
.kblist{max-height:200px;overflow-y:auto;display:flex;flex-direction:column;gap:5px;padding-right:4px}
.kbi{display:flex;align-items:center;gap:8px;background:#0c0d10;border:1px solid var(--bd);border-radius:7px;padding:5px 9px}
.kbi-t{flex:1;font-size:12.5px;color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.consult-grid{display:grid;grid-template-columns:1fr 1fr 1fr 1.4fr;gap:7px;margin-bottom:7px}
.consult-grid select,.consult-grid input{background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:7px;padding:6px 9px;font:12px system-ui}
.consult-half{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:760px){.consult-grid{grid-template-columns:1fr 1fr}.consult-half{grid-template-columns:1fr}}
.consult-res{margin-top:9px;background:#0c0d10;border:1px solid var(--bd);border-left:3px solid var(--gold);border-radius:7px;padding:8px 11px;font-size:12.5px}
.mbar .e{max-width:90px}
.drag{cursor:grab;color:#5a6472;font-size:15px;margin-right:9px;user-select:none;vertical-align:middle}.drag:hover{color:var(--gold)}.drag:active{cursor:grabbing}
.card.dragover{outline:2px dashed var(--gold);outline-offset:2px}
.collapse-btn{cursor:pointer;color:#7a8696;font-size:13px;margin-right:5px;user-select:none}.collapse-btn:hover{color:var(--gold)}
.card.collapsed>*:not(h2){display:none}
.card.collapsed{padding-bottom:13px}.card.collapsed h2{margin-bottom:0}
.gallery{max-height:330px;overflow-y:auto;padding-right:4px}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.86);z-index:50;align-items:center;justify-content:center;padding:24px}
.modal.show{display:flex}.mbox{max-width:92vw;max-height:92vh;display:flex;flex-direction:column;gap:8px}
.mbar{display:flex;gap:10px;align-items:center}.mbar span{flex:1;font-size:13px;color:var(--mut)}
.mbtn{background:#1f2227;border:1px solid var(--bd);color:var(--fg);border-radius:7px;padding:5px 11px;cursor:pointer;text-decoration:none;font-size:12.5px}
.mbtn:hover{background:#2a2d34}.mbox img{max-width:92vw;max-height:82vh;object-fit:contain;border:1px solid var(--bd);border-radius:8px;background:#000}
.cmodal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:55;align-items:center;justify-content:center;padding:28px}
.cmodal.show{display:flex}
.cbox{width:min(740px,94vw);height:min(82vh,740px);background:var(--card);border:1px solid var(--bd);border-radius:14px;display:flex;flex-direction:column;overflow:hidden}
.cbar{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--bd)}.cbar span{flex:1;font-weight:600;font-size:14px}
.cbody{flex:1;overflow-y:auto;padding:14px 16px}
.crow{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--bd)}
.crow input{flex:1;background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:8px;padding:8px 12px;font-size:13px}
.chatbtn{background:#0c0d10;border:1px solid var(--bd);color:var(--gold);border-radius:6px;padding:3px 8px;cursor:pointer;font-size:12px}.chatbtn:hover{background:#1f1b29}
/* 🏭 FÁBRICA — barra de estado atual */
#sec-factory{border-left:3px solid var(--gold)}
.facbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
.facpill{background:#15131c;border:1px solid #2c2636;border-radius:9px;padding:3px 10px;font-size:12px;color:#cdb98a}
.facpill.cid{border-color:var(--gold);color:var(--gold);font-weight:700}
.facpill.st{background:#19281f;border-color:#2c3a2c;color:var(--ok)}
.facnext{font-size:13px;color:#e8e9ec;margin:4px 0}
.facacts{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:7px 0 4px}
.facbundle{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:12px;border-top:1px dashed #2c2636;padding-top:7px;margin-top:4px}
.facblock{margin-top:7px;background:#2a1717;border:1px solid #4a2a2a;border-radius:8px;padding:7px 11px;color:#e6a0a0;font-size:12.5px}
.refimg{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:8px;margin-bottom:8px;background:#000;cursor:pointer;border:1px solid var(--bd)}
.refimg-ph{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;width:100%;aspect-ratio:4/3;border-radius:8px;margin-bottom:8px;background:#101116;border:1px dashed var(--bd);color:var(--blu);text-decoration:none;font-size:12.5px}.refimg-ph:hover{border-color:var(--gold)}
/* 🔧 TIMELINE do ciclo */
.tllist{display:flex;flex-direction:column;gap:6px}
.tlstep{background:#0c0d10;border:1px solid var(--bd);border-left:3px solid #3a3f49;border-radius:8px;padding:7px 11px}
.tlstep.tl-done{border-left-color:var(--ok)}.tlstep.tl-doing{border-left-color:var(--blu)}
.tlstep.tl-wait{border-left-color:var(--warn)}.tlstep.tl-block{border-left-color:var(--red)}
.tlstep.tl-na,.tlstep.tl-pend{opacity:.62}
.tlhead{font-size:12.5px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}.tlface{font-size:15px}
.tlicon{font-weight:700}.tlstep.tl-done .tlicon{color:var(--ok)}.tlstep.tl-block .tlicon{color:var(--red)}.tlstep.tl-wait .tlicon{color:var(--warn)}
.tlsum{font-size:12px;color:var(--mut);margin-top:3px;line-height:1.4}
/* 🖼️ REFERENCE PACK + curadoria */
.refgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:11px}
.refcard{background:#0c0d10;border:1px solid var(--bd);border-radius:10px;padding:11px 13px;border-top:3px solid #3a3f49}
.refcard.rs-main{border-top-color:var(--gold);box-shadow:0 0 0 1px rgba(201,168,106,.35)}
.refcard.rs-approved{border-top-color:var(--ok)}.refcard.rs-rejected{border-top-color:var(--red);opacity:.7}
.refcard.rs-anti{border-top-color:#a05a5a;background:#160f0f}
.refhd{font-size:13px;margin-bottom:5px}.reftags{margin-bottom:6px;display:flex;gap:5px;flex-wrap:wrap}
.rb-main{background:#2a2417;color:var(--gold)}.rb-approved{background:#19281f;color:var(--ok)}.rb-rejected{background:#281717;color:var(--red)}.rb-anti{background:#2a1717;color:#e6a0a0}.rb-pending{color:var(--mut)}
.refbody{font-size:12px;color:#cfd2d8;line-height:1.5;margin-bottom:8px}.refbody b{color:var(--fg)}
.refact{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.cbtn{background:#15131c;border:1px solid #2c2636;border-radius:7px;padding:3px 10px;cursor:pointer;font-size:14px}.cbtn:hover{background:#221c2e;border-color:var(--gold)}
.cbtn-star{font-size:12.5px;color:var(--gold);border-color:#4a3f22;font-weight:600}.cbtn-star:hover{background:#2a2417}
.cbtn-star.pulse{box-shadow:0 0 0 0 rgba(201,168,106,.5);animation:starpulse 1.6s infinite}
@keyframes starpulse{0%{box-shadow:0 0 0 0 rgba(201,168,106,.45)}70%{box-shadow:0 0 0 7px rgba(201,168,106,0)}100%{box-shadow:0 0 0 0 rgba(201,168,106,0)}}
.tlneed{margin-top:5px;font-size:12px;color:var(--warn);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.refhint{background:#1a1622;border:1px solid #4a3f22;border-left:3px solid var(--gold);border-radius:8px;padding:8px 12px;font-size:12.5px;color:#e8d9b8;margin-bottom:8px}
.refhint.ok{border-color:#2c3a2c;border-left-color:var(--ok);background:#13191420;color:var(--ok)}
.reftray{margin-top:12px;border-top:1px dashed #2c2636;padding-top:8px}
.reftrayrow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:#0c0d10;border:1px solid var(--bd);border-radius:7px;padding:5px 10px;margin-bottom:5px;font-size:12.5px}
.reftrayt{flex:1;min-width:200px;color:var(--mut)}
/* 📚 LEARNING LOG */
.llgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.lllist{margin:4px 0;padding-left:18px;font-size:12.5px;line-height:1.5;max-height:240px;overflow-y:auto}.lllist li{margin:2px 0}
/* 🧠 LEARNING PATCH (diff) */
#sec-patch{border-left:3px solid var(--gold)}
.patchhd{font-size:13.5px;margin-bottom:3px}
.patchdiff{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:6px 0}
@media(max-width:760px){.patchdiff{grid-template-columns:1fr}}
.difflist{margin:4px 0;padding-left:6px;list-style:none;font-size:12.5px;line-height:1.55}
.difflist li{padding:2px 8px;border-radius:5px;margin:3px 0}
.difflist li.add{background:#14241a;border-left:3px solid var(--ok);color:#bfe8cb}.difflist li.add::before{content:'+ ';color:var(--ok);font-weight:700}
.difflist li.dup{background:#181a20;color:#7a8696;text-decoration:line-through;opacity:.7}.difflist li.dup::before{content:'≡ '}
.patchacts{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;border-top:1px dashed #2c2636;padding-top:8px}
</style></head><body>
<header><span class=hdot></span><h1>INTERIOR STUDIO <span style="font-size:11px;color:var(--mut);font-weight:400">· o dash · :8782</span></h1>
<nav><a href="http://localhost:8783/" target=_blank style="color:#f0a868;font-weight:700" title="vitrine / porta de entrada (Mapa, Fluxo, Agentes, Como funciona)">🏠 Vitrine :8783</a><a href="http://localhost:8783/grafo" target=_blank style="color:var(--gold);font-weight:700">🕸 Mapa</a><a href="http://localhost:8783/fluxo" target=_blank style="color:var(--gold);font-weight:700">⛓ Fluxo</a><a href="#sec-factory">Ciclo</a><a href="#sec-agents">Agentes</a><a href="#sec-cur">Curadoria</a><a href="#sec-ren">Renders</a></nav>
<span class=mut style="margin-left:auto;font-size:11px">🔓 ⠿ mover · ▭ largura · puxa a borda ↕ pra altura</span><button onclick=resetLayout() title="voltar ao layout padrão" style="background:#0c0d10;border:1px solid var(--bd);color:var(--mut);border-radius:6px;padding:3px 8px;cursor:pointer;font-size:11px;margin:0 12px">↺ layout</button><span class=mut id=ts>carregando…</span><span class=mut>· :8782</span></header>
<div class=wrap id=root></div>
<div id=modal class=modal onclick="if(event.target===this)closeModal()">
 <div class=mbox><div class=mbar><span id=mname></span>
  <a id=mdl class=mbtn download>⬇ baixar</a><button class=mbtn onclick="copyImg(event)">copiar URL</button><button class=mbtn onclick=closeModal()>✕ fechar</button></div>
  <img id=mimg></div></div>
<div id=chatmodal class=cmodal>
 <div class=cbox><div class=cbar><span id=cname></span><button class=mbtn onclick=closeChat()>✕ fechar</button></div>
  <div id=cbody class=cbody></div>
  <div class=crow><input id=cinput placeholder="escreve aqui… (Enter envia)" onkeydown="if(event.key==='Enter')sendChat()"><button class=send onclick=sendChat()>➤ enviar</button><button class=chatbtn onclick="sendChat(1)" title="consenso: pergunta pros 3 LLMs locais e sintetiza (mais lento, mais pensado)">🧠 consenso</button></div>
 </div></div>
<script>
const el=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstChild}
const esc=(t)=>(t||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))
const hhmm=(ts)=>ts?new Date(ts*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):''
const MODELFACE={'deepseek-r1:14b':'🐳','qwen2.5-coder:14b':'🤖','llama3.1:8b':'🦙','interior-designer:latest':'🎨','coder-assistant:latest':'🛠️','qwen2.5vl:7b':'👁️','moondream:latest':'👁️'}
const viaTag=(v)=>!v?'':(v.indexOf('consenso')===0?' · 🧠 consenso (3 IAs)':' · via '+(MODELFACE[v]||'🤖'))
function leadCard(a){const act=(a.status==='working'||a.status==='thinking')?'act':''
 const clr=a.status==='error'?`<button class=clearbtn onclick="clearErr('${a.id}')">limpar</button>`:''
 const to=(a.to&&a.to!=='felipe')?`<span class=askto>→ ${FACES[a.to]||''} ${esc(LABELS[a.to]||a.to)}</span>`:''
 let ic={working:'⚙️ trabalhando…',thinking:'💭 pensando…',done:'✓ respondeu',error:'⚠️ deu erro',idle:'• ocioso',waiting:'⏳ aguardando'}[a.status]||a.status
 if(a.message&&a.message.indexOf('aprendi')===0)ic='📚 aprendeu algo'
 return `<div class="lead s-${a.status} ${act}" id="lead-${a.id}"><div class=face>${a.face}</div>
  <div style=flex:1><div class=nm>${a.label}<span class=stag>${a.status}</span> <span class=sdot></span>${to}${clr}</div>
  <div class=msg>${ic}</div></div></div>`}
function subCard(a){const act=(a.status==='working'||a.status==='thinking'||a.online)?'act':''
 const on=a.online?'<span class=onl>online</span>':'<span class=off>offline</span>'
 return `<div class="sub s-${a.status} ${act}" title="${esc(a.message)}"><span class=face>${a.face}</span><span class=nm>${a.label}</span> ${on}<span class="sdot ${a.online?'on':''}"></span></div>`}
function colChat(feed,ids){const f=(feed||[]).filter(x=>ids.includes(x.agent)||(x.agent==='felipe'&&ids.includes(x.to))).slice(-16)
 return f.map(x=>{const me=x.agent==='felipe'
  return `<div class="bub ${me?'me':'them'}"><div class=btxt>${esc(x.message)}</div><div class=bt>${FACES[x.agent]||'🤖'} ${esc(LABELS[x.agent]||x.agent)}${viaTag(x.via)} · ${hhmm(x.ts)}</div></div>`}).join('')||'<span class=mut>sem conversa — pergunta abaixo ⬇</span>'}
function drawArrows(ag){const svg=document.getElementById('arrows'),wrap=document.getElementById('org');if(!svg||!wrap)return
 const wr=wrap.getBoundingClientRect();svg.setAttribute('width',wr.width);svg.setAttribute('height',wr.height)
 const amap=ag.agent_umbrella||{},recent=(ag.feed||[]).slice(-7).filter(f=>f.to)
 const errU=new Set((ag.umbrellas||[]).filter(u=>u.lead.status==='error').map(u=>u.id))
 const edges=new Set();recent.forEach(f=>{const su=amap[f.agent],tu=amap[f.to]||f.to;if(su&&tu&&su!==tu)edges.add(su+'>'+tu)})
 const box=(u)=>{const e=document.getElementById('lead-'+leadOf(u));if(!e)return null;const r=e.getBoundingClientRect()
  return{l:r.left-wr.left,ri:r.right-wr.left,cx:r.left-wr.left+r.width/2,my:r.top-wr.top+r.height/2}}
 let p='<defs><marker id=ah markerWidth=8 markerHeight=8 refX=6 refY=3 orient=auto><path d="M0,0 L6,3 L0,6 Z" fill="#7fd99a"/></marker><marker id=ahr markerWidth=8 markerHeight=8 refX=6 refY=3 orient=auto><path d="M0,0 L6,3 L0,6 Z" fill="#e67c7c"/></marker></defs>'
 edges.forEach(e=>{const[a,b]=e.split('>'),A=box(a),B=box(b);if(!A||!B)return
  const lr=B.cx>A.cx,x0=lr?A.ri:A.l,x1=lr?B.l:B.ri,cy=(A.my+B.my)/2-10,er=errU.has(b)
  p+=`<path class="arrow ${er?'err':''}" marker-end="url(#${er?'ahr':'ah'})" d="M${x0},${A.my} Q${(x0+x1)/2},${cy} ${x1},${B.my}"/>`})
 svg.innerHTML=p}
let LEADOF={},FACES={},LABELS={};const leadOf=(u)=>LEADOF[u]
async function curate(slug,action){await fetch('/api/curate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slug,action})});tick(1)}
let FACTORY={},BUNDLE=null
function curateRef(packId,refId,action){fetch('/api/curate-ref',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pack_id:packId,ref_id:refId,action,cycle_id:FACTORY.cycle_id||null})}).then(()=>tick(1))}
function cpTxt(t,ev){if(t&&navigator.clipboard)navigator.clipboard.writeText(t);if(ev){const b=ev.target,o=b.textContent;b.textContent=t?'copiado!':'gera o pacote 1º';setTimeout(()=>b.textContent=o,1300)}}
function refpackImages(packId){const m=document.getElementById('rpimgmsg');if(m)m.textContent='🖼 puxando imagens (og:image)…'
 fetch('/api/refpack-images',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pack_id:packId})}).then(r=>r.json()).then(r=>{if(m)m.textContent=r.ok?('✓ '+r.resolved+'/'+r.total+' imagens'):('erro: '+(r.error||''));tick(1)})}
function genBundle(){const m=document.getElementById('bundlemsg');if(m)m.textContent='📦 gerando pacote pro GPT…'
 fetch('/api/gpt-bundle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})}).then(r=>r.json()).then(r=>{BUNDLE=r
  if(m)m.textContent=r.ok?('✓ '+(r.md_path||'')+' · branch '+(r.branch||'?')+(r.raw_link?' · link raw pronto (pós-push)':' · sem remote')):('erro: '+(r.error||''));tick(1)})}
function copyBundle(ev){cpTxt(BUNDLE&&BUNDLE.md,ev)}
function copyBundleLink(ev){cpTxt(BUNDLE&&BUNDLE.raw_link,ev)}
function copyShortQ(ev){cpTxt(BUNDLE&&BUNDLE.question,ev)}
function nextStepGo(kind){jumpTo({scout:'sec-scout',consult:'sec-consult',curate:'sec-refpack',build:'sec-ciclo'}[kind]||'sec-ciclo')}
function consultRelay(){const m=document.getElementById('cqmsg');if(m)m.textContent='🤖 pedindo relay…'
 fetch('/api/consult/relay-request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})}).then(r=>r.json()).then(r=>{if(m)m.textContent=r.ok?('🤖 relay pedido pra '+r.question_id+' — me fala "relaya" no chat que eu dirijo o ChatGPT'):('erro: '+(r.error||''));tick(1)})}
function jumpTo(id){const sec=document.getElementById(id);if(sec){sec.scrollIntoView({behavior:'smooth',block:'center'});sec.classList.add('kc-hl');setTimeout(()=>sec.classList.remove('kc-hl'),2000)}}
function flagErr(){const a=document.getElementById('flagag').value,m=document.getElementById('flagmsg').value;if(!m)return
 fetch('/api/flag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent:a,message:m})}).then(()=>{document.getElementById('flagmsg').value='';tick(1)})}
function clearErr(agent){fetch('/api/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent})}).then(()=>tick(1))}
function fetchPreview(slug){fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slug})}).then(()=>tick(1))}
function feedArch(){const t=(document.getElementById('feedtext').value||'').trim(),ti=(document.getElementById('feedtitle').value||'').trim();if(!t)return
 const msg=document.getElementById('feedmsg');msg.textContent='alimentando…'
 fetch('/api/feed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,title:ti})}).then(r=>r.json()).then(r=>{document.getElementById('feedtext').value='';document.getElementById('feedtitle').value='';msg.textContent=r.ok?('✓ aprendido — '+(r.count||'?')+' bloco(s), '+r.chars+' chars'):'erro';tick(1)})}
function feedTxt(inp){const files=[...inp.files];if(!files.length)return;const msg=document.getElementById('feedmsg');msg.textContent='lendo '+files.length+' arquivo(s)…';let done=0
 ;(async()=>{for(const f of files){let text='';try{text=await f.text()}catch(e){}if(!text.trim())continue;const title=f.name.replace(/\.(txt|md)$/i,'')
   try{const r=await (await fetch('/api/feed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,title})})).json();if(r.ok)done++}catch(e){}}
  inp.value='';msg.textContent='✓ '+done+'/'+files.length+' arquivo(s) aprendido(s)';tick(1)})()}
function forgetKb(id){fetch('/api/forget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})}).then(()=>tick(1))}
let CONSULT_MD='',CONSULT_INGEST=null
function cval(id){const e=document.getElementById(id);return e?e.value:''}
function consultGen(){const m=document.getElementById('cqmsg');if(m)m.textContent='montando contrato…'
 const payload={mode:cval('cq-mode'),room:cval('cq-room'),phase:cval('cq-phase'),theme:cval('cq-theme'),image:cval('cq-image'),context:cval('cq-context'),decision_goal:cval('cq-goal'),hypothesis:cval('cq-hyp')}
 fetch('/api/consult/question',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json()).then(r=>{
  if(r.ok){CONSULT_MD=r.md;if(m)m.textContent='✓ pergunta '+r.question_id+' gerada — copie pro ChatGPT'}else{if(m)m.textContent='erro: '+(r.error||'')}
  tick(1)})}
function consultCopy(ev){const t=CONSULT_MD||cval('cq-out');if(!t)return;if(navigator.clipboard)navigator.clipboard.writeText(t)
 const b=ev.target,o=b.textContent;b.textContent='copiado!';setTimeout(()=>b.textContent=o,1200)}
function consultLearn(){const a=cval('cq-answer');const m=document.getElementById('camsg');if(!a.trim()){if(m)m.textContent='cole algo primeiro';return}
 if(m)m.textContent='aprendendo… (resposta estruturada pode levar alguns segundos)'
 fetch('/api/consult/learn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:a})}).then(r=>r.json()).then(r=>{
  if(r.ok){CONSULT_INGEST=null
   if(r.mode==='patch_draft'){const d=r.diff||{};if(m)m.textContent='✓ '+r.patch_id+' (draft) gerado — revisa o DIFF no 🧠 Learning Patch (+'+((d.rules_add||[]).length)+' regra, +'+((d.anti_add||[]).length)+' anti) e aprova/rejeita'
    const sec=document.getElementById('sec-patch');if(sec)setTimeout(()=>sec.scrollIntoView({behavior:'smooth',block:'center'}),300)}
   else{if(m)m.textContent='✓ orientação aprendida ('+(r.count||'?')+' bloco(s) na memória do Arquiteto)'}
   const ta=document.getElementById('cq-answer');if(ta)ta.value=''}
  else{if(m)m.textContent='erro: '+(r.error||'')}
  tick(1)})}
function patchAction(pid,action){const reason=action==='reject'?(prompt('motivo da rejeição (opcional):')||''):''
 fetch('/api/patch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patch_id:pid,action,reason})}).then(()=>tick(1))}
function moveTask(mt,dir){fetch('/api/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mt,direction:dir})}).then(()=>tick(1))}
function goToMT(mt){const sec=document.getElementById('sec-backlog');if(sec)sec.scrollIntoView({behavior:'smooth',block:'center'})
 const c=document.getElementById('kc-'+mt);if(c){c.classList.add('kc-hl');c.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>c.classList.remove('kc-hl'),2400)}}
function goToCycle(){const c=document.getElementById('sec-agents');if(!c)return
 c.scrollIntoView({behavior:'smooth',block:'start'})}
function micAsk(btn){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){const m=document.getElementById('askmsg');if(m)m.textContent='teu navegador não suporta voz (usa Chrome)';return}
 const r=new SR();r.lang='pt-BR';r.interimResults=false;r.maxAlternatives=1;const o=btn.textContent;btn.textContent='🔴'
 r.onresult=e=>{const t=e.results[0][0].transcript;const q=document.getElementById('ask-q');if(q){q.value=t;q.focus()}}
 r.onerror=()=>{btn.textContent=o};r.onend=()=>{btn.textContent=o};r.start()}
function teamAsk(){const ag=cval('ask-agent')||'interior-designer',q=(cval('ask-q')||'').trim();const m=document.getElementById('askmsg');if(!q){if(m)m.textContent='escreve a pergunta';return}
 if(m)m.textContent='enquadrando e perguntando… (pode levar alguns segundos)'
 const e=document.getElementById('ask-q');if(e)e.value=''
 fetch('/api/team-ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent:ag,question:q})}).then(r=>r.json()).then(r=>{if(m)m.textContent=r.ok?('✓ respondeu — olha no chat (rola até Agentes)'):('erro: '+(r.error||''));tick(1)})}
let SCOUT_RESULTS=null
function scoutSearch(){const q=(cval('scout-q')||'').trim();const m=document.getElementById('scoutmsg');if(!q){if(m)m.textContent='escreve o que buscar';return}
 if(m)m.textContent='🔭 buscando na web…'
 fetch('/api/scout-search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})}).then(r=>r.json()).then(r=>{SCOUT_RESULTS=r;if(m)m.textContent=r.ok?('✓ '+((r.results||[]).length)+' resultados'):('erro: '+(r.error||''));tick(1)})}
let AUTOCYCLE=null,CYCLES=[]
function runCycle(){const m=document.getElementById('cyclemsg');if(m)m.textContent='rodando ciclo nos LLMs locais… (pode levar ~1-2 min)'
 fetch('/api/cycle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})}).then(r=>r.json()).then(r=>{
  const empty=r.msg&&r.msg.indexOf('vazia')>=0
  if(m)m.textContent=r.ok?(empty?'⏸ fila PELE vazia':('✓ '+(r.cycle_id||'ciclo')+' rodou')):('erro: '+(r.error||''))
  if(empty&&AUTOCYCLE){clearInterval(AUTOCYCLE);AUTOCYCLE=null;if(m)m.textContent='⏸ fila PELE vazia — auto parado'}
  tick(1)})}
function toggleAuto(el){if(AUTOCYCLE){clearInterval(AUTOCYCLE);AUTOCYCLE=null}
 if(el.checked){const min=parseInt((document.getElementById('auto-min')||{}).value||'3');AUTOCYCLE=setInterval(runCycle,min*60000);runCycle()}}
function cycleToConsult(i){const c=CYCLES[i];if(!c)return;const set=(id,v)=>{const e=document.getElementById(id);if(e)e.value=v}
 set('cq-mode','SPEC');set('cq-room','kitchen');set('cq-phase','skin')
 set('cq-context','Validar a diretriz do ciclo '+c.cycle_id+' para '+c.mt+' ('+(c.what||'')+'). Geometria congelada (PDF/golden); só a linguagem visual muda.')
 set('cq-goal','A diretriz do Arquiteto está alinhada ao gosto dark premium do Felipe? Precisa ajuste antes de virar render?')
 set('cq-hyp',c.directive||'')
 const sec=document.getElementById('sec-consult');if(sec)sec.scrollIntoView({behavior:'smooth',block:'start'})
 const m=document.getElementById('cqmsg');if(m)m.textContent='✏️ pré-preenchido do '+c.cycle_id+' — clique "🧩 gerar pergunta"'}
function askAgent(agent,umb){const inp=document.getElementById('ask-'+umb),q=(inp.value||'').trim();if(!q)return
 inp.value='';inp.blur()   // tira o foco -> o tick pode mostrar o balão
 fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent,prompt:q})}).then(()=>tick(1))
 setTimeout(()=>tick(1),500)}   // mostra a TUA pergunta já (a resposta vem quando o LLM termina)
function uploadRef(){const f=document.getElementById('upfile').files[0];if(!f)return
 const msg=document.getElementById('upmsg');msg.textContent='subindo…'
 const r=new FileReader();r.onload=async()=>{const res=await (await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name,data:r.result})})).json()
  msg.textContent=res.ok?('✓ '+res.slug):('erro: '+res.error);tick(1)};r.readAsDataURL(f)}
function openModal(src,name){const m=document.getElementById('modal');document.getElementById('mimg').src=src
 document.getElementById('mname').textContent=name||'';const dl=document.getElementById('mdl');dl.href=src;dl.download=(name||'imagem')+(src.endsWith('.png')?'.png':'')
 m.dataset.url=location.origin+src;m.classList.add('show')}
function closeModal(){document.getElementById('modal').classList.remove('show')}
function copyImg(ev){const u=document.getElementById('modal').dataset.url;if(navigator.clipboard)navigator.clipboard.writeText(u)
 const b=ev.target;const t=b.textContent;b.textContent='copiado!';setTimeout(()=>b.textContent=t,1200)}
let CHATAG='',CHATIDS=[]
function openChat(agent,umb,idsStr){CHATAG=agent;CHATIDS=idsStr.split(',')
 document.getElementById('cname').textContent='Chat — '+agent;document.getElementById('chatmodal').classList.add('show');loadChat();setTimeout(()=>document.getElementById('cinput').focus(),60)}
function closeChat(){document.getElementById('chatmodal').classList.remove('show')}
async function loadChat(){const cm=document.getElementById('chatmodal');if(!cm.classList.contains('show'))return
 let s;try{s=await (await fetch('/api/state')).json()}catch(e){return}
 const feed=(s.agents.feed||[]).filter(x=>CHATIDS.includes(x.agent)||(x.agent==='felipe'&&x.to&&CHATIDS.includes(x.to)))
 const b=document.getElementById('cbody'),atBottom=b.scrollHeight-b.scrollTop-b.clientHeight<60
 b.innerHTML=feed.map(x=>{const me=x.agent==='felipe';return `<div class="bub ${me?'me':'them'}"><div class=btxt>${esc(x.message)}</div><div class=bt>${FACES[x.agent]||'🤖'} ${esc(LABELS[x.agent]||x.agent)}${viaTag(x.via)} · ${hhmm(x.ts)}</div></div>`}).join('')||'<span class=mut>sem mensagens — manda a primeira</span>'
 if(atBottom)b.scrollTop=b.scrollHeight}
function sendChat(cons){const inp=document.getElementById('cinput'),q=(inp.value||'').trim();if(!q)return;inp.value=''
 fetch(cons?'/api/consensus':'/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent:CHATAG,prompt:q})}).then(()=>loadChat());setTimeout(loadChat,500)}
setInterval(loadChat,3000)
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();closeChat()}})
// LAYOUT LIVRE — arraste cada card pelo punho ⠿; a ordem fica salva no navegador (localStorage)
let DRAGID=null
function cardOrder(){try{return JSON.parse(localStorage.getItem('studio_order')||'[]')}catch(e){return[]}}
function saveOrder(){const root=document.getElementById('root');if(!root)return
 localStorage.setItem('studio_order',JSON.stringify([...root.children].filter(c=>c.id&&c.classList.contains('card')).map(c=>c.id)))}
function applyOrder(){const root=document.getElementById('root');if(!root)return
 const saved=cardOrder();if(!saved.length)return
 const present=[...root.children].filter(c=>c.id&&c.classList.contains('card')).map(c=>c.id)
 const full=[...saved.filter(id=>present.includes(id)),...present.filter(id=>!saved.includes(id))]
 full.forEach(id=>{const e=document.getElementById(id);if(e)root.appendChild(e)})}
// RECOLHER cards — só Agentes/Loop/Consult/Backlog abertos por padrão; o resto recolhido (menos poluição)
const DEFAULT_OPEN=['sec-factory','sec-ciclo','sec-refpack','sec-ask','sec-agents','sec-consult','sec-patch','sec-learning','sec-backlog']
function collapsedSet(){try{const v=JSON.parse(localStorage.getItem('studio_collapsed')||'null');return v===null?null:new Set(v)}catch(e){return null}}
function saveCollapsed(s){localStorage.setItem('studio_collapsed',JSON.stringify([...s]))}
function applyCollapsed(){const root=document.getElementById('root');if(!root)return
 let set=collapsedSet()
 if(set===null){set=new Set([...root.children].filter(c=>c.id&&c.classList.contains('card')&&!DEFAULT_OPEN.includes(c.id)).map(c=>c.id));saveCollapsed(set)}
 ;[...root.children].forEach(c=>{if(c.id&&c.classList.contains('card'))c.classList.toggle('collapsed',set.has(c.id))})}
function toggleCollapse(id){const set=collapsedSet()||new Set();if(set.has(id))set.delete(id);else set.add(id);saveCollapsed(set)
 const c=document.getElementById(id);if(c)c.classList.toggle('collapsed',set.has(id))}
// REDIMENSIONAR — altura livre (puxa a borda de baixo, salva no mouseup) + largura ½/inteira
function cardSizes(){try{return JSON.parse(localStorage.getItem('studio_sizes')||'{}')}catch(e){return{}}}
function saveSizes(){const root=document.getElementById('root');if(!root)return;const sz=cardSizes()
 ;[...root.children].forEach(c=>{if(!c.id||!c.classList.contains('card'))return;const o=sz[c.id]=sz[c.id]||{}
   if(c.style.height)o.h=c.style.height;if(c.style.width)o.w=c.style.width})
 localStorage.setItem('studio_sizes',JSON.stringify(sz))}
function applySizes(){const sz=cardSizes();Object.keys(sz).forEach(id=>{const c=document.getElementById(id);if(!c)return
 if(sz[id].w)c.style.width=sz[id].w
 if(sz[id].h&&!c.classList.contains('collapsed'))c.style.height=sz[id].h})}
function toggleWidth(id){const sz=cardSizes(),c=document.getElementById(id);if(!c)return
 const w=c.style.width==='49%'?'100%':'49%';c.style.width=w;(sz[id]=sz[id]||{}).w=w;localStorage.setItem('studio_sizes',JSON.stringify(sz))}
document.addEventListener('mouseup',()=>saveSizes())
function makeDraggable(){const root=document.getElementById('root');if(!root)return
 ;[...root.children].forEach(card=>{if(!card.id||!card.classList.contains('card'))return
  card.ondragover=e=>{e.preventDefault();e.dataTransfer.dropEffect='move';if(DRAGID&&DRAGID!==card.id)card.classList.add('dragover')}
  card.ondragleave=()=>card.classList.remove('dragover')
  card.ondrop=e=>{card.classList.remove('dragover');cardDrop(e,card.id)}
  if(!card.querySelector('.drag')){const h=document.createElement('span');h.className='drag';h.textContent='⠿';h.title='arraste pra mover este card';h.draggable=true
   h.ondragstart=e=>{DRAGID=card.id;if(e.dataTransfer.setDragImage)e.dataTransfer.setDragImage(card,18,18);e.dataTransfer.effectAllowed='move'}
   h.ondragend=()=>{DRAGID=null;document.querySelectorAll('.card.dragover').forEach(c=>c.classList.remove('dragover'))}
   const hd=card.querySelector('h2');if(hd)hd.insertBefore(h,hd.firstChild);else card.insertBefore(h,card.firstChild)}
  if(!card.querySelector('.collapse-btn')){const cb=document.createElement('span');cb.className='collapse-btn';cb.title='recolher/expandir';cb.textContent=card.classList.contains('collapsed')?'▸':'▾'
   cb.onclick=()=>{toggleCollapse(card.id);cb.textContent=card.classList.contains('collapsed')?'▸':'▾'}
   const hd=card.querySelector('h2');if(hd)hd.insertBefore(cb,hd.firstChild)}
  if(!card.querySelector('.wbtn')){const wb=document.createElement('span');wb.className='wbtn';wb.title='largura ½ / inteira (ou puxa o canto pra qualquer tamanho)';wb.textContent=card.style.width==='49%'?'◫':'▭'
   wb.onclick=()=>{toggleWidth(card.id);wb.textContent=card.style.width==='49%'?'◫':'▭'}
   const hd=card.querySelector('h2');if(hd)hd.insertBefore(wb,hd.firstChild)}})}
function cardDrop(e,targetId){e.preventDefault();if(!DRAGID||DRAGID===targetId)return
 const root=document.getElementById('root'),drag=document.getElementById(DRAGID),tgt=document.getElementById(targetId)
 if(!root||!drag||!tgt)return
 const r=tgt.getBoundingClientRect(),after=e.clientY>r.top+r.height/2
 root.insertBefore(drag,after?tgt.nextSibling:tgt);DRAGID=null;saveOrder()}
function resetLayout(){localStorage.removeItem('studio_order');localStorage.removeItem('studio_collapsed');localStorage.removeItem('studio_sizes');tick(1)}
let LASTSTATE=''
async function tick(force){
 if(document.hidden&&!force)return   // aba em background -> não trabalha (perf)
 // pausa com modal aberto OU enquanto digita/seleciona (senao apaga)
 const m=document.getElementById('modal'),cm=document.getElementById('chatmodal')
 if((m&&m.classList.contains('show'))||(cm&&cm.classList.contains('show')))return
 const ae=document.activeElement
 if(ae&&/^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName))return
 let txt;try{txt=await (await fetch('/api/state')).text()}catch(e){return}
 document.getElementById('ts').textContent='atualizado '+new Date().toLocaleTimeString('pt-BR')
 if(txt===LASTSTATE&&!force)return   // NADA mudou -> nao re-renderiza (preserva input/upload/foco)
 LASTSTATE=txt
 const s=JSON.parse(txt)
 const b=s.backlog,refs=s.references||{},by=refs.by_theme||{},bk=refs.by_kind||{},ag=s.agents||{umbrellas:[],feed:[],metrics:{}}
 LEADOF={};FACES={};LABELS={};(ag.umbrellas||[]).forEach(u=>{LEADOF[u.id]=u.lead.id;FACES[u.id]=u.lead.face;LABELS[u.id]=u.label;[u.lead,...u.subs].forEach(c=>{FACES[c.id]=c.face;LABELS[c.id]=c.label})})
 FACES['felipe']='🧑';LABELS['felipe']='você'
 const root=document.getElementById('root');const sy=window.scrollY;root.innerHTML=''
 // 🏭 FÁBRICA + 🔧 CICLO ATUAL + 🖼️ REFERENCE PACK — a esteira por ciclo (topo, unidade principal)
 FACTORY=s.factory||{}
 const fac=FACTORY
 if(fac.has_cycle){const ns=fac.next_step||{}
  const nsBtn=ns.actionable?`<button class=send onclick="nextStepGo('${ns.kind}')">${esc(ns.label||'▶ próxima etapa')}</button>`:`<span class="facpill st" style="background:#2a2417;color:var(--gold);border-color:var(--gold)">${esc(ns.label||fac.next_action||'—')}</span>`
  root.appendChild(el(`<div class="card full" id=sec-factory><h2>🏭 Fábrica de interiores — o que decidir AGORA</h2>
   <div class=facbar><span class=facpill>📐 ${esc(fac.project||'')}</span><span class=facpill>🛋️ ${esc(fac.room||'')} · ${esc(fac.asset||'')}</span><span class=facpill>⚙ ${esc(fac.mode||'')}</span><span class="facpill cid">${esc(fac.cycle_id||'')}</span><span class=facpill>${esc(fac.microtask||'')} — ${esc(fac.title||'')}</span><span class="facpill st">${esc(fac.status||'')}</span></div>
   <div class=facnext>▶ próxima ação: <b>${esc(fac.next_action||'—')}</b></div>
   <div class=facacts>${nsBtn} <button class=chatbtn onclick="nextStepGo('scout')">🔭 Scout</button> <button class=chatbtn onclick="nextStepGo('consult')">🔌 Consult GPT</button> <button class=chatbtn onclick="genBundle()" title="gera GPT_REVIEW_BUNDLE.md — fonte única pro GPT revisar o dash sem localhost">📦 Pacote GPT</button></div>
   <div class=facbundle><span class=mut>pacote p/ GPT:</span> <button class=chatbtn onclick="copyBundle(event)">📋 copiar bundle</button> <button class=chatbtn onclick="copyBundleLink(event)">🔗 copiar link raw</button> <button class=chatbtn onclick="copyShortQ(event)">🧾 copiar pergunta</button> <span class=mut id=bundlemsg></span></div>
   ${fac.architect_blocked?`<div class=facblock>⛔ Arquiteto BLOQUEADO — sem referência ⭐ principal curada. NÃO constrói o ${esc(fac.asset||'móvel')} até você escolher (regra-trava).</div>`:''}</div>`))
  const tl=(fac.timeline||[]).map(st=>{const cl={done:'tl-done',doing:'tl-doing',waiting:'tl-wait',blocked:'tl-block',na:'tl-na',pending:'tl-pend'}[st.status]||'tl-pend'
   const need=st.needs?`<div class=tlneed>⚠ falta: <b>${esc(st.needs)}</b> <button class=cbtn onclick="jumpTo('${st.jump||'sec-refpack'}')">→ resolver</button></div>`:''
   return `<div class="tlstep ${cl}"><div class=tlhead><span class=tlface>${st.face}</span> <b>${esc(st.agent)}</b> <span class=tlicon>${st.icon}</span> <span class=mut>${esc(st.status)}</span>${st.model?`<span class=stag>${esc(st.model)}</span>`:''}</div>${st.summary?`<div class=tlsum>${esc(st.summary)}</div>`:''}${need}</div>`}).join('')
  root.appendChild(el(`<div class="card full" id=sec-ciclo><h2>🔧 Ciclo atual — ${esc(fac.cycle_id||'')} · ${esc(fac.microtask||'')} <span class=mut>(esteira: PM→Lead→Scout→Felipe→Arquiteto→Gates→Consult→Learning)</span></h2>
   <div class=tllist>${tl}</div></div>`))
 }
 const rp=s.refpack||{}
 if(rp.ok&&(rp.references||[]).length){const cc=rp.counts||{},needMain=(cc.main||0)===0
  const tlbl={boutique_premium:'boutique premium',compact_premium:'compacto premium',anti_example:'anti-exemplo'}
  const blbl={approved:'👍 aprovada',rejected:'👎 rejeitada',main:'⭐ PRINCIPAL',anti:'🚫 anti-pattern',pending:'• pendente'}
  const allr=rp.references||[],withImg=allr.filter(r=>r.og_image),noImg=allr.filter(r=>!r.og_image)
  const acts=(r)=>{const star=r.type==='anti_example'?'':`<button class="cbtn cbtn-star ${needMain?'pulse':''}" title="marcar ⭐ PRINCIPAL — desbloqueia o Arquiteto" onclick="curateRef('${rp.pack_id}','${r.id}','main')">⭐ principal</button>`
   return `<button class=cbtn title=aprovar onclick="curateRef('${rp.pack_id}','${r.id}','approve')">👍 aprovar</button> ${star} <button class=cbtn title=rejeitar onclick="curateRef('${rp.pack_id}','${r.id}','reject')">👎</button> <button class=cbtn title="anti-pattern" onclick="curateRef('${rp.pack_id}','${r.id}','anti')">🚫</button> <button class=cbtn title="remover do pack" onclick="curateRef('${rp.pack_id}','${r.id}','remove')">🗑</button>`}
  const cards=withImg.map(r=>{const st=r.status||'pending'
   return `<div class="refcard rs-${st}">
    <img class=refimg loading=lazy src="${esc(r.og_image)}" onclick="openModal('${esc(r.og_image)}','${esc(r.title)}')" onerror="this.replaceWith(el('<a class=refimg-ph href=\\'${esc(r.link||'#')}\\' target=_blank>🖼 abrir no site ↗</a>'))">
    <div class=refhd><b>${esc(r.title)}</b> <span class=mut>· ${esc(r.source||'')}</span></div>
    <div class=reftags><span class=pill>${esc(tlbl[r.type]||r.type||'')}</span> <span class="pill rb-${st}">${blbl[st]||st}</span></div>
    <div class=refbody><b>por que:</b> ${esc(r.why_good||'')}<br><b>copiar:</b> ${esc(r.copy||'')}<br><b>evitar:</b> ${esc(r.avoid||'')}</div>
    <div class=refact><a class=mbtn href="${esc(r.link||'#')}" target=_blank rel=noopener>🖼 ver ↗</a> ${acts(r)}</div></div>`}).join('')
  const tray=noImg.length?`<div class=reftray><div class=kblist-h>🚫 Sem imagem / link quebrado (${noImg.length}) <span class=mut>— não dá pra curar pelo visual: puxa imagem, substitui ou remove</span></div>${noImg.map(r=>{const broke=r.link_status==='broken'
   return `<div class=reftrayrow><span class=reftrayt>${broke?'⚠ ':''}${esc(r.title)} <span class=mut>· ${esc(r.source||'')}</span>${broke?' <span class="pill rb-rejected">link quebrado</span>':' <span class=mut>(sem preview)</span>'}</span> <a class=mbtn href="${esc(r.link||'#')}" target=_blank rel=noopener>ver ↗</a> <button class=cbtn title="remover do pack de vez" onclick="curateRef('${rp.pack_id}','${r.id}','remove')">🗑 remover</button></div>`}).join('')}</div>`:''
  const hint=needMain?`<div class=refhint>👉 marque <b>UMA</b> com imagem como <b style="color:var(--gold)">⭐ principal</b> pra <b>destravar o Arquiteto</b>. Aprovar (👍) sozinho <b>NÃO</b> destrava.</div>`:`<div class="refhint ok">✓ principal escolhido — Arquiteto destravado. Segue pro Consult GPT → SOFA_BUILD_SPEC.</div>`
  const scoutHtml=SCOUT_RESULTS&&SCOUT_RESULTS.ok?((SCOUT_RESULTS.results||[]).map(r=>`<div class=scoutrow><a class=lnk href="${esc(r.url)}" target=_blank rel=noopener>${esc(r.title)} ↗</a></div>`).join('')||'<span class=mut>nada encontrado</span>'):(SCOUT_RESULTS?`<span class=mut>erro: ${esc(SCOUT_RESULTS.error||'')}</span>`:'<span class=mut>busca referências na web — os links abrem no teu navegador</span>')
  root.appendChild(el(`<div class="card full" id=sec-refpack><h2>🖼️ Reference Pack — ${esc(rp.asset||'')} <span class=mut>(${withImg.length} com imagem · ⭐${cc.main||0} · 👍${cc.approved||0} · 👎${cc.rejected||0} · 🚫${cc.anti||0})</span> <button class=chatbtn onclick="refpackImages('${rp.pack_id}')" title="puxa og:image + checa links quebrados">🖼 puxar imagens + checar links</button> <span class=mut id=rpimgmsg></span></h2>
   ${hint}
   <div class=refgrid>${cards||'<span class=mut>nenhuma referência com imagem — clica "🖼 puxar imagens" ou busca novas abaixo</span>'}</div>
   ${tray}
   <div class=cycsec><div class=cycsec-h>🔭 Buscar mais referências na web</div>
    <div class=mut style="font-size:11.5px;margin-bottom:6px">Quem busca: <b>o Claude</b> (eu, via WebSearch — foi assim que montei estas 6) ou <b>esta busca</b> (servidor, via DuckDuckGo). Os <b>LLMs locais (DeepSeek/Qwen/Llama) NÃO navegam</b> — eles só organizam/comparam o que já foi trazido.</div>
    <div class=askbar><input id=scout-q placeholder="ex.: sofá couro caramelo industrial boutique braço baixo" onkeydown="if(event.key==='Enter')scoutSearch()"><button class=send onclick=scoutSearch()>🔎 buscar</button> <span class=mut id=scoutmsg></span></div>
    <div class=scoutlist>${scoutHtml}</div></div></div>`))
 }
 // ORG (guarda-chuvas + setas + métricas)
 const cols=(ag.umbrellas||[]).map(u=>{const ids=[u.lead.id,...u.subs.map(x=>x.id)]
   return `<div class=col>${leadCard(u.lead)}<div class=subs>${u.subs.map(subCard).join('')}</div>
    <div class=chat>${colChat(ag.feed,ids)}</div>
    <div class=askrow><input id="ask-${u.id}" onkeydown="if(event.key==='Enter')askAgent('${u.lead.id}','${u.id}')" placeholder="${u.id==='pm'?'tarefa/prioridade (design? → pergunta pro Arquiteto)':('perguntar pro '+esc(u.lead.label)+'…')}"><button class=send onclick="askAgent('${u.lead.id}','${u.id}')">➤</button><button class=chatbtn onclick="openChat('${u.lead.id}','${u.id}','${ids.join(',')}')" title="abrir chat grande">⛶</button></div></div>`}).join('')
 const ents=Object.entries(ag.metrics||{}).sort((a,b)=>b[1].calls-a[1].calls)
 const tot=ents.reduce((s,[,m])=>s+m.calls,0)||1, COL=['#6ca8ff','#7fd99a','#e6c069','#c08ae6','#5ad1c8','#e69a6c','#e67c7c']
 let acc=0
 const slices=ents.map(([id,m],i)=>{const fr=m.calls/tot,a0=acc*6.2832,a1=(acc+fr)*6.2832;acc+=fr
   const x0=(60+46*Math.sin(a0)).toFixed(1),y0=(60-46*Math.cos(a0)).toFixed(1),x1=(60+46*Math.sin(a1)).toFixed(1),y1=(60-46*Math.cos(a1)).toFixed(1)
   return `<path d="M60,60 L${x0},${y0} A46,46 0 ${fr>.5?1:0} 1 ${x1},${y1} Z" fill="${COL[i%COL.length]}"/>`}).join('')
 const leg=ents.map(([id,m],i)=>`<div class=lg><span class=sw style=background:${COL[i%COL.length]}></span>${esc(id)} <span class=mut>${m.calls}</span></div>`).join('')
 const errs=ents.filter(([,m])=>m.errors>0),emx=Math.max(1,...errs.map(([,m])=>m.errors))
 const ebars=errs.length?errs.map(([id,m])=>`<div class=mrow><span class=nm>${esc(id)}</span><span class=mbar><span class=e style=width:${Math.round(130*m.errors/emx)}px></span></span><span class=mnum>${m.errors} erro(s)</span></div>`).join(''):'<span class=mut>nenhum erro de design marcado ainda</span>'
 const flagopts=ents.map(([id])=>`<option>${esc(id)}</option>`).join('')||'<option>interior-designer</option>'
 // CICLO — computa antes pra injetar DENTRO da seção de agentes (abaixo dos chats)
 CYCLES=s.cycles||[]
 const cbk=s.backlog||{}, cnx=(cbk.tasks||[]).find(t=>!t.done&&!t.geo&&(t.status==='backlog'||t.status==='refinamento'))
 const cyctrl=`<div class=pmbox>
   <div class=cyc-help>Um <b>ciclo</b> roda nos LLMs locais (sem Claude): <b>PM</b>(llama) escolhe a próxima tarefa PELE → <b>Team Lead</b>(qwen) valida → <b>Arquiteto</b>(deepseek) dá a diretriz. O card vai pra <b>execução</b>. É decisão/texto — <b>não</b> mexe no .skp.</div>
   ${cnx?`<div class=cyc-next>▶ próximo ciclo vai rodar: <b class=mtlink onclick="goToMT('${cnx.mt}')" title="ver no Kanban">${cnx.mt}</b> — ${esc((cnx.what||'').slice(0,60))}</div>`:`<div class=cyc-next><span class=mut>sem tarefa PELE na fila — as GEO esperam teu OK</span></div>`}
   <button class=send style=margin-top:6px onclick=runCycle() ${cnx?'':'disabled'}>▶ Rodar próximo ciclo</button>
   <label class=mut style="font-size:11px;display:inline-flex;align-items:center;gap:4px;margin-left:6px"><input type=checkbox onchange=toggleAuto(this) ${AUTOCYCLE?'checked':''}>auto a cada <select id=auto-min style="background:#0c0d10;border:1px solid var(--bd);color:var(--fg);border-radius:4px;padding:1px 3px"><option>2</option><option selected>3</option><option>5</option><option>10</option></select> min</label>
   <span class=mut id=cyclemsg></span></div>`
 const cyhtml=CYCLES.length?CYCLES.map((c,i)=>`<div class=cyrow>
   <div class=cyhd><b class=mtlink onclick="goToMT('${esc(c.mt||'')}')">${esc(c.cycle_id||'CYCLE')}</b> · <b>${esc(c.mt||'')}</b> ${esc((c.what||'').slice(0,46))} <span class=mut>· ${hhmm(c.ts)}</span></div>
   <div class=cydir onclick="this.classList.toggle('exp')" title="clica pra expandir/recolher">🎯 ${esc(c.directive||'(sem diretriz)')}</div>
   <div class=cymeta><span class=mut>🦙 llama → 🤖 qwen → 🐳 deepseek</span> <button class=chatbtn onclick="cycleToConsult(${i})" title="virar pergunta pro Consult GPT validar">→ validar no Consult GPT</button>${c.consulted?' <span class=mut>✓ consultado</span>':''}</div></div>`).join(''):'<span class=mut>nenhum ciclo rodado ainda — clica "▶ Rodar próximo ciclo" acima. A diretriz que sair vira o item aqui.</span>'
 // 🗣️ PERGUNTE AO TIME — o ó de tudo (topo): traduz a pergunta plana num bom prompt pro local
 const myq=(ag.feed||[]).filter(x=>x.agent==='felipe'&&(x.message||'').trim()).slice(-10).reverse()
 const qseen=new Set(),myqU=myq.filter(x=>{const k=(x.message||'').slice(0,60);if(qseen.has(k))return false;qseen.add(k);return true}).slice(0,6)
 const qhist=myqU.length?`<div class=qhist><span class=mut>tuas últimas:</span>${myqU.map(x=>`<span class=qchip title="reusar esta pergunta" data-q="${esc(x.message)}" onclick="const e=document.getElementById('ask-q');if(e){e.value=this.dataset.q;e.focus()}">${esc((x.message||'').slice(0,42))}${(x.message||'').length>42?'…':''}</span>`).join('')}</div>`:''
 root.appendChild(el(`<div class="card full" id=sec-ask><h2>🗣️ Pergunte ao time <span class=mut>(em português normal — eu enquadro o prompt com teu DNA pra o local não alucinar nem fugir do teu gosto)</span></h2>
  <div class=askbar><select id=ask-agent title="pra quem"><option value=interior-designer>🐳 Arquiteto</option><option value=interior-pm>🦙 PM</option><option value=interior-orchestrator>🤖 Team Lead</option><option value=consenso>🧠 consenso (3)</option></select>
   <input id=ask-q placeholder="pergunte qualquer coisa (ex.: qual piso pra não aparecer sujeira?)" onkeydown="if(event.key==='Enter')teamAsk()">
   <button class=chatbtn onclick="micAsk(this)" title="perguntar por voz (pt-BR) — o navegador transcreve">🎤</button>
   <button class=send onclick=teamAsk()>➤ perguntar</button> <span class=mut id=askmsg></span></div>
  ${qhist}</div>`))
 // 🔄 CICLO — card SOLTO, logo após "Pergunte ao time" (você move/redimensiona à vontade)
 root.appendChild(el(`<div class="card full" id=sec-cycles><h2>🔁 Rascunho de diretriz (LLMs locais) <span class=mut>(secundário — NÃO é o "Ciclo atual" lá em cima; aqui o PM/llama gera um texto-diretriz pra você levar ao Consult GPT)</span></h2>
  ${cyctrl}<div class=kblist-h>Ciclos recentes</div><div class=cylist>${cyhtml}</div></div>`))
 // AGENTES — só os 3 + chats
 root.appendChild(el(`<div class="card full" id=sec-agents><h2>Agentes — PM · Team Lead · Arquiteto</h2>
  <div class=org id=org><svg class=arrows id=arrows></svg><div class=cols>${cols}</div></div></div>`))
 drawArrows(ag)
 // 💬 CONVERSA DO TIME — thread única (em ordem), pra saber quem fala com quem + a resposta oficial
 const conv=(ag.feed||[]).slice(-30)
 const convHtml=conv.map(x=>{const me=x.agent==='felipe',isC=x.via&&(''+x.via).indexOf('consenso')>=0
   return `<div class="bub ${me?'me':'them'}${isC?' cons':''}"><div class=btxt>${esc(x.message)}</div><div class=bt>${FACES[x.agent]||'🤖'} ${esc(LABELS[x.agent]||x.agent)}${x.to&&x.to!=='felipe'?(' → '+esc(LABELS[x.to]||x.to)):''}${viaTag(x.via)} · ${hhmm(x.ts)}</div></div>`}).join('')
 root.appendChild(el(`<div class="card full" id=sec-conversa><h2>💬 Conversa do time <span class=mut>(tudo numa thread, em ordem — quem fala com quem; resposta do 🐳 Arquiteto ou 🧠 consenso = a oficial)</span></h2>
  <div class=convbox>${convHtml||'<span class=mut>sem conversa ainda — pergunta lá em cima</span>'}</div></div>`))
 const critic=(s.renders||[])[0]
 // ERROS — card próprio, grande, logo abaixo dos agentes
 root.appendChild(el(`<div class="card full" id=sec-err><h2>Erros de design — o que TU não curtiu (vira lição)</h2>
  <div class=critwrap>${critic?`<img class=critic loading=lazy onclick="openModal('/img/${encodeURIComponent(critic.name)}','${esc(critic.name)}')" src="/img/${encodeURIComponent(critic.name)}" title="clica pra ampliar">`:''}
   <div style=flex:1>${ebars}
    <div class=flagrow><select id=flagag>${flagopts}</select>
     <input id=flagmsg onkeydown="if(event.key==='Enter')flagErr()" placeholder="ex.: parede muito escura, coifa não combina… (Enter)"><button class=send onclick=flagErr()>marcar erro</button></div></div></div></div>`))
 // GRÁFICOS (pizza = mensagens no feed · barras = chamadas reais de modelo)
 const mu=Object.entries(ag.model_usage||{}).sort((a,b)=>b[1]-a[1])
 const muTot=mu.reduce((s,[,n])=>s+n,0)||1
 const muRows=mu.length?mu.map(([mdl,n])=>`<div class=mrow><span class=nm>${esc(mdl)}</span><span class=mbar><span style="display:inline-block;height:9px;border-radius:5px;background:var(--blu);width:${Math.round(130*n/muTot)}px"></span></span><span class=mnum>${n} (${Math.round(100*n/muTot)}%)</span></div>`).join(''):'<span class=mut>nenhuma chamada de modelo registrada ainda</span>'
 root.appendChild(el(`<div class="card full" id=sec-graf><h2>Gráficos</h2>
  <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-start">
   <div class=chartbox style="max-width:340px"><h2>Mensagens no feed por agente <span class=mut style=font-weight:400>(quem mais falou — NÃO é chamada de LLM)</span></h2><div class=pie><svg viewBox="0 0 120 120">${slices||'<circle cx=60 cy=60 r=46 fill=#20242b/>'}</svg><div class=legend>${leg||'<span class=mut>—</span>'}</div></div></div>
   <div class=chartbox style="flex:1;min-width:270px"><h2>Modelos usados <span class=mut style=font-weight:400>(chamadas REAIS aos LLMs)</span></h2>${muRows}
    <div class=mut style="font-size:11px;margin-top:7px;line-height:1.45">Por que <b>DeepSeek</b> aparece mais: o papel do <b>Arquiteto</b> mapeia pra <code>deepseek-r1</code> (raciocínio), então toda pergunta de design vai nele. Só o <b>🧠 consenso</b> usa os 3 (deepseek+qwen+llama). PM=llama, Team Lead=qwen.</div></div>
  </div></div>`))
 // BACKLOG
 const COLS=['backlog','refinamento','execução','teste','executado']
 const COLLBL={backlog:'Backlog',refinamento:'Em refinamento','execução':'Em execução',teste:'Em teste',executado:'Executado'}
 const board=COLS.map(col=>{const items=(b.tasks||[]).filter(t=>t.status===col)
   const cards=items.map(t=>`<div class=kcard id="kc-${esc(t.mt)}" data-mt="${esc(t.mt)}"><div class=kc-top><span class="tg ${t.geo?'geo':'pele'}">${t.geo?'GEO':'PELE'}</span> <b>${t.mt}</b></div>
     <div class=kc-what>${esc(t.what)}</div>
     <div class=kc-mv><button onclick="moveTask('${t.mt}','prev')" title="voltar">◀</button><button onclick="moveTask('${t.mt}','next')" title="avançar">▶</button></div></div>`).join('')
   return `<div class=kcol><div class=kcol-h>${COLLBL[col]} <span class=mut>${items.length}</span></div><div class=kcol-b>${cards||'<span class=mut style=font-size:11px>—</span>'}</div></div>`}).join('')
 root.appendChild(el(`<div class="card full" id=sec-backlog><h2>Backlog — quadro Kanban <span class=mut>(${b.total} microtarefas · ${b.done} done · arrasta com ◀ ▶)</span></h2>
  <div class=kboard>${board}</div></div>`))
 // ALIMENTAR O ARQUITETO
 const K=s.knowledge||{},kb=K.chars||0,kents=K.entries||[]
 const klist=kents.length?kents.slice().reverse().map(e=>`<div class=kbi title="${esc(e.preview||'')}"><span class=kbi-t>${esc(e.title)}</span><span class=mut>${e.chars}c</span><button class=trash title=esquecer onclick="forgetKb(${e.id})">🗑</button></div>`).join(''):'<span class=mut style=font-size:12px>nada aprendido ainda — cola um texto ou sobe um .txt</span>'
 const Kj=(K.judge||{}),Kdna=K.dna
 root.appendChild(el(`<div class="card full" id=sec-feed><h2>📚 Alimentar o Arquiteto <span class=mut>(cola ou sobe orientações do GPT → ele aprende e USA nas respostas · ${kents.length} bloco(s) · ${kb} chars)</span></h2>
  <div class=mut style="margin-bottom:8px;font-size:12px">O Arquiteto carrega 3 camadas antes de responder: <b style="color:${Kdna?'var(--ok)':'var(--red)'}">🧬 DNA ${Kdna?'✓':'ausente'}</b> · <b>🧑‍⚖️ ${Kj.anti_patterns||0} anti-patterns + ${Kj.flagged||0} erro(s) marcado(s)</b> · <b>📚 ${kents.length} orientação(ões)</b></div>
  <input id=feedtitle placeholder="título (ex.: paleta black wood gold)" style="width:100%;margin-bottom:7px">
  <textarea id=feedtext placeholder="cola aqui o texto/orientação do GPT sobre teu gosto, paleta, regras de design…"></textarea>
  <div style="margin-top:7px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
   <button class=send onclick=feedArch()>📚 alimentar (colado)</button>
   <label class=upbtn>📄 subir .txt<input type=file accept=".txt,.md,text/plain" multiple style=display:none onchange=feedTxt(this)></label>
   <span class=mut id=feedmsg></span></div>
  <div class=kblist-h>📖 o que o Arquiteto já aprendeu <span class=mut>(${kents.length})</span></div>
  <div class=kblist>${klist}</div></div>`))
 // 🔌 CONSULT GPT BRIDGE (sidecar do Arquiteto — MVP manual)
 const co=s.consult||{}
 const opt=(arr,sel)=>arr.map(v=>`<option${v===sel?' selected':''}>${v}</option>`).join('')
 let ingHtml=''
 if(CONSULT_INGEST&&CONSULT_INGEST.ok){const r=CONSULT_INGEST
  ingHtml=`<div class=consult-res><b>Último aprendizado ingerido</b> — veredito <b style="color:${r.verdict==='PASS'?'var(--ok)':r.verdict==='FAIL'?'var(--red)':'var(--warn)'}">${esc(r.verdict||'?')}</b> · correção nº1: ${esc(r.top_fix||'-')}<br>
   🧬 ${(r.rules_added||[]).length} regra(s) no DNA · 🧑‍⚖️ ${(r.anti_patterns_added||[]).length} anti-pattern(s)${r.next_microtask&&r.next_microtask.title?(' · 🎯 próxima: <b>'+esc(r.next_microtask.id||'MT')+'</b> '+esc(r.next_microtask.title)):''}${(r.warnings||[]).length?(' · ⚠ '+esc((r.warnings||[]).join('; '))):''}</div>`}
 const cqid=co.latest_question&&co.latest_question.question_id?co.latest_question.question_id:'—'
 const cwait=co.status==='waiting_gpt_answer'
 root.appendChild(el(`<div class="card full" id=sec-consult><h2>🔌 Consult GPT Bridge <span class=mut>(contrato oficial — rastreável · modo <b>${esc(co.bridge_mode||'manual')}</b> · ${co.ingested_count||0} ingerida(s))</span> ${cwait?`<span class="facpill st" style="background:#2a2417;color:var(--gold);border-color:var(--gold)">⏳ waiting_gpt_answer · ${esc(cqid)}</span>`:''}</h2>
  <div class=mut style="font-size:12px;margin-bottom:8px">Fluxo OFICIAL (rastreável): gera a pergunta aqui → 📋 copia pro ChatGPT → cola a resposta → vira <b>Learning Patch draft</b> (não aplica direto) → você aprova o diff → só então altera o DNA. <i>Pergunta solta no chat = só conversa; aqui = contrato.</i></div>
  ${cwait?`<div class=refhint>⏳ Pergunta <b>${esc(cqid)}</b> gerada e salva (status <b>waiting_gpt_answer</b>). Copia abaixo (📋), manda no Consult GPT, e cola a resposta no campo da direita → vira Learning Patch.</div>`:''}
  <div class=consult-grid>
   <select id=cq-mode title=modo>${opt(['JUDGE','SPEC','REPAIR','LEARN','COMPARE'],'JUDGE')}</select>
   <select id=cq-room title=cômodo>${opt(['kitchen','living','bedroom','bathroom','laundry','full_apartment'],'kitchen')}</select>
   <select id=cq-phase title=fase>${opt(['skin','layout','form','lighting','render','final_validation'],'skin')}</select>
   <input id=cq-theme value="BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE" title=tema>
  </div>
  <input id=cq-image placeholder="imagem principal (raw github url ou caminho local) — opcional p/ SPEC" style="width:100%;margin-bottom:6px">
  <textarea id=cq-context placeholder="Contexto (3-8 linhas: o que está acontecendo)" style="min-height:60px"></textarea>
  <textarea id=cq-goal placeholder="Objetivo da decisão (que decisão o Consult GPT precisa tomar)" style="min-height:46px"></textarea>
  <textarea id=cq-hyp placeholder="Hipótese do Arquiteto (o que você tentou fazer)" style="min-height:46px"></textarea>
  <div style="margin:6px 0"><button class=send onclick=consultGen()>🧩 gerar pergunta</button> <button class=chatbtn onclick=consultRelay() title="o Claude pega esta pergunta, dirige o TEU ChatGPT Plus pela extensão do Chrome, lê a resposta e devolve aqui → vira Learning Patch">🤖 relay via Claude (Chrome)</button> <span class=mut id=cqmsg></span> ${co.relay?`<span class=mut>· último relay: <b>${esc(co.relay.question_id||'')}</b> ${esc(co.relay.status||'')}${co.relay.patch_id?(' → '+esc(co.relay.patch_id)):''}</span>`:''}</div>
  <div class=consult-half>
   <div><div class=kblist-h>Pergunta gerada <span class=mut>(${esc(cqid)})</span> <button class=chatbtn onclick=consultCopy(event)>copiar</button></div>
    <textarea id=cq-out readonly placeholder="clique 'gerar pergunta' — o contrato aparece aqui pra copiar" style="min-height:150px;font:11px ui-monospace,monospace"></textarea></div>
   <div><div class=kblist-h>Resposta do GPT (ou orientação solta) <button class=send onclick=consultLearn()>✓ aprender</button> <span class=mut id=camsg></span></div>
    <textarea id=cq-answer placeholder="cole a resposta do GPT (ARCHITECT_ANSWER_CONTRACT) OU qualquer orientação de design — o sistema detecta sozinho e aprende (vira regra/anti-pattern/microtarefa, ou conhecimento do Arquiteto)" style="min-height:150px"></textarea></div>
  </div>
  ${ingHtml}</div>`))
 const _co=document.getElementById('cq-out');if(_co)_co.value=CONSULT_MD||(co.latest_question_md||'')
 // 🧠 LEARNING PATCH — resposta GPT vira patch (draft) → DIFF → Felipe aprova/rejeita → só então DNA
 const pt=s.patches||{},draft=pt.draft,pdiff=pt.diff||{},pcc=pt.counts||{}
 const dl=(arr,cls)=>(arr||[]).map(x=>`<li class=${cls}>${esc(typeof x==='string'?x:JSON.stringify(x))}</li>`).join('')
 let patchBody
 if(draft){const nm=draft.next_microtask||{}
  patchBody=`<div class=patchhd><b>${esc(draft.patch_id)}</b> <span class="pill rb-${(draft.verdict||'').toLowerCase()==='pass'?'approved':(draft.verdict||'').toLowerCase()==='fail'?'rejected':'pending'}">${esc(draft.verdict||'?')}</span> <span class=mut>de ${esc(draft.source_question_id||'?')} · ${esc(draft.cycle_id||'')} · confiança ${esc(draft.confidence||'?')} · sha ${esc((draft.commit_sha||'').slice(0,8))}</span></div>
   <div class=mut style="font-size:11.5px;margin:4px 0">Aplicação <b>MANUAL</b> — nada vai pro DNA até você aprovar. O diff mostra só o que <b>MUDA</b> (＋ novo · ≡ já existe, ignorado).</div>
   <div class=patchdiff>
    <div><div class=kblist-h>🧬 Regras novas <span class=mut>→ felipe_style_dna.md</span></div><ul class=difflist>${dl(pdiff.rules_add,'add')||'<li class=mut>nada novo</li>'}${dl(pdiff.rules_dup,'dup')}</ul></div>
    <div><div class=kblist-h>🚫 Anti-patterns <span class=mut>→ juiz visual</span></div><ul class=difflist>${dl(pdiff.anti_add,'add')||'<li class=mut>nada novo</li>'}${dl(pdiff.anti_dup,'dup')}</ul></div>
   </div>
   ${pdiff.build_spec?`<div class=kblist-h style="margin-top:8px">🔧 build_spec_constraints <span class=mut>(guiam a CONSTRUÇÃO do sofá, não só o DNA)</span></div>
    <div class=patchdiff><div><b style="color:var(--ok);font-size:12px">must_have</b><ul class=difflist>${dl(pdiff.build_spec.must_have,'add')}</ul></div>
     <div><b style="color:var(--red);font-size:12px">must_not_have</b><ul class=difflist>${dl(pdiff.build_spec.must_not_have,'dup')}</ul></div></div>`:''}
   ${nm.title?`<div class=mut style="font-size:12px;margin-top:2px">🎯 próxima microtarefa sugerida: <b>${esc(nm.id||'MT')}</b> ${esc(nm.title)}</div>`:''}
   <div class=patchacts><button class=send onclick="patchAction('${draft.patch_id}','approve')">✅ aprovar e aplicar no DNA</button> <button class=cbtn onclick="patchAction('${draft.patch_id}','reject')">⛔ rejeitar</button></div>`
 }else{patchBody=`<span class=mut>nenhum patch pendente. Cole uma resposta ESTRUTURADA do Consult GPT (ARCHITECT_ANSWER) no sidecar 🔌 acima → ela vira um patch <b>draft</b> aqui, com diff, pra você aprovar antes de virar memória.</span>`}
 root.appendChild(el(`<div class="card full" id=sec-patch><h2>🧠 Learning Patch <span class=mut>(resposta GPT → patch → diff → você aprova → DNA · ${pcc.draft||0} draft · ${pcc.applied||0} aplicado · ${pcc.rejected||0} rejeitado)</span></h2>
  ${patchBody}</div>`))
 // 📚 LEARNING LOG — o que a fábrica aprendeu (regras/anti-patterns/golden) = repertório
 const ll=s.learning||{}
 const lcol=(arr,empty)=>arr&&arr.length?arr.map(x=>`<li>${esc(typeof x==='string'?x:JSON.stringify(x))}</li>`).join(''):`<li class=mut>${empty}</li>`
 root.appendChild(el(`<div class="card full" id=sec-learning><h2>📚 Learning Log <span class=mut>(o que a fábrica aprendeu — vira repertório reutilizável)</span></h2>
  <div class=llgrid>
   <div><div class=kblist-h>🧬 Regras novas <span class=mut>(Consult GPT → DNA)</span></div><ul class=lllist>${lcol(ll.new_rules,'nenhuma regra nova ainda')}</ul></div>
   <div><div class=kblist-h>🚫 Anti-patterns <span class=mut>(juiz visual)</span></div><ul class=lllist>${lcol(ll.anti_patterns,'nenhum anti-pattern ainda')}</ul></div>
   <div><div class=kblist-h>⭐ Golden samples <span class=mut>(forma congelada)</span></div><ul class=lllist>${lcol(ll.golden_samples,'nenhum golden sample ainda')}</ul></div>
  </div></div>`))
 // SESSÕES
 const cl=(s.sessions.claims||[]).map(c=>`<tr><td>${esc(c.desc)}</td><td>${esc(c.status)}</td></tr>`).join('')
 const nwt=(s.sessions.worktrees||[]).length
 root.appendChild(el(`<div class=card id=sec-sessions><h2>O que cada sessão está fazendo</h2>
  <table><tr><th>tarefa</th><th>status</th></tr>${cl||'<tr><td colspan=2 class=mut>nada em andamento</td></tr>'}</table>
  <div class=mut style=margin-top:8px>${nwt} sessão(ões) de trabalho ativa(s)</div></div>`))
 // REFERÊNCIAS
 const themes=Object.entries(by).map(([t,n])=>`<tr><td>${esc(t)}</td><td>${n}</td></tr>`).join('')
 root.appendChild(el(`<div class=card id=sec-refs><h2>Banco de referências (reference_db)</h2>
  <div class=mut style=margin-bottom:8px>${Object.entries(bk).map(([k,n])=>`<span class=pill>${k}: ${n}</span>`).join(' ')||refs.error||''}</div>
  <table><tr><th>tema</th><th>refs</th></tr>${themes}</table></div>`))
 // INBOX
 const fn=(i)=>i.local_path?encodeURIComponent(i.local_path.split('/').pop()):''
 const inb=(s.inbox||[]).map(i=>{const st=i.status||'pending',nm=esc(i.title||i.slug)
   const thumb=i.local_path?`<img class=minithumb loading=lazy src="/inbox-img/${fn(i)}" onclick="openModal('/inbox-img/${fn(i)}','${esc(i.slug)}')">`:(i.source_url?`<button class=chatbtn onclick="fetchPreview('${esc(i.slug)}')" title="puxar imagem do site">🖼</button>`:'')
   const cell=i.local_path?`<td class=lnk onclick="openModal('/inbox-img/${fn(i)}','${esc(i.slug)}')">${nm}</td>`
     :(i.source_url?`<td><a class=lnk href="${esc(i.source_url)}" target=_blank>${nm} ↗</a></td>`:`<td>${nm}</td>`)
   return `<tr><td>${thumb}</td>${cell}<td>${i.theme||'-'}</td><td>${st}</td>
   <td>${st!=='approved'?`<button onclick="curate('${esc(i.slug)}','approve')" title=aprovar>✓</button> `:''}${st!=='rejected'?`<button onclick="curate('${esc(i.slug)}','reject')" title=reprovar>✕</button> `:''}<button class=trash onclick="curate('${esc(i.slug)}','delete')" title=apagar>🗑</button></td></tr>`}).join('')
 const thumbs=(s.inbox||[]).filter(i=>i.local_path).map(i=>`<div class=thumb><img loading=lazy src="/inbox-img/${fn(i)}" onclick="openModal('/inbox-img/${fn(i)}','${esc(i.slug)}')"><button class="trash thumbtrash" onclick="curate('${esc(i.slug)}','delete')" title=apagar>🗑</button><div class=cap>${esc(i.slug)}<div class=t>${i.status||'pending'}</div></div></div>`).join('')
 // (🔭 Scout foi consolidado DENTRO do Reference Pack — não é mais card solto)
 root.appendChild(el(`<div class="card full" id=sec-cur><h2>Curadoria — inbox de referência <span class=mut>(✓ aprova · ✕ reprova (fica) · 🗑 apaga · 🖼 puxa imagem do site)</span></h2>
  <div class=uprow><label class=upbtn>⬆ escolher imagem<input type=file id=upfile accept="image/*" onchange=uploadRef() hidden></label> <span class=mut id=upmsg>escolhe a imagem → sobe sozinho</span></div>
  ${thumbs?`<div class=grid style="margin:10px 0">${thumbs}</div>`:''}
  <table><tr><th></th><th>referência</th><th>tema</th><th>status</th><th>ação</th></tr>${inb||'<tr><td colspan=5 class=mut>fila vazia — sobe uma referência acima</td></tr>'}</table></div>`))
 // RENDERS
 const rr=(s.renders||[]).map(r=>`<div class=thumb onclick="openModal('/img/${encodeURIComponent(r.name)}','${esc(r.name)}')"><img loading=lazy src="/img/${encodeURIComponent(r.name)}">
   <div class=cap>${esc(r.name.replace('.png',''))}<div class=t>${r.theme} · ${r.sub} · ${r.kb}KB</div></div></div>`).join('')
 root.appendChild(el(`<div class="card full" id=sec-ren><h2>Renders (${(s.renders||[]).length}) — clica pra ampliar/baixar · mais novos primeiro</h2>
  <div class="grid gallery">${rr||'<span class=mut>sem renders</span>'}</div></div>`))
 applyOrder();applyCollapsed();applySizes();makeDraggable()   // layout livre: ordem + recolher + tamanho + punho ⠿
 document.querySelectorAll('.chat,.convbox').forEach(c=>{c.scrollTop=c.scrollHeight})   // chat/conversa sempre na última msg
 window.scrollTo(0,sy)   // mantém a rolagem onde estava (não sobe ao mandar mensagem)
}
tick(true);setInterval(tick,10000);window.addEventListener('resize',()=>tick(1))
document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick(1)})   // aba voltou -> re-renderiza
</script></body></html>"""


def _curate(slug, action):
    """3 ações: approve (aprovado) · reject (reprovado, FICA visível p/ saber o que não curtiu) ·
    delete (SOME + deleta o arquivo). Tudo direto no INBOX.json, sem Claude."""
    if not INBOX.exists() or not slug:
        return {"ok": False}
    data = json.loads(INBOX.read_text("utf-8"))
    items = data.get("items", [])
    if action == "delete":
        for it in items:
            if it.get("slug") == slug and it.get("local_path"):
                try:
                    (ROOT / it["local_path"]).unlink()
                except Exception:  # noqa: BLE001
                    pass
        data["items"] = [it for it in items if it.get("slug") != slug]
    else:  # approve / reject -> só muda o status (continua na lista)
        for it in items:
            if it.get("slug") == slug:
                it["status"] = "approved" if action == "approve" else "rejected"
    INBOX.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return {"ok": True, "slug": slug, "action": action}


def _fetch_preview(slug):
    """Puxa a imagem de preview (og:image) do site de um candidato e salva como miniatura no inbox.
    Acionado pelo Felipe (botão 🖼) — é a curadoria dele, não scraping em massa."""
    import re as _re
    import urllib.request
    if not INBOX.exists():
        return {"ok": False}
    data = json.loads(INBOX.read_text("utf-8"))
    item = next((it for it in data.get("items", []) if it.get("slug") == slug), None)
    if not item or not item.get("source_url"):
        return {"ok": False, "error": "sem url"}
    hdr = {"User-Agent": "Mozilla/5.0"}
    try:
        html = urllib.request.urlopen(
            urllib.request.Request(item["source_url"], headers=hdr), timeout=12).read().decode("utf-8", "ignore")
        m = (_re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html)
             or _re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html))
        if not m:
            return {"ok": False, "error": "site sem og:image"}
        img_url = m.group(1)
        raw = urllib.request.urlopen(urllib.request.Request(img_url, headers=hdr), timeout=12).read()
        ext = ".png" if ".png" in img_url.lower() else (".webp" if ".webp" in img_url.lower() else ".jpg")
        fname = slug + "_preview" + ext
        (INBOX.parent / fname).write_bytes(raw)
        item["local_path"] = f"inbox/{fname}"
        INBOX.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return {"ok": True, "path": item["local_path"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _upload(filename, data_b64):
    """Felipe sobe uma imagem de referência -> inbox/ + entra no INBOX.json. Claude/LLM-visão lê depois."""
    import base64 as _b64
    import re as _re
    if not filename or not data_b64:
        return {"ok": False, "error": "sem arquivo"}
    safe = _re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    if not safe.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return {"ok": False, "error": "so imagem (png/jpg/jpeg/webp)"}
    dest = INBOX.parent / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_bytes(_b64.b64decode(data_b64.split(",")[-1]))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    data = json.loads(INBOX.read_text("utf-8")) if INBOX.exists() else {"items": []}
    slug = safe.rsplit(".", 1)[0]
    items = data.setdefault("items", [])
    if not any(it.get("slug") == slug for it in items):
        items.append({"slug": slug, "theme": None, "title": filename, "source_url": "",
                      "status": "uploaded", "local_path": f"inbox/{safe}", "source": "felipe_upload"})
    INBOX.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return {"ok": True, "slug": slug, "path": f"inbox/{safe}"}


def _flag(agent, message):
    """Felipe marca um ERRO de design (ex.: 'parede muito escura') — vira erro no log E lição do agente.
    A lição é o que torna o erro APRENDIZADO: o agente LÊ esse arquivo no próximo dispatch e não repete."""
    agent = agent or "interior-designer"
    message = message or "correção do Felipe"
    try:
        from tools import studio_log
        studio_log.post(agent, "error", message)
        lessons = ROOT / f".ai_bridge/lessons/{agent}.md"
        lessons.parent.mkdir(parents=True, exist_ok=True)
        with lessons.open("a", encoding="utf-8") as f:
            f.write(f"- [erro marcado pelo Felipe] {message}\n")
        _judge_append_flag(agent, message)   # vira regra estruturada do juiz (o Arquiteto não repete)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _judge_append_flag(agent, message):
    """Acrescenta o erro marcado pelo Felipe em `flagged[]` das regras do juiz visual — camada estruturada
    (distinta da lição em prosa) que o Arquiteto carrega no priming pra não repetir. Idempotente por (agent,msg)."""
    try:
        data = json.loads(JUDGE_RULES.read_text("utf-8")) if JUDGE_RULES.exists() else {
            "spec": "FelipeVisualJudgeRules", "version": "1.0.0", "checks": [], "anti_patterns": [], "flagged": []}
        flagged = data.setdefault("flagged", [])
        if not any(f.get("agent") == agent and f.get("message") == message for f in flagged):
            flagged.append({"agent": agent, "message": message})
            JUDGE_RULES.parent.mkdir(parents=True, exist_ok=True)
            JUDGE_RULES.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except Exception:  # noqa: BLE001
        pass   # a lição em prosa já foi gravada; não derruba o flag por causa do JSON


# ---------------------------------------------------------------- Consult GPT Bridge (sidecar do Arquiteto)
# Loop Arquiteto -> Consult GPT (manual): gera pergunta estruturada -> Felipe copia/cola no ChatGPT ->
# cola a resposta -> ingere virando regra/anti-pattern/DNA/próxima-microtarefa. Lazy-import (resiliente).
def _consult_state() -> dict:
    try:
        from tools.interior_studio.consult_gpt_bridge import contracts, openai_client, store
        la = store.latest_answer()
        lq = store.latest_question()
        c = store.counts()
        # pergunta gerada no painel = contrato oficial → status waiting_gpt_answer até a resposta chegar
        cc = ic_cycles.current_cycle() or {}
        cstat = (cc.get("consult") or {}).get("status")
        return {"pending_questions": store.pending_questions(), "latest_question": lq,
                "latest_question_md": contracts.render_question_md(lq) if lq else None,
                "latest_answer": la.get("raw") if la else None,
                "latest_answer_path": la.get("path") if la else None,
                "status": cstat, "relay": _relay_state(),
                "ingested_count": c["ingested"], "failed_count": c["failed"],
                "bridge_mode": "manual", "openai_enabled": openai_client.is_enabled()}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "pending_questions": [], "latest_question": None, "latest_answer": None,
                "ingested_count": 0, "failed_count": 0, "bridge_mode": "manual", "openai_enabled": False}


def _consult_latest(which: str) -> dict:
    try:
        from tools.interior_studio.consult_gpt_bridge import store
        return {"ok": True, "data": store.latest_question() if which == "question" else store.latest_answer()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _cycle_references() -> list[dict]:
    """As referências CURADAS do ciclo atual (⭐ principal · 👍 aprovadas · 🚫 anti) com título+link —
    pra entrar no ARCHITECT_QUESTION_CONTRACT (rastreabilidade do gosto)."""
    c = ic_cycles.current_cycle()
    if not c:
        return []
    refs = c.get("references") or {}
    pack = ic_refpacks.load_pack(refs.get("pack_id") or DEFAULT_PACK) or {}
    by_id = {r.get("id"): r for r in pack.get("references", [])}
    out, seen = [], set()
    for role, ids in (("main", refs.get("main")), ("approved", refs.get("approved")), ("anti", refs.get("anti"))):
        for rid in ids or []:
            if rid in seen:
                continue
            r = by_id.get(rid)
            if r:
                seen.add(rid)
                out.append({"title": r.get("title"), "link": r.get("link"), "role": role})
    return out


def _consult_question(body: dict) -> dict:
    try:
        from tools.interior_studio.consult_gpt_bridge import contracts, prompt_builder, store
        refs = body.get("references")
        if refs is None:
            refs = _cycle_references()   # auto: puxa as referências curadas do ciclo
        q = prompt_builder.build_question(
            mode=body.get("mode") or "JUDGE", room=body.get("room") or "kitchen",
            phase=body.get("phase") or "skin",
            theme=body.get("theme") or "BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE",
            context=body.get("context") or "", decision_goal=body.get("decision_goal") or "",
            architect_hypothesis=body.get("hypothesis") or "", references=refs,
            questions=body.get("questions") or None,
            frozen_constraints=body.get("frozen"), mutable=body.get("mutable"),
            visual_inputs={"main": body.get("image") or None, "aux": body.get("aux") or [],
                           "compare": body.get("compare") or {}},
            priority=body.get("priority") or "high", question_id=body.get("question_id") or None)
        saved = store.save_question(q)
        try:   # amarra a pergunta ao ciclo (rastreabilidade) + status waiting_gpt_answer
            c = ic_cycles.current_cycle()
            if c:
                c.setdefault("consult", {})["question_id"] = q["question_id"]
                c["consult"]["status"] = "waiting_gpt_answer"
                ic_cycles.save_cycle(c)
        except Exception:  # noqa: BLE001
            pass
        try:
            from tools import studio_log
            studio_log.post("consult-liaison", "working",
                            f"pergunta {q['question_id']} pronta — copie pro Consult GPT", to="architect")
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "question_id": q["question_id"], "md": contracts.render_question_md(q),
                "status": "waiting_gpt_answer", "paths": saved}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _relay_state() -> dict | None:
    try:
        return json.loads(RELAY_FILE.read_text("utf-8")) if RELAY_FILE.exists() else None
    except (json.JSONDecodeError, OSError):
        return None


def _relay_mark(qid: str, status: str, **extra) -> None:
    RELAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    rec = {"question_id": qid, "status": status, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **extra}
    RELAY_FILE.write_text(json.dumps(rec, ensure_ascii=False, indent=2), "utf-8")


def _consult_relay_request(body: dict) -> dict:
    """Felipe pede o RELAY: o Claude vai pegar a pergunta pendente, dirigir o ChatGPT Plus dele pela
    extensão do Chrome, ler a resposta e devolver pro dash. (Semi-auto: roda quando o Claude está na sessão.)"""
    try:
        from tools.interior_studio.consult_gpt_bridge import store
        qid = body.get("question_id") or (store.latest_question() or {}).get("question_id")
        if not qid:
            return {"ok": False, "error": "sem pergunta pendente pra relayar — gere uma primeiro"}
        _relay_mark(qid, "requested")
        try:
            from tools import studio_log
            studio_log.post("consult-liaison", "working",
                            f"relay PEDIDO: {qid} → Claude vai dirigir o ChatGPT (Chrome)", to="architect")
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "question_id": qid, "status": "requested"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _consult_answer(body: dict) -> dict:
    try:
        from tools.interior_studio.consult_gpt_bridge import store
        raw = body.get("answer") or body.get("answer_md") or ""
        if not raw.strip():
            return {"ok": False, "error": "resposta vazia"}
        qid = body.get("question_id") or (store.latest_question() or {}).get("question_id") or "sem_id"
        return {"ok": True, **store.save_answer(qid, raw)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _consult_ingest(body: dict) -> dict:
    try:
        from tools.interior_studio.consult_gpt_bridge import ingest as ci
        r = ci.ingest(body.get("question_id") or None)
        try:
            from tools import studio_log
            if r.get("ok"):
                studio_log.post("consult-liaison", "done",
                                f"ingeri {r.get('question_id')}: {r.get('verdict')} · "
                                f"+{len(r.get('rules_added', []))} regra(s), +{len(r.get('anti_patterns_added', []))} anti-pattern(s)",
                                to="architect")
        except Exception:  # noqa: BLE001
            pass
        return r
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _scout_search(query, n=8):
    """🔭 Scout: busca referência/preço na web pelo SERVIDOR (DuckDuckGo HTML, sem chave nem LLM — os
    locais não navegam). Devolve [{title,url}]. É o que vai alimentar a curadoria de referências/preços."""
    import html as _html
    import re as _re
    import urllib.parse
    import urllib.request
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "escreve o que buscar"}
    try:
        data = urllib.parse.urlencode({"q": q}).encode()   # DDG html exige POST (GET devolve página vazia)
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/", data=data,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                     "Content-Type": "application/x-www-form-urlencoded"})
        html = urllib.request.urlopen(req, timeout=14).read().decode("utf-8", "ignore")
        out = []
        for m in _re.finditer(r'<a\s+([^>]*?class="result__a"[^>]*?)>(.*?)</a>', html, _re.DOTALL):
            hm = _re.search(r'href="([^"]+)"', m.group(1))
            if not hm:
                continue
            title = _html.unescape(_re.sub(r"<[^>]+>", "", m.group(2))).strip()
            mm = _re.search(r"uddg=([^&]+)", hm.group(1))   # caso venha redirect
            real = urllib.parse.unquote(mm.group(1)) if mm else hm.group(1)
            if title and real.startswith("http"):
                out.append({"title": title[:130], "url": real})
            if len(out) >= n:
                break
        return {"ok": True, "query": q, "results": out}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "hint": "o container precisa de internet"}


def _team_ask(agent, question):
    """Pergunta PLANA do Felipe -> ENQUADRA num bom prompt (domínio cozinha, PT, sem inventar) -> manda
    pro agente/consenso local. É o tradutor: o local não alucina com pergunta casual."""
    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "escreve a pergunta"}
    labels = {"interior-pm": "PM", "interior-orchestrator": "Team Lead", "interior-designer": "Arquiteto"}
    role = agent if agent in labels else "interior-designer"
    base = (f"Você é o {labels.get(role, 'Arquiteto')} de um estúdio de design de INTERIORES (cozinha "
            f"planta_74, apê 74m2, estilo dark premium BLACK_WOOD_GOLD). Responda em português, foco em "
            f"design/execução de COZINHA, RESPEITANDO o gosto do Felipe abaixo. Sem inventar nem sair do tema.")
    # injeta o DNA pra QUALQUER agente responder no gosto do Felipe (o Arquiteto já recebe via _ask)
    prime = "" if agent == "interior-designer" else _architect_priming(dna_budget=2500, feed_budget=900)
    framed = ((prime + "\n\n") if prime else "") + f"{base}\n\nPergunta do Felipe: {q}"
    if agent == "consenso":
        return _consensus("interior-designer", framed, display=q)
    return _ask(role, framed, display=q)


def _consult_learn(body: dict) -> dict:
    """UM botão pra aprender. Cola a resposta do Consult GPT OU qualquer orientação solta — auto-detecta:
    se é um ARCHITECT_ANSWER_CONTRACT (tem veredito/respostas) salva+ingere (vira regra/anti-pattern/MT no DNA);
    senão alimenta direto o conhecimento do Arquiteto (architect.md). Mata o 'salvar/ingerir' separado."""
    text = (body.get("text") or body.get("answer") or "").strip()
    if not text:
        return {"ok": False, "error": "cole a resposta do GPT ou uma orientação primeiro"}
    low = text.lower()
    is_answer = ("architect_answer_contract" in low or "## veredito" in low or "## respostas" in low
                 or bool(re.search(r"(?im)^\s*-?\s*verdict\s*:", text)))
    try:
        if is_answer:
            # GPT decision: resposta estruturada NÃO aplica direto. Vira LEARNING_PATCH draft → diff → Felipe aprova.
            from tools.interior_studio import learning_patch as lp
            from tools.interior_studio.consult_gpt_bridge import answer_parser, store
            parsed = answer_parser.parse_answer(text)
            qid = (body.get("question_id") or parsed.get("question_id")
                   or (store.latest_question() or {}).get("question_id") or "colado")
            saved = store.save_answer(qid, text)
            parsed["question_id"] = qid
            patch = lp.from_answer(parsed, answer_path=saved.get("path", ""))
            diff = lp.compute_diff(patch)
            rs = _relay_state()   # se havia relay pendente desse qid, fecha o loop
            if rs and rs.get("question_id") == qid:
                _relay_mark(qid, "answered", patch_id=patch["patch_id"])
            try:
                from tools import studio_log
                studio_log.post("consult-liaison", "done",
                                f"gerei {patch['patch_id']} (draft) de {qid}: "
                                f"+{len(diff['rules_add'])} regra(s), +{len(diff['anti_add'])} anti — aguarda Felipe",
                                to="architect")
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "mode": "patch_draft", "patch_id": patch["patch_id"],
                    "verdict": patch.get("verdict"), "diff": diff}
        r = _feed(text, body.get("title"))
        r["mode"] = "feed"
        return r
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _consult_ask_openai(body: dict) -> dict:
    try:
        from tools.interior_studio.consult_gpt_bridge import openai_client
        return openai_client.ask(body or {})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "fallback": "manual"}


# Arquiteto CONVERSA (deepseek, responde de verdade); o spec-cuspidor é um ESPECIALISTA embaixo dele.
#
# Conhecimento do Arquiteto = blocos ATÔMICOS no architect.md. Cada alimentação vira UM bloco com
# header sentinela `<!--KB id=N | title=...-->` + corpo verbatim. O header NÃO colide com markdown
# colado do GPT (que tem '##', '#', etc.), então um texto com várias seções continua sendo UMA entrada
# — e o "esquecer" usa o ID ESTÁVEL, nunca a posição (posição muda quando a lista re-renderiza).
_KB_HEAD_FMT = "<!--KB id={id} | title={title}-->"
_KB_HEAD_RE = re.compile(r"^<!--KB id=(\d+) \| title=(.*?)-->\s*$")


def _kb_read():
    """Lê o architect.md como lista de blocos atômicos [{id,title,body}]. Arquivo sem header KB (legado)
    vira UM único bloco id=0 — não adivinha fronteiras (markdown colado não é fronteira de entrada)."""
    if not ARCH_KB.exists():
        return []
    text = ARCH_KB.read_text("utf-8")
    if "<!--KB id=" not in text:
        body = text.strip()
        return [{"id": 0, "title": "(conhecimento legado)", "body": body}] if body else []
    entries, cur = [], None
    for line in text.splitlines():
        m = _KB_HEAD_RE.match(line)
        if m:
            cur = {"id": int(m.group(1)), "title": m.group(2).strip() or "(sem título)", "body": []}
            entries.append(cur)
        elif cur is not None:
            cur["body"].append(line)
    for e in entries:
        e["body"] = "\n".join(e["body"]).strip()
    return entries


def _kb_write(entries):
    """Reescreve o architect.md a partir de [{id,title,body}] no formato atômico (idempotente)."""
    if not entries:
        ARCH_KB.write_text("", "utf-8")
        return
    parts = [f"{_KB_HEAD_FMT.format(id=e['id'], title=e['title'])}\n{e['body']}".rstrip() for e in entries]
    ARCH_KB.write_text("\n" + "\n\n".join(parts) + "\n", "utf-8")


def _feed(text, title=None):
    """Felipe cola (ou sobe um .txt) orientações de design (do GPT, que já sabe o gosto dele) -> o
    Arquiteto APRENDE e usa nas respostas. Cada alimentação = UM bloco atômico (id estável, corpo
    verbatim) — o '##' do markdown do GPT NÃO fragmenta a entrada."""
    if not text or not text.strip():
        return {"ok": False, "error": "sem texto"}
    entries = _kb_read()
    new_id = max((e["id"] for e in entries), default=0) + 1
    safe = (title or "orientação").replace("\n", " ").replace("-->", "→").strip()[:120] or "orientação"
    ARCH_KB.parent.mkdir(parents=True, exist_ok=True)
    with ARCH_KB.open("a", encoding="utf-8") as f:
        f.write(f"\n{_KB_HEAD_FMT.format(id=new_id, title=safe)}\n{text.strip()}\n")
    try:
        from tools import studio_log
        studio_log.post("interior-designer", "done", f"aprendi: {safe[:80]}")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": new_id, "chars": len(ARCH_KB.read_text("utf-8")), "count": len(entries) + 1}


def _kb_entries():
    """Resumo p/ o painel: o que o Arquiteto já aprendeu (id estável, título, tamanho, preview).
    Lista compacta -> Felipe manda VÁRIOS blocos sem encavalar/sair da tela."""
    return [{"id": e["id"], "title": e["title"], "chars": len(e["body"]), "preview": e["body"][:160]}
            for e in _kb_read()]


def _knowledge_state():
    jr = _judge_rules()
    return {"chars": len(ARCH_KB.read_text("utf-8")) if ARCH_KB.exists() else 0,
            "entries": _kb_entries(),
            "dna": FELIPE_DNA.exists(),
            "judge": {"anti_patterns": len(jr.get("anti_patterns", [])), "flagged": len(jr.get("flagged", []))}}


def _forget(entry_id):
    """Felipe apaga UMA entrada pelo ID ESTÁVEL (não por posição — id não muda quando a lista
    re-renderiza, então nunca apaga o bloco errado). Reescreve sem ela. Idempotente."""
    try:
        entry_id = int(entry_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "id inválido"}
    entries = _kb_read()
    keep = [e for e in entries if e["id"] != entry_id]
    if len(keep) == len(entries):
        return {"ok": False, "error": "id não encontrado"}
    dropped = next(e for e in entries if e["id"] == entry_id)
    _kb_write(keep)
    try:
        from tools import studio_log
        studio_log.post("interior-designer", "done", f"esqueci: {dropped['title'][:60]}")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "chars": len(ARCH_KB.read_text("utf-8")) if ARCH_KB.exists() else 0,
            "count": len(keep)}


def _arch_knowledge(budget=6000):
    """Texto que PRIMA o Arquiteto antes de responder: entradas INTEIRAS (nunca cortadas no meio),
    das mais recentes pra trás até o budget, em ordem cronológica. Antes era 'últimos 2500 chars'
    (cortava bloco no meio e perdia tudo quando o Felipe alimenta MUITO)."""
    entries = _kb_read()
    if not entries:
        return ""
    blocks = [f"## {e['title']}\n{e['body']}".strip() for e in entries]
    chosen, used = [], 0
    for blk in reversed(blocks):
        if chosen and used + len(blk) > budget:
            break
        chosen.append(blk)
        used += len(blk)
    return "\n\n".join(reversed(chosen))


def _judge_rules():
    """Lê as regras do juiz visual do Felipe (anti-patterns + erros que ele marcou no painel)."""
    if not JUDGE_RULES.exists():
        return {}
    try:
        return json.loads(JUDGE_RULES.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _architect_priming(dna_budget=4000, feed_budget=4000):
    """Contexto que o Arquiteto carrega ANTES de responder — as 3 CAMADAS do gosto do Felipe (modelo do
    Felipe): (1) DNA de estilo canônico, (2) anti-patterns + erros marcados (não repetir), (3) orientações
    coladas/subidas (architect.md). Camadas vazias são puladas."""
    parts = []
    if FELIPE_DNA.exists():
        dna = FELIPE_DNA.read_text("utf-8").strip()
        if dna:
            parts.append("[FELIPE STYLE DNA — identidade canônica, é RESTRIÇÃO não sugestão]:\n" + dna[:dna_budget])
    jr = _judge_rules()
    aps = jr.get("anti_patterns", []) + [{"what": f.get("message", ""), "why": "erro marcado pelo Felipe"}
                                         for f in jr.get("flagged", [])]
    if aps:
        lines = "\n".join(f"- NÃO: {a.get('what','')}" + (f" ({a['why']})" if a.get("why") else "") for a in aps if a.get("what"))
        parts.append("[ANTI-PATTERNS — o que o Felipe NÃO curtiu, não repita]:\n" + lines)
    feed = _arch_knowledge(budget=feed_budget)
    if feed:
        parts.append("[ORIENTAÇÕES alimentadas pelo Felipe — SIGA]:\n" + feed)
    return "\n\n".join(parts)


AGENT_ROLE = {"interior-designer": "deepseek", "interior-orchestrator": "coder",
              "interior-pm": "llama", "ollama-deepseek": "deepseek",
              "ollama-qwen": "qwen", "ollama-llama": "llama", "gpt-visual": "vision",
              "ollama-spec": "designer"}


def _ask(agent, prompt, image=None, display=None):
    """Felipe/studio pergunta a um agente -> roteia pro LLM LOCAL via Ollama, SEM Claude (peão local).
    `display` = o que aparece na bolha do Felipe (pergunta PLANA); `prompt` = o que vai pro LLM (enquadrado)."""
    agent = agent or "interior-designer"
    try:
        from tools import ollama_bridge, studio_log
        role = AGENT_ROLE.get(agent, "llama")
        studio_log.post("felipe", "working", (display or prompt or "").strip(), to=agent)   # bolha do Felipe (pergunta plana)
        q = prompt or ""
        if agent == "interior-designer":   # Arquiteto responde JÁ usando as 3 camadas do gosto do Felipe
            ctx = _architect_priming()
            if ctx:
                q = f"{ctx}\n\n[Pergunta]: {q}"
        r = ollama_bridge.ask(role, q, image=image)
        import re as _re
        raw = r.get("response") or r.get("error") or ""
        resp = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()[:1500]  # tira o raciocínio do deepseek; cap 1500 (era 600, cortava)
        studio_log.post(agent, "done" if r.get("ok") else "error", resp, via=r.get("model"))  # bolha do agente
        return {"ok": r.get("ok", False), "agent": agent, "model": r.get("model"), "response": resp}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _consensus(agent, prompt, display=None):
    """Fan-out: pergunta pros 3 LLMs locais (deepseek/qwen/llama), eles opinam, e um sintetiza
    numa resposta concisa e mais 'pensada'. Mais lento, mas mais inteligente (ideia do Felipe).
    `display` = pergunta PLANA pra bolha do Felipe (vs `prompt` enquadrado)."""
    import re as _re
    agent = agent or "interior-designer"
    prompt = prompt or ""

    def _clean(r):
        return _re.sub(r"<think>.*?</think>", "", r.get("response") or "", flags=_re.DOTALL).strip()
    try:
        from tools import ollama_bridge, studio_log
        studio_log.post("felipe", "working", (display or prompt or "").strip(), to=agent)
        opinions = []
        for role in ("deepseek", "qwen", "llama"):
            studio_log.post(f"ollama-{role}", "thinking", f"opinando: {prompt[:40]}")
            t = _clean(ollama_bridge.ask(role, prompt, timeout=90))
            opinions.append((role, t))
            studio_log.post(f"ollama-{role}", "done", t[:160] or "(vazio)")
        synth_prompt = (f"Pergunta: '{prompt}'. Três modelos responderam:\n"
                        + "\n".join(f"- {r}: {t[:350]}" for r, t in opinions)
                        + "\nSintetize tudo numa resposta CONCISA e bem pensada (1 parágrafo), pegando os melhores pontos. Responda em PT-BR.")
        synth = _clean(ollama_bridge.ask("deepseek", synth_prompt, timeout=120))[:700]
        studio_log.post(agent, "done", "[consenso] " + synth, via="consenso (deepseek+qwen+llama)")
        return {"ok": True, "synthesis": synth, "opinions": [{"model": r, "text": t} for r, t in opinions]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _cycle_save(rec: dict) -> None:
    CYCLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CYCLES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _cycles_count() -> int:
    if not CYCLES_FILE.exists():
        return 0
    return sum(1 for ln in CYCLES_FILE.read_text("utf-8", "ignore").splitlines() if ln.strip())


def _cycles_recent(n: int = 8) -> list[dict]:
    """Últimos ciclos persistidos (mais recente primeiro) — é o 'banco' que fecha o loop: cada ciclo
    guarda a diretriz do Arquiteto pra virar pergunta ao Consult GPT / próxima ação no .skp."""
    if not CYCLES_FILE.exists():
        return []
    out = []
    for ln in CYCLES_FILE.read_text("utf-8", "ignore").splitlines()[-n:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out


def _cycle(goal=None):
    """UM ciclo do orquestrador rodando nos LLMs LOCAIS (sem Claude): PM escolhe a próxima tarefa
    -> consulta o Team Lead -> que consulta o Arquiteto. Cada passo posta no feed = a cadeia viva.
    O resultado é PERSISTIDO (cycles.jsonl) com a diretriz do Arquiteto = saída útil do ciclo."""
    import re as _re
    try:
        from tools import ollama_bridge, studio_log
        bk = _backlog()
        nxt = next((t for t in bk.get("tasks", [])
                    if not t["done"] and not t["geo"] and t["status"] in ("backlog", "refinamento")), None)
        if not nxt:
            studio_log.post("interior-pm", "idle", "sem tarefa PELE na fila — preciso de OK p/ GEO")
            return {"ok": True, "msg": "fila PELE vazia"}
        mt = f"{nxt['mt']} ({nxt['what'][:55]})"
        g = goal or "deixar a cozinha 100%"

        def clean(r):
            return _re.sub(r"<think>.*?</think>", "", r.get("response") or "", flags=_re.DOTALL).strip()
        dom = ("Voce e o {role} de um estudio de design de INTERIORES, cozinha da planta_74 (apto 74m2, "
               "estilo dark premium BLACK_WOOD_GOLD). Responda SO em portugues, 1 frase curta, "
               "estritamente sobre design/execucao de COZINHA. NAO invente tarefa nova; NAO fale de "
               "solda, codigo, software, emergencia nem nada fora de cozinha.")
        pm = clean(ollama_bridge.ask("llama", f"{dom.format(role='PM')} Meta: {g}. Tarefa atual: {mt}. Em 1 frase: por que puxar essa tarefa agora?", timeout=60))
        studio_log.post("interior-pm", "done", pm[:200] or f"puxei {mt}", to="team_lead", via="llama3.1:8b")
        # PM MOVE o card pra execução (ele é o dono do Kanban)
        k = _kanban_load()
        k[nxt["mt"]] = "execução"
        KANBAN_FILE.write_text(json.dumps(k, ensure_ascii=False, indent=2), "utf-8")
        tl = clean(ollama_bridge.ask("coder", f"{dom.format(role='Team Lead')} Tarefa: {mt}. Em 1 frase: o que o time precisa pra executar bem?", timeout=60))
        studio_log.post("interior-orchestrator", "done", tl[:200] or "organizei o time", to="architect", via="qwen2.5-coder:14b")
        prime = _architect_priming()   # DNA + anti-patterns + orientações (não só architect.md)
        ar = clean(ollama_bridge.ask("deepseek", (f"{prime}\n\n" if prime else "") + f"{dom.format(role='Arquiteto')} Tarefa: {mt}. Em 1 frase: a diretriz de design.", timeout=90))
        studio_log.post("interior-designer", "done", ar[:250] or "diretriz dada", via="deepseek-r1:14b")
        cid = f"CYCLE-{_cycles_count() + 1:03d}"
        directive = (ar or "").strip()[:600] or "(sem diretriz)"
        _cycle_save({"cycle_id": cid, "ts": time.time(), "mt": nxt["mt"], "what": nxt.get("what", ""),
                     "goal": g, "pm": (pm or "").strip()[:300], "lead": (tl or "").strip()[:300],
                     "directive": directive, "models": ["llama3.1:8b", "qwen2.5-coder:14b", "deepseek-r1:14b"],
                     "consulted": False})
        if len(directive) > 40 and directive != "(sem diretriz)":
            _feed(directive, f"diretriz de ciclo {nxt['mt']}")   # alimenta o Arquiteto com a própria diretriz
        return {"ok": True, "task": nxt["mt"], "cycle_id": cid, "directive": directive}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _gpt_bundle(body: dict) -> dict:
    """Gera o GPT_REVIEW_BUNDLE.{md,json} a partir do estado atual (fonte única pro Consult GPT)."""
    try:
        return ic_bundle.build(_state(), now=time.strftime("%Y-%m-%dT%H:%M:%S"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _refpack_images(body: dict) -> dict:
    """Resolve o og:image de cada referência do pack (só a URL — o navegador carrega da CDN, sem baixar
    arquivo). Persiste `og_image` no pack pra virar curadoria VISUAL (não tabela de texto)."""
    import re as _re
    import urllib.error
    import urllib.request
    pack_id = body.get("pack_id") or DEFAULT_PACK
    pack = ic_refpacks.load_pack(pack_id)
    if not pack:
        return {"ok": False, "error": f"pack {pack_id} não encontrado"}
    hdr = {"User-Agent": "Mozilla/5.0"}
    out, broken, changed = {}, [], False

    def _set(ref, key, val):
        nonlocal changed
        if ref.get(key) != val:
            ref[key] = val
            changed = True

    for ref in pack.get("references", []):
        url = ref.get("link")
        if ref.get("og_image"):   # já resolvido antes → link estava ok
            out[ref["id"]] = ref["og_image"]
            _set(ref, "link_status", "ok")
            continue
        if not url:
            continue
        try:
            html = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=12).read().decode("utf-8", "ignore")
            _set(ref, "link_status", "ok")
            m = (_re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html)
                 or _re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html)
                 or _re.search(r'name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)', html))
            if m:
                _set(ref, "og_image", m.group(1))
                out[ref["id"]] = m.group(1)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):      # página morta (gone) = link quebrado
                _set(ref, "link_status", "broken")
                broken.append(ref["id"])
            else:                         # 403/500/etc: respondeu, página existe
                _set(ref, "link_status", "ok")
        except urllib.error.URLError:     # DNS / conexão recusada = quebrado
            _set(ref, "link_status", "broken")
            broken.append(ref["id"])
        except Exception:  # noqa: BLE001  (timeout etc: não marca, pode ser transitório)
            continue
    if changed:
        ic_refpacks.save_pack(pack)
    return {"ok": True, "images": out, "resolved": len(out), "broken": broken,
            "total": len(pack.get("references", []))}


def _patch_action(body: dict) -> dict:
    """Felipe aprova/rejeita um LEARNING_PATCH draft (só após aprovação ele altera DNA/juiz)."""
    pid = body.get("patch_id")
    act = body.get("action")
    try:
        if act == "approve":
            r = ic_patch.approve(pid, now=time.strftime("%Y-%m-%dT%H:%M:%S"))
            try:
                from tools import studio_log
                if r.get("ok"):
                    studio_log.post("consult-liaison", "done",
                                    f"Felipe APROVOU {pid}: +{len(r.get('rules_added', []))} regra(s) no DNA",
                                    to="architect")
            except Exception:  # noqa: BLE001
                pass
            return r
        if act == "reject":
            return ic_patch.reject(pid, body.get("reason"), now=time.strftime("%Y-%m-%dT%H:%M:%S"))
        return {"ok": False, "error": f"ação inválida: {act}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _curate_ref(body: dict) -> dict:
    """Curadoria visual do Felipe numa referência do Reference Pack (👍/👎/⭐/🚫 + comentário)."""
    try:
        return ic_refpacks.curate(body.get("pack_id") or DEFAULT_PACK, body.get("ref_id"),
                                  body.get("action"), body.get("comment"), body.get("cycle_id"),
                                  ts=time.time())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _clear(agent):
    """Felipe tira um agente do status de erro (volta pra idle)."""
    try:
        from tools import studio_log
        studio_log.post(agent or "interior-orchestrator", "idle", "(status limpo pelo Felipe)")
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")  # sempre versão fresca
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send(200, json.dumps(_state(), ensure_ascii=False))
        elif path == "/api/consult/state":
            self._send(200, json.dumps(_consult_state(), ensure_ascii=False))
        elif path == "/api/consult/latest-question":
            self._send(200, json.dumps(_consult_latest("question"), ensure_ascii=False))
        elif path == "/api/consult/latest-answer":
            self._send(200, json.dumps(_consult_latest("answer"), ensure_ascii=False))
        elif path.startswith("/img/"):
            fp = (ANGLES / path[len("/img/"):]).resolve()
            if fp.is_file() and ANGLES.resolve() in fp.parents and fp.suffix == ".png":
                self._send(200, fp.read_bytes(), "image/png")
            else:
                self._send(404, b"not found", "text/plain")
        elif path.startswith("/inbox-img/"):
            inbox_dir = INBOX.parent.resolve()
            fp = (inbox_dir / path[len("/inbox-img/"):]).resolve()
            ct = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".webp": "image/webp"}.get(fp.suffix.lower())
            if fp.is_file() and inbox_dir in fp.parents and ct:
                self._send(200, fp.read_bytes(), ct)
            else:
                self._send(404, b"not found", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            body = {}
        if path == "/api/curate":
            self._send(200, json.dumps(_curate(body.get("slug"), body.get("action"))))
        elif path == "/api/flag":
            self._send(200, json.dumps(_flag(body.get("agent"), body.get("message"))))
        elif path == "/api/ask":
            self._send(200, json.dumps(_ask(body.get("agent"), body.get("prompt"), body.get("image"))))
        elif path == "/api/upload":
            self._send(200, json.dumps(_upload(body.get("filename"), body.get("data"))))
        elif path == "/api/clear":
            self._send(200, json.dumps(_clear(body.get("agent"))))
        elif path == "/api/consensus":
            self._send(200, json.dumps(_consensus(body.get("agent"), body.get("prompt"))))
        elif path == "/api/preview":
            self._send(200, json.dumps(_fetch_preview(body.get("slug"))))
        elif path == "/api/feed":
            self._send(200, json.dumps(_feed(body.get("text"), body.get("title"))))
        elif path == "/api/forget":
            self._send(200, json.dumps(_forget(body.get("id"))))
        elif path == "/api/consult/question":
            self._send(200, json.dumps(_consult_question(body), ensure_ascii=False))
        elif path == "/api/consult/answer":
            self._send(200, json.dumps(_consult_answer(body), ensure_ascii=False))
        elif path == "/api/consult/ingest":
            self._send(200, json.dumps(_consult_ingest(body), ensure_ascii=False))
        elif path == "/api/consult/learn":
            self._send(200, json.dumps(_consult_learn(body), ensure_ascii=False))
        elif path == "/api/consult/relay-request":
            self._send(200, json.dumps(_consult_relay_request(body), ensure_ascii=False))
        elif path == "/api/team-ask":
            self._send(200, json.dumps(_team_ask(body.get("agent"), body.get("question")), ensure_ascii=False))
        elif path == "/api/scout-search":
            self._send(200, json.dumps(_scout_search(body.get("query")), ensure_ascii=False))
        elif path == "/api/consult/ask-openai":
            self._send(200, json.dumps(_consult_ask_openai(body), ensure_ascii=False))
        elif path == "/api/move":
            self._send(200, json.dumps(_move_task(body.get("mt"), body.get("direction"))))
        elif path == "/api/cycle":
            self._send(200, json.dumps(_cycle(body.get("goal"))))
        elif path == "/api/curate-ref":
            self._send(200, json.dumps(_curate_ref(body), ensure_ascii=False))
        elif path == "/api/gpt-bundle":
            self._send(200, json.dumps(_gpt_bundle(body), ensure_ascii=False))
        elif path == "/api/refpack-images":
            self._send(200, json.dumps(_refpack_images(body), ensure_ascii=False))
        elif path == "/api/patch":
            self._send(200, json.dumps(_patch_action(body), ensure_ascii=False))
        else:
            self._send(404, b"not found", "text/plain")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8782)
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    print(f"INTERIOR STUDIO dashboard -> http://127.0.0.1:{a.port}/  (Ctrl+C p/ parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
