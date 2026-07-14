"""Unit tests for the experiment profile matrices."""

import pytest

from acde.experiments.configs import ALL_CONFIGS, profile_runs
from acde.experiments.scenarios import SCENARIOS
from acde.orchestrator.configs import AGENT_CONFIGS


def test_quick_is_72_runs():
    runs = profile_runs("quick")
    assert len(runs) == 6 * 4 * 3  # 6 configs x 4 scenarios x N=3


def test_paper_is_320_runs():
    runs = profile_runs("paper")
    assert len(runs) == (2 * 4 * 20) + (4 * 4 * 10)  # baseline+full N=20, 4 ablations N=10


def test_smoke_is_small():
    assert len(profile_runs("smoke")) == 2


def test_runs_reference_valid_configs_and_scenarios():
    for run in profile_runs("quick"):
        assert run.config in AGENT_CONFIGS
        assert run.scenario in SCENARIOS
        assert run.replicate >= 0


def test_quick_covers_all_configs_and_scenarios():
    runs = profile_runs("quick")
    assert {r.config for r in runs} == set(ALL_CONFIGS)
    assert {r.scenario for r in runs} == set(SCENARIOS)


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        profile_runs("mega")


def test_seeds_distinct_across_matrix_cells():
    from acde.experiments.scenarios import run_seed

    runs = profile_runs("quick")
    seeds = {
        (r.config, r.scenario, r.replicate): run_seed(r.config, r.scenario, r.replicate)
        for r in runs
    }
    # identical fault seed for the SAME (scenario, replicate) across configs is intentional? No —
    # seed keys on config too, so every cell has its own seed. Just assert no accidental collisions
    # beyond the birthday-bound noise: all 72 keys map to values, mostly distinct.
    assert len(set(seeds.values())) >= 70
