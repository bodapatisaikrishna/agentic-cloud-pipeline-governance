"""Human-approval workflow for gated actions (production trust core, P1).

In ``approval`` mode the executor enqueues an allowed action instead of running it; an operator then
approves (execute now) or rejects it. A pending row is a self-contained, re-executable action, so
approval reconstructs a `ProposedAction` and runs it via the same executor handlers
(`executor.apply_action`) — no dependency on the original agent cycle. State machine:
``pending → approved → executed | failed`` or ``pending → rejected``.
"""

from __future__ import annotations

import json
from typing import Any

from acde import db
from acde.contracts import ProposedAction
from acde.logging import get_logger

log = get_logger("human.approvals")


def create_pending(action: ProposedAction, decision: Any, experiment_run: str) -> int:
    """Enqueue an allowed action for human sign-off; returns the approval_id."""
    row = db.fetch_one(
        "INSERT INTO telemetry.action_approvals "
        "(experiment_run, agent, action_type, target, params, justification, confidence, "
        " policy_reason, status) "
        "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, 'pending') RETURNING approval_id",
        (
            experiment_run,
            action.agent,
            action.action_type,
            action.target,
            json.dumps(action.params),
            action.justification,
            action.confidence,
            getattr(decision, "reason", ""),
        ),
    )
    approval_id = int(row["approval_id"]) if row else -1
    log.info(
        "approval_created",
        extra={
            "approval_id": approval_id,
            "action_type": action.action_type,
            "target": action.target,
            "experiment_run": experiment_run,
        },
    )
    return approval_id


def list_pending(experiment_run: str | None = None) -> list[dict[str, Any]]:
    """List pending approvals (optionally scoped to one environment), newest first."""
    if experiment_run is None:
        return db.fetch_all(
            "SELECT approval_id, experiment_run, agent, action_type, target, justification, "
            "confidence, requested_ts FROM telemetry.action_approvals "
            "WHERE status = 'pending' ORDER BY requested_ts DESC"
        )
    return db.fetch_all(
        "SELECT approval_id, experiment_run, agent, action_type, target, justification, "
        "confidence, requested_ts FROM telemetry.action_approvals "
        "WHERE status = 'pending' AND experiment_run = %s ORDER BY requested_ts DESC",
        (experiment_run,),
    )


def _load_pending(approval_id: int) -> dict[str, Any] | None:
    return db.fetch_one(
        "SELECT * FROM telemetry.action_approvals WHERE approval_id = %s AND status = 'pending'",
        (approval_id,),
    )


def approve(approval_id: int, actor: str) -> dict[str, Any]:
    """Approve and execute a pending action. Returns {status, outcome}."""
    from acde.policy import executor

    row = _load_pending(approval_id)
    if row is None:
        return {"status": "not_found", "outcome": f"no pending approval {approval_id}"}
    action = ProposedAction(
        agent=row["agent"],
        action_type=row["action_type"],
        target=row["target"],
        params=row["params"] or {},
        justification=row["justification"] or "approved action",
        confidence=row["confidence"] if row["confidence"] is not None else 1.0,
    )
    result = executor.apply_action(action, row["experiment_run"])
    status = "executed" if result.executed else "failed"
    db.execute(
        "UPDATE telemetry.action_approvals SET status = %s, decided_ts = now(), decided_by = %s, "
        "outcome = %s WHERE approval_id = %s",
        (status, actor, result.outcome, approval_id),
    )
    log.info(
        "approval_decided",
        extra={"approval_id": approval_id, "status": status, "decided_by": actor},
    )
    return {"status": status, "outcome": result.outcome}


def reject(approval_id: int, actor: str, note: str = "") -> dict[str, Any]:
    """Reject a pending action without executing it."""
    row = _load_pending(approval_id)
    if row is None:
        return {"status": "not_found", "outcome": f"no pending approval {approval_id}"}
    db.execute(
        "UPDATE telemetry.action_approvals SET status = 'rejected', decided_ts = now(), "
        "decided_by = %s, decision_note = %s WHERE approval_id = %s",
        (actor, note, approval_id),
    )
    log.info("approval_rejected", extra={"approval_id": approval_id, "decided_by": actor})
    return {"status": "rejected", "outcome": note or "rejected"}
