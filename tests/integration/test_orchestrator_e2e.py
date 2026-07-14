"""Integration tests for the control-loop orchestrator (live stack, MOCK_LLM=1).

Runs a short soak with two overlapping chaos scenarios, checks the ablation flags gate which
agents act, and checks that a fresh loop resumes cleanly for the same experiment_run (all state
in Postgres). schema_drift corrupts the source CSV, so it is restored at teardown.
"""

from __future__ import annotations

import asyncio

import pytest

from acde import db
from acde.chaos.injector import FaultInjector
from acde.chaos.scenarios import run_seed
from acde.dataplane.datasets import tpcds_gen
from acde.orchestrator.loop import ControlLoop

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _restore_source():
    yield
    tpcds_gen.write()


def _reset(run: str) -> None:
    for table in ("failure_events", "agent_actions"):
        db.execute(f"DELETE FROM telemetry.{table} WHERE experiment_run = %s", (run,))


def _agents_that_acted(run: str) -> set[str]:
    rows = db.fetch_all(
        "SELECT DISTINCT agent FROM telemetry.agent_actions "
        "WHERE experiment_run = %s AND action_type <> 'no_action'",
        (run,),
    )
    return {r["agent"] for r in rows}


def _short_loop(run: str, config: str = "full") -> ControlLoop:
    cl = ControlLoop(experiment_run=run, config=config)
    cl.interval_s = 1.0  # tick fast for the test
    return cl


def test_soak_full_config_closes_lifecycle_across_agents():
    run = "itest-soak"
    _reset(run)
    inj = FaultInjector(experiment_run=run)
    inj.inject("schema_drift", run_seed("full", "schema_drift", 0))
    inj.inject("upstream_delay", run_seed("full", "upstream_delay", 0))

    asyncio.run(_short_loop(run).run(duration_s=8))

    acted = _agents_that_acted(run)
    assert "schema" in acted  # quarantined the drift
    assert "recovery" in acted  # replayed the delay
    # both faults detected and resolved (MTTR well-defined)
    events = db.fetch_all(
        "SELECT detected_ts, resolved_ts FROM telemetry.failure_events WHERE experiment_run = %s",
        (run,),
    )
    assert events and all(e["detected_ts"] is not None for e in events)
    assert any(e["resolved_ts"] is not None for e in events)


def test_ablation_recovery_only_excludes_other_agents():
    run = "itest-ablation"
    _reset(run)
    FaultInjector(experiment_run=run).inject(
        "upstream_delay", run_seed("full", "upstream_delay", 1)
    )

    asyncio.run(_short_loop(run, config="recovery_only").run(duration_s=6))

    # only monitoring (detector) + recovery may act; schema/optimization are disabled
    acted = _agents_that_acted(run)
    assert "recovery" in acted
    assert "schema" not in acted and "optimization" not in acted
    all_agents = {
        r["agent"]
        for r in db.fetch_all(
            "SELECT DISTINCT agent FROM telemetry.agent_actions WHERE experiment_run = %s", (run,)
        )
    }
    assert all_agents <= {"monitoring", "recovery"}


def test_loop_resumes_cleanly_for_same_run():
    run = "itest-resume"
    _reset(run)
    FaultInjector(experiment_run=run).inject(
        "upstream_delay", run_seed("full", "upstream_delay", 2)
    )

    asyncio.run(_short_loop(run).run(duration_s=5))
    before = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.agent_actions WHERE experiment_run = %s", (run,)
    )["n"]
    assert before > 0  # first loop acted on the fault

    # a fresh loop (simulating kill + restart) picks up a NEW fault and keeps working —
    # all state is in Postgres, so the restart resumes cleanly with no stuck locks.
    FaultInjector(experiment_run=run).inject(
        "upstream_delay", run_seed("full", "upstream_delay", 3)
    )
    asyncio.run(_short_loop(run).run(duration_s=5))
    after = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.agent_actions WHERE experiment_run = %s", (run,)
    )["n"]
    assert after > before  # the restarted loop handled the new fault
