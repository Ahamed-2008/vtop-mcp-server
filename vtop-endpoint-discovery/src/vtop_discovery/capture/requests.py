from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlparse

from playwright.sync_api import Request

from vtop_discovery.storage.models import CapturedRequest
from vtop_discovery.utils.redaction import cookie_names_redacted, redact_headers, redact_payload

MAX_BODY_CHARS = 50_000


def _parse_body(raw: str | None, content_type: str | None):
    if raw is None:
        return None
    lowered = (content_type or "").lower()
    if "json" in lowered:
        try:
            return redact_payload(json.loads(raw))
        except json.JSONDecodeError:
            return redact_payload(raw[:MAX_BODY_CHARS])
    if "x-www-form-urlencoded" in lowered or ("=" in raw and "&" in raw):
        parsed = dict(parse_qsl(raw, keep_blank_values=True))
        if parsed:
            return redact_payload(parsed)
    if len(raw) > MAX_BODY_CHARS:
        raw = raw[:MAX_BODY_CHARS]
    return redact_payload(raw)


def capture_request(request: Request) -> CapturedRequest:
    parsed = urlparse(request.url)
    headers = dict(request.headers)
    post_data = None
    try:
        post_data = request.post_data
    except Exception:
        post_data = None

    content_type = headers.get("content-type")
    cookies = cookie_names_redacted(headers.get("cookie"))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    return CapturedRequest(
        method=request.method.upper(),
        url=request.url,
        path=parsed.path or "/",
        query=redact_payload(query) or {},
        headers=redact_headers(headers),
        cookies=cookies,
        body=_parse_body(post_data, content_type),
        resource_type=request.resource_type,
        timestamp=datetime.now(timezone.utc),
    )
