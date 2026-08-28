"""Compliance / audit evidence report (D-096) — pure SQL over telemetry, no research extra
required, safe to run in production. Follows ``ops/roi.py``'s exact pattern (same module shape,
same "the interpolated window is always a function-typed ``float``, never a client-supplied
string" trust boundary) but answers a different question: not "did ACDE save us time" but "can we
show an auditor what happened and that it was governed."
"""

from __future__ import annotations

import statistics

from acde import db
from acde.config import get_settings
from acde.orchestrator.control import heartbeat_age_s


def _policy_verdict_distribution(window: str) -> dict[str, object]:
    rows = db.fetch_all(
        f"SELECT policy_decision, count(*) AS n FROM telemetry.agent_actions "
        f"WHERE ts > {window} GROUP BY policy_decision"
    )
    counts = {r["policy_decision"] or "unknown": int(r["n"]) for r in rows}
    total = sum(counts.values())
    pct = {k: round(100.0 * v / total, 1) for k, v in counts.items()}
    return {"counts": counts, "percentages": pct, "total": total}


def _incidents(window: str) -> dict[str, object]:
    resolved = db.fetch_all(
        f"SELECT EXTRACT(EPOCH FROM (resolved_ts - detected_ts)) AS mttr "
        f"FROM telemetry.failure_events "
        f"WHERE resolved_ts IS NOT NULL AND detected_ts IS NOT NULL AND injected_ts > {window}"
    )
    mttrs = [float(r["mttr"]) for r in resolved if r["mttr"] is not None]
    detected = db.fetch_one(
        f"SELECT count(*) AS n FROM telemetry.failure_events "
        f"WHERE detected_ts IS NOT NULL AND injected_ts > {window}"
    )
    open_now = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.failure_events WHERE resolved_ts IS NULL"
    )
    return {
        "detected": int(detected["n"]) if detected else 0,
        "resolved": len(mttrs),
        "open_now": int(open_now["n"]) if open_now else 0,
        "mttr_median_s": round(statistics.median(mttrs), 2) if mttrs else 0.0,
        "mttr_p90_s": round(sorted(mttrs)[int(0.9 * (len(mttrs) - 1))], 2) if mttrs else 0.0,
    }


def _availability() -> dict[str, object]:
    """A point-in-time heartbeat freshness check, not a historical uptime percentage (D-096) --
    ACDE's own DB has no heartbeat *history* table, only the latest value, and adding one is out
    of scope here. Same honesty standard as ``roi.py``'s own disclosed-estimate ``note`` field:
    the limitation is stated in the output, not silently papered over with a fabricated number.
    """
    age = heartbeat_age_s()
    max_age = get_settings().monitoring_interval_s * 3
    healthy = age is not None and age <= max_age
    return {
        "healthy": healthy,
        "last_tick_seconds_ago": round(age, 1) if age is not None else None,
        "stale_threshold_seconds": max_age,
        "note": (
            "point-in-time check only (last control-loop tick vs. 3x the tick interval) -- "
            "ACDE retains no heartbeat history, so this is not a measured historical uptime %."
        ),
    }


def compliance_report(since_hours: float = 720.0) -> dict[str, object]:
    """Compute a compliance/audit report over the last ``since_hours`` (30-day default window)."""
    window = f"now() - interval '{float(since_hours)} hours'"
    return {
        "window_hours": since_hours,
        "policy_verdicts": _policy_verdict_distribution(window),
        "incidents": _incidents(window),
        "availability": _availability(),
    }
