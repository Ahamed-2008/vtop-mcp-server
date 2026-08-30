
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from vtop_discovery.analysis.diff import diff_catalogs, format_diff, load_catalog
from vtop_discovery.storage.models import (
    DiscoveryCatalog,
    Endpoint,
    EndpointRequest,
    EndpointResponse,
)


def _make_endpoint(path: str, method: str = "GET", purpose: str = "unknown", query: dict = None) -> Endpoint:
    now = datetime.now(timezone.utc)
    return Endpoint(
        method=method,
        path=path,
        purpose=purpose,
        first_seen=now,
        last_seen=now,
        request=EndpointRequest(query=query or {}),
        response=EndpointResponse(status=200),
    )


def test_diff_catalogs_added_removed_changed_unchanged():
    now = datetime.now(timezone.utc)
    ep_common = _make_endpoint("/vtop/common", purpose="login")
    ep_removed = _make_endpoint("/vtop/old_endpoint", purpose="old")
    ep_changed_old = _make_endpoint("/vtop/attendance", purpose="unknown")
    ep_changed_new = _make_endpoint("/vtop/attendance", purpose="attendance", query={"sem": "WIN2026"})
    ep_added = _make_endpoint("/vtop/new_endpoint", purpose="marks")

    cat_old = DiscoveryCatalog(
        discovered_at=now,
        base_url="https://vtop.vit.ac.in",
        endpoints=[ep_common, ep_removed, ep_changed_old],
    )

    cat_new = DiscoveryCatalog(
        discovered_at=now,
        base_url="https://vtop.vit.ac.in",
        endpoints=[ep_common, ep_changed_new, ep_added],
    )

    diff = diff_catalogs(cat_old, cat_new)

    assert len(diff.added) == 1
    assert diff.added[0].path == "/vtop/new_endpoint"

    assert len(diff.removed) == 1
    assert diff.removed[0].path == "/vtop/old_endpoint"

    assert len(diff.changed) == 1
    assert diff.changed[0].endpoint.path == "/vtop/attendance"
    assert any("purpose" in c for c in diff.changed[0].changes)

    assert len(diff.unchanged) == 1
    assert diff.unchanged[0].path == "/vtop/common"

    formatted = format_diff(diff)
    assert "[+] ADDED" in formatted
    assert "[-] REMOVED" in formatted
    assert "[~] CHANGED" in formatted
    assert "[=] UNCHANGED: 1 endpoints" in formatted
