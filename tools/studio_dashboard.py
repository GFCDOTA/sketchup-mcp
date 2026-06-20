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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ANGLES = ROOT / "artifacts/planta_74/furnished/kitchen_angles"
BACKLOG = ROOT / "artifacts/reference_lab/kitchen/spec/KITCHEN_TO_100.md"
COORD = ROOT / ".ai_bridge/SESSION_COORDINATION.md"
INBOX = ROOT / "artifacts/reference_lab/inbox/INBOX.json"
SKIP = (".denoiser.png", ".effectsResult.png")

ROSTER = [
    {"id": "interior-orchestrator", "face": "\U0001F3AC", "label": "Team Lead"},
    {"id": "interior-pm",           "face": "\U0001F4CB", "label": "PM"},
    {"id": "interior-designer",     "face": "\U0001F3A8", "label": "Arquiteto"},
    {"id": "reference-scout",       "face": "\U0001F52D", "label": "Scout"},
    {"id": "ollama-deepseek",       "face": "\U0001F433", "label": "DeepSeek"},
    {"id": "ollama-qwen",           "face": "\U0001F916", "label": "Qwen-coder"},
    {"id": "gpt-visual",            "face": "\U0001F9E0", "label": "GPT (visão)"},
]
UMBRELLAS = [
    {"id": "pm",        "label": "PM",        "lead": "interior-pm",           "subs": ["reference-scout"]},
    {"id": "team_lead", "label": "Team Lead", "lead": "interior-orchestrator", "subs": ["ollama-deepseek", "ollama-qwen"]},
    {"id": "architect", "label": "Arquiteto", "lead": "interior-designer",     "subs": ["gpt-visual"]},
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
        return {"total": 0, "pele": 0, "geo": 0, "done": 0}
    txt = BACKLOG.read_text("utf-8", "ignore")
    mts = set(re.findall(r"MT-\d+", txt))
    geo = set(re.findall(r"(MT-\d+)\s*`?\[GEO\]", txt))
    done = set(re.findall(r"(MT-\d+)[^\n]*(?:DONE|✓|completed)", txt))
    return {"total": len(mts), "geo": len(geo), "pele": len(mts) - len(geo), "done": len(done)}


def _references() -> dict:
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
        return {"by_kind": by_kind, "by_theme": by_theme}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


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

    def card(aid):
        rec = last.get(aid)
        base = facemap.get(aid, {"face": "•", "label": aid})
        return {"id": aid, "face": base["face"], "label": base["label"],
                "status": rec["status"] if rec else "idle",
                "message": rec["message"] if rec else "—",
                "ts": rec.get("ts") if rec else None}

    metrics = {}
    for r in allrecs:
        m = metrics.setdefault(r["agent"], {"calls": 0, "errors": 0})
        m["calls"] += 1
        if r.get("status") == "error":
            m["errors"] += 1

    umbrellas = [{"id": u["id"], "label": u["label"], "lead": card(u["lead"]),
                  "subs": [card(s) for s in u["subs"]]} for u in UMBRELLAS]
    agent_umbrella = {}
    for u in UMBRELLAS:
        agent_umbrella[u["lead"]] = u["id"]
        for s in u["subs"]:
            agent_umbrella[s] = u["id"]
    return {"umbrellas": umbrellas, "feed": feed, "metrics": metrics,
            "agent_umbrella": agent_umbrella}


def _state() -> dict:
    return {"agents": _agents(), "renders": _renders(), "sessions": _sessions(),
            "backlog": _backlog(), "references": _references(), "inbox": _inbox()}


PAGE = r"""<!doctype html><html lang=pt-BR><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>INTERIOR STUDIO — live</title>
<style>
:root{--bg:#0f1013;--card:#181a1f;--bd:#262a32;--fg:#e8e9ec;--mut:#9aa0aa;--ok:#7fd99a;--warn:#e6c069;--blu:#6ca8ff;--red:#e67c7c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Arial}
header{padding:14px 20px;border-bottom:1px solid var(--bd);display:flex;align-items:center;gap:14px}
h1{font-size:17px;margin:0}.hdot{width:9px;height:9px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok)}
.mut{color:var(--mut);font-size:12.5px}.wrap{padding:16px 20px;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px}
.card.full{grid-column:1/3}h2{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);margin:0 0 10px}
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
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:26px;position:relative;z-index:1;padding-top:30px}
.col{background:#13151a;border:1px solid var(--bd);border-radius:12px;padding:12px}
.lead{display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--bd);padding-bottom:9px;margin-bottom:9px}
.lead .face{font-size:30px;line-height:1}.lead .nm{font-weight:700;font-size:15px}
.lead .msg{color:var(--mut);font-size:11.5px;margin-top:2px;max-height:30px;overflow:hidden}
.subs{display:flex;flex-direction:column;gap:7px;margin-bottom:9px}
.sub{display:flex;gap:8px;align-items:center;background:#181a1f;border:1px solid var(--bd);border-radius:8px;padding:6px 9px}
.sub .face{font-size:18px;opacity:.55}.sub.act .face,.lead.act .face{opacity:1}
.sub .nm{font-size:12.5px}.sub .msg{color:var(--mut);font-size:11px;max-height:16px;overflow:hidden}
.sdot{width:8px;height:8px;border-radius:50%;background:#5a606b;display:inline-block;margin-left:auto;flex:none}
.s-working .sdot,.s-thinking .sdot{background:var(--ok);box-shadow:0 0 7px var(--ok);animation:pulse 1.1s infinite}
.s-done .sdot{background:var(--blu)}.s-blocked .sdot,.s-error .sdot{background:var(--red)}.s-waiting .sdot{background:var(--warn)}
.stag{font-size:10px;color:var(--mut);margin-left:6px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.chat{background:#0c0d10;border:1px solid var(--bd);border-radius:8px;padding:6px 8px;max-height:120px;overflow-y:auto;font-size:11.5px}
.chat .ln{padding:2px 0;border-bottom:1px solid #16181d}.chat .to{color:var(--ok)}.chat .t{color:var(--mut);font-size:10px;float:right}
.arrow{fill:none;stroke:var(--ok);stroke-width:2.2;stroke-dasharray:7 6;animation:flow 1s linear infinite;filter:drop-shadow(0 0 4px var(--ok))}
@keyframes flow{to{stroke-dashoffset:-13}}
/* métricas */
.metrics{margin-top:14px}.mrow{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12px}
.mrow .nm{width:130px;color:var(--mut)}.mbar{flex:1;display:flex;gap:3px;align-items:center}
.mbar .c{height:11px;background:var(--blu);border-radius:3px;min-width:2px}.mbar .e{height:11px;background:var(--red);border-radius:3px}
.mnum{font-size:11px;color:var(--mut);width:92px}
</style></head><body>
<header><span class=hdot></span><h1>INTERIOR STUDIO</h1><span class=mut id=ts>carregando…</span>
<span class=mut style=margin-left:auto>auto-refresh 5s · :8782 (separado do oráculo :8765)</span></header>
<div class=wrap id=root></div>
<script>
const el=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstChild}
const esc=(t)=>(t||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))
const hhmm=(ts)=>ts?new Date(ts*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):''
function leadCard(a){const act=(a.status==='working'||a.status==='thinking')?'act':''
 return `<div class="lead s-${a.status} ${act}" id="lead-${a.id}"><div class=face>${a.face}</div>
  <div style=flex:1><div class=nm>${a.label}<span class=stag>${a.status}</span> <span class=sdot></span></div>
  <div class=msg>${esc(a.message)}</div></div></div>`}
function subCard(a){const act=(a.status==='working'||a.status==='thinking')?'act':''
 return `<div class="sub s-${a.status} ${act}"><span class=face>${a.face}</span>
  <div style=flex:1><div class=nm>${a.label}</div><div class=msg>${esc(a.message)}</div></div><span class=sdot></span></div>`}
function colChat(feed,ids){const f=(feed||[]).filter(x=>ids.includes(x.agent)).slice(-6)
 return f.map(x=>`<div class=ln><span class=t>${hhmm(x.ts)}</span>${esc(x.message)}${x.to?` <span class=to>→ ${esc(x.to)}</span>`:''}</div>`).join('')||'<span class=mut>—</span>'}
function drawArrows(ag){const svg=document.getElementById('arrows'),wrap=document.getElementById('org');if(!svg||!wrap)return
 const wr=wrap.getBoundingClientRect();svg.setAttribute('width',wr.width);svg.setAttribute('height',wr.height)
 const amap=ag.agent_umbrella||{},recent=(ag.feed||[]).slice(-7).filter(f=>f.to)
 const edges=new Set();recent.forEach(f=>{const su=amap[f.agent],tu=amap[f.to]||f.to;if(su&&tu&&su!==tu)edges.add(su+'>'+tu)})
 const ctr=(u)=>{const e=document.getElementById('lead-'+leadOf(u));if(!e)return null;const r=e.getBoundingClientRect();return{x:r.left-wr.left+r.width/2,y:r.top-wr.top}}
 let p='<defs><marker id=ah markerWidth=9 markerHeight=9 refX=7 refY=3 orient=auto><path d="M0,0 L7,3 L0,6 Z" fill="#7fd99a"/></marker></defs>'
 edges.forEach(e=>{const[a,b]=e.split('>'),u=ctr(a),v=ctr(b);if(!u||!v)return;const my=Math.min(u.y,v.y)-20
  p+=`<path class=arrow marker-end="url(#ah)" d="M${u.x},${u.y} Q${(u.x+v.x)/2},${my} ${v.x},${v.y}"/>`})
 svg.innerHTML=p}
let LEADOF={};const leadOf=(u)=>LEADOF[u]
async function tick(){
 let s;try{s=await (await fetch('/api/state')).json()}catch(e){return}
 document.getElementById('ts').textContent='atualizado '+new Date().toLocaleTimeString('pt-BR')
 const b=s.backlog,refs=s.references||{},by=refs.by_theme||{},bk=refs.by_kind||{},ag=s.agents||{umbrellas:[],feed:[],metrics:{}}
 LEADOF={};(ag.umbrellas||[]).forEach(u=>LEADOF[u.id]=u.lead.id)
 const root=document.getElementById('root');root.innerHTML=''
 // ORG (guarda-chuvas + setas + métricas)
 const cols=(ag.umbrellas||[]).map(u=>{const ids=[u.lead.id,...u.subs.map(x=>x.id)]
   return `<div class=col>${leadCard(u.lead)}<div class=subs>${u.subs.map(subCard).join('')}</div>
    <div class=chat>${colChat(ag.feed,ids)}</div></div>`}).join('')
 const mx=Math.max(1,...Object.values(ag.metrics||{}).map(m=>m.calls))
 const met=Object.entries(ag.metrics||{}).sort((a,b)=>b[1].calls-a[1].calls).map(([id,m])=>{
   const lbl=(LEADOF&&id)||id;return `<div class=mrow><span class=nm>${esc(id)}</span>
    <span class=mbar><span class=c style=width:${Math.round(120*m.calls/mx)}px></span>
    ${m.errors?`<span class=e style=width:${Math.round(120*m.errors/mx)}px></span>`:''}</span>
    <span class=mnum>${m.calls} chamadas${m.errors?` · ${m.errors} erro`:''}</span></div>`}).join('')
 root.appendChild(el(`<div class="card full"><h2>Agentes — guarda-chuvas (PM · Team Lead · Arquiteto)</h2>
  <div class=org id=org><svg class=arrows id=arrows></svg><div class=cols>${cols}</div></div>
  <div class=metrics><h2 style=margin:14px_0_6px>Chamadas / erros por agente</h2>${met||'<span class=mut>sem dados ainda</span>'}</div></div>`))
 drawArrows(ag)
 // BACKLOG
 const pct=b.total?Math.round(100*b.done/b.total):0
 root.appendChild(el(`<div class=card><h2>Backlog — KITCHEN_TO_100</h2>
  <span class=k><b>${b.total}</b> <span class=mut>microtarefas</span></span>
  <span class=k><b>${b.pele}</b> <span class=mut>PELE</span></span>
  <span class=k><b>${b.geo}</b> <span class=mut>GEO (espera Felipe)</span></span>
  <span class=k><b style=color:var(--ok)>${b.done}</b> <span class=mut>done</span></span>
  <div class=bar><i style=width:${pct}%></i></div></div>`))
 // SESSÕES
 const cl=(s.sessions.claims||[]).map(c=>`<tr><td>${c.mt}</td><td>${esc(c.owner)}</td><td>${esc(c.status)}</td></tr>`).join('')
 const wt=(s.sessions.worktrees||[]).map(w=>`<div class=mut>${esc(w)}</div>`).join('')
 root.appendChild(el(`<div class=card><h2>Sessões / coordenação</h2>
  <table><tr><th>MT</th><th>dono</th><th>status</th></tr>${cl||'<tr><td colspan=3 class=mut>sem claims</td></tr>'}</table>
  <div style=margin-top:8px>${wt}</div></div>`))
 // REFERÊNCIAS
 const themes=Object.entries(by).map(([t,n])=>`<tr><td>${esc(t)}</td><td>${n}</td></tr>`).join('')
 root.appendChild(el(`<div class=card><h2>Banco de referências (reference_db)</h2>
  <div class=mut style=margin-bottom:8px>${Object.entries(bk).map(([k,n])=>`<span class=pill>${k}: ${n}</span>`).join(' ')||refs.error||''}</div>
  <table><tr><th>tema</th><th>refs</th></tr>${themes}</table></div>`))
 // INBOX
 const inb=(s.inbox||[]).map(i=>`<tr><td>${esc(i.slug)}</td><td>${i.theme||'-'}</td><td>${i.status||'pending'}</td></tr>`).join('')
 root.appendChild(el(`<div class=card><h2>Curadoria — inbox de referência</h2>
  <table><tr><th>slug</th><th>tema</th><th>status</th></tr>${inb||'<tr><td colspan=3 class=mut>fila vazia</td></tr>'}</table></div>`))
 // RENDERS
 const rr=(s.renders||[]).slice(0,24).map(r=>`<div class=thumb><img loading=lazy src="/img/${encodeURIComponent(r.name)}">
   <div class=cap>${esc(r.name.replace('.png',''))}<div class=t>${r.theme} · ${r.sub} · ${r.kb}KB</div></div></div>`).join('')
 root.appendChild(el(`<div class="card full"><h2>Renders (${(s.renders||[]).length}) — mais novos primeiro</h2>
  <div class=grid>${rr||'<span class=mut>sem renders</span>'}</div></div>`))
}
tick();setInterval(tick,5000);window.addEventListener('resize',()=>tick())
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send(200, json.dumps(_state(), ensure_ascii=False))
        elif path.startswith("/img/"):
            fp = (ANGLES / path[len("/img/"):]).resolve()
            if fp.is_file() and ANGLES.resolve() in fp.parents and fp.suffix == ".png":
                self._send(200, fp.read_bytes(), "image/png")
            else:
                self._send(404, b"not found", "text/plain")
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
