import json, sys
from tools.sketchup import jobs
for f in sys.argv[1:]:
    d = json.load(open(f, encoding="utf-8"))
    pid = d.get("pid") or (d.get("build") or {}).get("pid")
    print(f, pid, jobs.close(pid=int(pid), force=True, confirm=True) if pid else "no pid")
