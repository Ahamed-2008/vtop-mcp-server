from __future__ import annotations

import json
from urllib.parse import urlparse

from playwright.sync_api import Response

from vtop_discovery.storage.models import CapturedResponse
from vtop_discovery.utils.redaction import redact_headers, redact_payload, set_cookie_names_redacted

MAX_BODY_CHARS = 50_000
MAX_BODY_BYTES = 50_000

BINARY_CONTENT_PREFIXES = (
    "image/",
    "font/",
    "audio/",
    "video/",
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/wasm",
)


def looks_like_captcha(url: str) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.path}?{parsed.query}".lower()
    return "captcha" in haystack


def is_useful_text_body(content_type: str | None, url: str) -> bool:
    if looks_like_captcha(url):
        # Keep the captcha *endpoint*, never the image bytes.
        lowered = (content_type or "").lower()
        if lowered.startswith("image/") or not lowered:
            return False
    lowered = (content_type or "").lower()
    if not lowered:
        return False
    if any(lowered.startswith(prefix) for prefix in BINARY_CONTENT_PREFIXES):
        return False
    if "javascript" in lowered or lowered.endswith("/ecmascript"):
        return False
    return any(
        token in lowered
        for token in ("json", "html", "xml", "text/", "x-www-form-urlencoded")
    )


def _parse_body(raw: str, content_type: str | None):
    if "json" in (content_type or "").lower():
        try:
            return redact_payload(json.loads(raw))
        except json.JSONDecodeError:
            pass
    if len(raw) > MAX_BODY_CHARS:
        raw = raw[:MAX_BODY_CHARS]
    return redact_payload(raw)


def capture_response(response: Response) -> CapturedResponse:
    headers = dict(response.headers)
    content_type = headers.get("content-type")
    cookies = set_cookie_names_redacted(headers.get("set-cookie"))
    body = None
    if is_useful_text_body(content_type, response.url):
        try:
            raw = response.text()
            body = _parse_body(raw, content_type)
        except Exception:
            body = None

    return CapturedResponse(
        status=response.status,
        content_type=content_type,
        headers=redact_headers(headers),
        cookies=cookies,
        body=body,
    )
