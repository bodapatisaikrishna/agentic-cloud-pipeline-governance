"""Prometheus metrics for the operator API (P3) — read from the telemetry tables.

Exposes the operational signals an SRE watches: proposals, policy verdicts, executions, escalations,
pending approvals, and LLM token spend. Text exposition format (no client library dependency).
"""

from __future__ import annotations

from acde import db


def _scalar(sql: str) -> float:
    row = db.fetch_one(sql)
    if not row:
        return 0.0
    return float(next(iter(row.values())) or 0)


def snapshot() -> dict[str, int]:
    """The raw metric values, shared by the Prometheus renderer and the dashboard."""
    return {
        "proposals_total": int(_scalar("SELECT count(*) FROM telemetry.agent_actions")),
        "actions_executed": int(
            _scalar("SELECT count(*) FROM telemetry.agent_actions WHERE executed = TRUE")
        ),
        "actions_escalated": int(
            _scalar(
                "SELECT count(*) FROM telemetry.agent_actions WHERE policy_decision = 'escalated'"
            )
        ),
        "actions_denied": int(
            _scalar("SELECT count(*) FROM telemetry.agent_actions WHERE policy_decision = 'denied'")
        ),
        "approvals_pending": int(
            _scalar("SELECT count(*) FROM telemetry.action_approvals WHERE status = 'pending'")
        ),
        "llm_tokens": int(
            _scalar(
                "SELECT COALESCE(SUM(llm_tokens_in + llm_tokens_out), 0) "
                "FROM telemetry.agent_actions"
            )
        ),
    }


def render() -> str:
    """Return Prometheus text-format metrics."""
    m = snapshot()
    lines = [
        "# HELP acde_proposals_total Agent actions proposed.",
        "# TYPE acde_proposals_total counter",
        f"acde_proposals_total {m['proposals_total']}",
        "# HELP acde_actions_executed_total Actions executed (side effects applied).",
        "# TYPE acde_actions_executed_total counter",
        f"acde_actions_executed_total {m['actions_executed']}",
        "# HELP acde_actions_escalated_total Actions escalated to a human.",
        "# TYPE acde_actions_escalated_total counter",
        f"acde_actions_escalated_total {m['actions_escalated']}",
        "# HELP acde_actions_denied_total Actions denied by policy.",
        "# TYPE acde_actions_denied_total counter",
        f"acde_actions_denied_total {m['actions_denied']}",
        "# HELP acde_approvals_pending Current pending human approvals.",
        "# TYPE acde_approvals_pending gauge",
        f"acde_approvals_pending {m['approvals_pending']}",
        "# HELP acde_llm_tokens_total Total LLM tokens consumed.",
        "# TYPE acde_llm_tokens_total counter",
        f"acde_llm_tokens_total {m['llm_tokens']}",
    ]
    return "\n".join(lines) + "\n"
