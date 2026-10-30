"""Chaos scenario definitions and the seed policy (§6).

Every run derives its seed from ``run_seed(config, scenario, replicate)``, so each run is
reproducible. Only the ``paired`` variant (D-105) gives every config the same fault conditions.
Each scenario has a warmup → fault-window → recovery timeline bounded by a hard cap.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from acde.config import get_settings
from acde.contracts import FaultType


def run_seed(config: str, scenario: str, replicate: int, *, paired: bool = False) -> int:
    """Deterministic per-run seed: sha256("{config}:{scenario}:{replicate}") % 2**32.

    ``paired`` (D-105) drops the config from the hash, so every config sees the same fault and
    human-latency draws at a given (scenario, replicate) and the comparison is a true paired one.
    """
    key = f"{scenario}:{replicate}" if paired else f"{config}:{scenario}:{replicate}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest, 16) % 2**32


@dataclass(frozen=True)
class Scenario:
    """One failure scenario and its per-run timeline (seconds)."""

    name: str
    fault_type: FaultType
    warmup_s: float
    fault_window_s: float
    recovery_s: float

    @property
    def total_s(self) -> float:
        return self.warmup_s + self.fault_window_s + self.recovery_s

    def within_cap(self) -> bool:
        return self.total_s <= get_settings().chaos_hard_cap_s


def _make(name: str, fault_type: FaultType) -> Scenario:
    s = get_settings()
    return Scenario(
        name=name,
        fault_type=fault_type,
        warmup_s=s.chaos_warmup_s,
        fault_window_s=s.chaos_fault_window_s,
        recovery_s=s.chaos_recovery_s,
    )


def all_scenarios() -> dict[str, Scenario]:
    """The four §6 scenarios, timings from settings."""
    return {
        "schema_drift": _make("schema_drift", "schema_drift"),
        "upstream_delay": _make("upstream_delay", "upstream_delay"),
        "resource_contention": _make("resource_contention", "resource_contention"),
        "ingress_burst": _make("ingress_burst", "ingress_burst"),
    }


def get_scenario(name: str) -> Scenario:
    scenarios = all_scenarios()
    if name not in scenarios:
        raise KeyError(f"unknown scenario {name!r}; choose from {sorted(scenarios)}")
    return scenarios[name]
