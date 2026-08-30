"""Authenticated session representation and secure local persistence.

A :class:`Session` holds the state needed to talk to VTOP on behalf of the
authenticated student: the server-side cookie jar, the dynamic CSRF token,
and the ``authorizedID`` bound to the session.

Security notes
--------------
* Only sessions for the *authenticated student's own* VTOP account are ever
  created; ``authorized_id`` cannot be overridden by callers.
* Persistence writes ownership-restricted files (``0600``) and the JSON is
  never committed (see ``.gitignore``). The default location is documented in
  the README. If you do not want on-disk persistence, disable it and keep the
  session in memory only.
* Cookies, CSRF tokens, and authorizedID are secrets: they are never logged.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any, Optional

import httpx

from ..errors import InvalidConfigurationError, SessionExpiredError
from ..redaction import Redactor

_MAX_AGE_SECONDS = 60 * 60 * 6  # hard ceiling for a persisted session


@dataclass
class Session:
    """In-memory authenticated VTOP session."""

    csrf_token: str
    authorized_id: str
    username: str = ""
    cookies: list[dict[str, Any]] = field(default_factory=list)
    established_at: float = field(default_factory=time.time)

    # -- lifecycle -----------------------------------------------------------
    @property
    def age_seconds(self) -> float:
        return time.time() - self.established_at

    def is_fresh(self, ttl: float) -> bool:
        """True when this locally-stored session is still inside its TTL."""
        return 0 < self.age_seconds < ttl

    def mark_expired(self) -> None:
        """Force-expire this session (used when VTOP rejects it)."""
        self.established_at = time.time() - (_MAX_AGE_SECONDS + 1)

    # -- mutation ------------------------------------------------------------
    def refresh_csrf(self, token: str) -> None:
        self.csrf_token = token

    def set_authorized_id(self, authorized_id: str) -> None:
        self.authorized_id = authorized_id

    # -- cookies -------------------------------------------------------------
    def update_cookies(self, client: httpx.AsyncClient) -> None:
        """Snapshot cookies from an httpx client into this session."""
        self.cookies = _serialize_cookies(client.cookies)

    def apply_to(self, client: httpx.AsyncClient) -> None:
        """Apply this session's cookies to an httpx client."""
        client.cookies.clear()
        for item in self.cookies:
            try:
                client.cookies.set(
                    item["name"],
                    item["value"],
                    domain=item.get("domain"),
                    path=item.get("path"),
                )
            except Exception:  # pragma: no cover - ignore individual cookie quirks
                continue

    # -- serialization -------------------------------------------------------
    def to_dict(self, redactor: Optional[Redactor] = None) -> dict[str, Any]:
        payload = {
            "version": 1,
            "csrf_token": self.csrf_token,
            "authorized_id": self.authorized_id,
            "username": self.username,
            "cookies": self.cookies,
            "established_at": self.established_at,
        }
        if redactor is not None:
            # Keep keys but mask every secret value (used for debugging only).
            payload["csrf_token"] = redactor.placeholder
            payload["authorized_id"] = redactor.placeholder
            payload["username"] = redactor.placeholder
            payload["cookies"] = [
                {**c, "value": redactor.placeholder} for c in self.cookies
            ]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        if data.get("version") != 1:
            raise InvalidConfigurationError("Unsupported session format version.")
        csrf = data.get("csrf_token")
        authorized_id = data.get("authorized_id")
        if not csrf or not authorized_id:
            raise InvalidConfigurationError("Stored session is missing csrf_token or authorized_id.")
        if data.get("established_at", 0) <= 0:
            raise InvalidConfigurationError("Stored session has no establishment timestamp.")
        return cls(
            csrf_token=csrf,
            authorized_id=authorized_id,
            username=data.get("username", ""),
            cookies=data.get("cookies") or [],
            established_at=float(data["established_at"]),
        )

    # -- file persistence ----------------------------------------------------
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover
            pass

    @classmethod
    def load(cls, path: Path) -> Optional["Session"]:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise InvalidConfigurationError(
                f"Session file at {path} is unreadable/corrupt; delete it and re-authenticate."
            )
        return cls.from_dict(data)

    def enforce_hard_max_age(self) -> None:
        """Reject persisted sessions older than a hard ceiling."""
        if self.age_seconds > _MAX_AGE_SECONDS:
            raise SessionExpiredError(
                "The stored VTOP session is too old; authenticate again with `vtop-mcp login`."
            )


def _serialize_cookies(cookies: httpx.Cookies) -> list[dict[str, Any]]:
    """Serialize an httpx cookie jar into plain JSON-safe items."""
    jar = getattr(cookies, "jar", None)  # http.cookiejar.CookieJar when present
    out: list[dict[str, Any]] = []
    if jar is not None:
        for cookie in jar:
            if isinstance(cookie, Cookie):
                out.append(
                    {
                        "name": cookie.name,
                        "value": cookie.value or "",
                        "domain": cookie.domain,
                        "path": cookie.path or "/",
                    }
                )
        return out
    # Fallback: httpx.Cookie lightweight objects.
    for cookie in cookies:
        out.append(
            {
                "name": cookie.name,
                "value": cookie.value or "",
                "domain": cookie.domain,
                "path": cookie.path or "/",
            }
        )
    return out