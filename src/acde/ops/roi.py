"""ROI report from the audit trail (P5) — the renewal/expansion artifact.

Summarizes what ACDE did over a window from `telemetry.agent_actions` + `failure_events` +
`manual_interventions`: actions executed, incidents auto-resolved, MTTR, escalations, and an
**explicitly-estimated** operator time saved (auto-resolutions x the configured human-intervention
latency). Pure SQL over telemetry — always available (no research extra), safe to run in production.
"""

from __future__ import annotations

import statistics

from acde import db
from acde.config import get_settings


def roi_report(since_hours: float = 720.0) -> dict[str, object]:
    """Compute an ROI summary over the last ``since_hours`` (default 30 days)."""
    window = f"now() - interval '{float(since_hours)} hours'"
    executed = db.fetch_one(
        f"SELECT count(*) AS n FROM telemetry.agent_actions WHERE executed = TRUE AND ts > {window}"
    )
    escalated = db.fetch_one(
        f"SELECT count(*) AS n FROM telemetry.agent_actions "
        f"WHERE policy_decision = 'escalated' AND ts > {window}"
    )
    interventions = db.fetch_one(
        f"SELECT count(*) AS n FROM telemetry.manual_interventions WHERE requested_ts > {window}"
    )
    tokens = db.fetch_one(
        f"SELECT COALESCE(SUM(llm_tokens_in + llm_tokens_out), 0) AS t "
        f"FROM telemetry.agent_actions WHERE ts > {window}"
    )
    resolved = db.fetch_all(
        f"SELECT EXTRACT(EPOCH FROM (resolved_ts - detected_ts)) AS mttr, resolution "
        f"FROM telemetry.failure_events "
        f"WHERE resolved_ts IS NOT NULL AND detected_ts IS NOT NULL AND injected_ts > {window}"
    )
    mttrs = [float(r["mttr"]) for r in resolved if r["mttr"] is not None]
    auto_resolved = sum(1 for r in resolved if r["resolution"] not in (None, "human"))

    # Estimate: each auto-resolution avoided a manual intervention at the configured human latency.
    human_s = get_settings().human_latency_median_s
    est_operator_hours_saved = round(auto_resolved * human_s / 3600.0, 2)

    return {
        "window_hours": since_hours,
        "actions_executed": int(executed["n"]) if executed else 0,
        "incidents_auto_resolved": auto_resolved,
        "incidents_escalated_to_human": int(escalated["n"]) if escalated else 0,
        "manual_interventions": int(interventions["n"]) if interventions else 0,
        "mttr_median_s": round(statistics.median(mttrs), 2) if mttrs else 0.0,
        "mttr_p90_s": round(sorted(mttrs)[int(0.9 * (len(mttrs) - 1))], 2) if mttrs else 0.0,
        "llm_tokens": int(tokens["t"]) if tokens else 0,
        "estimated_operator_hours_saved": est_operator_hours_saved,
        "note": (
            "operator_hours_saved is an estimate = auto-resolutions x configured human latency "
            f"({human_s / 60:.0f} min); not a measured figure."
        ),
    }
