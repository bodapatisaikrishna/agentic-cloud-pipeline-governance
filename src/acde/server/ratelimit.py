"""In-process request-rate limiter for the operator API (D-098).

Fixed-window counter, keyed by string (the caller's resolved actor when credentials match, else
their raw client address — see ``server/app.py``'s middleware for the key-resolution logic). No
new dependency, no new infra: a self-hosted, single-process deployment doesn't need a distributed
limiter, the same "hand-roll over adding a client library" call already made for the CSV export
(D-094) and the Prometheus exposition format (D-088). A multi-instance deployment sharing one
limiter is explicitly out of scope -- documented, not silently assumed away.

Distinct from ``Settings.rate_limit_max_per_10min`` (``infra/opa/policies/rate_limit.rego``),
which caps how many actions an *agent* proposes -- an unrelated, pre-existing concern this module
does not touch.
"""

from __future__ import annotations

import threading
import time

# Process-wide, cumulative -- correct for a Prometheus counter (every other counter in
# metrics.py is process-wide too); the actual limiting decision lives on app.state instead (see
# RateLimiter below), so tests creating multiple `create_app()` instances never share that state.
_total_rate_limited = 0
_total_lock = threading.Lock()


def _record_rate_limited() -> None:
    global _total_rate_limited
    with _total_lock:
        _total_rate_limited += 1


def total_rate_limited() -> int:
    """Cumulative count of requests rejected with 429 across this process's lifetime."""
    with _total_lock:
        return _total_rate_limited


def reset_total_rate_limited() -> None:
    """Test-only: zero the process-wide counter so assertions don't depend on run order."""
    global _total_rate_limited
    with _total_lock:
        _total_rate_limited = 0


class RateLimiter:
    """Fixed-window request counter. One instance per app (``app.state.rate_limiter``), so
    concurrent test suites or repeated ``create_app()`` calls never share window state.

    A fixed window (not a sliding one or a token bucket) is the simplest correct choice here: it
    can allow a short burst right at a window boundary, a known and accepted trade-off for a
    coarse abuse guard, not a precise API-billing meter.
    """

    def __init__(self, limit_per_minute: int, window_s: float = 60.0) -> None:
        self.limit_per_minute = limit_per_minute
        self.window_s = window_s
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Record one request for ``key``. Returns ``(allowed, retry_after_s)`` -- ``retry_after``
        is only meaningful when ``allowed`` is ``False``. ``limit_per_minute <= 0`` always allows
        (disabled), matching ``blast_radius_max_per_hour``'s existing "0 = unlimited" convention.
        """
        if self.limit_per_minute <= 0:
            return True, 0.0
        now = time.monotonic()
        with self._lock:
            window_start, count = self._windows.get(key, (now, 0))
            elapsed = now - window_start
            if elapsed >= self.window_s:
                window_start, count = now, 0
                elapsed = 0.0
            count += 1
            self._windows[key] = (window_start, count)
            if count > self.limit_per_minute:
                _record_rate_limited()
                return False, round(self.window_s - elapsed, 1)
            return True, 0.0

    def reset(self) -> None:
        """Test-only: clear all window state."""
        with self._lock:
            self._windows.clear()
