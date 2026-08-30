"""Manually probe the vtop-mcp server over stdio.

Spawns `vtop-mcp serve` (the real MCP server) and calls a list of tools,
printing each JSON result. Useful to verify the server works end-to-end
against a persisted, live-VTOP session (run `vtop-mcp login` first).

Usage (from the repository root so the default session path resolves):

    .venv/bin/python scripts/mcp_probe.py --tools get_cgpa get_session_status
    .venv/bin/python scripts/mcp_probe.py            # default tool set
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
VTOP_MCP = ROOT / ".venv" / "bin" / "vtop-mcp"

DEFAULT_TOOLS = (
    "get_session_status",
    "get_cgpa",
    "get_current_courses",
    "get_academic_summary",
    "get_events",
    "get_assignments",
    "get_feedback",
    "get_proctor_message",
)


async def probe(tool_names: tuple[str, ...]) -> None:
    server = StdioServerParameters(
        command=str(VTOP_MCP),
        args=["serve"],
        cwd=str(ROOT),
        env=None,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            available = {t.name: t for t in (await session.list_tools()).tools}
            print(f"tools available ({len(available)}): {', '.join(sorted(available))}")
            for name in tool_names:
                if name not in available:
                    print(f"\n### {name}: NOT AVAILABLE ###")
                    continue
                result = await session.call_tool(name, {})
                print(f"\n### {name} ###")
                for chunk in result.content:
                    if getattr(chunk, "type", "") == "text":
                        print(chunk.text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe vtop-mcp over MCP stdio.")
    parser.add_argument(
        "--tools",
        nargs="+",
        default=list(DEFAULT_TOOLS),
        help="Tool names to call (default: a representative set).",
    )
    args = parser.parse_args()
    try:
        asyncio.run(probe(tuple(args.tools)))
    except Exception as exc:  # surface transport/init errors clearly
        print(f"probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())