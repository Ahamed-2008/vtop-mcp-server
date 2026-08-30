"""Privacy-conscious in-process metrics.

Counters are deliberately aggregate — no student-specific data is recorded.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass
class Metrics:
    vtop_requests: Counter[str] = field(default_factory=Counter)  # endpoint -> count
    vtop_http_status: Counter[int] = field(default_factory=Counter)
    vtop_errors: Counter[str] = field(default_factory=Counter)
    auth_failures: Counter[str] = field(default_factory=Counter)
    parser_failures: Counter[str] = field(default_factory=Counter)
    tool_calls: Counter[str] = field(default_factory=Counter)
    tool_errors: Counter[str] = field(default_factory=Counter)
    latencies: Deque[float] = field(default_factory=lambda: deque(maxlen=256))

    def record_request(self, endpoint: str, status: int, duration: float) -> None:
        self.vtop_requests[endpoint] += 1
        self.vtop_http_status[status] += 1
        self.latencies.append(duration)

    def snapshot(self) -> dict:
        lat = list(self.latencies)
        avg = sum(lat) / len(lat) if lat else 0.0
        return {
            "vtop_requests": dict(self.vtop_requests),
            "vtop_http_status": {str(k): v for k, v in self.vtop_http_status.items()},
            "vtop_errors": dict(self.vtop_errors),
            "auth_failures": dict(self.auth_failures),
            "parser_failures": dict(self.parser_failures),
            "tool_calls": dict(self.tool_calls),
            "tool_errors": dict(self.tool_errors),
            "avg_vtop_latency_ms": round(avg * 1000.0, 2) if lat else 0.0,
        }


class RateLimiter:
    """Minimal token-bucket rate limiter for outgoing VTOP requests."""

    def __init__(self, rate_per_second: float) -> None:
        self._rate = rate_per_second
        self._tokens = rate_per_second
        self._last = time.monotonic()

    async def acquire(self) -> None:
        if self._rate <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
        self._last = now
        if self._tokens < 1:
            await asyncio.sleep((1 - self._tokens) / self._rate)
            self._tokens = 0.0
        else:
            self._tokens -= 1.0


import asyncio  # noqa: E402

__all__ = ["Metrics", "RateLimiter"]