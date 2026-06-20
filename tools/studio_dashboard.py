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
    {"id": "ollama-llama",          "face": "\U0001F999", "label": "Llama"},
    {"id": "gpt-visual",            "face": "\U0001F9E0", "label": "GPT (visão)"},
]
# Topologia: PM coordena (sem LLM); Team Lead consulta os LOCAIS (código); Arquiteto consulta GPT (visão).
UMBRELLAS = [
    {"id": "pm",        "label": "PM",        "lead": "interior-pm",           "subs": ["reference-scout"]},
    {"id": "team_lead", "label": "Team Lead", "lead": "interior-orchestrator", "subs": ["ollama-deepseek", "ollama-qwen", "ollama-llama"]},
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

    # status ONLINE dos LLMs locais (Ollama) — bolinha verde mesmo idle se o modelo está up
    try:
        from tools import ollama_bridge
        avail = set(ollama_bridge.available())
        rm = ollama_bridge.ROLE_MODEL
    except Exception:  # noqa: BLE001
        avail, rm = set(), {}
    online_map = {"ollama-deepseek": rm.get("deepseek"), "ollama-qwen": rm.get("qwen"),
                  "ollama-llama": rm.get("llama")}

    def card(aid):
        rec = last.get(aid)
        base = facemap.get(aid, {"face": "•", "label": aid})
        mdl = online_map.get(aid)
        return {"id": aid, "face": base["face"], "label": base["label"],
                "status": rec["status"] if rec else "idle",
                "message": rec["message"] if rec else "—",
                "ts": rec.get("ts") if rec else None,
                "online": bool(mdl and mdl in avail)}

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
.bub{max-width:82%;padding:5px 9px;border-radius:11px;margin:4px 0;font-size:11.5px;word-break:break-word}
.bub.me{background:#1f3a4d;margin-left:auto;border-bottom-right-radius:3px}
.bub.them{background:#1d2026;border:1px solid var(--bd);margin-right:auto;border-bottom-left-radius:3px}
.bub .bt{font-size:9px;color:var(--mut);margin-top:2px}
.send{background:var(--ok)!important;color:#0c1410!important;border:none!important;font-weight:600}.send:hover{filter:brightness(1.1)}
.critwrap{display:flex;gap:12px;align-items:flex-start;margin-bottom:8px}
.critic{width:160px;border:1px solid var(--bd);border-radius:8px;flex:none}
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
function subCard(a){const act=(a.status==='working'||a.status==='thinking'||a.online)?'act':''
 const on=a.online?'<span class=onl>online</span>':'<span class=off>offline</span>'
 return `<div class="sub s-${a.status} ${act}"><span class=face>${a.face}</span>
  <div style=flex:1><div class=nm>${a.label} ${on}</div><div class=msg>${esc(a.message)}</div></div><span class="sdot ${a.online?'on':''}"></span></div>`}
function colChat(feed,ids){const f=(feed||[]).filter(x=>ids.includes(x.agent)||(x.agent==='felipe'&&ids.includes(x.to))).slice(-8)
 return f.map(x=>{const me=x.agent==='felipe'
  return `<div class="bub ${me?'me':'them'}"><div class=btxt>${esc(x.message)}</div><div class=bt>${me?'você':'🤖 agente'} · ${hhmm(x.ts)}</div></div>`}).join('')||'<span class=mut>sem conversa — pergunta abaixo ⬇</span>'}
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
let LEADOF={};const leadOf=(u)=>LEADOF[u]
async function curate(slug,action){await fetch('/api/curate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slug,action})});tick()}
function flagErr(){const a=document.getElementById('flagag').value,m=document.getElementById('flagmsg').value;if(!m)return
 fetch('/api/flag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent:a,message:m})}).then(()=>{document.getElementById('flagmsg').value='';tick()})}
async function askAgent(agent,umb){const inp=document.getElementById('ask-'+umb),q=(inp.value||'').trim();if(!q)return
 inp.value='';inp.placeholder='perguntando ao LLM local…'
 await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent,prompt:q})});tick()}
function uploadRef(){const f=document.getElementById('upfile').files[0];if(!f)return
 const msg=document.getElementById('upmsg');msg.textContent='subindo…'
 const r=new FileReader();r.onload=async()=>{const res=await (await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name,data:r.result})})).json()
  msg.textContent=res.ok?('✓ '+res.slug):('erro: '+res.error);tick()};r.readAsDataURL(f)}
async function tick(){
 // NÃO atualizar enquanto o Felipe digita/seleciona — senão apaga o que ele tá escrevendo
 const ae=document.activeElement
 if(ae&&/^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName)&&ae.type!=='file')return
 let s;try{s=await (await fetch('/api/state')).json()}catch(e){return}
 document.getElementById('ts').textContent='atualizado '+new Date().toLocaleTimeString('pt-BR')
 const b=s.backlog,refs=s.references||{},by=refs.by_theme||{},bk=refs.by_kind||{},ag=s.agents||{umbrellas:[],feed:[],metrics:{}}
 LEADOF={};(ag.umbrellas||[]).forEach(u=>LEADOF[u.id]=u.lead.id)
 const root=document.getElementById('root');root.innerHTML=''
 // ORG (guarda-chuvas + setas + métricas)
 const cols=(ag.umbrellas||[]).map(u=>{const ids=[u.lead.id,...u.subs.map(x=>x.id)]
   return `<div class=col>${leadCard(u.lead)}<div class=subs>${u.subs.map(subCard).join('')}</div>
    <div class=chat>${colChat(ag.feed,ids)}</div>
    <div class=askrow><input id="ask-${u.id}" onkeydown="if(event.key==='Enter')askAgent('${u.lead.id}','${u.id}')" placeholder="perguntar pro ${esc(u.lead.label)}… (Enter envia)"><button class=send onclick="askAgent('${u.lead.id}','${u.id}')">➤ enviar</button></div></div>`}).join('')
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
 root.appendChild(el(`<div class="card full"><h2>Agentes — guarda-chuvas (PM · Team Lead · Arquiteto)</h2>
  <div class=org id=org><svg class=arrows id=arrows></svg><div class=cols>${cols}</div></div></div>`))
 drawArrows(ag)
 // GRÁFICOS + marcar erro (com o render que tu critica do lado)
 const critic=(s.renders||[])[0]
 root.appendChild(el(`<div class="card full"><h2>Gráficos & erros de design</h2>
  <div class=charts>
   <div class=chartbox><h2>Chamadas por agente</h2><div class=pie><svg viewBox="0 0 120 120">${slices||'<circle cx=60 cy=60 r=46 fill=#20242b/>'}</svg><div class=legend>${leg||'<span class=mut>—</span>'}</div></div></div>
   <div class=chartbox><h2>Erros — o que TU não curtiu (vira lição)</h2>
    <div class=critwrap>${critic?`<img class=critic src="/img/${encodeURIComponent(critic.name)}" title="${esc(critic.name)}">`:''}
     <div style=flex:1>${ebars}</div></div>
    <div class=flagrow><select id=flagag>${flagopts}</select>
     <input id=flagmsg onkeydown="if(event.key==='Enter')flagErr()" placeholder="ex.: parede muito escura… (Enter envia)"><button class=send onclick=flagErr()>marcar erro</button></div></div>
  </div></div>`))
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
 const inb=(s.inbox||[]).map(i=>{const st=i.status||'pending';return `<tr><td>${esc(i.slug)}</td><td>${i.theme||'-'}</td><td>${st}</td>
   <td>${(st==='pending'||st==='uploaded')?`<button onclick="curate('${esc(i.slug)}','approve')">✓</button> <button onclick="curate('${esc(i.slug)}','reject')">✕</button>`:''}</td></tr>`}).join('')
 const thumbs=(s.inbox||[]).filter(i=>i.local_path).map(i=>`<div class=thumb><img loading=lazy src="/inbox-img/${encodeURIComponent(i.local_path.split('/').pop())}"><div class=cap>${esc(i.slug)}<div class=t>${i.status||'pending'}</div></div></div>`).join('')
 root.appendChild(el(`<div class="card full"><h2>Curadoria — inbox de referência <span class=mut>(sobe imagem + aprova/rejeita — sem Claude)</span></h2>
  <div class=uprow><input type=file id=upfile accept="image/*"><button onclick=uploadRef()>⬆ subir referência</button> <span class=mut id=upmsg></span></div>
  ${thumbs?`<div class=grid style="margin:10px 0">${thumbs}</div>`:''}
  <table><tr><th>slug</th><th>tema</th><th>status</th><th>ação</th></tr>${inb||'<tr><td colspan=4 class=mut>fila vazia — sobe uma referência acima</td></tr>'}</table></div>`))
 // RENDERS
 const rr=(s.renders||[]).slice(0,24).map(r=>`<div class=thumb><img loading=lazy src="/img/${encodeURIComponent(r.name)}">
   <div class=cap>${esc(r.name.replace('.png',''))}<div class=t>${r.theme} · ${r.sub} · ${r.kb}KB</div></div></div>`).join('')
 root.appendChild(el(`<div class="card full"><h2>Renders (${(s.renders||[]).length}) — mais novos primeiro</h2>
  <div class=grid>${rr||'<span class=mut>sem renders</span>'}</div></div>`))
}
tick();setInterval(tick,5000);window.addEventListener('resize',()=>tick())
</script></body></html>"""


def _curate(slug, action):
    """Felipe aprova/rejeita um candidato do inbox — grava direto no INBOX.json (sem Claude)."""
    if not INBOX.exists() or not slug:
        return {"ok": False}
    data = json.loads(INBOX.read_text("utf-8"))
    for it in data.get("items", []):
        if it.get("slug") == slug:
            it["status"] = "approved" if action == "approve" else "rejected"
    INBOX.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return {"ok": True, "slug": slug, "action": action}


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
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


AGENT_ROLE = {"interior-designer": "designer", "interior-orchestrator": "coder",
              "interior-pm": "llama", "ollama-deepseek": "deepseek",
              "ollama-qwen": "qwen", "ollama-llama": "llama", "gpt-visual": "vision"}


def _ask(agent, prompt, image=None):
    """Felipe/studio pergunta a um agente -> roteia pro LLM LOCAL via Ollama, SEM Claude (peão local)."""
    agent = agent or "interior-designer"
    try:
        from tools import ollama_bridge, studio_log
        role = AGENT_ROLE.get(agent, "llama")
        studio_log.post("felipe", "working", prompt or "", to=agent)   # bolha do Felipe (direita)
        r = ollama_bridge.ask(role, prompt or "", image=image)
        resp = (r.get("response") or r.get("error") or "")[:600]
        studio_log.post(agent, "done" if r.get("ok") else "error", resp)  # bolha do agente (esquerda)
        return {"ok": r.get("ok", False), "agent": agent, "model": r.get("model"), "response": resp}
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
