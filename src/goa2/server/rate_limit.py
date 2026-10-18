"""Per-IP limit on creating games and drafts."""

from __future__ import annotations

import math
import os
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request

DEFAULT_CREATE_LIMIT_PER_HOUR = 5
WINDOW_SECONDS = 3600.0


def create_limit_per_hour() -> int:
    try:
        limit = int(os.environ.get("GOA2_CREATE_LIMIT_PER_HOUR", DEFAULT_CREATE_LIMIT_PER_HOUR))
    except ValueError:
        return DEFAULT_CREATE_LIMIT_PER_HOUR
    return limit if limit > 0 else DEFAULT_CREATE_LIMIT_PER_HOUR


class CreationLimiter:
    """Sliding-window count of creations per IP, held in memory only."""

    SWEEP_MIN = 1024

    def __init__(
        self,
        limit: int,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._sweep_at_size = self.SWEEP_MIN
        self._last_sweep = clock()

    def retry_after(self, ip: str) -> int | None:
        """Seconds until `ip` may create again, or None if it may now."""
        hits = self._hits.get(ip)
        if hits is None:
            return None
        now = self._clock()
        self._expire(hits, now)
        if not hits:
            del self._hits[ip]
            return None
        if len(hits) < self.limit:
            return None
        return max(1, math.ceil(hits[0] + self.window - now))

    def record(self, ip: str) -> None:
        now = self._clock()
        hits = self._hits.get(ip)
        if hits is None:
            self._maybe_sweep(now)
            hits = self._hits[ip] = deque(maxlen=self.limit)
        hits.append(now)

    def tracked_ips(self) -> int:
        return len(self._hits)

    def _expire(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self.window:
            hits.popleft()

    def _maybe_sweep(self, now: float) -> None:
        if len(self._hits) < self._sweep_at_size and now - self._last_sweep < self.window:
            return
        cutoff = now - self.window
        self._hits = {ip: hits for ip, hits in self._hits.items() if hits[-1] > cutoff}
        self._sweep_at_size = max(self.SWEEP_MIN, 2 * len(self._hits))
        self._last_sweep = now


def client_ip(request: Request) -> str:
    # Uvicorn's proxy-headers handling has already replaced this with the
    # forwarded address of the tunnelled client.
    return request.client.host if request.client else "unknown"


def check_creation_budget(request: Request) -> str:
    """Raise 429 if the caller's IP is out of creations; return the IP.

    Call with no `await` between this and `spend_creation_budget`, so that
    concurrent requests cannot all pass the check before any of them spends.
    """
    limiter: CreationLimiter = request.app.state.creation_limiter
    ip = client_ip(request)
    wait = limiter.retry_after(ip)
    if wait is not None:
        minutes = math.ceil(wait / 60)
        unit = "minute" if minutes == 1 else "minutes"
        raise HTTPException(
            status_code=429,
            detail=f"Too many games created from your network; try again in {minutes} {unit}",
            headers={"Retry-After": str(wait)},
        )
    return ip


def spend_creation_budget(request: Request, ip: str) -> None:
    request.app.state.creation_limiter.record(ip)
