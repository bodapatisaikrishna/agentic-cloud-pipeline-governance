"""Integration tests for Phase 2 telemetry (requires `make up` + `make seed`).

Triggers a batch DAG, runs the collector a few ticks, aggregates the cost ledger, and
asserts every telemetry table fills for the run and that one cost window recomputes by hand.
"""

from __future__ import annotations

import time

import httpx
import pytest

from acde import db
from acde.config import get_settings
from acde.telemetry import cost
from acde.telemetry.collector import TelemetryCollector

pytestmark = pytest.mark.integration

RUN = "itest-telemetry"


def _trigger_tpcds() -> None:
    s = get_settings()
    with httpx.Client(
        base_url=s.airflow_url, auth=(s.airflow_user, s.airflow_password), timeout=30
    ) as c:
        c.patch("/dags/tpcds_ingest", json={"is_paused": False}).raise_for_status()
        run_id = f"tel__{int(time.time())}"
        c.post("/dags/tpcds_ingest/dagRuns", json={"dag_run_id": run_id}).raise_for_status()
        deadline = time.time() + 120
        while time.time() < deadline:
            state = c.get(f"/dags/tpcds_ingest/dagRuns/{run_id}").json()["state"]
            if state in {"success", "failed"}:
                assert state == "success"
                return
            time.sleep(3)
        pytest.fail("tpcds_ingest did not finish")


def test_telemetry_tables_fill_and_cost_is_consistent():
    for table in ("task_runs", "resource_usage", "pipeline_metrics", "cost_ledger"):
        db.execute(f"DELETE FROM telemetry.{table} WHERE experiment_run = %s", (RUN,))

    _trigger_tpcds()
    collector = TelemetryCollector(experiment_run=RUN)
    for _ in range(3):
        collector.collect_task_runs()
        collector.collect_resource_usage()
        time.sleep(2)
    from acde.telemetry import freshness

    freshness.collect(RUN)
    rows_written = cost.compute_cost_windows(experiment_run=RUN, window_s=60)
    assert rows_written > 0

    # every table has rows for this run
    for table in ("task_runs", "resource_usage", "pipeline_metrics", "cost_ledger"):
        n = db.fetch_one(
            f"SELECT count(*) AS n FROM telemetry.{table} WHERE experiment_run = %s", (RUN,)
        )
        assert n is not None and n["n"] > 0, f"{table} empty"

    # hand-recompute one cost row: cost_units == compute*0.05 + storage*0.01
    s = get_settings()
    row = db.fetch_one(
        "SELECT compute_unit_seconds, storage_gb_hours, cost_units FROM telemetry.cost_ledger "
        "WHERE experiment_run = %s ORDER BY cost_units DESC LIMIT 1",
        (RUN,),
    )
    assert row is not None
    expected = (
        row["compute_unit_seconds"] * s.cost_rate_compute_unit_second
        + row["storage_gb_hours"] * s.cost_rate_storage_gb_hour
    )
    assert row["cost_units"] == pytest.approx(expected, rel=1e-9)
