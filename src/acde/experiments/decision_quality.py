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


def is_correct(scenario: str, executed_action_types: list[str]) -> bool:
    """True if any executed action is an acceptable mitigation for the scenario."""
    expected = expected_for(scenario)
    return bool(expected) and any(a in expected for a in executed_action_types)
