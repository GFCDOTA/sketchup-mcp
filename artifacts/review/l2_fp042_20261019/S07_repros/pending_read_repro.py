"""Repro: filho com uma thread fazendo leitura BLOQUEANTE pendente no stdin (pipe) —
como o servidor MCP stdio — roda jobs.inspect_model. Variante 'devnull' aplica o
stdin=DEVNULL no popen do SketchUp (monkeypatch de System.popen).
uso: pending_read_repro.py <skp> <out_dir> inherit|devnull"""
import json, subprocess, sys
skp, out, how = sys.argv[1:4]
patch = ""
if how == "devnull":
    patch = ("import subprocess as sp; from tools.sketchup import process as P\n"
             "def popen(self, cmd, env=None):\n"
             "    return sp.Popen(cmd, env=env, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=sp.DEVNULL,"
             " creationflags=getattr(sp,'DETACHED_PROCESS',0), close_fds=True)\n"
             "P.System.popen = popen\n")
code = (patch + "import json,sys,threading\n"
        "threading.Thread(target=lambda: sys.stdin.buffer.read(1), daemon=True).start()\n"
        "from tools.sketchup import jobs\n"
        f"r=jobs.inspect_model(r'{skp}', out_dir=r'{out}', timeout_s=60)\n"
        "print(json.dumps({k:r.get(k) for k in ('status','pid','elapsed_s')}), flush=True)\n")
p = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
o = p.stdout.readline()
print(how, o.strip())
r = json.loads(o)
from tools.sketchup import jobs
if r.get("pid") and r["pid"] in [x["pid"] for x in jobs.status()["instances"]]:
    print(jobs.close(pid=int(r["pid"]), force=True, confirm=True))
p.stdin.close(); p.wait(timeout=30)
