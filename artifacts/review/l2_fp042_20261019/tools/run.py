"""Helper L2: chama tools.sketchup.jobs.<verb>(**kwargs) e salva o resultado em utf-8.
uso: run.py <out_json> <verb> '<json kwargs>'"""
import json, sys
from tools.sketchup import jobs
out, verb, kw = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
r = getattr(jobs, verb)(**kw)
with open(out, "w", encoding="utf-8") as f:
    json.dump(r, f, indent=1, default=str, ensure_ascii=False)
s = json.dumps({k: v for k, v in r.items() if k != "result"}, indent=1, default=str, ensure_ascii=False)
sys.stdout.buffer.write(s[:3000].encode("utf-8") + b"\n")
