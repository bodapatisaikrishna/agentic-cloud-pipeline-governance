"""Experiment configs and profile matrices (§6).

A ``Run`` is one cell of the matrix: (config, scenario, replicate). Profiles build the full run
list; the seed for a run is ``run_seed(config, scenario, replicate)`` so the same fault conditions
recur across configs for paired statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

from acde.experiments.scenarios import SCENARIOS
from acde.orchestrator.configs import AGENT_CONFIGS, enabled_agents

__all__ = ["AGENT_CONFIGS", "PROFILES", "Run", "enabled_agents", "profile_runs"]

ALL_CONFIGS = (
    "baseline",
    "monitor_only",
    "recovery_only",
    "optimization_only",
    "schema_only",
    "full",
)
SINGLE_ABLATIONS = ("monitor_only", "recovery_only", "optimization_only", "schema_only")


@dataclass(frozen=True)
class Run:
    """One matrix cell."""

    config: str
    scenario: str
    replicate: int


def _matrix(configs: tuple[str, ...], n: int) -> list[Run]:
    return [
        Run(config, scenario, r) for config in configs for scenario in SCENARIOS for r in range(n)
    ]


# quick: all 6 configs x 4 scenarios x N=3 = 72 runs (smoke of the full matrix).
# paper: baseline & full at N=20, the four single-agent ablations at N=10 = 320 runs.
# smoke: a tiny 2-run profile for the automated gate.
PROFILES: dict[str, list[Run]] = {
    "smoke": [Run("baseline", "upstream_delay", 0), Run("full", "upstream_delay", 0)],
    "quick": _matrix(ALL_CONFIGS, 3),
    "paper": (_matrix(("baseline", "full"), 20) + _matrix(SINGLE_ABLATIONS, 10)),
}


def profile_runs(profile: str) -> list[Run]:
    """Return the run list for a profile."""
    if profile not in PROFILES:
        raise KeyError(f"unknown profile {profile!r}; choose from {sorted(PROFILES)}")
    return PROFILES[profile]
