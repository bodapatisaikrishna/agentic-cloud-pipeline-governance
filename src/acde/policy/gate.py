"""OPA policy gate: turn a ProposedAction + context into a PolicyDecision.

The gate assembles the policy ``context`` (projected marginal cost, prior-version existence,
recent-action count) so OPA stays a pure decision function (DEVIATIONS D-021), then POSTs
``input`` to ``data.acde.policy.decision``. If OPA is unreachable it fails safe by escalating
(D-023).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from acde import db
from acde.config import get_settings
from acde.contracts import PolicyDecision, ProposedAction
from acde.dataplane.partitions import PartitionVersionManager
from acde.logging import get_logger

log = get_logger("policy.gate")

DECISION_PATH = "/v1/data/acde/policy/decision"


# Marginal cost of one added streaming worker or pool slot over one cost window, in cost units
# (workers * window_s * compute rate). Used to price scale-ups for the budget policy.
def _unit_marginal_cost() -> float:
    s = get_settings()
    return s.cost_window_s * s.cost_rate_compute_unit_second


def projected_marginal_cost(action: ProposedAction, current_workers: int) -> float:
    """Estimate the marginal cost of a scaling action (>0 scale-up, <=0 scale-down)."""
    if action.action_type == "scale_workers":
        target = int(action.params.get("n_workers", current_workers))
        return (target - current_workers) * _unit_marginal_cost()
    if action.action_type == "adjust_pool_slots":
        target = int(action.params.get("slots", current_workers))
        return (target - current_workers) * _unit_marginal_cost()
    return 0.0


def _actions_last_10min(agent: str, experiment_run: str) -> int:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
    row = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.agent_actions "
        "WHERE agent = %s AND experiment_run = %s AND ts >= %s",
        (agent, experiment_run, since),
    )
    return int(row["n"]) if row else 0


def _has_prior_version(action: ProposedAction) -> bool:
    if action.action_type != "rollback":
        return False
    dataset = action.params.get("dataset", action.target)
    partition_key = action.params.get("partition_key", "2026-01")
    versions = PartitionVersionManager().list_versions(dataset, partition_key)
    active = PartitionVersionManager().get_active(dataset, partition_key)
    if active is None:
        return len(versions) >= 1
    return any(v["version"] < active["version"] for v in versions)


def build_context(
    action: ProposedAction,
    experiment_run: str,
    current_workers: int = 2,
    schema_compat: str = "unknown",
    budget_remaining_units: float | None = None,
    pipeline_criticality: str = "normal",
    mode: str = "acde",
) -> dict[str, Any]:
    """Assemble the OPA input context for ``action`` from settings + live state."""
    settings = get_settings()
    return {
        "projected_marginal_cost": projected_marginal_cost(action, current_workers),
        "budget_remaining_units": (
            settings.budget_default_units
            if budget_remaining_units is None
            else budget_remaining_units
        ),
        "actions_last_10min": _actions_last_10min(action.agent, experiment_run),
        "schema_compat": schema_compat,
        "has_prior_version": _has_prior_version(action),
        "pipeline_criticality": pipeline_criticality,
        "mode": mode,
    }


_ESCALATE_ON_FAILURE = PolicyDecision(
    allowed=False,
    escalate=True,
    reason="OPA unavailable; failing safe by escalating",
    policy_id="gate_failsafe",
)


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, max=2),
    reraise=True,
)
def _query_opa(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    resp = httpx.post(f"{settings.opa_url}{DECISION_PATH}", json={"input": payload}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def evaluate(action: ProposedAction, context: dict[str, Any]) -> PolicyDecision:
    """Evaluate ``action`` against OPA; fail safe (escalate) if OPA is unreachable."""
    payload = {"action": action.model_dump(mode="json"), "context": context}
    try:
        result = _query_opa(payload)
    except httpx.HTTPError:
        log.warning("opa_unavailable_failsafe_escalate", extra={"action_id": str(action.action_id)})
        return _ESCALATE_ON_FAILURE
    if not result:
        log.warning("opa_empty_result_failsafe", extra={"action_id": str(action.action_id)})
        return _ESCALATE_ON_FAILURE
    decision = PolicyDecision(
        allowed=bool(result["allowed"]),
        escalate=bool(result["escalate"]),
        reason=str(result["reason"]),
        policy_id=str(result["policy_id"]),
    )
    log.info(
        "policy_decision",
        extra={
            "action_id": str(action.action_id),
            "agent": action.agent,
            "action_type": action.action_type,
            "allowed": decision.allowed,
            "escalate": decision.escalate,
            "policy_id": decision.policy_id,
        },
    )
    return decision
