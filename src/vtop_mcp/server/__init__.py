"""MCP server layer: transports, tools, and schemas."""

from .mcp_server import VTopMcpServer, run_stdio_session
from .schemas import AttendanceRows, SessionStatus
from .tools import ToolSpec, build_tools, tool_specs_to_mcp

__all__ = [
    "VTopMcpServer",
    "run_stdio_session",
    "AttendanceRows",
    "SessionStatus",
    "ToolSpec",
    "build_tools",
    "tool_specs_to_mcp",
]