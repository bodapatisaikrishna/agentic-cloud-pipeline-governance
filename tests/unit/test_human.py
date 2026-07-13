"""Unit tests for the human simulator (mocked acde.db)."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

from acde.human import simulator
from acde.human.simulator import HumanSimulator, sample_latency


class TestSampleLatency:
    def test_deterministic_for_same_key(self):
        a = sample_latency(seed=42, key=1, median_s=360, sigma=0.5)
        b = sample_latency(seed=42, key=1, median_s=360, sigma=0.5)
        assert a == b

    def test_varies_by_key(self):
        a = sample_latency(seed=42, key=1, median_s=360, sigma=0.5)
        b = sample_latency(seed=42, key=2, median_s=360, sigma=0.5)
        assert a != b

    def test_positive_and_near_median_magnitude(self):
        vals = [sample_latency(42, k, 360, 0.5) for k in range(200)]
        assert all(v > 0 for v in vals)
        median = sorted(vals)[len(vals) // 2]
        assert 180 < median < 720  # within a factor of ~2 of the 360s median


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(simulator, "db", fake)
    return fake


class TestAssignAndResolve:
    def test_assigns_latency_to_pending_rows(self, fake_db):
        fake_db.fetch_all.side_effect = [[{"id": 1}, {"id": 2}], []]  # assign query, then resolve
        sim = HumanSimulator(experiment_run="run-1", seed=42)
        assigned, _ = sim.assign_and_resolve(now=dt.datetime.now(dt.UTC))
        assert assigned == 2
        # each assignment updates simulated_latency_s
        updates = [
            c.args
            for c in fake_db.execute.call_args_list
            if "simulated_latency_s = %s" in c.args[0]
        ]
        assert len(updates) == 2

    def test_resolves_only_due_rows(self, fake_db):
        now = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
        old = now - dt.timedelta(seconds=500)  # requested 500s ago
        recent = now - dt.timedelta(seconds=5)  # requested 5s ago
        fake_db.fetch_all.side_effect = [
            [],  # nothing to assign
            [
                {"id": 1, "requested_ts": old, "simulated_latency_s": 300.0},  # due (300 < 500)
                {"id": 2, "requested_ts": recent, "simulated_latency_s": 300.0},  # not due
            ],
        ]
        sim = HumanSimulator(experiment_run="run-1", seed=42)
        _, resolved = sim.assign_and_resolve(now=now)
        assert resolved == 1
        completed = [
            c.args for c in fake_db.execute.call_args_list if "completed_ts = %s" in c.args[0]
        ]
        assert len(completed) == 1
        assert completed[0][1][1] == 1  # only row id 1 completed
