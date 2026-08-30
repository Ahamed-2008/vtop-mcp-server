"""Tool-layer tests: registration, schemas, and error mapping."""

from __future__ import annotations

import json

import pytest

from mock_vtop import MOCK_CAPTCHA, MOCK_PASSWORD, MOCK_USERNAME
from vtop_mcp.errors import AuthenticationRequiredError, LoginFailedError, VTopError
from vtop_mcp.server.tools import _run_tool, _to_mcp_error, build_tools


def test_build_tools_registers_expected_set(auth, service, metrics):
    specs = build_tools(service, auth, metrics)
    names = {s.name for s in specs}
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


def test_tools_are_no_args_read_only(auth, service, metrics):
    specs = build_tools(service, auth, metrics)
    for spec in specs:
        tool = spec.to_mcp_tool()
        assert tool.input_schema["additionalProperties"] is False
        assert tool.input_schema["properties"] == {}


async def test_unauthenticated_tool_returns_mcp_error(auth, service, metrics):
    specs = build_tools(service, auth, metrics)
    spec = next(s for s in specs if s.name == "get_cgpa")

    with pytest.raises(Exception) as excinfo:
        await spec.handler()
    payload = excinfo.value.error.data if hasattr(excinfo.value, "error") else None
    assert payload is not None
    assert payload["error"] == "AUTHENTICATION_REQUIRED"


async def test_tool_success_returns_json_content(auth, service, metrics):
    await auth.login(MOCK_USERNAME, MOCK_PASSWORD, MOCK_CAPTCHA)
    content = await _run_tool("get_cgpa", metrics, service.get_cgpa())
    assert len(content) == 1
    assert content[0].type == "text"
    data = json.loads(content[0].text)
    assert data["current_cgpa"] == 8.72
    assert metrics.tool_calls["get_cgpa"] == 1


async def test_tool_error_is_mapped_cleanly(service, metrics):
    async def boom():
        raise AuthenticationRequiredError()

    with pytest.raises(Exception) as excinfo:
        await _run_tool("get_cgpa", metrics, boom())
    payload = excinfo.value.error.data if hasattr(excinfo.value, "error") else None
    assert payload == {"error": "AUTHENTICATION_REQUIRED", "message": "A valid VTOP session is required. Authenticate first."}
    assert metrics.tool_errors["get_cgpa"] == 1


async def test_unknown_error_maps_to_internal_error(service, metrics):
    async def boom():
        raise RuntimeError("db exploded")

    with pytest.raises(Exception) as excinfo:
        await _run_tool("get_cgpa", metrics, boom())
    payload = excinfo.value.error.data if hasattr(excinfo.value, "error") else None
    assert payload["error"] == "INTERNAL_ERROR"
    assert "exploded" not in payload["message"]  # internals never leaked


def test_to_mcp_error_has_stable_shape():
    from mcp.shared.exceptions import MCPError

    exc = LoginFailedError("bad captcha")
    err = _to_mcp_error(exc)
    assert isinstance(err, MCPError)
    assert err.code == -32603
    assert err.message == "bad captcha"
    assert err.data["error"] == "LOGIN_FAILED"