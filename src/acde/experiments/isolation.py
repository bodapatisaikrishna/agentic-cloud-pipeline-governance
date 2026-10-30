"""Per-run isolation and metering for measurement protocol v2 (D-105).

v1 left two kinds of shared state between runs: the agents' desired-state writes (streaming worker
target, ingestion blocks, priorities, schema mappings) and Airflow pool slots. Each run therefore
started from whatever the previous agent action left behind, which confounded the cost comparison.
v1 also sampled resources only before injection and after the settle, so the metered term never
saw changes an agent made mid-loop. This module puts the shared state back before every run and
samples resources at a fixed cadence while the run responds.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import httpx

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("experiments.isolation")

# Desired-state keys an agent action can write (executor handlers). The kill switch and the loop
# heartbeat (orchestrator.control) are deliberately not listed: they are operator state, not run
# state.
RUN_STATE_KEYS = ("streaming.workers",)
RUN_STATE_PREFIXES = ("ingestion.blocked.", "pipeline.priority.", "schema.mapping.")


def reset_desired_state() -> None:
    """Remove every agent-written desired-state key, so readers fall back to their defaults."""
    clauses = ["key = %s"] * len(RUN_STATE_KEYS) + ["key LIKE %s"] * len(RUN_STATE_PREFIXES)
    params = (*RUN_STATE_KEYS, *(f"{p}%" for p in RUN_STATE_PREFIXES))
    db.execute(f"DELETE FROM control.desired_state WHERE {' OR '.join(clauses)}", params)


def reset_airflow_pools() -> None:  # pragma: no cover - Airflow REST
    """Patch every configured pool back to its baseline slot count."""
    from acde.policy.executor import _patch_pool

    for pool, slots in get_settings().airflow_pool_baseline_slots.items():
        _patch_pool(pool, slots)


def reset_run_state(reset_pools: Callable[[], None] = reset_airflow_pools) -> bool:
    """Restore the shared data-plane state every run must start from.

    Returns False when the pools could not be reset (Airflow unreachable). The run still goes ahead
    and the runner records ``state_reset_ok = 0`` with its metrics, so the analysis can see and
    exclude it; aborting would lose the run, and carrying on silently would hide the confound.
    """
    reset_desired_state()
    try:
        reset_pools()
    except httpx.HTTPError as exc:
        log.warning("pool_reset_failed", extra={"error": str(exc)})
        return False
    log.info("run_state_reset", extra={"pools": sorted(get_settings().airflow_pool_baseline_slots)})
    return True


class ResourceSampler:
    """Calls ``sample`` every ``interval_s`` on a background thread until stopped.

    Used as a context manager around a run's response phase. A failed sample is logged and
    skipped: a missing point only coarsens the step integral, while an exception here would kill
    the run.
    """

    def __init__(self, sample: Callable[[], None], interval_s: float) -> None:
        self._sample = sample
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="resource-sampler", daemon=True)
        self.taken = 0

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_s):
            try:
                self._sample()
                self.taken += 1
            except Exception as exc:  # one bad sample must not end the run
                log.warning("resource_sample_failed", extra={"error": str(exc)})

    def __enter__(self) -> ResourceSampler:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval_s + 30)
