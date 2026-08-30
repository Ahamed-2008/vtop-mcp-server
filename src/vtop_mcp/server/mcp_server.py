"""MCP transport → MCP server wiring.

A low-level MCP ``Server`` registers the tool list and the call-tool handler
via the constructor's ``on_list_tools`` / ``on_call_tool`` hooks (mcp SDK >=
1.27). Transport (stdio) is kept separate from business logic so another
transport (streamable HTTP/WebSocket) can be added without touching the VTOP
layer.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
)

from ..logging_setup import app_logger, get_logger
from ..metrics import Metrics
from ..services import AcademicService
from ..vtop.auth import AuthManager
from .tools import ToolSpec, build_tools

log = get_logger("server.mcp")

_MCP_INVALID_PARAMS = -32602


class VTopMcpServer:
    """Wraps an MCP :class:`Server` with the VTOP tool set."""

    def __init__(
        self,
        service: AcademicService,
        auth: AuthManager,
        metrics: Metrics,
        *,
        tool_specs: Optional[list[ToolSpec]] = None,
    ) -> None:
        self._service = service
        self._auth = auth
        self._metrics = metrics
        self._specs = tool_specs or build_tools(service, auth, metrics)
        self._tools = {s.name: s for s in self._specs}
        self._server = Server(
            "vtop-mcp",
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

    async def _list_tools(self, ctx, params: Optional[PaginatedRequestParams]) -> ListToolsResult:
        return ListToolsResult(tools=[s.to_mcp_tool() for s in self._specs])

    async def _call_tool(self, ctx, params: CallToolRequestParams) -> CallToolResult:
        spec = self._tools.get(params.name)
        if spec is None:
            from mcp.shared.exceptions import MCPError

            raise MCPError(
                code=_MCP_INVALID_PARAMS,
                message=f"Unknown tool: {params.name}",
                data={"error": "UNKNOWN_TOOL"},
            )
        content = await spec.handler()
        return CallToolResult(content=content)

    async def run_stdio(self) -> None:
        """Serve over stdio until the client disconnects."""
        app_logger().info("vtop-mcp ready (stdio). %d tools registered.", len(self._specs))
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream, write_stream, self._server.create_initialization_options()
            )


async def run_stdio_session(service: AcademicService, auth: AuthManager, metrics: Metrics) -> None:
    server = VTopMcpServer(service, auth, metrics)
    await server.run_stdio()


__all__ = ["VTopMcpServer", "run_stdio_session"]