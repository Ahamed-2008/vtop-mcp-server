"""VTOP MCP server — a secure, structured, read-only AI interface to a
student's own VIT VTOP account.

Layered architecture: MCP client → MCP tool layer → VTOP service layer →
VTOP HTTP client → VTOP web endpoints.
"""

__version__ = "0.1.0"

from .errors import (  # noqa: F401
    AuthenticationRequiredError,
    AuthorizationIDError,
    CaptchaRequiredError,
    CSRFError,
    InvalidConfigurationError,
    LoginFailedError,
    RateLimitError,
    SessionConcurrencyError,
    SessionExpiredError,
    VTopError,
    VTOPParseError,
    VTOPResponseError,
    VTOPTimeoutError,
    VTOPUnavailableError,
)

__all__ = ["__version__"]