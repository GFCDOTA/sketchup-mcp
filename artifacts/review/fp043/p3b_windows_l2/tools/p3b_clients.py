"""P3b-01: Job Object do servidor MCP com cliente Python e cliente Node + efeito de fechar o cliente sobre um SketchUp aberto.
uso (cwd = repo): p3b_clients.py <saida.json> <modelo.skp>"""
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path.cwd().resolve()
OUT = Path(sys.argv[1]).resolve()
SKP = Path(sys.argv[2]).resolve()
NODE_CLIENT = Path(__file__).with_name("node_client.mjs")
PY = sys.executable


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    return f'"{pid}"' in out


def kill_own(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)       # PID que ESTE teste abriu


async def python_client() -> dict:
    params = StdioServerParameters(command=PY, args=["-m", "tools.mcp_server.server"], cwd=str(REPO),
                                   env={**os.environ, "PYTHONPATH": str(REPO), "PT_TO_M": "0.0259"})
    out = {"client": "python-mcp", "python": sys.version.split()[0]}
    t0 = time.time()
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out["connect_ms"] = round((time.time() - t0) * 1000)
            tools = [t.name for t in (await s.list_tools()).tools]
            out["tool_count"], out["tools"] = len(tools), tools
            st = json.loads((await s.call_tool("su_status", {})).content[0].text)
            out["su_status"] = {k: st.get(k) for k in ("server_job", "instances", "mode_default", "proof_state")}
            res = await s.call_tool("su_open", {"skp_path": str(SKP)}, read_timeout_seconds=timedelta(seconds=120))
            r2 = json.loads(res.content[0].text)
            out["su_open"] = {"status": r2.get("status"), "pid": r2.get("pid"), "reason": r2.get("reason")}
    return out                                          # sair do `async with` = fechar o cliente (e o servidor)


def node_client(action: str, skp: Path | None = None) -> dict:
    cmd = ["node", str(NODE_CLIENT), str(REPO), action] + ([str(skp)] if skp else [])
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except Exception:
        return {"client": "node", "error": done.stdout[-500:] + done.stderr[-500:]}


def survive(pid: int | None, label: str) -> dict:
    if not pid:
        return {"label": label, "pid": pid, "note": "sem PID"}
    time.sleep(4)
    a = alive(pid)
    row = {"label": label, "pid": pid, "alive_4s_after_client_closed": a}
    if a:
        kill_own(pid)
        time.sleep(2)
        row["cleanup_closed_by_pid"] = not alive(pid)
    return row


results = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "cases": []}
before = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq SketchUp.exe"], capture_output=True, text=True).stdout
results["sketchup_instances_before"] = before.count("SketchUp.exe")
py_res = asyncio.run(python_client())
results["cases"].append(py_res)
results["python_survival"] = survive((py_res.get("su_open") or {}).get("pid"), "python client closed")
node_status = node_client("status")
results["cases"].append(node_status)
node_open = node_client("open", SKP)
results["cases"].append(node_open)
results["node_survival"] = survive((node_open.get("su_open") or {}).get("pid"), "node client closed")
OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: results[k] for k in ("python_survival", "node_survival")}), flush=True)
for c in results["cases"]:
    print(c.get("client"), "tools", c.get("tool_count"), "job", (c.get("su_status") or {}).get("server_job"), flush=True)
