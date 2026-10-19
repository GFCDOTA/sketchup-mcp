"""Chama UMA tool do servidor MCP real (tools.mcp_server.server) pelo transporte stdio
— processo novo por chamada, env (PT_TO_M) definido ANTES de subir o server.
uso: mcp_call.py <out.json> <tool> '<json args>'"""
import asyncio, json, os, sys
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    out, tool, args = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    params = StdioServerParameters(command=sys.executable, args=(["-c", "import faulthandler,os,runpy; faulthandler.dump_traceback_later(int(os.environ['MCP_FH']), repeat=True, file=open(os.environ['MCP_FH_FILE'],'w')); runpy.run_module('tools.mcp_server.server', run_name='__main__')"] if os.environ.get("MCP_FH") else ["-m", "tools.mcp_server.server"]),
                                   cwd=".", env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            res = await s.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=900))
            txt = res.content[0].text if res.content else ""
            try:
                data = json.loads(txt)
            except ValueError:
                data = {"_raw": txt}
            rec = {"transport": "stdio", "tool": tool, "args": args, "is_error": res.isError,
                   "n_tools": len(names), "server_env_PT_TO_M": os.environ.get("PT_TO_M"), "result": data}
            json.dump(rec, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            short = {k: v for k, v in data.items() if k not in ("result", "nodes", "rooms", "log", "build", "gates")} if isinstance(data, dict) else data
            sys.stdout.buffer.write(json.dumps({"is_error": res.isError, "n_tools": len(names), **short}, ensure_ascii=False, default=str)[:2500].encode("utf-8") + b"\n")

asyncio.run(main())
