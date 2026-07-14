"""Unit tests for the ablation config → enabled-agents map."""

import pytest

from acde.orchestrator.configs import AGENT_CONFIGS, enabled_agents


def test_baseline_has_no_agents():
    assert enabled_agents("baseline") == set()


def test_full_has_all_four():
    assert enabled_agents("full") == {"monitoring", "recovery", "optimization", "schema"}


@pytest.mark.parametrize("config", ["recovery_only", "optimization_only", "schema_only"])
def test_single_agent_configs_include_monitoring(config):
    agents = enabled_agents(config)
    assert "monitoring" in agents  # detector for MTTR
    assert len(agents) == 2


def test_monitor_only():
    assert enabled_agents("monitor_only") == {"monitoring"}


def test_unknown_config_raises():
    with pytest.raises(KeyError):
        enabled_agents("turbo")


def test_six_configs_registered():
    assert set(AGENT_CONFIGS) == {
        "baseline",
        "monitor_only",
        "recovery_only",
        "optimization_only",
        "schema_only",
        "full",
    }
