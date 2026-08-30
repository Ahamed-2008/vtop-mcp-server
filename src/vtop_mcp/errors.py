"""Explicit, layered exception types for the VTOP MCP server.

Every error is marked with a stable :attr:`code` that is safe to surface to an
MCP client. Error messages must NEVER contain secrets (passwords, cookies,
CSRF tokens, authorization headers, authorizedID, or raw VTOP HTML).
"""

from __future__ import annotations

from typing import Optional


class VTopError(Exception):
    """Base class for all errors raised by the VTOP integration."""

    code = "VTOP_ERROR"

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code

    def to_mcp_payload(self) -> dict[str, str]:
        """Safe, client-facing representation.

        ``message`` must already be free of secrets — callers are responsible
        for constructing it that way.
        """
        return {"error": self.code, "message": str(self)}


class InvalidConfigurationError(VTopError):
    """The server or session configuration is malformed or missing."""

    code = "INVALID_CONFIGURATION"


class AuthenticationRequiredError(VTopError):
    """A valid authenticated VTOP session is required but absent."""

    code = "AUTHENTICATION_REQUIRED"

    def __init__(self, message: str = "A valid VTOP session is required. Authenticate first.") -> None:
        super().__init__(message)


class SessionExpiredError(VTopError):
    """The VTOP session was valid once but has now expired on the server side."""

    code = "SESSION_EXPIRED"

    def __init__(self, message: str = "The VTOP session has expired. Authenticate again.") -> None:
        super().__init__(message)


class CaptchaRequiredError(VTopError):
    """VTOP requires the user to manually solve the CAPTCHA."""

    code = "CAPTCHA_REQUIRED"


class LoginFailedError(VTopError):
    """VTOP rejected the login credentials or CAPTCHA."""

    code = "LOGIN_FAILED"


class CSRFError(VTopError):
    """A CSRF token is missing, invalid, or was rejected by VTOP."""

    code = "CSRF_ERROR"


class AuthorizationIDError(VTopError):
    """The authorizedID bound to the session does not match VTOP's identity."""

    code = "AUTHORIZATION_ID_MISMATCH"


class VTOPUnavailableError(VTopError):
    """VTOP could not be reached or returned an unserviceable status."""

    code = "VTOP_UNAVAILABLE"


class VTOPTimeoutError(VTopError):
    """A VTOP request exceeded its configured timeout."""

    code = "VTOP_TIMEOUT"


class VTOPParseError(VTopError):
    """A VTOP response could not be parsed into the expected structured model."""

    code = "VTOP_PARSE_ERROR"


class VTOPResponseError(VTopError):
    """VTOP returned an unexpected or invalid response (status/structure)."""

    code = "VTOP_RESPONSE_ERROR"


class RateLimitError(VTopError):
    """The client-side request budget was exceeded."""

    code = "RATE_LIMITED"


class SessionConcurrencyError(VTopError):
    """A concurrent authentication attempt was already in progress."""

    code = "SESSION_CONCURRENCY"


__all__ = [
    "VTopError",
    "InvalidConfigurationError",
    "AuthenticationRequiredError",
    "SessionExpiredError",
    "CaptchaRequiredError",
    "LoginFailedError",
    "CSRFError",
    "AuthorizationIDError",
    "VTOPUnavailableError",
    "VTOPTimeoutError",
    "VTOPParseError",
    "VTOPResponseError",
    "RateLimitError",
    "SessionConcurrencyError",
]