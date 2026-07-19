"""Connector protocol: the boundary between ACDE and a customer's orchestrator (P2).

A `Connector` exposes what ACDE needs from an external pipeline system: read telemetry (task
runs / freshness) and apply the small set of remediation actions the executor performs (retry a
pipeline, clear failed tasks, resize a worker pool). Implementations wrap a real system (Airflow)
or do nothing (noop, observe-only). Keeping this narrow means adding Dagster/Prefect later is a new
class, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ConnectorHealth:
    """Result of a connector reachability/authz probe (for `acde doctor`)."""

    name: str
    ok: bool
    detail: str
    can_act: bool = False  # False for observe-only connectors


@dataclass
class TaskRun:
    """A normalized pipeline task-run observation."""

    pipeline_id: str
    task_id: str
    state: str
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    """What the ACDE runtime requires of an external orchestrator."""

    name: str
    can_act: bool  # whether this connector performs side effects (False = observe-only)
    is_production: bool  # game-day/chaos must refuse to run against a production connector

    def health(self) -> ConnectorHealth:
        """Probe reachability + auth; used by `acde doctor` and startup validation."""
        ...

    def get_task_runs(self, pipeline_id: str) -> list[TaskRun]:
        """Recent task runs for a pipeline (telemetry source)."""
        ...

    def trigger_pipeline(self, pipeline_id: str) -> str:
        """Trigger/replay a pipeline run; returns a run id."""
        ...

    def clear_tasks(self, pipeline_id: str, task_ids: list[str]) -> None:
        """Clear (re-run) failed task instances."""
        ...

    def set_pool_slots(self, pool: str, slots: int) -> None:
        """Resize a worker/execution pool."""
        ...
