"""Unit tests for the experiment profile matrices."""

import pytest

from acde.experiments.configs import ALL_CONFIGS, profile_runs
from acde.experiments.scenarios import SCENARIOS


def test_quick_is_96_runs():
    runs = profile_runs("quick")
    assert len(runs) == 8 * 4 * 3  # 8 configs x 4 scenarios x N=3


def test_paper_run_count():
    runs = profile_runs("paper")
    assert len(runs) == (4 * 4 * 20) + (4 * 4 * 10)  # 3 baselines+full N=20, 4 ablations N=10


def test_smoke_is_small():
    assert len(profile_runs("smoke")) == 2


def test_runs_reference_valid_configs_and_scenarios():
    for run in profile_runs("quick"):
        assert run.config in ALL_CONFIGS
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
    # seed keys on config too, so every cell has its own seed. Just assert no accidental collisions
    # beyond the birthday-bound noise: nearly all 96 keys map to distinct values.
    assert len(set(seeds.values())) >= 94
