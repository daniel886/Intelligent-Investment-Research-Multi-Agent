"""Async-friendly token-bucket rate limiter."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque


class AsyncRateLimiter:
    """Sliding-window async rate limiter."""

    def __init__(self, max_calls: int, period: float = 60.0) -> None:
        self.max_calls = max_calls
        self.period = period
        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] >= self.period:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_calls:
                wait = self.period - (now - self._timestamps[0])
                if wait > 0:
                    await asyncio.sleep(wait)
            self._timestamps.append(time.monotonic())

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None
