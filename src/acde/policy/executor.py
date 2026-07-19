"""Action executor: carry out the §5.2 action→side-effect mapping for allowed actions.

Only ``PolicyDecision``-approved actions run; escalations (from the policy or explicit
``escalate*`` actions) insert a ``telemetry.manual_interventions`` row that the human simulator
later resolves. Writing ``telemetry.agent_actions`` is the agents' job (Phase 5); the executor
returns a structured :class:`ExecutionOutcome` (DEVIATIONS D-025).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from acde import db
from acde.config import get_settings
from acde.contracts import PolicyDecision, ProposedAction
from acde.dataplane.partitions import PartitionVersionManager
from acde.logging import get_logger

log = get_logger("policy.executor")


def _airflow_retry() -> Any:
    """Bounded retry for transient Airflow-REST failures (mirrors ``db._db_retry``, D-052)."""
    s = get_settings()
    return retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(s.executor_retry_attempts),
        wait=wait_exponential(multiplier=s.executor_retry_backoff_s, max=5),
        reraise=True,
    )


@dataclass
class ExecutionOutcome:
    """Result of attempting to execute a proposed action."""

    executed: bool
    outcome: str


# --- Control-plane writes -------------------------------------------------------------------


def _upsert_desired_state(key: str, value: dict) -> None:
    db.execute(
        "INSERT INTO control.desired_state (key, value, updated_ts) "
        "VALUES (%s, %s::jsonb, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_ts = now()",
        (key, json.dumps(value)),
    )


# --- Airflow REST (integration-verified) ----------------------------------------------------


def _airflow_client() -> httpx.Client:  # pragma: no cover - network
    s = get_settings()
    return httpx.Client(
        base_url=s.airflow_url, auth=(s.airflow_user, s.airflow_password), timeout=30
    )


def _trigger_dag(dag_id: str) -> str:  # pragma: no cover - network
    run_id = f"recovery__{int(time.time() * 1000)}"

    @_airflow_retry()
    def _run() -> None:
        with _airflow_client() as c:
            c.post(f"/dags/{dag_id}/dagRuns", json={"dag_run_id": run_id}).raise_for_status()

    _run()
    return run_id


def _clear_task_instances(dag_id: str, task_ids: list[str]) -> None:  # pragma: no cover - network
    body: dict = {"dry_run": False, "reset_dag_runs": True, "only_failed": True}
    if task_ids:
        body["task_ids"] = task_ids

    @_airflow_retry()
    def _run() -> None:
        with _airflow_client() as c:
            c.post(f"/dags/{dag_id}/clearTaskInstances", json=body).raise_for_status()

    _run()


def _patch_pool(pool: str, slots: int) -> None:  # pragma: no cover - network
    @_airflow_retry()
    def _run() -> None:
        with _airflow_client() as c:
            c.patch(f"/pools/{pool}", json={"name": pool, "slots": slots}).raise_for_status()

    _run()


# --- Per-action handlers --------------------------------------------------------------------


def _retry(action: ProposedAction, experiment_run: str) -> str:
    return f"triggered dag run {_trigger_dag(action.target)}"


def _partial_recompute(action: ProposedAction, experiment_run: str) -> str:
    task_ids = action.params.get("task_ids", [])
    _clear_task_instances(action.target, task_ids)
    return f"cleared {task_ids or 'failed'} tasks on {action.target}"


def _rollback(action: ProposedAction, experiment_run: str) -> str:
    dataset = action.params.get("dataset", action.target)
    partition_key = action.params.get("partition_key", "2026-01")
    version = PartitionVersionManager(experiment_run=experiment_run).rollback(
        dataset, partition_key
    )
    return f"rolled back {dataset}/{partition_key} to v{version}" if version else "no prior version"


def _scale_workers(action: ProposedAction, experiment_run: str) -> str:
    n = int(action.params.get("n_workers", get_settings().stream_default_workers))
    _upsert_desired_state("streaming.workers", {"n": n})
    return f"streaming.workers -> {n}"


def _adjust_pool_slots(action: ProposedAction, experiment_run: str) -> str:
    slots = int(action.params.get("slots", 1))
    _patch_pool(action.target, slots)
    return f"pool {action.target} slots -> {slots}"


def _quarantine(action: ProposedAction, experiment_run: str) -> str:
    dataset = action.params.get("dataset", action.target)
    partition_key = action.params.get("partition_key", "2026-01")
    db.execute(
        "UPDATE warehouse.partition_versions SET active = FALSE "
        "WHERE dataset = %s AND partition_key = %s",
        (dataset, partition_key),
    )
    db.execute(
        "INSERT INTO warehouse.quarantine_events (dataset, partition_key, reason, payload, "
        "experiment_run) VALUES (%s, %s, %s, %s::jsonb, %s)",
        (dataset, partition_key, action.justification, json.dumps(action.params), experiment_run),
    )
    return f"quarantined {dataset}/{partition_key}"


def _apply_mapping(action: ProposedAction, experiment_run: str) -> str:
    dataset = action.params.get("dataset", action.target)
    mapping = action.params.get("mapping", {})
    _upsert_desired_state(f"schema.mapping.{dataset}", mapping)
    return f"stored schema mapping for {dataset}"


def _block_ingestion(action: ProposedAction, experiment_run: str) -> str:
    dataset = action.params.get("dataset", action.target)
    _upsert_desired_state(f"ingestion.blocked.{dataset}", {"blocked": True})
    return f"blocked ingestion for {dataset}"


def _reprioritize(action: ProposedAction, experiment_run: str) -> str:
    priority = int(action.params.get("priority", 1))
    _upsert_desired_state(f"pipeline.priority.{action.target}", {"priority": priority})
    return f"{action.target} priority -> {priority}"


def _noop(action: ProposedAction, experiment_run: str) -> str:
    return f"acknowledged {action.action_type}"


_HANDLERS = {
    "retry_with_backoff": _retry,
    "replay": _retry,
    "partial_recompute": _partial_recompute,
    "rollback": _rollback,
    "scale_workers": _scale_workers,
    "adjust_pool_slots": _adjust_pool_slots,
    "quarantine_partition": _quarantine,
    "apply_mapping": _apply_mapping,
    "block_ingestion": _block_ingestion,
    "reprioritize_pipeline": _reprioritize,
    "allow_compatible": _noop,
    "raise_anomaly": _noop,
    "no_action": _noop,
}


def _escalate(action: ProposedAction, decision: PolicyDecision, experiment_run: str) -> None:
    db.execute(
        "INSERT INTO telemetry.manual_interventions (experiment_run, reason, requested_ts) "
        "VALUES (%s, %s, now())",
        (experiment_run, f"{action.agent}/{action.action_type}: {decision.reason}"),
    )
    log.info(
        "escalated_to_human",
        extra={
            "action_id": str(action.action_id),
            "agent": action.agent,
            "reason": decision.reason,
            "experiment_run": experiment_run,
        },
    )


# Side-effect-free acknowledgements: always run regardless of execution mode (nothing to gate).
AUTO_ACTIONS = frozenset({"no_action", "raise_anomaly", "allow_compatible"})


def apply_action(action: ProposedAction, experiment_run: str) -> ExecutionOutcome:
    """Run an action's side-effect handler (the real execution core, mode-agnostic).

    On a bounded-retry-exhausted infra error, returns ``executed=False`` with an
    ``execution_failed`` outcome (caller decides whether to escalate). Reused by :func:`execute`
    and the approval workflow (`acde.human.approvals`).
    """
    handler = _HANDLERS.get(action.action_type, _noop)
    try:
        return ExecutionOutcome(executed=True, outcome=handler(action, experiment_run))
    except httpx.HTTPError as exc:
        log.warning(
            "action_execution_failed",
            extra={
                "action_id": str(action.action_id),
                "action_type": action.action_type,
                "error": str(exc),
                "experiment_run": experiment_run,
            },
        )
        return ExecutionOutcome(executed=False, outcome=f"execution_failed: {exc}")


def _effective_mode(action_type: str) -> str:
    """Resolve the execution mode for an allowed action (autonomous can be upgraded to approval)."""
    settings = get_settings()
    mode = settings.acde_mode
    if mode == "autonomous" and action_type in settings.approval_required_set:
        return "approval"  # high-blast-radius action always needs sign-off
    return mode


def execute(
    action: ProposedAction, decision: PolicyDecision, experiment_run: str
) -> ExecutionOutcome:
    """Carry out a gated action per the execution mode (shadow / approval / autonomous)."""
    from acde.notify.webhook import notify

    parts: list[str] = []
    executed = False
    if decision.allowed:
        if action.action_type in AUTO_ACTIONS:
            out = apply_action(action, experiment_run)  # side-effect-free ack, always runs
            executed = out.executed
            parts.append(out.outcome)
        else:
            mode = _effective_mode(action.action_type)
            if mode == "shadow":
                parts.append(f"shadow: would execute {action.action_type} on {action.target}")
                notify("shadow_proposal", action, decision, experiment_run)
            elif mode == "approval":
                from acde.human.approvals import create_pending

                aid = create_pending(action, decision, experiment_run)
                parts.append(f"pending_approval:{aid}")
                notify("pending_approval", action, decision, experiment_run, approval_id=aid)
            else:  # autonomous
                out = apply_action(action, experiment_run)
                executed = out.executed
                parts.append(out.outcome)
                if not out.executed:  # infra failure after retries → escalate, never crash
                    _escalate(action, decision, experiment_run)
                    notify("execution_failure", action, decision, experiment_run)
                    parts.append("escalated_to_human")
    if decision.escalate:
        _escalate(action, decision, experiment_run)
        notify("escalation", action, decision, experiment_run)
        parts.append("escalated_to_human")
    if not decision.allowed and not decision.escalate:
        parts.append(f"denied: {decision.reason}")
    outcome = "; ".join(parts)
    log.info(
        "action_executed",
        extra={
            "action_id": str(action.action_id),
            "action_type": action.action_type,
            "executed": executed,
            "outcome": outcome,
            "experiment_run": experiment_run,
        },
    )
    return ExecutionOutcome(executed=executed, outcome=outcome)
