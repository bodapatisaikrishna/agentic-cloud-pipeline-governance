"""Live decision-quality monitoring (D-100) — pure SQL over telemetry, no research extra
required, safe to run in production. Extends ``experiments/decision_quality.py``'s scoring logic
(previously only ever exercised in offline chaos experiments) to real, resolved production
incidents: for each one, did the acting agent choose an accepted mitigation for that fault type?
"""

from __future__ import annotations

from acde import db
from acde.experiments.decision_quality import expected_for_live, is_correct_live


def live_decision_quality(
    since_hours: float = 720.0, tenant_id: str | None = None
) -> dict[str, object]:
    """Score every real, resolved incident in the window against the live taxonomy
    (``decision_quality.LIVE_EXPECTED_ACTIONS``). ``tenant_id`` (D-097) restricts to one tenant
    when the caller is bound to one.

    One query, not a per-incident loop: a ``LEFT JOIN`` to ``agent_actions`` executed inside each
    incident's own detected→resolved window, aggregated with ``array_agg`` -- memory and query
    count both stay flat regardless of how many incidents are in the window.
    """
    tenant_clause = " AND fe.tenant_id = %(tenant_id)s" if tenant_id is not None else ""
    rows = db.fetch_all(
        f"""
        SELECT fe.event_id, fe.fault_type,
               COALESCE(
                   array_agg(aa.action_type) FILTER (WHERE aa.action_type IS NOT NULL),
                   ARRAY[]::text[]
               ) AS actions_taken
        FROM telemetry.failure_events fe
        LEFT JOIN telemetry.agent_actions aa
          ON aa.experiment_run = fe.experiment_run
         AND aa.executed = TRUE
         AND aa.ts BETWEEN fe.detected_ts AND fe.resolved_ts
        WHERE fe.resolved_ts IS NOT NULL
          AND fe.detected_ts IS NOT NULL
          AND fe.injected_ts > now() - interval '{float(since_hours)} hours'
          {tenant_clause}
        GROUP BY fe.event_id, fe.fault_type
        """,
        {"tenant_id": tenant_id},
    )

    by_fault_type: dict[str, dict[str, int]] = {}
    correct = 0
    total = 0
    unscored = 0
    for row in rows:
        fault_type = row["fault_type"] or "unknown"
        if not expected_for_live(fault_type):
            # no taxonomy entry for this fault_type (e.g. a future detector kind not yet added,
            # or an open_fault:* echo) -- excluded from the denominator entirely, not counted as
            # incorrect. Silently including it would drag accuracy down for something the
            # taxonomy simply doesn't cover yet, exactly the "looks scored, isn't really" gap
            # LIVE_EXPECTED_ACTIONS's own docstring exists to avoid.
            unscored += 1
            continue
        actions_taken = list(row["actions_taken"] or [])
        is_ok = is_correct_live(fault_type, actions_taken)
        bucket = by_fault_type.setdefault(fault_type, {"total": 0, "correct": 0})
        bucket["total"] += 1
        total += 1
        if is_ok:
            correct += 1
            bucket["correct"] += 1

    return {
        "window_hours": since_hours,
        "total_scored": total,
        "correct": correct,
        "unscored": unscored,
        # None (not 0.0) when nothing was scored -- a report reader must not read "0% accuracy"
        # for "no incidents happened," the same distinction compliance.py's own note field draws.
        "accuracy": round(correct / total, 3) if total else None,
        "by_fault_type": by_fault_type,
        "note": (
            "an incident whose fault_type has no entry in LIVE_EXPECTED_ACTIONS (e.g. a future "
            "detector kind not yet added to the taxonomy, or an open_fault:* echo) is excluded "
            "from total_scored/accuracy entirely, not counted as incorrect -- see 'unscored' "
            "above and experiments/decision_quality.py."
        ),
    }
