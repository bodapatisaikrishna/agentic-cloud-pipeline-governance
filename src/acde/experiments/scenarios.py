"""Experiment scenarios + per-profile run timings (§6).

Re-exports the four chaos scenarios and the seed policy, and defines how long each phase of a run
lasts per profile. ``quick`` uses short timings so the 72-run smoke finishes in minutes rather than
hours (DEVIATIONS D-042); ``paper`` uses the §6 timeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from acde.chaos.scenarios import all_scenarios, run_seed

__all__ = ["SCENARIOS", "TIMINGS", "RunTimings", "all_scenarios", "run_seed"]

SCENARIOS = tuple(all_scenarios())  # ("schema_drift", "upstream_delay", ...)


@dataclass(frozen=True)
class RunTimings:
    """How long each phase of a single run lasts, in seconds."""

    warmup_s: float
    loop_s: float  # how long the control loop (or baseline wait) runs during the fault+recovery
    settle_s: float  # brief settle before harvesting metrics


TIMINGS: dict[str, RunTimings] = {
    "smoke": RunTimings(warmup_s=0.5, loop_s=6.0, settle_s=0.5),
    "quick": RunTimings(warmup_s=1.0, loop_s=12.0, settle_s=1.0),
    "paper": RunTimings(warmup_s=120.0, loop_s=300.0, settle_s=5.0),
}
