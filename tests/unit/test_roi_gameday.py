"""Unit tests for the ROI report and game-day staging guard (mocked db/connector)."""

from unittest.mock import MagicMock

import pytest

from acde.config import Settings
from acde.ops import gameday, roi


class TestRoi:
    def test_report_aggregates_and_estimates(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.side_effect = [
            {"n": 10},  # executed
            {"n": 2},  # escalated
            {"n": 3},  # interventions
            {"t": 5000},  # tokens
        ]
        fake.fetch_all.return_value = [
            {"mttr": 5.0, "resolution": "replay"},
            {"mttr": 300.0, "resolution": "human"},
            {"mttr": 1.0, "resolution": "quarantine_partition"},
        ]
        monkeypatch.setattr(roi, "db", fake)
        monkeypatch.setattr(
            roi, "get_settings", lambda: Settings(_env_file=None, human_latency_median_s=360.0)
        )
        r = roi.roi_report(since_hours=24)
        assert r["actions_executed"] == 10
        assert r["incidents_auto_resolved"] == 2  # replay + quarantine (not the human one)
        assert r["estimated_operator_hours_saved"] == round(2 * 360 / 3600, 2)
        assert "estimate" in r["note"]


class TestGamedayGuard:
    def test_refuses_against_production_connector(self, monkeypatch):
        conn = MagicMock(is_production=True, name="airflow")
        monkeypatch.setattr("acde.connectors.get_connector", lambda: conn)
        with pytest.raises(RuntimeError, match="refusing to run game-day"):
            gameday.run_gameday("schema_drift", env="prod")

    def test_force_overrides_guard_but_needs_research(self, monkeypatch):
        conn = MagicMock(is_production=True)
        monkeypatch.setattr("acde.connectors.get_connector", lambda: conn)
        # force past the staging guard; without chaos importable it should raise the research hint
        # (we simulate by making the chaos import fail)
        import builtins

        real_import = builtins.__import__

        def _no_chaos(name, *a, **k):
            if name.startswith("acde.chaos"):
                raise ImportError("no chaos")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _no_chaos)
        with pytest.raises(RuntimeError, match="research extra"):
            gameday.run_gameday("schema_drift", env="staging", force=True)
