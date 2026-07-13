"""Unit tests for freshness metrics (mocked acde.db)."""

import datetime as dt
from unittest.mock import MagicMock

import pytest

from acde.telemetry import freshness


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(freshness, "db", fake)
    return fake


class TestStreamingFreshness:
    def test_records_latest_window_per_pipeline(self, fake_db):
        fake_db.fetch_all.return_value = [
            {"pipeline_id": "stream", "freshness_s": 12.5},
            {"pipeline_id": "other", "freshness_s": 41.0},
        ]
        recorded = freshness.streaming_freshness(experiment_run="run-1")
        assert recorded == [("stream", 12.5), ("other", 41.0)]
        # each write is an INSERT into pipeline_metrics with metric 'freshness_s'
        writes = [c.args for c in fake_db.execute.call_args_list]
        assert len(writes) == 2
        assert all("pipeline_metrics" in w[0] for w in writes)
        assert writes[0][1] == ("stream", "freshness_s", 12.5, "run-1")


class TestBatchFreshness:
    def test_records_partition_staleness(self, fake_db, monkeypatch):
        created = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=120)
        fake_db.fetch_all.return_value = [{"dataset": "tpcds_daily_revenue", "created_ts": created}]
        recorded = freshness.batch_freshness(experiment_run="run-1")
        assert recorded[0][0] == "tpcds_daily_revenue"
        assert recorded[0][1] == pytest.approx(120, abs=5)
        assert fake_db.execute.call_args.args[1][1] == "batch_freshness_s"
