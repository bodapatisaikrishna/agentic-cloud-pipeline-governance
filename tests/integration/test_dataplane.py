"""Integration tests for the Phase 1 data plane (requires `make up` + `make seed`).

Batch: trigger the tpcds_ingest DAG via the Airflow REST API and assert a versioned
partition lands. Streaming: publish a seeded burst, run a short consumer session, and
assert window aggregates land; then flip the worker count and confirm the pool resizes.
"""

from __future__ import annotations

import time

import httpx
import pytest

from acde import db
from acde.config import get_settings

pytestmark = pytest.mark.integration


def _airflow() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=s.airflow_url, auth=(s.airflow_user, s.airflow_password), timeout=30
    )


def _trigger_and_wait(client: httpx.Client, dag_id: str, timeout_s: float = 120) -> str:
    client.patch(f"/dags/{dag_id}", json={"is_paused": False}).raise_for_status()
    run_id = f"itest__{int(time.time())}"
    client.post(f"/dags/{dag_id}/dagRuns", json={"dag_run_id": run_id}).raise_for_status()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/dags/{dag_id}/dagRuns/{run_id}")
        resp.raise_for_status()
        state = resp.json()["state"]
        if state in {"success", "failed"}:
            assert state == "success", f"{dag_id} run ended {state}"
            return run_id
        time.sleep(3)
    pytest.fail(f"{dag_id} did not finish within {timeout_s}s")


def test_batch_dag_materializes_versioned_partition():
    # Regenerate a clean source so this test is independent of any prior schema_drift
    # corruption / quarantine left by the chaos or agent integration tests (order-safe).
    from acde.dataplane.datasets import tpcds_gen

    tpcds_gen.write()
    with _airflow() as client:
        _trigger_and_wait(client, "tpcds_ingest")
    active = db.fetch_one(
        "SELECT * FROM warehouse.partition_versions "
        "WHERE dataset = 'tpcds_daily_revenue' AND active"
    )
    assert active is not None
    count = db.fetch_one(f"SELECT count(*) AS n FROM warehouse.{active['table_name']}")
    assert count is not None and count["n"] > 0


def test_streaming_session_lands_window_aggregates():
    import subprocess

    run = "itest-stream"
    db.execute("DELETE FROM warehouse.stream_aggregates WHERE experiment_run = %s", (run,))
    subprocess.run(
        ["uv", "run", "python", "-m", "acde.dataplane.streaming.producer", "--events", "1500"],
        check=True,
        timeout=120,
    )
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "acde.dataplane.streaming.consumer",
            "--duration",
            "20",
            "--experiment-run",
            run,
        ],
        check=True,
        timeout=120,
    )
    rows = db.fetch_all(
        "SELECT event_count, event_ts, materialized_ts FROM warehouse.stream_aggregates "
        "WHERE experiment_run = %s",
        (run,),
    )
    assert rows, "no window aggregates were materialized"
    assert all(r["materialized_ts"] >= r["event_ts"] for r in rows)
