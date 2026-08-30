from __future__ import annotations

from urllib.parse import urlparse

from vtop_discovery.storage.models import CapturedExchange

STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".webp",
    ".avif",
}

STATIC_RESOURCE_TYPES = {"stylesheet", "image", "font", "media", "manifest"}

IGNORED_HOST_FRAGMENTS = (
    "google-analytics",
    "googletagmanager",
    "doubleclick",
    "facebook.net",
    "hotjar",
)


def looks_like_captcha(url: str) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.path}?{parsed.query}".lower()
    return "captcha" in haystack


def is_interesting(exchange: CapturedExchange, *, host_contains: str = "vtop") -> bool:
    """Keep VTOP document/XHR/fetch traffic; drop static assets and trackers.

    Captcha image/refresh URLs are kept so the catalog includes those endpoints.
    """
    url = exchange.request.url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()

    if host_contains not in host:
        return False
    if any(fragment in host for fragment in IGNORED_HOST_FRAGMENTS):
        return False
    if looks_like_captcha(url):
        return True
    if exchange.request.resource_type in STATIC_RESOURCE_TYPES:
        return False
    if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
        return False
    return True
