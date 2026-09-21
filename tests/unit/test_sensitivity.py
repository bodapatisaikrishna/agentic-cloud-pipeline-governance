"""Unit tests for the sensitivity analyses (pure functions over synthetic frames)."""

import math

import pandas as pd
import pytest

from acde.analysis import sensitivity as sens
from acde.analysis.sensitivity import ModelParams
from acde.human.simulator import sample_latency

P = ModelParams()


def _df(rows):
    return pd.DataFrame(rows, columns=["config", "metric", "value"])


class TestHumanScaleFamily:
    def test_sampler_is_exactly_linear_in_the_median(self):
        """The break-even's premise, verified against the real sampler (not assumed)."""
        for seed, key in [(1, 1), (42, 7), (2**31, 12345)]:
            base = sample_latency(seed, key, 360.0, 0.5)
            for m in (60.0, 180.0, 720.0, 3600.0):
                assert sample_latency(seed, key, m, 0.5) == pytest.approx(base * m / 360.0)

    def test_break_even_closed_form(self):
        # baseline 390 s at a 360 s human; automation 57 s -> wins until the human is ~52.6 s
        assert sens.break_even_human_median(57.0, 390.0, 360.0) == pytest.approx(52.615, abs=1e-2)
        # automation slower than the baseline -> break-even above the assumed median
        assert sens.break_even_human_median(500.0, 390.0, 360.0) > 360.0

    def test_break_even_actually_equates_the_mttrs(self):
        m_star = sens.break_even_human_median(100.0, 400.0, 360.0)
        assert 400.0 * m_star / 360.0 == pytest.approx(100.0)

    def test_degenerate_baseline(self):
        assert sens.break_even_human_median(1.0, 0.0, 360.0) == math.inf


class TestWinProbability:
    def test_instant_automation_always_wins(self):
        assert sens.win_probability([0.0, 0.0], 360.0, 0.5) == 1.0

    def test_equal_to_median_is_a_coin_flip(self):
        assert sens.win_probability([360.0], 360.0, 0.5) == pytest.approx(0.5)

    def test_monotone_in_human_median(self):
        ps = [sens.win_probability([100.0], m, 0.5) for m in (60, 120, 360, 1200)]
        assert ps == sorted(ps)

    def test_wider_sigma_pulls_towards_half(self):
        narrow = sens.win_probability([100.0], 360.0, 0.25)
        wide = sens.win_probability([100.0], 360.0, 1.0)
        assert 0.5 < wide < narrow < 1.0

    def test_empty_and_grid_shape(self):
        assert sens.win_probability([], 360.0, 0.5) == 0.0
        grid = sens.human_latency_grid([10.0], (60.0, 360.0), (0.5, 1.0))
        assert len(grid) == 4 and all(0 <= g["p_automation_faster"] <= 1 for g in grid)


class TestCost:
    def test_provisioning_terms(self):
        assert P.provisioning("baseline") == 8.0 * 300.0 * 0.05
        assert P.provisioning("full") == 3.0 * 300.0 * 0.05
        assert P.provisioning("full", rightsized=1.0, horizon_s=100.0) == 1.0 * 100.0 * 0.05

    def test_measured_strips_recorded_provisioning(self):
        df = _df([("baseline", "cost_units", 10.0 + P.provisioning("baseline"))])
        assert sens.measured_cost(df, "baseline", P) == [pytest.approx(10.0)]

    def test_reduction_at_recorded_params(self):
        # equal measured cost: the whole gap is provisioning (120 vs 45 -> 62.5% cheaper)
        assert sens.cost_reduction(0, 0, "full", "baseline", P) == pytest.approx(37.5 / 60 * 100)

    def test_break_even_static_units_is_cost_parity(self):
        s_star = sens.cost_break_even_static_units(measured_auto=20.0, measured_base=5.0, params=P)
        at_parity = sens.cost_reduction(20.0, 5.0, "full", "baseline", P, static=s_star)
        assert at_parity == pytest.approx(0.0)

    def test_agents_that_add_measured_cost_need_more_overprovisioning(self):
        cheaper = sens.cost_break_even_static_units(0.0, 0.0, P)
        dearer = sens.cost_break_even_static_units(15.0, 0.0, P)
        assert dearer > cheaper == pytest.approx(P.rightsized_units)

    def test_sweep_shape_and_direction(self):
        df = _df([("baseline", "cost_units", 6.0 + 120.0), ("full", "cost_units", 6.0 + 45.0)])
        grid = sens.cost_sweep(df, P, (4.0, 8.0, 12.0), (3.0,), (300.0,))
        assert len(grid) == 3
        pct = [g["cost_reduction_pct"] for g in grid]
        assert pct == sorted(pct)  # more static over-provisioning -> bigger saving


class TestReport:
    def _frame(self):
        rows = []
        for i in range(6):
            rows += [
                ("baseline", "mttr_s", 390.0 + i),
                ("full", "mttr_s", 57.0 + i),
                ("baseline", "cost_units", 6.0 + P.provisioning("baseline")),
                ("full", "cost_units", 8.0 + P.provisioning("full")),
                ("rule_based", "mttr_s", 30.0),
                ("rule_based", "cost_units", 6.0 + P.provisioning("rule_based")),
            ]
        return _df(rows)

    def test_report_structure(self):
        rep = sens.sensitivity_report(self._frame(), P)
        assert set(rep["human_latency"]["per_config"]) == {"full", "rule_based"}
        full = rep["human_latency"]["per_config"]["full"]
        assert full["break_even_human_median_s"] == pytest.approx(360.0 * 59.5 / 392.5, rel=1e-3)
        assert len(full["win_probability_grid"]) == len(sens.MEDIAN_GRID) * len(sens.SIGMA_GRID)
        assert rep["cost_by_config"]["full"]["break_even_static_units"] is not None
        rule_based = rep["cost_by_config"]["rule_based"]
        assert rule_based["break_even_static_units"] is None  # does not right-size
        assert rep["cost_sweep_full_vs_baseline"]

    def test_from_settings_matches_defaults(self):
        p = ModelParams.from_settings()
        assert (p.human_median_s, p.static_units, p.rightsized_units) == (360.0, 8.0, 3.0)
        assert "full" in p.rightsizing_configs

    def test_no_full_config_skips_sweep(self):
        df = _df([("baseline", "mttr_s", 1.0), ("rule_based", "mttr_s", 1.0)])
        assert sens.sensitivity_report(df, P)["cost_sweep_full_vs_baseline"] == []
