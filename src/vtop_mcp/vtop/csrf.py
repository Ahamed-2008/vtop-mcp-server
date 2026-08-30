"""CSRF token management.

VTOP supplies CSRF tokens as hidden form fields / inline JavaScript variables.
Tokens are dynamic and must never be hardcoded, logged, or exposed in MCP
output. This module only extracts and validates them from VTOP responses.
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from ..errors import CSRFError

_CSRF_INPUT_RE = re.compile(r"name=[\"']_csrf[\"'][^>]*value=[\"']([^\"']+)[\"']", re.I)
_CSRF_VALUE_JS_RE = re.compile(r"var\s+csrfValue\s*=\s*[\"']([^\"']+)[\"']")
_LOGIN_ID_RE = re.compile(r"var\s+id\s*=\s*[\"']([^\"']+)[\"']")
_AUTH_ID_INPUT_RE = re.compile(r"name=[\"']authorizedIDX?[\"'][^>]*value=[\"']([^\"']+)[\"']", re.I)

_TOKEN_HINT = re.compile(r"^[A-Za-z0-9\-_]{8,128}$")


def _is_plausible_token(value: str) -> bool:
    return bool(_TOKEN_HINT.match(value or ""))


def extract_csrf_from_html(html: str, *, source: str = "") -> str:
    """Extract the first plausible ``_csrf`` value (hidden input or JS var).

    Raises :class:`CSRFError` if none is found, indicating VTOP changed its
    layout (the caller must not guess or default the token).
    """
    if not html:
        raise CSRFError(f"No HTML to extract a CSRF token from{_ctx(source)}")

    # Hidden input first (present on /vtop/login and /vtop/open/page).
    soup = BeautifulSoup(html, "lxml")
    for inp in soup.find_all("input", attrs={"name": "_csrf"}):
        value = inp.get("value") or inp.get("content")
        if value and _is_plausible_token(value):
            return value
        if value:
            raise CSRFError(f"VTOP returned an implausible CSRF token{_ctx(source)}")

    m = _CSRF_VALUE_JS_RE.search(html)
    if m and _is_plausible_token(m.group(1)):
        return m.group(1)

    raise CSRFError(f"Could not locate a CSRF token in the VTOP response{_ctx(source)}")


def extract_content_tokens(html: str) -> tuple[str, str]:
    """Extract the authenticated session's (csrf, authorizedID) from /vtop/content.

    The content page embeds ``var csrfValue=\"...\"; var id=\"...\";`` and
    hidden ``authorizedID`` inputs. Raises :class:`CSRFError` if the protected
    identity cannot be confirmed.
    """
    csrf = extract_csrf_from_html(html, source="content page")

    authorized_id: Optional[str] = None
    soup = BeautifulSoup(html, "lxml")
    for inp in soup.find_all("input", attrs={"name": "authorizedID"}):
        value = (inp.get("value") or "").strip()
        if value:
            authorized_id = value
            break

    if not authorized_id:
        m = _AUTH_ID_INPUT_RE.search(html)
        if m:
            authorized_id = m.group(1).strip()
    if not authorized_id:
        m = _LOGIN_ID_RE.search(html)
        if m:
            authorized_id = m.group(1).strip()

    if not authorized_id:
        raise CSRFError("The authenticated content page did not expose an authorizedID (VTOP layout may have changed).")

    return csrf, authorized_id


def ensure_valid(value: str, *, label: str = "CSRF token") -> str:
    """Validate a token before it is sent; raise a clear error if malformed."""
    value = (value or "").strip()
    if not _is_plausible_token(value):
        raise CSRFError(f"Refusing to send malformed {label}.")
    return value


def _ctx(source: str) -> str:
    return f" ({source})" if source else ""