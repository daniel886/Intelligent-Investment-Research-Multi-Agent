"""Async-friendly token-bucket rate limiter."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque


class AsyncRateLimiter:
    """Sliding-window async rate limiter.

    Concurrency note: the internal lock is *only* held while updating the
    timestamp window — never across ``await asyncio.sleep`` — so a slow
    waiter does not serialize unrelated callers. Each acquire iterates
    through "purge expired → check capacity → either reserve a slot or
    sleep & retry".
    """

    def __init__(self, max_calls: int, period: float = 60.0) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be > 0")
        if period <= 0:
            raise ValueError("period must be > 0")
        self.max_calls = max_calls
        self.period = period
        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                # Purge timestamps outside the sliding window.
                while self._timestamps and now - self._timestamps[0] >= self.period:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.max_calls:
                    # Reserve a slot atomically and return.
                    self._timestamps.append(now)
                    return
                # Compute wait time, then release the lock before sleeping
                # so other callers (especially those whose oldest timestamp
                # has now expired) can proceed in parallel.
                wait = self.period - (now - self._timestamps[0])
            if wait > 0:
                await asyncio.sleep(wait)
            # Loop back: re-check capacity under the lock.

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None
