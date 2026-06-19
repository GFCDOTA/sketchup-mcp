"""Prova end-to-end: sobe o servidor via stdio (como o Claude Code faz) e
faz o handshake MCP real — initialize + tools/list + call_tool.

Roda: python -m tools.mcp_server.stdio_check
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tools.mcp_server.server"],
        cwd=".",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(t.name for t in listed.tools)
            print("tools via stdio:", names)
            assert len(names) >= 9, names

            res = await session.call_tool("list_capabilities", {})
            txt = res.content[0].text if res.content else ""
            print("call_tool(list_capabilities) ok:", '"slice"' in txt or "slice" in txt)

            res2 = await session.call_tool(
                "furniture_class_derive", {"kind": "sofa", "seats": 3, "archetype": "lounge"}
            )
            txt2 = res2.content[0].text if res2.content else ""
            print("call_tool(furniture_class_derive sofa) ok:", '"gate"' in txt2)
    print("STDIO HANDSHAKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
