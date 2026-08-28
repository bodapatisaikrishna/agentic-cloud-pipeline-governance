"""Decision-quality ground truth: did an agent pick a *correct* mitigation? (Phase A, D-059).

The paper (and our earlier metrics) measure how *fast* a fault is resolved, never whether the agent
chose the *right* action. We add a per-scenario set of acceptable optimal mitigations and score
``decision_correct`` = 1.0 if the run logged an executed agent action in that set, else 0.0.

This is only meaningful for agent configs (they emit ``agent_actions``); the non-agent baselines
make no agentic decision and score 0 by construction — which is the point: they resolve without
reasoning about the *right* remediation.
"""

from __future__ import annotations

# scenario/fault_type -> acceptable optimal mitigations (any one counts as a correct decision).
EXPECTED_ACTIONS: dict[str, set[str]] = {
    "schema_drift": {"quarantine_partition", "block_ingestion", "apply_mapping"},
    "upstream_delay": {"replay", "retry_with_backoff", "partial_recompute"},
    "ingress_burst": {"scale_workers", "adjust_pool_slots"},
    "resource_contention": {"scale_workers", "adjust_pool_slots", "reprioritize_pipeline"},
}


def expected_for(scenario: str) -> set[str]:
    """Acceptable mitigation action_types for a scenario (empty if unknown)."""
    return EXPECTED_ACTIONS.get(scenario, set())


def _any_match(expected: set[str], executed_action_types: list[str]) -> bool:
    return bool(expected) and any(a in expected for a in executed_action_types)


def is_correct(scenario: str, executed_action_types: list[str]) -> bool:
    """True if any executed action is an acceptable mitigation for the scenario."""
    return _any_match(expected_for(scenario), executed_action_types)


# D-100: real detector kinds (``agents/detection.py::detect_anomalies``, wired into live
# monitoring by D-091) — ``task_failed``, ``freshness_breach``, ``cpu_high``, ``schema_breaking``
# — are *not* the chaos scenario names ``EXPECTED_ACTIONS`` above is keyed by. Reusing
# ``expected_for()`` against a real ``fault_type`` would silently return an empty set for every
# live incident, scoring every real decision "incorrect by construction." Each set below is not a
# fresh judgment call: it's copied verbatim from the one agent module that actually owns "what
# counts as resolving this" for that kind of problem — ``agents/recovery.py::_REMEDIATING``,
# ``agents/optimization.py::_RESOLVING``, ``agents/schema.py::_RESOLVING`` — the same three sets
# EXPECTED_ACTIONS's own buckets already mirror.
LIVE_EXPECTED_ACTIONS: dict[str, set[str]] = {
    # agents/recovery.py::_REMEDIATING
    "task_failed": {"retry_with_backoff", "replay", "rollback", "partial_recompute"},
    # freshness can be caught up either by retrying/replaying the lagging work (recovery) or by
    # giving the pipeline more capacity (optimization) -- both are real, accepted responses.
    "freshness_breach": {
        "retry_with_backoff",
        "replay",
        "partial_recompute",
        "scale_workers",
        "adjust_pool_slots",
    },
    # agents/optimization.py::_RESOLVING
    "cpu_high": {"scale_workers", "adjust_pool_slots", "reprioritize_pipeline"},
    # agents/schema.py::_RESOLVING
    "schema_breaking": {"quarantine_partition", "block_ingestion", "apply_mapping"},
}


def expected_for_live(fault_type: str) -> set[str]:
    """Acceptable mitigation action_types for a real, live-detected fault_type (D-100). Empty for
    an unmapped fault_type (e.g. an ``open_fault:*`` echo, D-091) -- unscored, not "incorrect."
    """
    return LIVE_EXPECTED_ACTIONS.get(fault_type, set())


def is_correct_live(fault_type: str, executed_action_types: list[str]) -> bool:
    """True if any executed action is an acceptable mitigation for a real ``fault_type``."""
    return _any_match(expected_for_live(fault_type), executed_action_types)
