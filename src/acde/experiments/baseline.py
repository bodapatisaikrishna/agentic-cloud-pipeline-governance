"""Baseline responder: unresolved failures are handled by the simulated on-call human (§6).

The baseline has no agents, so a fixed monitor "notices" (stamps ``detected_ts``) and every fault
is escalated to the simulated human, who resolves it after a seeded lognormal delay (median 360 s).
Agent configs call this too, as a fallback for any fault still unresolved at the end of a run. MTTR
then reflects the human latency for what agents didn't fix (DEVIATIONS D-044).

D-106: the human handles each *incident* once. The page is the earliest escalation filed for the
fault (an agent's, or the fixed monitor's at detection), and the delay is drawn once per fault from
``(seed, fault ordinal)``. v1 drew a delay per escalation row and resolved the fault at the fastest
one, so an agent that re-escalated on every tick got the minimum of several draws -- a shorter MTTR
produced by the simulator, not by the agent. Keying on the ordinal (not the row id) also gives
paired runs the same human draw.
"""

from __future__ import annotations

import datetime as dt

from acde import db
from acde.config import get_settings
from acde.human.simulator import sample_latency
from acde.logging import get_logger
from acde.tenancy import current_scope

log = get_logger("experiments.baseline")


def _page(experiment_run: str, fault: dict, ordinal: int, seed: int) -> dt.datetime:
    """Resolve one fault's incident; returns the human's completion time."""
    first = db.fetch_one(
        "SELECT id, requested_ts FROM telemetry.manual_interventions "
        "WHERE experiment_run = %s AND completed_ts IS NULL AND requested_ts >= %s "
        "ORDER BY requested_ts, id LIMIT 1",
        (experiment_run, fault["injected_ts"]),
    )
    if first is None:  # nobody escalated: the fixed monitor pages at detection
        tenant_id, environment = current_scope()
        first = db.fetch_one(
            "INSERT INTO telemetry.manual_interventions "
            "(experiment_run, reason, requested_ts, tenant_id, environment) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id, requested_ts",
            (
                experiment_run,
                f"baseline: unresolved fault {fault['event_id']}",
                fault["detected_ts"] or dt.datetime.now(dt.UTC),
                tenant_id,
                environment,
            ),
        )
        if first is None:  # pragma: no cover - INSERT ... RETURNING always yields the row
            raise RuntimeError("manual_interventions insert returned no row")
    s = get_settings()
    latency = sample_latency(seed, ordinal, s.human_latency_median_s, s.human_latency_sigma)
    completed = first["requested_ts"] + dt.timedelta(seconds=latency)
    db.execute(
        "UPDATE telemetry.manual_interventions SET simulated_latency_s = %s, completed_ts = %s "
        "WHERE id = %s",
        (latency, completed, first["id"]),
    )
    # Re-pages for the same open incident are closed by the same human action.
    db.execute(
        "UPDATE telemetry.manual_interventions SET completed_ts = %s, "
        "simulated_latency_s = EXTRACT(EPOCH FROM (%s::timestamptz - requested_ts)) "
        "WHERE experiment_run = %s AND completed_ts IS NULL "
        "AND requested_ts >= %s AND requested_ts <= %s",
        (completed, completed, experiment_run, fault["injected_ts"], completed),
    )
    return completed


def resolve_via_human(experiment_run: str, seed: int, fixed_detection: bool = True) -> int:
    """Hand every still-open fault to the simulated human; back-fill resolved_ts.

    ``fixed_detection`` stamps ``detected_ts`` for faults that were never detected (the baseline's
    static monitor). Returns the number of faults resolved this call.
    """
    if fixed_detection:
        db.execute(
            "UPDATE telemetry.failure_events SET detected_ts = COALESCE(detected_ts, injected_ts) "
            "WHERE experiment_run = %s AND resolved_ts IS NULL",
            (experiment_run,),
        )
    # Every fault of the run, in injection order: a fault's ordinal must not depend on which faults
    # an agent already resolved, or paired runs would draw different human delays.
    faults = db.fetch_all(
        "SELECT event_id, injected_ts, detected_ts, resolved_ts FROM telemetry.failure_events "
        "WHERE experiment_run = %s ORDER BY injected_ts, event_id",
        (experiment_run,),
    )
    resolved = 0
    for ordinal, fault in enumerate(faults):
        if fault["resolved_ts"] is not None:
            continue
        completed = _page(experiment_run, fault, ordinal, seed)
        db.execute(
            "UPDATE telemetry.failure_events SET resolved_ts = %s, resolution = 'human' "
            "WHERE event_id = %s",
            (completed, fault["event_id"]),
        )
        resolved += 1
    log.info("baseline_human_resolved", extra={"experiment_run": experiment_run, "count": resolved})
    return resolved
