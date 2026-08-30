from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode

REDACTED = "[REDACTED]"

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrf-token",
    "x-xsrf-token",
    "x-auth-token",
    "proxy-authorization",
}

SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "otp",
    "token",
    "csrf",
    "session",
    "jsessionid",
    "authorization",
    "authorizedid",
    "regno",
    "registrationno",
    "studentid",
    "memberid",
    "userpass",
    "secret",
}

_CAPTCHA_RE = re.compile(r"captcha", re.IGNORECASE)
_STUDENT_ID_RE = re.compile(r"^\d{2}[a-zA-Z]{3}\d{4,5}$")


def is_sensitive_field(name: str) -> bool:
    lowered = name.lower().replace("-", "").replace("_", "")
    if _CAPTCHA_RE.search(lowered):
        return True
    return any(token in lowered for token in SENSITIVE_FIELD_NAMES)


def is_sensitive_value(value: Any) -> bool:
    if isinstance(value, str):
        cleaned = value.strip()
        if _STUDENT_ID_RE.match(cleaned):
            return True
    return False


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in SENSITIVE_HEADER_NAMES:
            redacted[name] = REDACTED
        else:
            redacted[name] = value
    return redacted


def cookie_names_redacted(cookie_header: str | None) -> dict[str, str]:
    """Keep cookie names, replace every value with REDACTED."""
    if not cookie_header:
        return {}
    names: dict[str, str] = {}
    for part in cookie_header.split(";"):
        piece = part.strip()
        if not piece:
            continue
        name = piece.split("=", 1)[0].strip()
        if name:
            names[name] = REDACTED
    return names


def set_cookie_names_redacted(set_cookie: str | None) -> dict[str, str]:
    if not set_cookie:
        return {}
    names: dict[str, str] = {}
    for chunk in re.split(r"[\n,]", set_cookie):
        piece = chunk.strip()
        if not piece or "=" not in piece:
            continue
        name = piece.split("=", 1)[0].strip()
        if name and name.lower() not in {
            "expires",
            "path",
            "domain",
            "max-age",
            "secure",
            "httponly",
            "samesite",
        }:
            names[name] = REDACTED
    return names


def redact_value(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: REDACTED
            if is_sensitive_field(str(key)) or is_sensitive_value(value)
            else redact_value(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_value(item) for item in data]
    if is_sensitive_value(data):
        return REDACTED
    return data


def _redact_form(payload: str) -> str | None:
    pairs = parse_qsl(payload, keep_blank_values=True)
    if not pairs:
        return None
    redacted_pairs = [
        (
            key,
            REDACTED
            if is_sensitive_field(key) or is_sensitive_value(value)
            else value,
        )
        for key, value in pairs
    ]
    return urlencode(redacted_pairs)


def redact_payload(payload: str | dict | list | None) -> str | dict | list | None:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return redact_value(payload)
    form = _redact_form(payload)
    if form is not None and "=" in payload:
        return form
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        if is_sensitive_value(payload):
            return REDACTED
        return payload
    return json.dumps(redact_value(parsed))
