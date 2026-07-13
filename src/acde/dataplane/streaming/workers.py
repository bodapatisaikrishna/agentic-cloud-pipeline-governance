"""Async worker pool sized from ``control.desired_state`` (1-8 "resource units", §5.2).

The resize *decision* is pure and unit-tested; :class:`WorkerPool` applies it over asyncio
tasks created by an injected factory, so scaling can be tested without real work.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("dataplane.streaming.workers")

# A worker factory takes (index, stop_event) and returns the worker coroutine.
WorkerFactory = Callable[[int, asyncio.Event], Awaitable[None]]


def clamp_workers(n: int, lo: int, hi: int) -> int:
    """Clamp a desired worker count into the allowed [lo, hi] band."""
    return max(lo, min(hi, n))


def resize_plan(current: int, desired: int, lo: int, hi: int) -> tuple[int, int, int]:
    """Return (target, to_add, to_remove) for moving ``current`` toward a clamped ``desired``."""
    target = clamp_workers(desired, lo, hi)
    return target, max(0, target - current), max(0, current - target)


def read_desired_workers(default: int | None = None) -> int:
    """Read ``control.desired_state['streaming.workers']`` → n; fall back to default."""
    settings = get_settings()
    fallback = settings.stream_default_workers if default is None else default
    row = db.fetch_one(
        "SELECT value FROM control.desired_state WHERE key = %s", ("streaming.workers",)
    )
    if not row or row["value"] is None:
        return fallback
    value = row["value"]
    if isinstance(value, str):
        value = json.loads(value)
    return int(value.get("n", fallback))


class WorkerPool:
    """Grows/shrinks a set of asyncio worker tasks to a target size."""

    def __init__(self, factory: WorkerFactory, lo: int = 1, hi: int = 8) -> None:
        self._factory = factory
        self._lo = lo
        self._hi = hi
        self._workers: dict[int, tuple[asyncio.Task[None], asyncio.Event]] = {}
        self._next_index = 0

    def size(self) -> int:
        return len(self._workers)

    def _spawn(self) -> None:
        idx = self._next_index
        self._next_index += 1
        stop = asyncio.Event()
        task = asyncio.ensure_future(self._factory(idx, stop))
        self._workers[idx] = (task, stop)

    async def _retire_one(self) -> None:
        idx = next(iter(self._workers))
        task, stop = self._workers.pop(idx)
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):  # pragma: no cover - defensive
            task.cancel()

    async def resize(self, desired: int) -> int:
        """Scale to a clamped ``desired`` size; returns the achieved target."""
        target, to_add, to_remove = resize_plan(self.size(), desired, self._lo, self._hi)
        for _ in range(to_add):
            self._spawn()
        for _ in range(to_remove):
            await self._retire_one()
        log.info("worker_pool_resized", extra={"target": target, "size": self.size()})
        return target

    async def shutdown(self) -> None:
        """Stop all workers (bypasses the [lo, hi] floor that ``resize`` enforces)."""
        for _, stop in self._workers.values():
            stop.set()
        for idx in list(self._workers):
            task, _ = self._workers.pop(idx)
            try:
                await asyncio.wait_for(task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):  # pragma: no cover - defensive
                task.cancel()
