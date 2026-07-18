"""Bounded adaptation: incorporate logged outcomes into future proposals (E2, D-064).

The paper states (§V) that "outcomes are logged and incorporated into future reasoning cycles,
enabling bounded adaptation," but never specifies or evaluates a mechanism. This module provides a
concrete, bounded one: it computes the empirical success rate of each (fault_type, action_type) pair
from the `telemetry.agent_actions` log and blends it — within fixed clamps — into a proposal's
confidence. The policy gate still bounds every action, so adaptation can only *reprioritise* within
already-permitted behaviour, never expand it.

It is off by default (`adaptation_enabled=False`) so the reproducible benchmark stays deterministic;
enabling it is a separate, opt-in study. This module is pure/queryable and unit-tested; wiring it
into the live loop is left as the evaluated extension.
"""

from __future__ import annotations

from acde import db
from acde.config import get_settings


def success_prior(fault_type: str, action_type: str, experiment_run: str | None = None) -> float:
    """Empirical P(resolved | this action_type was executed for this fault_type), in [0, 1].

    Uses executed agent_actions joined to whether the matching fault ended up resolved. Returns a
    neutral 0.5 when there is no history (no evidence to adapt on).
    """
    row = db.fetch_one(
        "SELECT "
        "  COUNT(*) AS n, "
        "  COUNT(*) FILTER (WHERE fe.resolved_ts IS NOT NULL) AS ok "
        "FROM telemetry.agent_actions aa "
        "JOIN telemetry.failure_events fe ON fe.experiment_run = aa.experiment_run "
        "WHERE aa.executed = TRUE AND aa.action_type = %s AND fe.fault_type = %s"
        + ("" if experiment_run is None else " AND aa.experiment_run = %s"),
        (action_type, fault_type)
        if experiment_run is None
        else (action_type, fault_type, experiment_run),
    )
    if not row or not row["n"]:
        return 0.5
    return float(row["ok"]) / float(row["n"])


def blend_confidence(base_confidence: float, prior: float) -> float:
    """Blend a proposal's base confidence with the historical success prior, within fixed clamps.

    ``adaptation_weight`` controls how much history moves the confidence; the result is clamped to
    ``[adaptation_min, adaptation_max]`` so a bad history can never fully suppress nor a good one
    fully saturate a proposal — adaptation stays bounded.
    """
    s = get_settings()
    w = s.adaptation_weight
    blended = (1.0 - w) * base_confidence + w * prior
    return max(s.adaptation_min_confidence, min(s.adaptation_max_confidence, blended))


def adapt_confidence(
    fault_type: str, action_type: str, base_confidence: float, experiment_run: str | None = None
) -> float:
    """Return an outcome-adapted confidence (identity when adaptation is disabled)."""
    if not get_settings().adaptation_enabled:
        return base_confidence
    return blend_confidence(base_confidence, success_prior(fault_type, action_type, experiment_run))
