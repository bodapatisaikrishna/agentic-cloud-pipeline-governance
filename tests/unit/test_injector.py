"""Unit tests for the failure injector — determinism is the headline."""

import datetime as dt
from unittest.mock import MagicMock

import pandas as pd
import pytest

from acde.chaos import injector
from acde.chaos.injector import (
    FaultInjector,
    build_delayed_records,
    corrupt_frame,
    plan_timeline,
)
from acde.chaos.scenarios import all_scenarios, get_scenario
from acde.dataplane.batch import pipeline


class TestPlanDeterminism:
    @pytest.mark.parametrize("name", list(all_scenarios()))
    def test_same_seed_identical_plan(self, name):
        s = get_scenario(name)
        assert plan_timeline(s, 12345).as_dict() == plan_timeline(s, 12345).as_dict()

    @pytest.mark.parametrize("name", list(all_scenarios()))
    def test_different_seed_differs(self, name):
        s = get_scenario(name)
        assert plan_timeline(s, 1).as_dict() != plan_timeline(s, 2).as_dict()

    def test_plan_carries_scenario_and_fault_type(self):
        plan = plan_timeline(get_scenario("ingress_burst"), 7)
        assert plan.scenario == "ingress_burst"
        assert plan.fault_type == "ingress_burst"
        assert 5.0 <= plan.params["burst_factor"] <= 10.0

    def test_offset_after_warmup(self):
        s = get_scenario("schema_drift")
        plan = plan_timeline(s, 9)
        assert plan.at_offset_s >= s.warmup_s


class TestCorruptFrame:
    def _df(self):
        return pd.DataFrame(
            {
                "ss_sold_date": ["2026-01-01"],
                "ss_item_sk": [1],
                "ss_quantity": [2],
                "ss_net_paid": [10.0],
            }
        )

    def test_drop_removes_column(self):
        out = corrupt_frame(self._df(), "drop", "ss_net_paid")
        assert "ss_net_paid" not in out.columns

    def test_retype_breaks_numeric(self):
        out = corrupt_frame(self._df(), "retype", "ss_net_paid")
        assert out["ss_net_paid"].iloc[0] == "CORRUPT"

    def test_drop_fails_validate_as_missing_column(self):
        out = corrupt_frame(self._df(), "drop", "ss_net_paid")
        with pytest.raises(pipeline.SchemaValidationError, match="missing"):
            pipeline.validate(
                out, ["ss_sold_date", "ss_net_paid"], ["ss_net_paid"], numeric=["ss_net_paid"]
            )

    def test_retype_fails_validate_as_non_numeric(self):
        out = corrupt_frame(self._df(), "retype", "ss_net_paid")
        with pytest.raises(pipeline.SchemaValidationError, match="non-numeric"):
            pipeline.validate(
                out, ["ss_sold_date", "ss_net_paid"], ["ss_net_paid"], numeric=["ss_net_paid"]
            )

    def test_drift_columns_are_all_validated_numeric(self):
        from acde.chaos.injector import DRIFT_COLUMNS

        assert set(DRIFT_COLUMNS) <= {"ss_net_paid", "ss_quantity"}


class TestBuildDelayedRecords:
    def _records(self, n=100):
        base = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
        return [
            {"event_ts": (base + dt.timedelta(seconds=i)).isoformat(), "key": "k", "value": 1.0}
            for i in range(n)
        ]

    def test_drops_and_shifts_deterministically(self):
        a = build_delayed_records(self._records(), delay_ms=1000, drop_pct=0.5, seed=3)
        b = build_delayed_records(self._records(), delay_ms=1000, drop_pct=0.5, seed=3)
        assert [r["event_ts"] for r in a] == [r["event_ts"] for r in b]
        assert len(a) < 100  # some dropped

    def test_events_shifted_older(self):
        recs = self._records(10)
        out = build_delayed_records(recs, delay_ms=2000, drop_pct=0.0, seed=1)
        assert len(out) == 10
        assert dt.datetime.fromisoformat(out[0]["event_ts"]) < dt.datetime.fromisoformat(
            recs[0]["event_ts"]
        )


class TestInject:
    def test_records_failure_event_and_dispatches(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(injector, "db", fake)
        applied = {}
        monkeypatch.setattr(
            FaultInjector, "_apply_schema_drift", lambda self, plan: applied.update(hit=True)
        )
        event_id = FaultInjector(experiment_run="run-1").inject("schema_drift", seed=42)
        assert event_id
        assert applied["hit"]
        sql = fake.execute.call_args.args[0]
        assert "telemetry.failure_events" in sql
        assert fake.execute.call_args.args[1][2] == "schema_drift"  # scenario column
