"""Integration tests for the agents end-to-end (requires `make up` + `make seed`, MOCK_LLM=1).

For each scenario: inject the fault, run the owning agent, and assert an agent_actions row with
the sensible action plus the right side effect. Monitoring stamps detected_ts; recovery stamps
resolved_ts (the MTTR endpoints). schema_drift is restored from the seeded generator afterwards.
"""

from __future__ import annotations

import pytest

from acde import db
from acde.agents.monitoring import MonitoringAgent
from acde.agents.optimization import OptimizationAgent
from acde.agents.recovery import RecoveryAgent
from acde.agents.run import run_cycle
from acde.agents.schema import SchemaAgent
from acde.chaos.injector import FaultInjector
from acde.chaos.scenarios import run_seed
from acde.dataplane.datasets import tpcds_gen

pytestmark = pytest.mark.integration

RUN = "itest-agents"


@pytest.fixture(autouse=True)
def _clean_and_restore():
    for table in ("failure_events", "agent_actions"):
        db.execute(f"DELETE FROM telemetry.{table} WHERE experiment_run = %s", (RUN,))
    yield
    tpcds_gen.write()


def _inject(scenario: str) -> None:
    FaultInjector(experiment_run=RUN).inject(scenario, run_seed("full", scenario, 0))


def _last_action(agent: str) -> dict:
    row = db.fetch_one(
        "SELECT action_type, executed, llm_tokens_in, policy_decision FROM telemetry.agent_actions "
        "WHERE experiment_run = %s AND agent = %s ORDER BY ts DESC LIMIT 1",
        (RUN, agent),
    )
    assert row is not None, f"no agent_actions row for {agent}"
    return row


def test_schema_drift_triggers_quarantine():
    _inject("schema_drift")
    SchemaAgent(experiment_run=RUN).run_once()
    row = _last_action("schema")
    assert row["action_type"] == "quarantine_partition"
    assert row["executed"] and row["llm_tokens_in"] > 0
    # the quarantined partition is now inactive; other datasets are untouched
    q = db.fetch_one(
        "SELECT count(*) AS n FROM warehouse.quarantine_events WHERE experiment_run = %s", (RUN,)
    )
    assert q["n"] >= 1


def test_upstream_delay_triggers_replay():
    _inject("upstream_delay")
    RecoveryAgent(experiment_run=RUN).run_once()
    assert _last_action("recovery")["action_type"] == "replay"


def test_ingress_burst_triggers_scale_workers():
    _inject("ingress_burst")
    # optimization keys on freshness; set a breaching metric so the mock scales up
    db.execute(
        "INSERT INTO telemetry.pipeline_metrics (pipeline_id, metric, value, experiment_run) "
        "VALUES ('stream', 'freshness_s', 140, %s)",
        (RUN,),
    )
    OptimizationAgent(experiment_run=RUN).run_once()
    assert _last_action("optimization")["action_type"] == "scale_workers"


def test_monitoring_and_recovery_close_the_failure_lifecycle():
    _inject("upstream_delay")
    # monitoring detects (sets detected_ts), recovery resolves (sets resolved_ts)
    run_cycle(RUN, agents=["monitoring", "recovery"])
    event = db.fetch_one(
        "SELECT detected_ts, resolved_ts, resolution FROM telemetry.failure_events "
        "WHERE experiment_run = %s ORDER BY injected_ts DESC LIMIT 1",
        (RUN,),
    )
    assert event["detected_ts"] is not None
    assert event["resolved_ts"] is not None
    assert event["resolution"] == "replay"
    # MTTR is well-defined (resolved at or after detected)
    assert event["resolved_ts"] >= event["detected_ts"]


def test_nominal_run_is_no_action_and_logged():
    MonitoringAgent(experiment_run=RUN).run_once()
    assert _last_action("monitoring")["action_type"] == "no_action"
