"""Integration test for D-106: the simulated human handles each incident once (live Postgres)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from acde import db
from acde.config import get_settings
from acde.experiments.baseline import resolve_via_human
from acde.human.simulator import sample_latency

pytestmark = pytest.mark.integration

RUN = "it__human_incident__r0"


def _setup(n_escalations: int) -> dt.datetime:
    for table in ("telemetry.failure_events", "telemetry.manual_interventions"):
        db.execute(f"DELETE FROM {table} WHERE experiment_run = %s", (RUN,))
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    db.execute(
        "INSERT INTO telemetry.failure_events (event_id, experiment_run, scenario, fault_type, "
        "injected_ts, detected_ts) VALUES (%s, %s, 'schema_drift', 'schema_drift', %s, %s)",
        (str(uuid.uuid4()), RUN, t0, t0 + dt.timedelta(seconds=2)),
    )
    for i in range(n_escalations):  # an agent re-escalating on every 2 s tick
        db.execute(
            "INSERT INTO telemetry.manual_interventions (experiment_run, reason, requested_ts) "
            "VALUES (%s, 'agent', %s)",
            (RUN, t0 + dt.timedelta(seconds=4 + 2 * i)),
        )
    return t0


def _resolved() -> dt.datetime:
    row = db.fetch_one(
        "SELECT resolved_ts FROM telemetry.failure_events WHERE experiment_run = %s", (RUN,)
    )
    assert row is not None
    return row["resolved_ts"]


def test_six_escalations_resolve_on_one_draw_from_the_first_page():
    t0 = _setup(6)
    assert resolve_via_human(RUN, seed=77) == 1
    s = get_settings()
    latency = sample_latency(77, 0, s.human_latency_median_s, s.human_latency_sigma)
    assert _resolved() == t0 + dt.timedelta(seconds=4 + latency)
    open_rows = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.manual_interventions "
        "WHERE experiment_run = %s AND completed_ts IS NULL",
        (RUN,),
    )
    assert open_rows == {"n": 0}  # the re-pages were closed with the incident


def test_unescalated_fault_is_paged_at_detection_with_the_same_draw():
    t0 = _setup(0)
    resolve_via_human(RUN, seed=77)
    s = get_settings()
    latency = sample_latency(77, 0, s.human_latency_median_s, s.human_latency_sigma)
    assert _resolved() == t0 + dt.timedelta(seconds=2 + latency)


def test_one_request_against_overlapping_faults_is_one_incident():
    from acde.experiments.metrics import harvest_metrics

    t0 = _setup(1)  # schema drift plus one escalation at t0 + 4 s
    db.execute(  # the second, overlapping event schema drift raises
        "INSERT INTO telemetry.failure_events (event_id, experiment_run, scenario, fault_type, "
        "injected_ts, detected_ts) VALUES (%s, %s, 'schema', 'schema_breaking', %s, %s)",
        (str(uuid.uuid4()), RUN, t0 + dt.timedelta(seconds=1), t0 + dt.timedelta(seconds=2)),
    )
    m = harvest_metrics(RUN, 1.0, "schema_drift", "full")
    assert m["manual_interventions"] == 1.0
    assert m["escalated_incidents"] == 1.0
    assert m["secondary_events"] == 1.0


def test_host_load_the_monitor_flags_is_not_the_injected_incident():
    from acde.experiments.metrics import harvest_metrics

    t0 = _setup(0)  # the injected fault, never escalated
    db.execute(  # D-109: cpu_high on the scheduler, flagged two minutes in and paged
        "INSERT INTO telemetry.failure_events (event_id, experiment_run, scenario, fault_type, "
        "injected_ts, detected_ts, resolved_ts) VALUES (%s, %s, 'acde-airflow-scheduler-1', "
        "'cpu_high', %s, %s, %s)",
        (
            str(uuid.uuid4()),
            RUN,
            t0 + dt.timedelta(seconds=120),
            t0 + dt.timedelta(seconds=120),
            t0 + dt.timedelta(seconds=450),
        ),
    )
    db.execute(
        "UPDATE telemetry.failure_events SET resolved_ts = %s "
        "WHERE experiment_run = %s AND scenario = 'schema_drift'",
        (t0 + dt.timedelta(seconds=5), RUN),
    )
    db.execute(
        "INSERT INTO telemetry.manual_interventions (experiment_run, reason, requested_ts) "
        "VALUES (%s, 'cpu', %s)",
        (RUN, t0 + dt.timedelta(seconds=121)),
    )
    m = harvest_metrics(RUN, 1.0, "schema_drift", "full")
    assert m["mttr_injection_s"] == 5.0  # the injected fault alone
    assert m["escalated_incidents"] == 0.0  # paged after the injected fault was resolved
    assert m["secondary_events"] == 1.0
