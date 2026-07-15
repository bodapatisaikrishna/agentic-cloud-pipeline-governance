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
