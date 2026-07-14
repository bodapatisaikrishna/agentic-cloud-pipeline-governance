"""Postgres advisory locks keyed on an action target (§8 Phase 6).

``target_advisory_lock`` holds one pooled connection and runs a non-blocking
``pg_try_advisory_lock`` so two agents never act on the same target concurrently — real
cross-process locking, released on unlock or disconnect (DEVIATIONS D-037). The conflict rule
(recovery outranks optimization on a shared target) falls out of act order: whoever runs first
holds the lock, the later agent's ``try_lock`` returns false and it skips.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager

from acde import db
from acde.logging import get_logger

log = get_logger("orchestrator.locks")


def _lock_key(target: str) -> int:
    """Deterministic signed 32-bit key for a target (pg advisory-lock namespace)."""
    digest = hashlib.sha256(target.encode()).digest()
    unsigned = int.from_bytes(digest[:4], "big")
    return unsigned - 2**31  # map to signed int4 range


@contextmanager
def target_advisory_lock(target: str) -> Iterator[bool]:
    """Try to lock ``target``; yield True if acquired (and release on exit), else False."""
    key = _lock_key(target)
    with db.get_pool().connection() as conn:
        got = conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()
        acquired = bool(got and (got["pg_try_advisory_lock"] if isinstance(got, dict) else got[0]))
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
