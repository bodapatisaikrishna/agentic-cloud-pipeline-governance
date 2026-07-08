"""Telemetry-side contracts crossing component boundaries.

Field shapes mirror the ``telemetry`` schema tables (spec §5.1). The spec does
not enumerate fields for these models, so they are defined as minimal faithful
mirrors and may gain fields in Phase 2 (see DEVIATIONS.md).
"""

import datetime as dt
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

FaultType = Literal["schema_drift", "upstream_delay", "resource_contention", "ingress_burst"]
SchemaCompat = Literal["backward", "breaking", "unknown"]


class TaskRunObservation(BaseModel):
    """One Airflow task-instance state observation (telemetry.task_runs)."""

    run_id: str
    dag_id: str
    task_id: str
    state: str
    start_ts: dt.datetime | None = None
    end_ts: dt.datetime | None = None
    duration_s: float | None = None
    try_number: int = 0
    error: str | None = None


class ResourceUsage(BaseModel):
    """Point-in-time resource sample for one component (telemetry.resource_usage)."""

    component: str
    cpu_pct: float
    mem_mb: float
    workers: int
    ts: dt.datetime


class TelemetrySnapshot(BaseModel):
    """What an agent observes in one reasoning cycle.

    Deterministically serializable: identical pipeline state must hash
    identically for the in-run LLM cache (§5.6).
    """

    experiment_run: str
    window_start: dt.datetime
    window_end: dt.datetime
    task_runs: list[TaskRunObservation] = Field(default_factory=list)
    resource_usage: list[ResourceUsage] = Field(default_factory=list)
    pipeline_metrics: dict[str, float] = Field(default_factory=dict)
    schema_compat: SchemaCompat = "unknown"
    open_anomalies: list[dict[str, Any]] = Field(default_factory=list)

    def cache_key_material(self) -> str:
        """Canonical JSON used to key the per-run LLM cache."""
        return self.model_dump_json(exclude={"window_start", "window_end"})


class FailureEvent(BaseModel):
    """Lifecycle of one injected fault (telemetry.failure_events)."""

    event_id: UUID = Field(default_factory=uuid4)
    experiment_run: str
    scenario: str
    fault_type: FaultType
    injected_ts: dt.datetime
    detected_ts: dt.datetime | None = None
    resolved_ts: dt.datetime | None = None
    resolution: str | None = None
