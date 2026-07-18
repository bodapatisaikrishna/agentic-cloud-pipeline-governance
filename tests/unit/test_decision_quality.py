"""Unit tests for the decision-quality ground truth."""

from acde.experiments.decision_quality import EXPECTED_ACTIONS, expected_for, is_correct


def test_expected_actions_cover_all_scenarios():
    for scenario in ("schema_drift", "upstream_delay", "ingress_burst", "resource_contention"):
        assert expected_for(scenario), f"no ground truth for {scenario}"


def test_correct_when_action_in_expected_set():
    assert is_correct("schema_drift", ["quarantine_partition"])
    assert is_correct("upstream_delay", ["no_action", "replay"])  # any one match counts
    assert is_correct("ingress_burst", ["scale_workers"])


def test_incorrect_when_no_match_or_empty():
    assert not is_correct("schema_drift", ["scale_workers"])  # wrong mitigation
    assert not is_correct("schema_drift", [])  # nothing executed
    assert not is_correct("schema_drift", ["no_action"])
    assert not is_correct("unknown_scenario", ["quarantine_partition"])  # no ground truth


def test_mitigations_are_disjoint_enough():
    # schema mitigations should not overlap with resource-scaling mitigations
    assert EXPECTED_ACTIONS["schema_drift"].isdisjoint(EXPECTED_ACTIONS["ingress_burst"])
