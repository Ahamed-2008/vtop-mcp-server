from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl

from vtop_discovery.storage.models import (
    CapturedExchange,
    Endpoint,
    EndpointRequest,
    EndpointResponse,
)


def _normalize_path(path: str) -> str:
    cleaned = path.strip().lower()
    if cleaned.endswith("/") and len(cleaned) > 1:
        cleaned = cleaned[:-1]
    return cleaned or "/"


def _extract_body_param_names(body: Any) -> tuple[str, ...]:
    if not body:
        return ()
    if isinstance(body, dict):
        return tuple(sorted(str(k) for k in body.keys()))
    if isinstance(body, str):
        if "=" in body and "&" in body:
            pairs = parse_qsl(body, keep_blank_values=True)
            return tuple(sorted(k for k, _ in pairs))
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return tuple(sorted(str(k) for k in parsed.keys()))
        except (json.JSONDecodeError, TypeError):
            pass
    return ()


def compute_endpoint_signature(exchange: CapturedExchange) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    method = exchange.request.method.upper()
    path = _normalize_path(exchange.request.path)
    query_keys = tuple(sorted(exchange.request.query.keys()))
    body_keys = _extract_body_param_names(exchange.request.body)
    return (method, path, query_keys, body_keys)


def deduplicate(exchanges: list[CapturedExchange]) -> list[Endpoint]:
    """Collapse exchanges that share the same structural signature (method, path, query keys, body keys)."""
    by_key: dict[tuple, Endpoint] = {}

    for exchange in exchanges:
        sig = compute_endpoint_signature(exchange)
        existing = by_key.get(sig)
        seen = exchange.request.timestamp

        if existing is None:
            by_key[sig] = _to_endpoint(exchange)
            continue

        existing.hit_count += 1
        if seen < existing.first_seen:
            existing.first_seen = seen
        if seen >= existing.last_seen:
            existing.last_seen = seen
            _refresh_sample(existing, exchange)
        else:
            existing.request.query.update(exchange.request.query)

        # Upgrade purpose if the new sample is more specific
        if existing.purpose == "unknown" or exchange.purpose in {"attendance", "marks", "timetable", "courses", "profile", "captcha"}:
            if exchange.purpose != "unknown":
                existing.purpose = exchange.purpose

    return list(by_key.values())


def _to_endpoint(exchange: CapturedExchange) -> Endpoint:
    response = exchange.response
    return Endpoint(
        method=exchange.request.method.upper(),
        path=_normalize_path(exchange.request.path),
        purpose=exchange.purpose,
        hit_count=1,
        first_seen=exchange.request.timestamp,
        last_seen=exchange.request.timestamp,
        request=EndpointRequest(
            query=dict(exchange.request.query),
            headers=dict(exchange.request.headers),
            cookies=dict(exchange.request.cookies),
            body=exchange.request.body,
        ),
        response=EndpointResponse(
            status=response.status if response else None,
            content_type=response.content_type if response else None,
            body=response.body if response else None,
        ),
    )


def _refresh_sample(endpoint: Endpoint, exchange: CapturedExchange) -> None:
    endpoint.request.query.update(exchange.request.query)
    endpoint.request.headers = dict(exchange.request.headers)
    endpoint.request.cookies = dict(exchange.request.cookies)
    endpoint.request.body = exchange.request.body
    if exchange.response is not None:
        endpoint.response.status = exchange.response.status
        endpoint.response.content_type = exchange.response.content_type
        endpoint.response.body = exchange.response.body
