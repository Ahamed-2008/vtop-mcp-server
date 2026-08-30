"""End-to-end MCP tests: a real client session talking to the real MCP server.

Uses in-memory streams (the same ones stdio transport is built on), so no
subprocess machinery is needed while still exercising the full JSON-RPC
protocol: initialize, tools/list, tools/call — including the error payload
path for unauthenticated tools.

Every scenario runs inside a single asyncio task (``_with_mcp``) so anyio
cancel-scope enter/exit pairs never cross pytest task boundaries.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable

import anyio
import pytest

from mock_vtop import MOCK_CAPTCHA, MOCK_PASSWORD, MOCK_USERNAME
from vtop_mcp.server.mcp_server import VTopMcpServer


def _text_of(result) -> str:
    parts = []
    for content in result.content:
        if getattr(content, "type", None) == "text":
            parts.append(content.text)
    return "\n".join(parts)


async def _with_mcp(service, auth, metrics, fn: Callable[["ClientSession"], Awaitable]):
    from mcp.client.session import ClientSession

    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(8)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(8)

    server = VTopMcpServer(service, auth, metrics)
    task = asyncio.create_task(
        server._server.run(
            client_to_server_recv,
            server_to_client_send,
            server._server.create_initialization_options(),
        )
    )
    try:
        async with ClientSession(server_to_client_recv, client_to_server_send) as session:
            await session.initialize()
            return await fn(session)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, ExceptionGroup):
            await task


async def test_list_tools(service, auth, metrics):
    async def body(session):
        result = await session.list_tools()
        return {t.name for t in result.tools}

    names = await _with_mcp(service, auth, metrics, body)
    assert names == {
        "get_academic_summary",
        "get_cgpa",
        "get_current_courses",
        "get_attendance",
        "get_marks",
        "get_assignments",
        "get_events",
        "get_feedback",
        "get_proctor_message",
        "get_session_status",
    }


async def test_session_status_when_unauthenticated(service, auth, metrics):
    async def body(session):
        result = await session.call_tool("get_session_status", {})
        return _text_of(result)

    text = await _with_mcp(service, auth, metrics, body)
    assert "authenticated" in text


async def test_tool_error_payload_when_unauthenticated(service, auth, metrics):
    async def body(session):
        with pytest.raises(Exception) as excinfo:
            await session.call_tool("get_cgpa", {})
        return excinfo.value

    err = await _with_mcp(service, auth, metrics, body)
    assert err.code == -32603
    assert err.data["error"] == "AUTHENTICATION_REQUIRED"


async def test_authenticated_tool_call_roundtrip(service, auth, metrics):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)

    async def body(session):
        result = await session.call_tool("get_cgpa", {})
        return _text_of(result)

    text = await _with_mcp(service, auth, metrics, body)
    assert '"current_cgpa":8.72' in text
    assert "earned_credits" in text


async def test_academic_summary_roundtrip(service, auth, metrics):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)

    async def body(session):
        result = await session.call_tool("get_academic_summary", {})
        return _text_of(result)

    text = await _with_mcp(service, auth, metrics, body)
    assert '"semester":"FALLSEM2026-27"' in text


async def test_unknown_tool_rejected(service, auth, metrics):
    async def body(session):
        with pytest.raises(Exception) as excinfo:
            await session.call_tool("definitely_not_a_tool", {})
        return excinfo.value

    err = await _with_mcp(service, auth, metrics, body)
    assert err.code == -32602