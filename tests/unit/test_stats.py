"""Unit tests for the statistics core — hand-computed known answers."""

import math

import pytest

from acde.analysis import stats


class TestMedianIqr:
    def test_median(self):
        assert stats.median([1, 2, 3, 4]) == 2.5
        assert stats.median([5]) == 5.0

    def test_median_empty_is_nan(self):
        assert math.isnan(stats.median([]))

    def test_iqr(self):
        assert stats.iqr([1, 2, 3, 4, 5]) == 2.0  # Q3=4, Q1=2

    def test_iqr_short(self):
        assert stats.iqr([7]) == 0.0


class TestBootstrapCi:
    def test_deterministic_for_seed(self):
        data = [10, 11, 12, 13, 14, 15]
        assert stats.bootstrap_ci(data, seed=1) == stats.bootstrap_ci(data, seed=1)

    def test_brackets_point_estimate(self):
        data = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        lo, hi = stats.bootstrap_ci(data, seed=7)
        assert lo <= stats.median(data) <= hi

    def test_single_point(self):
        assert stats.bootstrap_ci([5.0]) == (5.0, 5.0)

    def test_empty_is_nan(self):
        lo, hi = stats.bootstrap_ci([])
        assert math.isnan(lo) and math.isnan(hi)


class TestPairedWilcoxon:
    def test_monotone_difference_significant(self):
        a = [1, 2, 3, 4, 5, 6, 7, 8]
        b = [10, 11, 12, 13, 14, 15, 16, 17]  # b always larger
        _, p = stats.paired_wilcoxon(a, b)
        assert p < 0.05

    def test_identical_is_nonsignificant(self):
        _, p = stats.paired_wilcoxon([1, 2, 3], [1, 2, 3])
        assert p == 1.0

    def test_length_mismatch(self):
        stat, p = stats.paired_wilcoxon([1, 2], [1, 2, 3])
        assert math.isnan(stat) and p == 1.0


class TestHolmBonferroni:
    def test_ordering_and_rejection(self):
        # p = [0.01, 0.04, 0.03], m=3: sorted 0.01,0.03,0.04 -> adj 0.03, 0.06, 0.06
        result = stats.holm_bonferroni([0.01, 0.04, 0.03])
        adj = [round(r[0], 4) for r in result]
        assert adj == [0.03, 0.06, 0.06]
        assert result[0][1] is True  # 0.03 < 0.05
        assert result[1][1] is False  # 0.06 not < 0.05

    def test_empty(self):
        assert stats.holm_bonferroni([]) == []


class TestCliffsDelta:
    def test_fully_greater_is_plus_one(self):
        assert stats.cliffs_delta([10, 20, 30], [1, 2, 3]) == 1.0

    def test_fully_less_is_minus_one(self):
        assert stats.cliffs_delta([1, 2, 3], [10, 20, 30]) == -1.0

    def test_identical_is_zero(self):
        assert stats.cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0

    def test_empty_is_zero(self):
        assert stats.cliffs_delta([], [1, 2]) == 0.0


@pytest.mark.parametrize("bad", [[], [1.0]])
def test_bootstrap_edge_cases_no_crash(bad):
    stats.bootstrap_ci(bad)  # must not raise


class TestWilsonCi:
    def test_perfect_rate_still_has_a_lower_bound(self):
        lo, hi = stats.wilson_ci(400, 400)
        assert hi == pytest.approx(1.0)
        assert lo == pytest.approx(0.99046, abs=1e-4)  # ~ 3.84/(400+3.84) complement

    def test_matches_known_value(self):
        lo, hi = stats.wilson_ci(8, 10)  # textbook example: Wilson 95% for 8/10
        assert (lo, hi) == pytest.approx((0.4902, 0.9433), abs=1e-3)

    def test_zero_successes_and_empty(self):
        lo, hi = stats.wilson_ci(0, 50)
        assert lo == pytest.approx(0.0, abs=1e-12) and 0.0 < hi < 0.1
        assert stats.wilson_ci(0, 0) == (0.0, 1.0)

    def test_rejects_impossible_counts(self):
        with pytest.raises(ValueError):
            stats.wilson_ci(11, 10)


class TestMannWhitneyAndIntervals:
    def test_mann_whitney_separated_groups(self):
        u, p = stats.mann_whitney([1, 2, 3, 4, 5, 6], [10, 11, 12, 13, 14, 15])
        assert u == 0.0 and p < 0.01

    def test_mann_whitney_identical_and_empty(self):
        _, p = stats.mann_whitney([1, 2, 3], [1, 2, 3])
        assert p > 0.9
        assert stats.mann_whitney([], [1.0]) == (0.0, 1.0)
        assert stats.mann_whitney([1.0, 1.0], [1.0, 1.0])[1] == 1.0  # all ties: no evidence

    def test_cliffs_delta_ci_brackets_the_point_estimate_and_is_seeded(self):
        a = [1.0, 2.0, 3.0, 8.0, 9.0, 10.0]
        b = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        lo, hi = stats.cliffs_delta_ci(a, b, n_resamples=500, seed=1)
        assert lo <= stats.cliffs_delta(a, b) <= hi
        assert (lo, hi) == stats.cliffs_delta_ci(a, b, n_resamples=500, seed=1)  # deterministic

    def test_cliffs_delta_ci_perfect_separation_is_tight(self):
        lo, hi = stats.cliffs_delta_ci([10, 11, 12, 13], [1, 2, 3, 4], n_resamples=200, seed=0)
        assert lo == hi == 1.0

    def test_median_diff_ci(self):
        lo, hi = stats.median_diff_ci([10.0] * 8, [1.0] * 8, n_resamples=200, seed=0)
        assert lo == hi == 9.0
        assert stats.median_diff_ci([], [1.0]) == (0.0, 0.0)
        assert stats.cliffs_delta_ci([], [1.0]) == (0.0, 0.0)
