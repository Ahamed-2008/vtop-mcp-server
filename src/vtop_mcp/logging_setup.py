"""Logging setup.

A single redacting filter is attached to the package handler so that no log
statement can leak secrets even if a caller accidentally passes one in.

Fields never logged: passwords, CAPTCHA values, session cookies, CSRF tokens,
authorization headers, complete authenticated request bodies, and private
academic data.
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Optional

from .redaction import RedactingFormatter, RedactingFilter, Redactor

_PKG_NAME = "vtop_mcp"
_LOGGER_NAME = "vtop_mcp"

_configured = False


def configure_logging(level: str = "INFO", redactor: Optional[Redactor] = None) -> None:
    """Idempotently configure package logging with secret redaction."""
    global _configured
    if _configured:
        return
    _configured = True

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False

    if not logger.handlers:
        redactor = redactor or Redactor()
        handler = logging.StreamHandler(sys.stderr)
        handler.addFilter(RedactingFilter(redactor))
        handler.addFilter(SharedContextFilter())
        handler.setFormatter(
            RedactingFormatter(
                redactor,
                "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s",
                "%Y-%m-%dT%H:%M:%S%z",
            )
        )
        logger.addHandler(handler)


def app_logger() -> logging.Logger:
    """Top-level logger for the package (module child loggers use it via propagate)."""
    return logging.getLogger(_LOGGER_NAME)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the package namespace."""
    if name.startswith(_PKG_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_PKG_NAME}.{name}")


class SharedContextFilter(logging.Filter):
    """Fills a per-request ``correlation_id`` via :func:`ContextVars`/overridable hook."""

    def __init__(self) -> None:
        super().__init__()
        self._var = _CORRELATION_ID_VAR

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self._var.get() or "-"
        return True


# Correlation id propagation using context vars (works across async tasks).
import contextvars  # noqa: E402

_CORRELATION_ID_VAR: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


def set_correlation_id(value: str) -> None:
    _CORRELATION_ID_VAR.set(value or "-")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


__all__ = [
    "configure_logging",
    "app_logger",
    "get_logger",
    "set_correlation_id",
    "new_correlation_id",
]