from __future__ import annotations

import asyncio
import json
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import __version__
from .tools import ExtractError, extract_plan

server: Server = Server("sketchup-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="extract_plan",
            description=(
                "Run the floor-plan extraction pipeline on a PDF or SVG. "
                "Returns the full ObservedModel JSON (walls, junctions, rooms, "
                "openings, scores) plus paths to debug artifacts the pipeline "
                "wrote to disk."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Path to a .pdf or .svg input. Absolute or relative to CWD.",
                    },
                    "out_dir": {
                        "type": "string",
                        "description": "Optional output dir. Default: runs/<input stem>/.",
                    },
                },
                "required": ["pdf_path"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    if name != "extract_plan":
        raise ValueError(f"Unknown tool: {name}")

    args = arguments or {}
    try:
        result = await extract_plan(**args)
    except ExtractError as exc:
        return [types.TextContent(type="text", text=json.dumps({"error": str(exc)}))]
    except TypeError as exc:
        return [
            types.TextContent(
                type="text",
                text=json.dumps({"error": f"invalid arguments: {exc}"}),
            )
        ]

    return [
        types.TextContent(type="text", text=json.dumps(result, default=str, indent=2))
    ]


async def _run() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sketchup-mcp",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> int:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"sketchup-mcp-server fatal: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
