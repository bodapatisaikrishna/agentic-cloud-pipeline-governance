"""Prometheus metrics for the operator API (P3) — read from the telemetry tables.

Exposes the operational signals an SRE watches: proposals, policy verdicts, executions, escalations,
pending approvals, and LLM token spend. Text exposition format (no client library dependency).

D-088 adds two liveness signals, both read cross-process from Postgres (this is the API process;
the control loop is a separate process — ``control.desired_state`` is how one learns the other's
state, the same mechanism the kill switch already uses): the loop's last-tick timestamp (a stopped
clock means a hung or crashed loop) and a count of actions stuck at ``status='executing'`` (D-084's
write-ahead row that never got its outcome update — the exact failure mode that fix targets).
"""

from __future__ import annotations

import time

from acde import db
from acde.orchestrator.control import heartbeat_age_s
from acde.server.ratelimit import total_rate_limited
from acde.telemetry.cost import costs_by_tenant


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
        "stale_executing": int(
            _scalar("SELECT count(*) FROM telemetry.agent_actions WHERE status = 'executing'")
        ),
    }


def _loop_last_tick_ts() -> float | None:
    """Unix timestamp of the control loop's last recorded tick, or None if never recorded."""
    age = heartbeat_age_s()
    return None if age is None else time.time() - age


def _escape_label(value: str) -> str:
    """Prometheus label-value escaping: backslash, double-quote, newline (text-format spec)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


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
        "# HELP acde_stale_executing_actions Actions stuck at status='executing' (D-084: a crash "
        "between the write-ahead insert and the outcome update).",
        "# TYPE acde_stale_executing_actions gauge",
        f"acde_stale_executing_actions {m['stale_executing']}",
    ]
    last_tick = _loop_last_tick_ts()
    if last_tick is not None:
        lines += [
            "# HELP acde_loop_last_tick_timestamp_seconds Unix timestamp of the control loop's "
            "last recorded tick. Alert on time() - this exceeding ~3x the tick interval.",
            "# TYPE acde_loop_last_tick_timestamp_seconds gauge",
            f"acde_loop_last_tick_timestamp_seconds {last_tick:.3f}",
        ]
    # D-095: per-tenant cost, trailing 24h -- same window costs_by_tenant defaults to, so /metrics
    # and /costs agree without a separate parameter to keep in sync.
    tenant_costs = costs_by_tenant(since_hours=24.0)
    lines += [
        "# HELP acde_cost_units_by_tenant Trailing-24h cost units, by tenant.",
        "# TYPE acde_cost_units_by_tenant gauge",
    ]
    for row in tenant_costs:
        label = _escape_label(str(row["tenant_id"]))
        lines.append(f'acde_cost_units_by_tenant{{tenant_id="{label}"}} {row["cost_units"]}')
    # D-098: cumulative count of requests this process has rejected with 429. Process-wide (not
    # per-app-instance like the limiter's own window state) -- correct for a cumulative counter,
    # the same as every other counter above.
    lines += [
        "# HELP acde_rate_limited_requests_total Requests rejected with 429 (D-098).",
        "# TYPE acde_rate_limited_requests_total counter",
        f"acde_rate_limited_requests_total {total_rate_limited()}",
    ]
    return "\n".join(lines) + "\n"
