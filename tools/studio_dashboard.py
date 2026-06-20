"""studio_dashboard.py — dashboard VIVA do INTERIOR_STUDIO (:8782).

Para de andar no escuro: mostra ao vivo o que o studio está criando — renders (matriz de
variantes + heros), backlog (KITCHEN_TO_100), o que cada sessão está fazendo (git worktrees +
SESSION_COORDINATION), as referências indexadas (reference_db) e a fila de curadoria (inbox).
Servidor SEPARADO do oráculo :8765 (que é frágil). stdlib only.

Uso:  python tools/studio_dashboard.py            # sobe em http://127.0.0.1:8782/
      python tools/studio_dashboard.py --port 8782
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

# elenco fixo: nossos agentes (studio) em cima, ajudantes LLM (local/oráculo) embaixo
ROSTER = [
    {"id": "interior-orchestrator", "face": "\U0001F3AC", "label": "Orquestrador", "tier": "studio"},
    {"id": "interior-pm",           "face": "\U0001F4CB", "label": "PM",          "tier": "studio"},
    {"id": "interior-designer",     "face": "\U0001F3A8", "label": "Designer",    "tier": "studio"},
    {"id": "reference-scout",       "face": "\U0001F52D", "label": "Scout",       "tier": "studio"},
    {"id": "ollama-deepseek",       "face": "\U0001F433", "label": "DeepSeek",    "tier": "local"},
    {"id": "ollama-qwen",           "face": "\U0001F916", "label": "Qwen-coder",  "tier": "local"},
    {"id": "gpt-visual",            "face": "\U0001F9E0", "label": "GPT (visão)", "tier": "local"},
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
        by_kind = dict(con.execute(
            "SELECT kind, COUNT(*) FROM reference GROUP BY kind").fetchall())
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
        feed = studio_log.tail(30)
    except Exception:  # noqa: BLE001
        last, feed = {}, []
    roster = []
    for a in ROSTER:
        rec = last.get(a["id"])
        roster.append({**a, "status": rec["status"] if rec else "idle",
                       "message": rec["message"] if rec else "—",
                       "ts": rec.get("ts") if rec else None})
    return {"roster": roster, "feed": feed}


def _state() -> dict:
    return {"agents": _agents(), "renders": _renders(), "sessions": _sessions(),
            "backlog": _backlog(), "references": _references(), "inbox": _inbox()}


PAGE = """<!doctype html><html lang=pt-BR><head><meta charset=utf-8>
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
.tier{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;margin:4px 0 7px}
.bots{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-bottom:12px}
.bot{display:flex;gap:10px;align-items:flex-start;background:#13151a;border:1px solid var(--bd);border-radius:10px;padding:9px 11px}
.bot .face{font-size:26px;line-height:1;filter:grayscale(.5);opacity:.6}
.bot.act .face{filter:none;opacity:1}
.bot .lbl{font-weight:600;display:flex;align-items:center;gap:6px}
.bot .msg{color:var(--mut);font-size:12px;margin-top:2px;max-height:34px;overflow:hidden}
.sdot{width:8px;height:8px;border-radius:50%;background:#5a606b;display:inline-block}
.s-working .sdot,.s-thinking .sdot{background:var(--ok);box-shadow:0 0 7px var(--ok);animation:pulse 1.1s infinite}
.s-done .sdot{background:var(--blu)}.s-blocked .sdot,.s-error .sdot{background:var(--red)}.s-waiting .sdot{background:var(--warn)}
.stag{font-size:10.5px;color:var(--mut)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.feed{background:#0c0d10;border:1px solid var(--bd);border-radius:8px;padding:8px 10px;max-height:150px;overflow-y:auto;font-size:12px}
.feed .ln{padding:2px 0;border-bottom:1px solid #181a1f}.feed .who{color:var(--fg)}.feed .t{color:var(--mut);font-size:10.5px;float:right}
</style></head><body>
<header><span class=hdot></span><h1>INTERIOR STUDIO</h1><span class=mut id=ts>carregando…</span>
<span class=mut style=margin-left:auto>auto-refresh 6s · :8782 (separado do oráculo :8765)</span></header>
<div class=wrap id=root></div>
<script>
const el=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstChild}
const esc=(t)=>(t||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))
const hhmm=(ts)=>ts?new Date(ts*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):''
function botCard(a){const act=(a.status==='working'||a.status==='thinking')?'act':''
 return `<div class="bot ${act} s-${a.status}"><div class=face>${a.face}</div>
  <div style=flex:1><div class=lbl>${a.label} <span class=sdot></span> <span class=stag>${a.status}</span></div>
  <div class=msg>${esc(a.message)}</div></div></div>`}
async function tick(){
 let s;try{s=await (await fetch('/api/state')).json()}catch(e){return}
 document.getElementById('ts').textContent='atualizado '+new Date().toLocaleTimeString('pt-BR')
 const b=s.backlog, refs=s.references||{}, by=refs.by_theme||{}, bk=refs.by_kind||{}, ag=s.agents||{roster:[],feed:[]}
 const root=document.getElementById('root');root.innerHTML=''
 // AGENTES (topo, full): nossos + ajudantes locais + feed chat
 const faces={};(ag.roster||[]).forEach(a=>faces[a.id]=a.face)
 const studio=(ag.roster||[]).filter(a=>a.tier==='studio').map(botCard).join('')
 const local=(ag.roster||[]).filter(a=>a.tier==='local').map(botCard).join('')
 const feed=(ag.feed||[]).map(f=>`<div class=ln><span class=t>${hhmm(f.ts)}</span><span class=who>${faces[f.agent]||'•'} ${esc(f.agent)}</span> <span class=mut>${esc(f.message)}</span></div>`).join('')
 root.appendChild(el(`<div class="card full"><h2>Agentes — quem está trabalhando agora</h2>
  <div class=tier>Studio</div><div class=bots>${studio}</div>
  <div class=tier>Ajudantes (LLM local / oráculo)</div><div class=bots>${local}</div>
  <div class=feed id=feed>${feed||'<span class=mut>sem atividade ainda</span>'}</div></div>`))
 const fd=document.getElementById('feed');if(fd)fd.scrollTop=fd.scrollHeight
 // BACKLOG
 const pct=b.total?Math.round(100*b.done/b.total):0
 root.appendChild(el(`<div class=card><h2>Backlog — KITCHEN_TO_100</h2>
  <span class=k><b>${b.total}</b> <span class=mut>microtarefas</span></span>
  <span class=k><b>${b.pele}</b> <span class=mut>PELE</span></span>
  <span class=k><b>${b.geo}</b> <span class=mut>GEO (espera Felipe)</span></span>
  <span class=k><b style=color:var(--ok)>${b.done}</b> <span class=mut>done</span></span>
  <div class=bar><i style=width:${pct}%></i></div></div>`))
 // SESSÕES
 const cl=(s.sessions.claims||[]).map(c=>`<tr><td>${c.mt}</td><td>${c.owner}</td><td>${c.status}</td></tr>`).join('')
 const wt=(s.sessions.worktrees||[]).map(w=>`<div class=mut>${esc(w)}</div>`).join('')
 root.appendChild(el(`<div class=card><h2>Sessões / coordenação</h2>
  <table><tr><th>MT</th><th>dono</th><th>status</th></tr>${cl||'<tr><td colspan=3 class=mut>sem claims</td></tr>'}</table>
  <div style=margin-top:8px>${wt}</div></div>`))
 // REFERÊNCIAS
 const themes=Object.entries(by).map(([t,n])=>`<tr><td>${t}</td><td>${n}</td></tr>`).join('')
 root.appendChild(el(`<div class=card><h2>Banco de referências (reference_db)</h2>
  <div class=mut style=margin-bottom:8px>${Object.entries(bk).map(([k,n])=>`<span class=pill>${k}: ${n}</span>`).join(' ')||refs.error||''}</div>
  <table><tr><th>tema</th><th>refs</th></tr>${themes}</table></div>`))
 // INBOX curadoria
 const inb=(s.inbox||[]).map(i=>`<tr><td>${esc(i.slug)}</td><td>${i.theme||'-'}</td><td>${i.status||'pending'}</td></tr>`).join('')
 root.appendChild(el(`<div class=card><h2>Curadoria — inbox de referência</h2>
  <table><tr><th>slug</th><th>tema</th><th>status</th></tr>${inb||'<tr><td colspan=3 class=mut>fila vazia — o reference-scout popula aqui</td></tr>'}</table></div>`))
 // RENDERS
 const rr=(s.renders||[]).slice(0,24).map(r=>`<div class=thumb><img loading=lazy src="/img/${encodeURIComponent(r.name)}">
   <div class=cap>${esc(r.name.replace('.png',''))}<div class=t>${r.theme} · ${r.sub} · ${r.kb}KB</div></div></div>`).join('')
 root.appendChild(el(`<div class="card full"><h2>Renders (${(s.renders||[]).length}) — mais novos primeiro</h2>
  <div class=grid>${rr||'<span class=mut>sem renders</span>'}</div></div>`))
}
tick();setInterval(tick,6000)
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso
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
            name = path[len("/img/"):]
            fp = (ANGLES / name).resolve()
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
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"INTERIOR STUDIO dashboard -> http://127.0.0.1:{a.port}/  (Ctrl+C p/ parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
