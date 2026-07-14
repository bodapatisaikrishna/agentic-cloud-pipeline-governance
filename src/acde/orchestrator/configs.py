"""Ablation configs → enabled agent sets (§6, drives the Phase 7 matrix).

Monitoring is the detector (it stamps ``failure_events.detected_ts``), so it is enabled in every
non-baseline config to keep MTTR measurable (DEVIATIONS D-040). ``baseline`` runs no agents — the
static-orchestration control that Phase 7 pairs against.
"""

from __future__ import annotations

AGENT_CONFIGS: dict[str, set[str]] = {
    "baseline": set(),
    "monitor_only": {"monitoring"},
    "recovery_only": {"monitoring", "recovery"},
    "optimization_only": {"monitoring", "optimization"},
    "schema_only": {"monitoring", "schema"},
    "full": {"monitoring", "recovery", "optimization", "schema"},
}


def enabled_agents(config: str) -> set[str]:
    """Return the set of enabled agents for a config name."""
    if config not in AGENT_CONFIGS:
        raise KeyError(f"unknown config {config!r}; choose from {sorted(AGENT_CONFIGS)}")
    return AGENT_CONFIGS[config]
