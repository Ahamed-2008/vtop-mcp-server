"""Small in-memory TTL cache for expensive read-only VTOP data.

Scope
-----
* Only derived academic *data* (CGPA, course/attendance rows, assignments,
  events, feedback) is cached — never cookies, CSRF tokens, or passwords.
* Keys are scoped to the authenticated student id so one account's cache can
  never be served to another.
* A zero/negative configured TTL effectively disables caching.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    created: float = field(default_factory=time.time)


class TTLCache(Generic[T]):
    """Minimal generic cache with per-entry TTL, scoped keys, and a size cap."""

    def __init__(self, ttl: float, max_entries: int = 256) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._store: dict[str, _Entry[T]] = {}

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: str) -> Optional[T]:
        if not self.enabled:
            return None
        item = self._store.get(key)
        if item is None:
            return None
        if time.time() - item.created > self._ttl:
            self._store.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: T) -> None:
        if not self.enabled:
            return
        if len(self._store) >= self._max:
            # Evict oldest entries.
            oldest = min(self._store, key=lambda k: self._store[k].created)
            self._store.pop(oldest, None)
        self._store[key] = _Entry(value)

    def get_or_fetch(self, key: str, fetch) -> T:
        """Return cached value or compute+store via ``await fetch()``."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fetch()
        self.set(key, value)
        return value

    def clear(self) -> None:
        self._store.clear()