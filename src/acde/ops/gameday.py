"""Game-day: rehearse an incident in staging and get an evidence report (P5, the moat feature).

Injects a controlled fault, lets the agents respond under the current execution mode, and reports
what happened (MTTR, chosen mitigation, whether it executed) for *the customer's* environment. This
is the "prove it on your pipelines" artifact no observe-only tool offers.

**Staging guard:** hard refusal unless the connector is non-production (`connector_is_production`),
so a rehearsal can never inject a fault against prod. Requires the research extra (chaos harness).
"""

from __future__ import annotations

from typing import Any

from acde import db
from acde.logging import get_logger

log = get_logger("ops.gameday")

_RUN_TABLES = ("failure_events", "agent_actions", "manual_interventions")


def run_gameday(scenario: str, env: str = "staging", force: bool = False) -> dict[str, Any]:
    """Inject ``scenario`` into ``env``; report the agents' response. Staging-only unless force."""
    from acde.connectors import get_connector

    conn = get_connector()
    if conn.is_production and not force:
        raise RuntimeError(
            "refusing to run game-day against a production connector — set "
            "CONNECTOR_IS_PRODUCTION=false for a staging environment (or pass force=True)"
        )
    try:
        from acde.chaos.injector import FaultInjector
        from acde.chaos.scenarios import run_seed
    except ImportError as exc:  # research extra not installed
        msg = "game-day needs the research extra: pip install 'acde[research]'"
        raise RuntimeError(msg) from exc
    from acde.agents.run import run_cycle

    for t in _RUN_TABLES:
        db.execute(f"DELETE FROM telemetry.{t} WHERE experiment_run = %s", (env,))
    FaultInjector(experiment_run=env).inject(scenario, run_seed("full", scenario, 0))
    run_cycle(env)  # all agents respond once

    event = db.fetch_one(
        "SELECT EXTRACT(EPOCH FROM (resolved_ts - detected_ts)) AS mttr, resolution "
        "FROM telemetry.failure_events WHERE experiment_run = %s ORDER BY injected_ts DESC LIMIT 1",
        (env,),
    )
    actions = db.fetch_all(
        "SELECT agent, action_type, executed, policy_decision FROM telemetry.agent_actions "
        "WHERE experiment_run = %s ORDER BY ts",
        (env,),
    )
    report = {
        "scenario": scenario,
        "environment": env,
        "connector": conn.name,
        "resolution": event["resolution"] if event else None,
        "mttr_s": round(float(event["mttr"]), 3) if event and event["mttr"] is not None else None,
        "actions": actions,
    }
    log.info("gameday_complete", extra={"scenario": scenario, "environment": env})
    return report
