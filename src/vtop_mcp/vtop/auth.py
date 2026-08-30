"""Session manager / authentication manager.

Responsibilities (§7): create an authenticated session, maintain cookies +
CSRF state, determine session validity, detect and handle expiration, prevent
concurrent authentication, and dispose of expired sessions securely.

The server is intentionally *never* able to re-authenticate on its own — VTOP
login requires the user to solve a CAPTCHA manually (§4). When a session is
missing or expired the manager raises ``AuthenticationRequiredError`` /
``SessionExpiredError`` and directs the operator to the ``vtop-mcp login``
bootstrap command.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..errors import AuthenticationRequiredError, SessionExpiredError
from ..logging_setup import get_logger
from ..metrics import Metrics
from ..redaction import Redactor
from .client import VTOPClient
from .session import Session

log = get_logger("vtop.auth")


class AuthManager:
    def __init__(
        self,
        client: VTOPClient,
        settings: Settings,
        metrics: Metrics,
        redactor: Redactor,
        persist_path: Optional[Path] = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._metrics = metrics
        self._redactor = redactor
        self._persist_path = persist_path or settings.resolved_session_path
        self._auth_lock = asyncio.Lock()
        self._bootstrapped = False

    # ------------------------------------------------------------- lifecycle
    async def bootstrap(self) -> None:
        """Load a persisted session (if any) and bind it, without logging in."""
        if self._bootstrapped:
            return
        async with self._auth_lock:
            if self._bootstrapped:
                return
            path = self._persist_path
            if path.exists():
                session = Session.load(path)
                session.enforce_hard_max_age()
                self._client.bind_session(session)
                log.info("Loaded persisted VTOP session (age %.0fs).", session.age_seconds)
            self._bootstrapped = True

    @property
    def session(self) -> Optional[Session]:
        return self._client.session

    @property
    def authenticated(self) -> bool:
        return self.session is not None

    def persist(self) -> None:
        if self.session is not None and self._persist_path is not None:
            self.session.save(self._persist_path)
            log.debug("Persisted session to %s", self._persist_path)

    # ------------------------------------------------------------- gating
    async def ensure_session(self, *, probe: bool = False) -> Session:
        """Return a valid authenticated session or raise.

        ``probe=True`` performs a cheap liveness GET against VTOP even when the
        locally-cached session is still fresh (used by ``get_session_status``).
        """
        await self.bootstrap()

        session = self._client.session
        if session is None:
            self._metrics.vtop_errors["no_session"] += 1
            raise AuthenticationRequiredError()
        if session.age_seconds > self._settings.session_ttl:
            probe = True

        if probe:
            alive = await self._client.check_liveness()
            if not alive:
                self._metrics.vtop_errors["session_expired"] += 1
                self._dispose()
                raise SessionExpiredError()
        return self._client.session  # type: ignore[return-value]

    async def probe(self) -> bool:
        """Liveness check without raising (used by the session-status tool)."""
        await self.bootstrap()
        if self._client.session is None:
            return False
        alive = await self._client.check_liveness()
        return alive

    def _dispose(self) -> None:
        if self._client.session is not None:
            self._client.session.mark_expired()
            self._client.session = None
        log.info("VTOP session disposed.")

    async def dispose(self) -> None:
        """Invalidate the in-memory session and remove the persisted copy."""
        async with self._auth_lock:
            self._dispose()
            path = self._persist_path
            if path is not None and path.exists():
                try:
                    path.unlink()
                    log.info("Removed persisted session file %s", path)
                except OSError:  # pragma: no cover
                    log.warning("Could not remove persisted session file %s", path)

    # ------------------------------------------------------------- login
    async def login(self, username: str, password: str, captcha: str, challenge=None) -> Session:
        """Complete the manual-CAPTCHA login and persist the session.

        ``challenge`` must be the login challenge whose CAPTCHA the user solved
        (its CSRF token is paired with that CAPTCHA). When omitted, a fresh
        challenge is fetched once and submitted immediately, so the pairing is
        never broken by re-rendering /vtop/login.
        """
        if not self._settings.enable_login:
            raise AuthenticationRequiredError("Login is disabled by configuration (VTOP_ENABLE_LOGIN=false).")

        async with self._auth_lock:
            if challenge is None:
                challenge = await self._client.initialize()
            session = await self._client.submit_login(challenge, username, password, captcha)
            self.persist()
            self._metrics.auth_failures["login"] += 1
            log.info("session established and persisted (authorizedID set).")
            return session

    async def started_login_snap(self) -> bool:
        """True when a login is underway (informational, for concurrency UX)."""
        return self._auth_lock.locked()