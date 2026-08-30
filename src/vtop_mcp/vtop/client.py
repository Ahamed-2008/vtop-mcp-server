"""VTOP HTTP client.

Owns the httpx session (cookies + headers), CSRF-aware form POSTing, timeout
and transient retry handling, authentication-expiry detection, and exposes
typed-ish methods to the service layer. It knows nothing about MCP.

Security invariants:
* No credentials or CAPTCHA values are logged here.
* Authentication requests are never retried.
* ``authorizedID`` and CSRF tokens come from the bound :class:`Session`, never
  from callers.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..config import Settings
from ..errors import (
    AuthenticationRequiredError,
    CSRFError,
    LoginFailedError,
    SessionExpiredError,
    VTOPResponseError,
    VTOPTimeoutError,
    VTOPUnavailableError,
)
from ..logging_setup import get_logger
from ..metrics import Metrics, RateLimiter
from ..redaction import Redactor
from . import endpoints as ep
from .csrf import extract_content_tokens, extract_csrf_from_html
from .session import Session

log = get_logger("vtop.client")

_SESSION_EXPIRED_MARKERS = (
    "sessionExpireCheckForm",
    "/vtop/login",
    "/vtop/session/expired",
)
_LOGIN_FORM_MARKER = re.compile(r'name=["\']username["\']')

_TRANSIENT_STATUSES = (502, 503, 504, 429)


@dataclass
class LoginChallenge:
    """Data VTOP offers for the *manual* CAPTCHA step.

    ``captcha_image`` is base64-encoded image data when VTOP uses its built-in
    CAPTCHA; ``captcha_type == "recaptcha"`` when a browser would use Google
    reCAPTCHA (in that case the CLI cannot render it and instructs the user).
    """

    csrf_token: str
    captcha_type: str  # "builtin" | "recaptcha"
    captcha_image: Optional[str] = None  # base64 payload (sans data-uri prefix)
    captcha_mime: str = "image/jpeg"

    @property
    def requires_browser(self) -> bool:
        return self.captcha_type == "recaptcha"


class VTOPClient:
    """All HTTP access to VTOP. One instance per process."""

    def __init__(
        self,
        settings: Settings,
        metrics: Metrics,
        redactor: Redactor,
        rate_limiter: Optional[RateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.settings = settings
        self.metrics = metrics
        self.redactor = redactor
        self._limiter = rate_limiter or RateLimiter(settings.request_rate)
        self._login_lock = asyncio.Lock()
        self.session: Optional[Session] = None
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": settings.base_url,
            },
        )

    # ------------------------------------------------------------------ util
    async def close(self) -> None:
        await self._client.aclose()
        self.session = None

    def bind_session(self, session: Session) -> None:
        """Attach an established (or persisted) session to this client."""
        self.session = session
        session.apply_to(self._client)
        self.redactor.register(session.csrf_token, session.authorized_id, session.username)

    def _url(self, path: str) -> str:
        return self.settings.base_url + path

    @staticmethod
    def _x_timestamp() -> str:
        import email.utils

        return email.utils.formatdate(time.time(), usegmt=True)

    async def _rate_limited(self, coro):
        await self._limiter.acquire()
        return await coro

    async def _request(self, method, path: str, *, retry: bool = False, **kwargs):
        """Run one VTOP request with timeout translation + optional transient retry."""
        attempts = self.settings.retry.attempts if retry else 0
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                resp = await self._rate_limited(
                    self._client.request(method, self._url(path), **kwargs)
                )
            except httpx.TimeoutException as exc:
                self.metrics.vtop_errors["timeout"] += 1
                raise VTOPTimeoutError(f"VTOP request timed out ({path}).") from exc
            except httpx.TransportError as exc:
                self.metrics.vtop_errors["unavailable"] += 1
                if retry and attempt < attempts:
                    await self._delay_before_retry(attempt)
                    attempt += 1
                    continue
                raise VTOPUnavailableError(f"VTOP could not be reached ({type(exc).__name__}).") from exc

            duration = time.monotonic() - started
            self.metrics.record_request(path, resp.status_code, duration)
            log.debug("http %s %s -> %s (%.1fms)", method, path, resp.status_code, duration * 1000)

            if resp.status_code in _TRANSIENT_STATUSES and retry and attempt < attempts:
                await self._delay_before_retry(attempt)
                attempt += 1
                continue
            if resp.status_code >= 500 and retry and attempt < attempts:
                await self._delay_before_retry(attempt)
                attempt += 1
                continue
            return resp

    async def _delay_before_retry(self, attempt_index: int) -> None:
        delay = self.settings.retry.delay_for(attempt_index)
        log.info("transient VTOP failure; retrying in %.1fs", delay)
        await asyncio.sleep(delay)

    # ------------------------------------------------------------- auth flow
    async def initialize(self) -> LoginChallenge:
        """Run the pre-login bootstrap and return the login challenge.

        GET open/page → POST prelogin/setup (CSRF, flag=VTOP) → login page.
        Never called concurrently for the same client.
        """
        resp = await self._request("GET", self.settings.initial_url)
        html = resp.text
        csrf = extract_csrf_from_html(html, source="open page")
        log.debug("pre-login CSRF acquired")

        # The prelogin POST redirects to /vtop/login (follow_redirects=True),
        # leaving the final response on the login page.
        login_html = ""
        setup_resp = await self._request(
            "POST",
            ep.PRELOGIN_SETUP.path,
            data={"flag": "VTOP", "_csrf": csrf},
        )
        login_html = setup_resp.text
        if not login_html:
            # Redirect chain should have left us on /vtop/login; fetch directly.
            login_resp = await self._request("GET", ep.LOGIN_GET.path)
            login_html = login_resp.text

        return self._parse_login_page(login_html)

    def _parse_login_page(self, html: str) -> LoginChallenge:
        csrf = extract_csrf_from_html(html, source="login page")
        soup = BeautifulSoup(html, "lxml")

        captcha_type = "builtin"
        captcha_image: Optional[str] = None
        mime = "image/jpeg"

        # The built-in CAPTCHA is the *largest* data-:image on the login page
        # (tiny data URIs, e.g. spacer GIFs, may appear earlier in the DOM).
        best_size = 64
        for img in soup.find_all("img", src=lambda s: s and s.startswith("data:image")):
            data_uri = img.get("src") or ""
            m = re.match(r"data:([^;]+);base64,(.+)", data_uri, re.DOTALL)
            if not m:
                continue
            payload = self._strip_whitespace(m.group(2))
            if len(payload) > best_size:
                best_size = len(payload)
                captcha_image = payload
                mime = m.group(1) or mime

        if captcha_image is None:
            # Built-in CAPTCHA not embeddable → Google reCAPTCHA in a browser.
            captcha_type = "recaptcha"

        return LoginChallenge(
            csrf_token=csrf,
            captcha_type=captcha_type,
            captcha_image=captcha_image,
            captcha_mime=mime,
        )

    @staticmethod
    def _strip_whitespace(value: str) -> str:
        return "".join(value.split())

    async def submit_login(self, challenge: LoginChallenge, username: str, password: str, captcha: str) -> Session:
        """Complete a manual-CAPTCHA login and build a Session.

        ``challenge`` MUST be the login challenge whose CAPTCHA image the user
        actually solved: VTOP rotates the CSRF + CAPTCHA answer on every render
        of /vtop/login, so submitting against a freshly re-fetched challenge
        would fail (the answer would not match). POST /vtop/login → (302 chain) →
        GET /vtop/content, from which the authenticated ``_csrf`` and
        ``authorizedID`` are extracted.
        """
        login_csrf = challenge.csrf_token

        started = time.monotonic()
        resp = await self._client.post(
            self._url(ep.LOGIN_POST.path),
            data={
                "_csrf": login_csrf,
                "username": username,
                "password": password,
                "captchaStr": captcha,
            },
            headers={
                "Referer": self._url(ep.LOGIN_GET.path),
                "Origin": self.settings.base_url,
            },
        )
        duration = time.monotonic() - started
        self.metrics.record_request(ep.LOGIN_POST.path, resp.status_code, duration)

        # Landing on the authenticated content page is the success marker.
        if resp.status_code != 200:
            if resp.is_redirect:
                self.metrics.auth_failures["redirect"] += 1
                log.warning("POST /vtop/login returned redirect (mostly CAPTCHA mismatch).")
                raise LoginFailedError(self._rejection_message(resp.text))
            self.metrics.auth_failures["rejected"] += 1
            log.warning("POST /vtop/login did not return HTML (http %s).", resp.status_code)
            raise LoginFailedError("VTOP rejected the login attempt. Please try again.")

        html = resp.text
        # On a rejection VTOP re-renders the login form / error page with HTTP
        # 200 (and a fresh `var csrfValue`), so the bare `var csrfValue` check is
        # NOT proof of authentication. A username field means we are still on
        # the login page.
        if _LOGIN_FORM_MARKER.search(html):
            self.metrics.auth_failures["rejected"] += 1
            log.warning("POST /vtop/login re-rendered the login form (http 200) -- rejected.")
            raise LoginFailedError(self._rejection_message(html))

        csrf, authorized_id = extract_content_tokens(html)
        self.redactor.register(csrf, authorized_id, username)
        session = Session(
            csrf_token=csrf,
            authorized_id=authorized_id,
            username=username,
            established_at=time.time(),
        )
        session.update_cookies(self._client)
        self.bind_session(session)
        log.info("authenticated VTOP session established.")
        return session

    @staticmethod
    def _rejection_message(html: str) -> str:
        """Turn VTOP's login-error page into a clear, actionable message."""
        if not html:
            return "VTOP rejected the login (username, password, or CAPTCHA). Please try again."
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        if re.search(r"session\s+timed\s+out", text, re.I):
            return (
                "VTOP reported: the login page timed out before you submitted. "
                "Re-run `vtop-mcp login` and enter the fresh CAPTCHA promptly."
            )
        if re.search(r"invalid\s+captcha", text, re.I):
            return (
                "VTOP reported: the CAPTCHA was not accepted. Re-run `vtop-mcp login` and "
                "type the latest code exactly (single-use, small window)."
            )
        if re.search(r"invalid\s+(username|user\s*name|password|credentials)", text, re.I):
            return "VTOP reported: the username or password was rejected. Please re-check your credentials."
        return "VTOP rejected the login (username, password, or CAPTCHA). Please try again."

    def bindable(self) -> Session:
        """Return the bound session or raise AuthenticationRequiredError."""
        if self.session is None:
            raise AuthenticationRequiredError()
        return self.session

    # ------------------------------------------------------- session checks
    async def check_liveness(self) -> bool:
        """Probe the session against GET /vtop/content. Returns True if valid."""
        if self.session is None:
            return False
        try:
            resp = await self._request("GET", ep.CONTENT.path)
        except (VTOPUnavailableError, VTOPTimeoutError):
            return False
        if resp.status_code != 200:
            return self._treat_unauthorized_bool(resp, label="liveness check")
        try:
            csrf, authorized_id = extract_content_tokens(resp.text)
        except CSRFError:
            return self._treat_unauthorized_bool(resp, label="liveness check")
        if authorized_id != self.session.authorized_id:
            return self._treat_unauthorized_bool(resp, label="liveness check")
        # Refresh tokens from the live page so long-lived sessions stay valid.
        self.session.refresh_csrf(csrf)
        self.redactor.register(csrf)
        return True

    # --------------------------------------------------------- data endpoints
    async def _post_data(self, endpoint: ep.Endpoint, *, retry: bool = True) -> str:
        """POST an authenticated read-only data endpoint and return raw HTML text."""
        session = self.bindable()
        body = {
            "authorizedID": session.authorized_id,
            "_csrf": session.csrf_token,
            "x": self._x_timestamp(),
        }
        resp = await self._request(
            "POST",
            endpoint.path,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self._url(ep.CONTENT.path),
                "Origin": self.settings.base_url,
            },
            retry=retry,
        )
        if resp.status_code not in (200,):
            if self._looks_like_auth_redirect(resp):
                return self._treat_unauthorized(resp, label=endpoint.name)
            raise VTOPResponseError(
                f"VTOP returned HTTP {resp.status_code} for {endpoint.name}."
            )
        if self._looks_like_auth_redirect(resp):
            return self._treat_unauthorized(resp, label=endpoint.name)
        if not resp.text.strip():
            return ""
        return resp.text

    def _looks_like_auth_redirect(self, resp: httpx.Response) -> bool:
        path = str(getattr(resp, "url", ""))
        if "/vtop/login" in path or "session/expired" in path:
            return True
        body = resp.text or ""
        return (
            _LOGIN_FORM_MARKER.search(body)
            and "captcha" in body.lower()
            and len(body) < 60_000
            and "/vtop/login" in (body)
        )

    def _treat_unauthorized(self, resp: httpx.Response, *, label: str):
        if self.session is not None:
            self.session.mark_expired()
            self.session = None
            log.warning("VTOP session invalidated after auth rejection (%s).", label)
        self.metrics.vtop_errors["auth_rejected"] += 1
        raise SessionExpiredError()

    def _treat_unauthorized_bool(self, resp: httpx.Response, *, label: str) -> bool:
        """Variant of :meth:`_treat_unauthorized` that returns False instead of raising."""
        if self.session is not None:
            self.session.mark_expired()
            self.session = None
        log.info("VTOP session invalidated after liveness rejection (%s).", label)
        return False

    async def get_cgpa(self) -> str:
        return await self._post_data(ep.CGPA_CREDITS)

    async def get_course_details(self) -> str:
        return await self._post_data(ep.COURSE_DETAILS)

    async def get_assignments(self) -> str:
        return await self._post_data(ep.ASSIGNMENTS)

    async def get_events(self) -> str:
        return await self._post_data(ep.EVENTS)

    async def get_feedback(self) -> str:
        return await self._post_data(ep.FEEDBACKS)

    async def get_proctor_message(self) -> str:
        return await self._post_data(ep.PROCTOR_MESSAGE)