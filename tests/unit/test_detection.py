"""Unit tests for statistical anomaly detection."""

import datetime as dt

from acde.agents.detection import detect_anomalies, zscore
from acde.contracts import ResourceUsage, TaskRunObservation, TelemetrySnapshot

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def _snap(**kw) -> TelemetrySnapshot:
    base = {"experiment_run": "t", "window_start": NOW, "window_end": NOW}
    base.update(kw)
    return TelemetrySnapshot(**base)


class TestZscore:
    def test_zero_spread(self):
        assert zscore([5, 5, 5], 5) == 0.0

    def test_short_series(self):
        assert zscore([5], 100) == 0.0

    def test_outlier_high_z(self):
        assert zscore([1, 2, 3, 2, 1], 20) > 3


class TestDetectAnomalies:
    def test_task_failure(self):
        snap = _snap(
            task_runs=[
                TaskRunObservation(
                    run_id="r", dag_id="tpcds_ingest", task_id="ingest", state="failed"
                )
            ]
        )
        kinds = {a.kind for a in detect_anomalies(snap)}
        assert "task_failed" in kinds

    def test_freshness_breach(self):
        snap = _snap(pipeline_metrics={"freshness_s": 200.0})
        assert any(a.kind == "freshness_breach" for a in detect_anomalies(snap))

    def test_freshness_within_sla_no_anomaly(self):
        snap = _snap(pipeline_metrics={"freshness_s": 10.0})
        assert not any(a.kind == "freshness_breach" for a in detect_anomalies(snap))

    def test_cpu_high(self):
        snap = _snap(
            resource_usage=[
                ResourceUsage(component="redpanda", cpu_pct=95.0, mem_mb=100, workers=1, ts=NOW)
            ]
        )
        assert any(a.kind == "cpu_high" for a in detect_anomalies(snap))

    def test_open_fault_and_schema_breaking(self):
        snap = _snap(
            open_anomalies=[{"fault_type": "schema_drift", "scenario": "schema_drift"}],
            schema_compat="breaking",
        )
        kinds = {a.kind for a in detect_anomalies(snap)}
        assert "open_fault:schema_drift" in kinds
        assert "schema_breaking" in kinds

    def test_nominal_no_anomalies(self):
        assert detect_anomalies(_snap()) == []
