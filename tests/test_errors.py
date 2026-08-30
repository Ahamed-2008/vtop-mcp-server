"""Error-model tests: stable codes and safe MCP payloads."""

from __future__ import annotations

import pytest

from vtop_mcp.errors import (
    AuthenticationRequiredError,
    LoginFailedError,
    SessionExpiredError,
    VTopError,
)


@pytest.mark.parametrize(
    "exc, code",
    [
        (VTopError("x"), "VTOP_ERROR"),
        (AuthenticationRequiredError(), "AUTHENTICATION_REQUIRED"),
        (SessionExpiredError(), "SESSION_EXPIRED"),
        (LoginFailedError("nope"), "LOGIN_FAILED"),
    ],
)
def test_error_code_payload(exc, code):
    payload = exc.to_mcp_payload()
    assert payload == {"error": code, "message": str(exc)}


def test_custom_code():
    exc = VTopError("secret-laden message", code="INTERNAL_ERROR")
    assert exc.to_mcp_payload()["error"] == "INTERNAL_ERROR"


def test_session_expired_default_message():
    exc = SessionExpiredError()
    assert "expired" in str(exc).lower()
    assert "Authenticate again" in str(exc)


def test_authentication_required_default_message():
    exc = AuthenticationRequiredError()
    assert "Authenticate first" in str(exc)


def test_error_is_exception_subclass():
    assert issubclass(SessionExpiredError, VTopError)
    assert isinstance(SessionExpiredError(), Exception)