from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from vtop_discovery.storage.models import DiscoveryCatalog, Endpoint


@dataclass
class EndpointChange:
    endpoint: Endpoint
    changes: list[str] = field(default_factory=list)


@dataclass
class CatalogDiff:
    added: list[Endpoint] = field(default_factory=list)
    removed: list[Endpoint] = field(default_factory=list)
    changed: list[EndpointChange] = field(default_factory=list)
    unchanged: list[Endpoint] = field(default_factory=list)


def load_catalog(path: Path) -> DiscoveryCatalog:
    raw = path.read_text(encoding="utf-8")
    return DiscoveryCatalog.model_validate_json(raw)


def _get_endpoints_list(catalog: DiscoveryCatalog) -> list[Endpoint]:
    if isinstance(catalog.endpoints, dict):
        return list(catalog.endpoints.values())
    return catalog.endpoints


def diff_catalogs(old_catalog: DiscoveryCatalog, new_catalog: DiscoveryCatalog) -> CatalogDiff:
    diff = CatalogDiff()

    old_list = _get_endpoints_list(old_catalog)
    new_list = _get_endpoints_list(new_catalog)

    old_map: dict[tuple[str, str], Endpoint] = {
        (ep.method, ep.path): ep for ep in old_list
    }
    new_map: dict[tuple[str, str], Endpoint] = {
        (ep.method, ep.path): ep for ep in new_list
    }

    # Find added & changed/unchanged
    for key, new_ep in new_map.items():
        if key not in old_map:
            diff.added.append(new_ep)
        else:
            old_ep = old_map[key]
            changes = _compare_endpoints(old_ep, new_ep)

            if changes:
                diff.changed.append(EndpointChange(endpoint=new_ep, changes=changes))
            else:
                diff.unchanged.append(new_ep)

    # Find removed
    for key, old_ep in old_map.items():
        if key not in new_map:
            diff.removed.append(old_ep)

    return diff


def _compare_endpoints(old_ep: Endpoint, new_ep: Endpoint) -> list[str]:
    changes: list[str] = []

    if old_ep.purpose != new_ep.purpose:
        changes.append(f"purpose: {old_ep.purpose} -> {new_ep.purpose}")

    if old_ep.request.query != new_ep.request.query:
        changes.append(f"query params: {old_ep.request.query} -> {new_ep.request.query}")

    if old_ep.request.body != new_ep.request.body:
        changes.append(f"request body changed")

    if old_ep.response.status != new_ep.response.status:
        changes.append(f"response status: {old_ep.response.status} -> {new_ep.response.status}")

    return changes


def format_diff(diff: CatalogDiff) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  ENDPOINT CATALOG DIFF REPORT")
    lines.append("=" * 60)

    if diff.added:
        lines.append(f"\n[+] ADDED ({len(diff.added)}):")
        for ep in diff.added:
            lines.append(f"  + {ep.method} {ep.path} (purpose: {ep.purpose})")

    if diff.removed:
        lines.append(f"\n[-] REMOVED ({len(diff.removed)}):")
        for ep in diff.removed:
            lines.append(f"  - {ep.method} {ep.path} (purpose: {ep.purpose})")

    if diff.changed:
        lines.append(f"\n[~] CHANGED ({len(diff.changed)}):")
        for ch in diff.changed:
            lines.append(f"  ~ {ch.endpoint.method} {ch.endpoint.path}:")
            for item in ch.changes:
                lines.append(f"      • {item}")

    lines.append(f"\n[=] UNCHANGED: {len(diff.unchanged)} endpoints")
    lines.append("=" * 60)
    return "\n".join(lines)
