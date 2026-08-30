"""Configuration loading.

Settings are read from environment variables (and optionally a ``.env`` file).
No secret configuration belongs here — credentials are supplied interactively
by the CLI authentication flow, never through plaintext config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

from .errors import InvalidConfigurationError

DEFAULT_BASE_URL = "https://vtop.vit.ac.in"
DEFAULT_INITIAL_URL = "/vtop/open/page"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise InvalidConfigurationError(f"Environment variable {name} must be numeric, got {raw!r}")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise InvalidConfigurationError(f"Environment variable {name} must be an integer, got {raw!r}")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_log_level(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    level = raw.strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise InvalidConfigurationError(f"{name} must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL, got {raw!r}")
    return level


def _project_default_session_dir() -> Path:
    """Located relative to this source tree; overridable via config."""
    root = Path(__file__).resolve().parent.parent.parent
    return root / ".vtop-session"


@dataclass(frozen=True)
class RetrySettings:
    attempts: int = 2
    backoff_base: float = 0.5
    backoff_factor: float = 2.0
    max_total: float = 10.0
    statuses: tuple = (502, 503, 504, 429)

    def delay_for(self, attempt_index: int) -> float:
        """0-based attempt_index -> seconds to wait before retrying."""
        return min(self.backoff_base * (self.backoff_factor ** attempt_index), self.max_total)


@dataclass(frozen=True)
class Settings:
    base_url: str = DEFAULT_BASE_URL
    initial_url: str = DEFAULT_INITIAL_URL
    enable_login: bool = True
    session_path: Optional[Path] = None
    session_ttl: float = 3600.0

    timeout_connect: float = 10.0
    timeout_read: float = 30.0
    timeout_write: float = 10.0
    timeout_pool: float = 10.0

    retry: RetrySettings = field(default_factory=RetrySettings)

    cache_ttl: float = 120.0
    min_captcha_render_ttl: float = 60.0

    log_level: str = "INFO"

    request_rate: float = 2.0  # max requests per second across VTOP (approx)

    @property
    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.timeout_connect,
            read=self.timeout_read,
            write=self.timeout_write,
            pool=self.timeout_pool,
        )

    @property
    def resolved_session_path(self) -> Path:
        if self.session_path is not None:
            return self.session_path
        return _project_default_session_dir() / "session.json"

    @classmethod
    def from_env(cls, *, dotenv_path: Optional[Path] = None) -> "Settings":
        if dotenv_path is not None and dotenv_path.exists():
            load_dotenv(dotenv_path)
        else:
            load_dotenv()

        base_url = os.environ.get("VTOP_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

        initial_url = os.environ.get("VTOP_INITIAL_URL", DEFAULT_INITIAL_URL).strip()
        if not initial_url.startswith("/"):
            raise InvalidConfigurationError("VTOP_INITIAL_URL must start with '/' (path only)")

        session_env = os.environ.get("VTOP_SESSION_PATH")
        session_path = Path(session_env).expanduser() if session_env else None

        retry = RetrySettings(
            attempts=_env_int("VTOP_RETRY_ATTEMPTS", 2),
            backoff_base=_env_float("VTOP_RETRY_BACKOFF_BASE", 0.5),
        )

        return cls(
            base_url=base_url,
            initial_url=initial_url,
            enable_login=_env_bool("VTOP_ENABLE_LOGIN", True),
            session_path=session_path,
            session_ttl=_env_float("VTOP_SESSION_TTL", 3600.0),
            timeout_connect=_env_float("VTOP_TIMEOUT_CONNECT", 10.0),
            timeout_read=_env_float("VTOP_TIMEOUT_READ", 30.0),
            timeout_write=_env_float("VTOP_TIMEOUT_WRITE", 10.0),
            timeout_pool=_env_float("VTOP_TIMEOUT_POOL", 10.0),
            cache_ttl=_env_float("VTOP_CACHE_TTL", 120.0),
            log_level=_env_log_level("VTOP_LOG_LEVEL", "INFO"),
            request_rate=_env_float("VTOP_REQUEST_RATE", 2.0),
        )


__all__ = ["Settings", "RetrySettings", "InvalidConfigurationError"]