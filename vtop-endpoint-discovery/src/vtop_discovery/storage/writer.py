from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from vtop_discovery.storage.models import (
    CapturedExchange,
    Endpoint,
    EndpointInventory,
    Workflow,
)
from vtop_discovery.utils.logging import get_logger
from vtop_discovery.utils.redaction import redact_headers, redact_payload

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://vtop.vit.ac.in"

UNNECESSARY_BROWSER_HEADERS = {
    "user-agent",
    "sec-ch-ua",
    "sec-ch-ua-platform",
    "sec-ch-ua-mobile",
    "sec-fetch-site",
    "sec-fetch-mode",
    "sec-fetch-dest",
    "sec-fetch-user",
    "upgrade-insecure-requests",
    "accept-language",
    "accept-encoding",
    "priority",
    "connection",
}


def _clean_endpoint_for_export(endpoint: Endpoint) -> Endpoint:
    copy = endpoint.model_copy(deep=True)

    # Redact headers and strip browser boilerplate headers
    redacted_hdrs = redact_headers(copy.request.headers)
    clean_hdrs = {
        k: v for k, v in redacted_hdrs.items()
        if k.lower() not in UNNECESSARY_BROWSER_HEADERS
    }
    copy.request.headers = clean_hdrs

    copy.request.query = redact_payload(copy.request.query) or {}
    copy.request.body = redact_payload(copy.request.body)

    # In clean export, strip huge raw HTML response bodies and keep response analysis metadata
    if isinstance(copy.response.body, str) and ("<html" in copy.response.body.lower() or len(copy.response.body) > 500):
        copy.response.body = None
    else:
        copy.response.body = redact_payload(copy.response.body)

    return copy


def write_inventory(
    endpoints: list[Endpoint] | dict[str, Endpoint],
    path: Path,
    *,
    workflows: list[Workflow] | None = None,
    base_url: str = DEFAULT_BASE_URL,
    generated_at: datetime | None = None,
) -> None:
    """Write the clean, machine-readable endpoint inventory JSON with endpoints and workflow dependencies."""
    endpoints_dict: dict[str, Endpoint] = {}
    if isinstance(endpoints, dict):
        for k, ep in endpoints.items():
            endpoints_dict[k] = _clean_endpoint_for_export(ep)
    else:
        for ep in endpoints:
            key = ep.id or f"{ep.method}_{ep.path.strip('/').replace('/', '_')}"
            endpoints_dict[key] = _clean_endpoint_for_export(ep)

    inventory = EndpointInventory(
        generated_at=generated_at or datetime.now(timezone.utc),
        base_domains=[base_url],
        endpoints=endpoints_dict,
        workflows=workflows or [],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = inventory.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %d clean endpoints and %d workflows to %s", len(endpoints_dict), len(inventory.workflows), path)


# Alias for compatibility with previous callers
def write_catalog(
    endpoints: list[Endpoint] | dict[str, Endpoint],
    path: Path,
    *,
    workflows: list[Workflow] | None = None,
    base_url: str = DEFAULT_BASE_URL,
    discovered_at: datetime | None = None,
) -> None:
    write_inventory(
        endpoints,
        path,
        workflows=workflows,
        base_url=base_url,
        generated_at=discovered_at,
    )


def write_raw_captures(
    exchanges: list[CapturedExchange],
    captures_dir: Path,
    session_id: str | None = None,
) -> Path:
    """Save raw HTTP exchanges for debugging in captures/<session>/."""
    sid = session_id or datetime.now(timezone.utc).strftime("session_%Y%m%d_%H%M%S")
    target_dir = captures_dir / sid
    target_dir.mkdir(parents=True, exist_ok=True)

    raw_file = target_dir / "raw_exchanges.json"
    payload = [ex.model_dump(mode="json") for ex in exchanges]
    raw_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("Saved %d raw captures for debugging to %s", len(exchanges), raw_file)
    return raw_file

