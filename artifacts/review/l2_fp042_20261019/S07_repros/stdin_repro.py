"""Repro: o mesmo jobs.inspect_model num filho cujo stdin é PIPE aberto (como o server
MCP stdio) vs DEVNULL. Fecha só o PID que o job devolve.
uso: stdin_repro.py <skp> <out_dir> pipe|devnull"""
import json, subprocess, sys, time
skp, out, how = sys.argv[1:4]
code = ("import json,sys; from tools.sketchup import jobs; "
        f"r=jobs.inspect_model(r'{skp}', out_dir=r'{out}', timeout_s=90); "
        "print(json.dumps({k:r.get(k) for k in ('status','pid','elapsed_s')}))")
p = subprocess.Popen([sys.executable, "-c", code],
                     stdin=subprocess.PIPE if how.startswith("pipe") else subprocess.DEVNULL,
                     stdout=subprocess.PIPE, text=True, creationflags=(subprocess.CREATE_NO_WINDOW if "nowin" in how else 0))
o, _ = p.communicate(timeout=200) if how.startswith("devnull") else (p.stdout.read(), None)
print(how, o.strip())
r = json.loads(o.strip().splitlines()[-1])
from tools.sketchup import jobs
if r.get("pid"):
    print(jobs.close(pid=int(r["pid"]), force=True, confirm=True))
