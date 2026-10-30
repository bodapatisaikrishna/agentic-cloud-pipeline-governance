"""Unit tests for the v2 statistics: equivalence (TOST), stratified permutation test, power."""

import numpy as np
import pytest

from acde.analysis import power, stats


class TestTost:
    def test_identical_samples_are_equivalent_within_a_margin(self):
        a = list(np.linspace(100, 200, 40))
        lo, hi, eq = stats.tost_median_diff(a, a, margin=20, seed=1)
        assert lo <= 0 <= hi and eq

    def test_shifted_samples_are_not_equivalent(self):
        a = list(np.linspace(100, 200, 40))
        b = [x + 50 for x in a]
        assert not stats.tost_median_diff(a, b, margin=20, seed=1)[2]

    def test_wide_interval_is_inconclusive_not_equivalent(self):
        rng = np.random.default_rng(0)
        a, b = list(rng.normal(0, 100, 6)), list(rng.normal(0, 100, 6))
        assert not stats.tost_median_diff(a, b, margin=5, seed=1)[2]

    def test_proportions(self):
        a, b = [1.0, 0.0] * 50, [0.0, 1.0] * 50
        assert stats.tost_proportion_diff(a, b, margin=0.15, seed=2)[2]
        assert not stats.tost_proportion_diff([1.0] * 50, [0.0] * 50, margin=0.15)[2]
        assert stats.tost_proportion_diff([], [1.0], margin=0.1)[2] is False


class TestStratifiedPermutation:
    def test_real_within_stratum_effect_is_detected(self):
        a = {"s1": [1.0, 2, 3, 4, 5, 6], "s2": [101.0, 102, 103, 104, 105, 106]}
        b = {"s1": [11.0, 12, 13, 14, 15, 16], "s2": [111.0, 112, 113, 114, 115, 116]}
        assert stats.stratified_permutation_test(a, b, n_permutations=999, seed=3) < 0.01

    def test_stratum_imbalance_alone_is_not_an_effect(self):
        # a sits mostly in the slow stratum; a pooled test would call that a difference.
        a = {"fast": [1.0, 2.0], "slow": [100.0, 101, 102, 103, 104, 105]}
        b = {"fast": [1.5, 2.5, 1.2, 2.2, 1.8, 2.1], "slow": [100.5, 102.5]}
        assert stats.stratified_permutation_test(a, b, n_permutations=999, seed=3) > 0.2

    def test_no_shared_strata(self):
        assert stats.stratified_permutation_test({"x": [1.0]}, {"y": [2.0]}) == 1.0


class TestPower:
    BASE = list(np.random.default_rng(0).lognormal(np.log(360), 0.5, 80))

    def test_power_grows_with_the_effect(self):
        small = power.power_at_ratio(self.BASE, 0.05, 80, 0.05, n_sim=100, seed=1)
        large = power.power_at_ratio(self.BASE, 0.5, 80, 0.05, n_sim=100, seed=1)
        assert small < 0.5 < large

    def test_mde_is_found_and_bounded(self):
        mde = power.min_detectable_ratio(self.BASE, 80, 0.05, n_sim=100, seed=1)
        assert mde is not None and 0.05 <= mde <= 0.5

    def test_unreachable_power_returns_none(self):
        assert power.min_detectable_ratio(self.BASE, 3, 1e-6, grid=(0.05,), n_sim=20) is None
