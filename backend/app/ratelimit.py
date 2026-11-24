from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque
from typing import Callable

UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_limit(spec: str) -> tuple[int, int]:
    count, _, unit = spec.strip().partition("/")
    unit = unit.strip().rstrip("s")
    if unit not in UNITS:
        raise ValueError(f"Bad rate limit {spec!r}; use e.g. '10/hour'")
    return int(count), UNITS[unit]


class RateLimiter:

    def __init__(self, spec: str, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 50_000):
        self.limit, self.window = parse_limit(spec)
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def check(self, key: str) -> float | None:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1.0, hits[0] + self.window - now)
            hits.append(now)
            if len(self._hits) > self._max_keys:
                self._prune(now)
            return None

    def _prune(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window]:
            del self._hits[k]


def client_ip(headers: dict, peer: str | None) -> str:
    if os.getenv("TRUST_PROXY") == "1":
        forwarded = headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer or "unknown"


def friendly_wait(seconds: float) -> str:
    if seconds < 90:
        return f"{math.ceil(seconds)} seconds"
    if seconds < 5400:
        return f"{math.ceil(seconds / 60)} minutes"
    return f"{math.ceil(seconds / 3600)} hours"
