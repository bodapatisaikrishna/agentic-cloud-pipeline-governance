"""Unit tests for chaos scenarios + the seed policy."""

import pytest

from acde.chaos import scenarios
from acde.chaos.scenarios import all_scenarios, get_scenario, run_seed


class TestRunSeed:
    def test_deterministic(self):
        assert run_seed("full", "schema_drift", 3) == run_seed("full", "schema_drift", 3)

    def test_differs_by_config_scenario_replicate(self):
        base = run_seed("full", "schema_drift", 0)
        assert run_seed("baseline", "schema_drift", 0) != base
        assert run_seed("full", "ingress_burst", 0) != base
        assert run_seed("full", "schema_drift", 1) != base

    def test_in_uint32_range(self):
        assert 0 <= run_seed("full", "schema_drift", 7) < 2**32


class TestScenarios:
    def test_four_scenarios_registered(self):
        assert set(all_scenarios()) == {
            "schema_drift",
            "upstream_delay",
            "resource_contention",
            "ingress_burst",
        }

    def test_fault_types_match_names(self):
        for name, scenario in all_scenarios().items():
            assert scenario.fault_type == name

    def test_all_within_hard_cap(self):
        for scenario in all_scenarios().values():
            assert scenario.within_cap()
            assert scenario.total_s == pytest.approx(
                scenario.warmup_s + scenario.fault_window_s + scenario.recovery_s
            )

    def test_unknown_scenario_raises(self):
        with pytest.raises(KeyError):
            get_scenario("meteor")

    def test_over_cap_detected(self, monkeypatch):
        s = get_scenario("schema_drift")
        monkeypatch.setattr(scenarios, "get_settings", lambda: _cap(1.0))
        assert not s.within_cap()


class _cap:
    def __init__(self, cap):
        self.chaos_hard_cap_s = cap
