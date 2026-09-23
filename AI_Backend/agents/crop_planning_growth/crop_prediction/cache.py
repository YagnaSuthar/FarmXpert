"""A small bounded TTL cache for scored fields.

Scoring is deterministic: the same field, region and shortlist length always
produce the same answer, and the expensive part - the variety sweep plus the
classifier - is pure CPU. Field readings repeat constantly in practice, from
dashboard refreshes, retries and a farmer re-opening the same plot, so the
second identical request should not pay for the first one again.

Bounded and time-limited on purpose: the key comes from a caller, so an
unbounded cache is a memory leak with a public entry point, and a stale
entry should not outlive the forecast it was scored against.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Hashable, Optional


class TTLCache:
    def __init__(self, maxsize: int = 512, ttl_seconds: float = 900.0):
        self.maxsize = max(1, int(maxsize))
        self.ttl = float(ttl_seconds)
        self._data: "OrderedDict[Hashable, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, value = entry
            if now - stored_at > self.ttl:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._data),
                "maxsize": self.maxsize,
                "ttl_seconds": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }
