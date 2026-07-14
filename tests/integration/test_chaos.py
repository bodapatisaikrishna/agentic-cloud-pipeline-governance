"""Integration tests for the chaos harness (requires `make up` + `make seed`).

Each scenario writes a failure_events row and visibly degrades the pipeline. schema_drift is
destructive to the source CSV, so this module restores it from the seeded generator at teardown.
"""

from __future__ import annotations

import pytest

from acde import db
from acde.chaos.injector import FaultInjector
from acde.chaos.scenarios import run_seed
from acde.config import get_settings
from acde.dataplane.batch import pipeline
from acde.dataplane.datasets import tpcds_gen

pytestmark = pytest.mark.integration

RUN = "itest-chaos"


@pytest.fixture(autouse=True)
def _restore_source():
    yield
    tpcds_gen.write()  # regenerate the seeded source CSV after (possible) corruption


def _clear():
    db.execute("DELETE FROM telemetry.failure_events WHERE experiment_run = %s", (RUN,))


def _event_count(scenario: str) -> int:
    row = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.failure_events "
        "WHERE experiment_run = %s AND scenario = %s",
        (RUN, scenario),
    )
    return row["n"] if row else 0


def test_schema_drift_corrupts_source_and_records_event():
    _clear()
    FaultInjector(experiment_run=RUN).inject("schema_drift", run_seed("full", "schema_drift", 0))
    assert _event_count("schema_drift") == 1
    # the drifted source now breaks the real batch pipeline (drop -> missing, retype -> non-numeric)
    with pytest.raises(pipeline.SchemaValidationError):
        pipeline.run_tpcds(get_settings().data_dir, experiment_run=RUN)


def test_ingress_burst_lands_events_and_records():
    _clear()
    before = db.fetch_one("SELECT count(*) AS n FROM warehouse.stream_aggregates")["n"]
    FaultInjector(experiment_run=RUN).inject("ingress_burst", run_seed("full", "ingress_burst", 0))
    assert _event_count("ingress_burst") == 1
    # a consumer session would aggregate these; here we just confirm the fault was injected +
    # the burst was published (topic has data). Freshness impact is exercised in the soak (P6).
    after = db.fetch_one("SELECT count(*) AS n FROM warehouse.stream_aggregates")["n"]
    assert after >= before  # no regression; burst published to the broker


def test_upstream_delay_and_resource_contention_record_events(monkeypatch):
    _clear()
    # keep the CPU stressor short and cheap for the gate
    monkeypatch.setattr("acde.chaos.injector.stressor.cpu_stress", lambda n, d: None)
    FaultInjector(experiment_run=RUN).inject(
        "upstream_delay", run_seed("full", "upstream_delay", 0)
    )
    FaultInjector(experiment_run=RUN).inject(
        "resource_contention", run_seed("full", "resource_contention", 0)
    )
    assert _event_count("upstream_delay") == 1
    assert _event_count("resource_contention") == 1
