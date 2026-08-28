"""Unit tests for the decision-quality ground truth."""

from acde.experiments.decision_quality import (
    EXPECTED_ACTIONS,
    LIVE_EXPECTED_ACTIONS,
    expected_for,
    expected_for_live,
    is_correct,
    is_correct_live,
)


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


class TestLiveExpectedActions:
    """D-100: the real-detector-kind taxonomy, distinct from EXPECTED_ACTIONS's chaos-scenario
    keys -- this is the exact gap that would otherwise score every real incident 'incorrect'."""

    def test_covers_every_real_detector_kind(self):
        # agents/detection.py::detect_anomalies's actual emitted kinds (minus open_fault:* echoes,
        # which are deliberately unscored -- see expected_for_live's docstring).
        for kind in ("task_failed", "freshness_breach", "cpu_high", "schema_breaking"):
            assert expected_for_live(kind), f"no live ground truth for {kind}"

    def test_a_chaos_scenario_name_is_not_a_live_fault_type(self):
        # mutation-test proof of the exact bug this taxonomy fixes: the chaos key must NOT also
        # resolve here, or a real "schema_breaking" incident could accidentally fall back to
        # "schema_drift"'s set through some future refactor and silently keep working by luck
        # rather than by design.
        assert expected_for_live("schema_drift") == set()

    def test_correct_when_action_in_the_live_expected_set(self):
        assert is_correct_live("schema_breaking", ["quarantine_partition"])
        assert is_correct_live("task_failed", ["replay"])
        assert is_correct_live("cpu_high", ["scale_workers"])
        assert is_correct_live("freshness_breach", ["adjust_pool_slots"])

    def test_incorrect_when_no_match_empty_or_unmapped(self):
        assert not is_correct_live("schema_breaking", ["scale_workers"])
        assert not is_correct_live("task_failed", [])
        assert not is_correct_live("open_fault:cpu_high", ["scale_workers"])  # echo, not a kind

    def test_each_live_set_mirrors_the_owning_agent_module(self):
        # locks the "not a guess, copied from the agent that owns it" design claim in place.
        assert LIVE_EXPECTED_ACTIONS["cpu_high"] == {
            "scale_workers",
            "adjust_pool_slots",
            "reprioritize_pipeline",
        }
        assert LIVE_EXPECTED_ACTIONS["schema_breaking"] == {
            "quarantine_partition",
            "block_ingestion",
            "apply_mapping",
        }
