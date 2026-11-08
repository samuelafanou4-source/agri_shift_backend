"""Simple in-memory sliding-window rate limiter (per device, or per IP before registration)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from app.errors import ApiError


class RateLimiter:
    def __init__(self, limit_per_min: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit_per_min
        self.window = 60.0
        self.clock = clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = self.clock()
        q = self.hits[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise ApiError(
                429,
                "rate_limited",
                "Trop de requêtes, réessayez dans une minute.",
            )
        q.append(now)
