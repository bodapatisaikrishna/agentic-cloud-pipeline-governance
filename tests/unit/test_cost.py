"""Unit tests for the cost model — pure math verified against hand fixtures."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

from acde.telemetry import cost
from acde.telemetry.cost import cost_units, integrate_worker_seconds

T0 = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)


def at(seconds: int) -> dt.datetime:
    return T0 + dt.timedelta(seconds=seconds)


class TestIntegrateWorkerSeconds:
    def test_hand_fixture_two_then_four(self):
        # 2 workers for [0,30), 4 workers for [30,60) over a 60s window => 2*30 + 4*30 = 180.
        samples = [(at(0), 2.0), (at(30), 4.0)]
        assert integrate_worker_seconds(samples, at(0), at(60)) == pytest.approx(180.0)

    def test_constant_workers(self):
        samples = [(at(0), 3.0)]
        assert integrate_worker_seconds(samples, at(0), at(60)) == pytest.approx(180.0)

    def test_sample_before_window_establishes_entry_count(self):
        # A sample at t=-10 (2 workers) holds through the whole [0,60) window.
        samples = [(at(-10), 2.0)]
        assert integrate_worker_seconds(samples, at(0), at(60)) == pytest.approx(120.0)

    def test_change_midwindow_from_prior_sample(self):
        samples = [(at(-10), 2.0), (at(20), 5.0)]
        # 2 workers for [0,20) = 40, 5 workers for [20,60) = 200 => 240
        assert integrate_worker_seconds(samples, at(0), at(60)) == pytest.approx(240.0)

    def test_empty_and_degenerate(self):
        assert integrate_worker_seconds([], at(0), at(60)) == 0.0
        assert integrate_worker_seconds([(at(0), 3.0)], at(60), at(0)) == 0.0


class TestCostUnits:
    def test_matches_disclosed_formula(self):
        # 180 compute-unit-seconds @0.05 + 2 gb-hours @0.01 = 9.0 + 0.02 = 9.02
        assert cost_units(180.0, 2.0, rate_compute=0.05, rate_storage=0.01) == pytest.approx(9.02)

    def test_uses_settings_rates_by_default(self):
        assert cost_units(100.0, 0.0) == pytest.approx(5.0)  # 100 * 0.05


class TestComputeCostWindows:
    def test_writes_ledger_rows_with_correct_math(self, monkeypatch):
        fake = MagicMock()
        # one 60s span of samples: streaming=2 workers, batch=1 worker
        fake.fetch_one.side_effect = [
            {"lo": at(0), "hi": at(0)},  # span
        ]

        def fetch_all(sql, params=None):
            if "resource_usage" in sql and "workers" in sql:
                component = params[1]
                n = {"streaming": 2.0, "batch": 1.0}[component]
                return [{"ts": at(0), "workers": n}]
            return []

        fake.fetch_all.side_effect = fetch_all
        monkeypatch.setattr(cost, "db", fake)
        monkeypatch.setattr(cost, "warehouse_size_gb", lambda: 0.0)

        written = cost.compute_cost_windows(experiment_run="run-1", window_s=60)
        # streaming + batch + storage = 3 rows for the single window
        assert written == 3
        inserts = [c.args for c in fake.execute.call_args_list if "INSERT" in c.args[0]]
        # find the streaming row: cost = 2*60*0.05 = 6.0
        streaming = next(a[1] for a in inserts if a[1][1] == "streaming")
        assert streaming[2] == pytest.approx(120.0)  # compute_unit_seconds
        assert streaming[4] == pytest.approx(6.0)  # cost_units

    def test_no_samples_writes_nothing(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"lo": None, "hi": None}
        monkeypatch.setattr(cost, "db", fake)
        assert cost.compute_cost_windows(experiment_run="empty") == 0
