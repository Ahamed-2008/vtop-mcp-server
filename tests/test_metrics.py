"""Metrics + rate limiter tests."""

from __future__ import annotations

import time

import pytest

from vtop_mcp.metrics import Metrics, RateLimiter


def test_metrics_record_request():
    m = Metrics()
    m.record_request("/vtop/get/dashboard", 200, 0.5)
    m.record_request("/vtop/get/dashboard", 200, 0.25)
    snap = m.snapshot()
    assert snap["vtop_requests"]["/vtop/get/dashboard"] == 2
    assert snap["vtop_http_status"]["200"] == 2
    assert snap["avg_vtop_latency_ms"] == pytest.approx(375.0, abs=1.0)


def test_metrics_empty_snapshot():
    snap = Metrics().snapshot()
    assert snap["avg_vtop_latency_ms"] == 0.0
    assert snap["vtop_requests"] == {}
    assert snap["parser_failures"] == {}


async def test_rate_limiter_disabled():
    limiter = RateLimiter(0.0)
    started = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    assert time.monotonic() - started < 0.2


async def test_rate_limiter_enforces_rate():
    limiter = RateLimiter(20.0)
    for _ in range(20):
        await limiter.acquire()  # drain the initial full bucket
    started = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - started
    assert elapsed >= 0.04


async def test_rate_limiter_high_rate_passes_fast():
    limiter = RateLimiter(1000.0)
    started = time.monotonic()
    for _ in range(10):
        await limiter.acquire()
    assert time.monotonic() - started < 0.5