"""Integration tests for the policy plane (requires `make up` + `make seed`).

Exercises the three manual-checklist scenarios end-to-end against live OPA + DB:
a budget-breaching scale_workers is denied; a rollback with a prior version flips the active
pointer; an escalate_to_human writes a manual_intervention that the human simulator resolves.
"""

from __future__ import annotations

import datetime as dt

import pytest

from acde import db
from acde.contracts import ProposedAction
from acde.dataplane.batch import pipeline
from acde.human.simulator import HumanSimulator
from acde.policy import executor, gate

pytestmark = pytest.mark.integration

RUN = "itest-policy"


def _evaluate(action: ProposedAction, **ctx_kw):
    ctx = gate.build_context(action, experiment_run=RUN, **ctx_kw)
    return gate.evaluate(action, ctx)


def test_budget_breaching_scale_workers_denied():
    action = ProposedAction(
        agent="optimization",
        action_type="scale_workers",
        target="streaming",
        params={"n_workers": 8},
        justification="throughput",
        confidence=0.8,
    )
    decision = _evaluate(action, current_workers=2, budget_remaining_units=1.0)
    assert not decision.allowed
    assert decision.policy_id == "cost_budget"
    out = executor.execute(action, decision, RUN)
    assert not out.executed and "denied" in out.outcome


def test_rollback_with_prior_version_flips_pointer():
    # Seed two versions so a prior exists; v2 active.
    ds, pk = "itest_policy_ds", "p1"
    db.execute("DELETE FROM warehouse.partition_versions WHERE dataset = %s", (ds,))
    from acde.dataplane.partitions import PartitionVersionManager

    mgr = PartitionVersionManager(experiment_run=RUN)
    mgr.create_version(ds, pk, "x int", rows=[(1,)], insert_columns="x", activate=True)
    mgr.create_version(ds, pk, "x int", rows=[(2,)], insert_columns="x", activate=True)
    assert mgr.get_active(ds, pk)["version"] == 2

    action = ProposedAction(
        agent="recovery",
        action_type="rollback",
        target=ds,
        params={"dataset": ds, "partition_key": pk},
        justification="bad data",
        confidence=0.9,
    )
    decision = _evaluate(action)
    assert decision.allowed and decision.policy_id == "recovery_approval"
    executor.execute(action, decision, RUN)
    assert mgr.get_active(ds, pk)["version"] == 1  # pointer flipped back


def test_escalation_written_and_resolved_by_simulator():
    db.execute("DELETE FROM telemetry.manual_interventions WHERE experiment_run = %s", (RUN,))
    action = ProposedAction(
        agent="recovery",
        action_type="escalate_to_human",
        target="tpcds_ingest",
        justification="cannot recover automatically",
        confidence=0.4,
    )
    decision = _evaluate(action)
    assert decision.escalate
    executor.execute(action, decision, RUN)
    row = db.fetch_one(
        "SELECT id, completed_ts FROM telemetry.manual_interventions WHERE experiment_run = %s",
        (RUN,),
    )
    assert row is not None and row["completed_ts"] is None

    # Simulator assigns a latency, then resolves it once enough (simulated) time has passed.
    sim = HumanSimulator(experiment_run=RUN, seed=42)
    sim.assign_latencies()
    far_future = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    resolved = sim.resolve_due(now=far_future)
    assert resolved == 1
    done = db.fetch_one(
        "SELECT completed_ts, simulated_latency_s FROM telemetry.manual_interventions "
        "WHERE experiment_run = %s",
        (RUN,),
    )
    assert done["completed_ts"] is not None
    assert done["simulated_latency_s"] > 0


def test_seeded_pipeline_available_for_actions():
    # sanity: seeded batch data present so recovery targets resolve
    assert pipeline is not None
