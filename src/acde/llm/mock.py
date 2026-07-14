"""Deterministic mock LLM (§8 Phase 5) — the single response source used by all tests.

``mock_propose`` inspects the ``TelemetrySnapshot`` (open faults, schema compatibility,
freshness) and returns a scenario-appropriate ``ProposedAction`` per agent, covering every
agent x scenario. No API calls; token counts are fixed so cost math stays deterministic.
"""

from __future__ import annotations

from typing import Any

from acde.contracts import AgentName, TelemetrySnapshot
from acde.llm.client import LLMResult

# Fixed synthetic token counts for the mock (keeps budget/cost math deterministic).
_TOKENS_IN = 320
_TOKENS_OUT = 48
_MODEL = "mock"


def _open_fault_types(snapshot: TelemetrySnapshot) -> set[str]:
    return {a.get("fault_type", "") for a in snapshot.open_anomalies}


def _action(
    agent: AgentName,
    action_type: str,
    target: str,
    justification: str,
    confidence: float,
    **params: Any,
) -> LLMResult:
    return LLMResult(
        action_json={
            "agent": agent,
            "action_type": action_type,
            "target": target,
            "params": params,
            "justification": justification,
            "confidence": confidence,
        },
        tokens_in=_TOKENS_IN,
        tokens_out=_TOKENS_OUT,
        model=_MODEL,
    )


def _no_action(agent: AgentName, reason: str) -> LLMResult:
    return _action(agent, "no_action", "none", reason, 0.5)


def _monitoring(s: TelemetrySnapshot) -> LLMResult:
    faults = _open_fault_types(s)
    failed = any(t.state in {"failed", "up_for_retry"} for t in s.task_runs)
    if faults or failed:
        target = next(iter(faults), "pipeline")
        return _action(
            "monitoring",
            "raise_anomaly",
            target,
            f"anomaly detected: {sorted(faults) or 'task failure'}",
            0.9,
        )
    return _no_action("monitoring", "all pipelines nominal")


def _recovery(s: TelemetrySnapshot) -> LLMResult:
    faults = _open_fault_types(s)
    if "upstream_delay" in faults:
        return _action(
            "recovery",
            "replay",
            "tpcds_ingest",
            "upstream stabilized; replay the delayed window instead of blind retry",
            0.85,
        )
    if any(t.state == "failed" for t in s.task_runs):
        return _action(
            "recovery",
            "retry_with_backoff",
            "tpcds_ingest",
            "transient task failure; retry with backoff",
            0.8,
        )
    return _no_action("recovery", "no recoverable task failure")


def _optimization(s: TelemetrySnapshot) -> LLMResult:
    faults = _open_fault_types(s)
    freshness = s.pipeline_metrics.get("freshness_s", 0.0)
    if "ingress_burst" in faults or freshness > 60.0:
        return _action(
            "optimization",
            "scale_workers",
            "streaming",
            "ingress burst raising freshness lag; scale streaming workers up",
            0.8,
            n_workers=6,
        )
    if "resource_contention" in faults:
        return _action(
            "optimization",
            "adjust_pool_slots",
            "default_pool",
            "CPU contention; reduce batch pool slots to relieve pressure",
            0.7,
            slots=4,
        )
    return _no_action("optimization", "resource usage within targets")


def _schema(s: TelemetrySnapshot) -> LLMResult:
    if s.schema_compat == "breaking" or "schema_drift" in _open_fault_types(s):
        return _action(
            "schema",
            "quarantine_partition",
            "tpcds_daily_revenue",
            "breaking schema drift; quarantine the partition, other pipelines continue",
            0.9,
            dataset="tpcds_daily_revenue",
            partition_key="2026-01",
        )
    if s.schema_compat == "backward":
        return _action(
            "schema",
            "allow_compatible",
            "tpcds_daily_revenue",
            "backward-compatible change; allow",
            0.8,
        )
    return _no_action("schema", "no schema change observed")


_HANDLERS = {
    "monitoring": _monitoring,
    "recovery": _recovery,
    "optimization": _optimization,
    "schema": _schema,
}


def mock_propose(agent: AgentName, snapshot: TelemetrySnapshot) -> LLMResult:
    """Deterministic proposal for ``agent`` given ``snapshot``."""
    return _HANDLERS[agent](snapshot)
