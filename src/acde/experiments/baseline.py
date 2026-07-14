"""Baseline responder: unresolved failures are handled by the simulated on-call human (§6).

The baseline has no agents, so a fixed monitor "notices" (stamps ``detected_ts``) and every fault
is escalated to the :class:`HumanSimulator`, which resolves it after a seeded lognormal delay
(median 360 s). Agent configs call this too, as a fallback for any fault still unresolved at the
end of a run. MTTR then reflects the human latency for what agents didn't fix (DEVIATIONS D-044).
"""

from __future__ import annotations

import datetime as dt

from acde import db
from acde.human.simulator import HumanSimulator
from acde.logging import get_logger

log = get_logger("experiments.baseline")


def resolve_via_human(experiment_run: str, seed: int, fixed_detection: bool = True) -> int:
    """Escalate every still-open fault to the human simulator; back-fill resolved_ts.

    ``fixed_detection`` stamps ``detected_ts`` for faults that were never detected (the baseline's
    static monitor). Returns the number of faults resolved this call.
    """
    if fixed_detection:
        db.execute(
            "UPDATE telemetry.failure_events SET detected_ts = COALESCE(detected_ts, injected_ts) "
            "WHERE experiment_run = %s AND resolved_ts IS NULL",
            (experiment_run,),
        )

    open_faults = db.fetch_all(
        "SELECT event_id, detected_ts FROM telemetry.failure_events "
        "WHERE experiment_run = %s AND resolved_ts IS NULL",
        (experiment_run,),
    )
    if not open_faults:
        return 0

    # One manual intervention per open fault, requested at detection time.
    for fault in open_faults:
        requested = fault["detected_ts"] or dt.datetime.now(dt.UTC)
        db.execute(
            "INSERT INTO telemetry.manual_interventions (experiment_run, reason, requested_ts) "
            "VALUES (%s, %s, %s)",
            (experiment_run, f"baseline: unresolved fault {fault['event_id']}", requested),
        )

    sim = HumanSimulator(experiment_run=experiment_run, seed=seed)
    sim.assign_latencies()
    # Resolve deterministically (no real waiting): the human "completes" at requested + latency.
    sim.resolve_due(now=dt.datetime.now(dt.UTC) + dt.timedelta(days=3650))

    # Back-fill each open fault's resolved_ts from a completed intervention (median completion).
    completions = db.fetch_all(
        "SELECT completed_ts FROM telemetry.manual_interventions "
        "WHERE experiment_run = %s AND completed_ts IS NOT NULL ORDER BY completed_ts",
        (experiment_run,),
    )
    resolved = 0
    for fault, completion in zip(open_faults, completions, strict=False):
        db.execute(
            "UPDATE telemetry.failure_events SET resolved_ts = %s, resolution = 'human' "
            "WHERE event_id = %s",
            (completion["completed_ts"], fault["event_id"]),
        )
        resolved += 1
    log.info("baseline_human_resolved", extra={"experiment_run": experiment_run, "count": resolved})
    return resolved
