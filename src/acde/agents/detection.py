"""Statistical anomaly detection (§5.6) — cheap, deterministic, no LLM.

The LLM only triages/proposes; detection is a z-score over a rolling window plus static
thresholds. Pure functions over a ``TelemetrySnapshot``.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from acde.config import get_settings
from acde.contracts import TelemetrySnapshot


@dataclass(frozen=True)
class Anomaly:
    """A detected anomaly: what kind, on which target, with a short detail."""

    kind: str
    target: str
    detail: str


def zscore(series: list[float], value: float) -> float:
    """Z-score of ``value`` against ``series`` (0.0 if the series has no spread)."""
    if len(series) < 2:
        return 0.0
    mean = statistics.fmean(series)
    stdev = statistics.pstdev(series)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def detect_anomalies(snapshot: TelemetrySnapshot) -> list[Anomaly]:
    """Detect anomalies from task states, freshness, resource usage, and open faults."""
    settings = get_settings()
    anomalies: list[Anomaly] = []

    for task in snapshot.task_runs:
        if task.state in {"failed", "up_for_retry"}:
            anomalies.append(Anomaly("task_failed", task.dag_id, f"{task.task_id}={task.state}"))

    freshness = snapshot.pipeline_metrics.get("freshness_s")
    if freshness is not None and freshness > settings.freshness_sla_streaming_s:
        anomalies.append(
            Anomaly("freshness_breach", "streaming", f"freshness {freshness:.0f}s > SLA")
        )

    for usage in snapshot.resource_usage:
        if usage.cpu_pct > settings.cpu_high_pct:
            anomalies.append(Anomaly("cpu_high", usage.component, f"cpu {usage.cpu_pct:.0f}%"))

    for fault in snapshot.open_anomalies:
        ft = fault.get("fault_type", "unknown")
        anomalies.append(Anomaly(f"open_fault:{ft}", fault.get("scenario", ft), ft))

    if snapshot.schema_compat == "breaking":
        anomalies.append(Anomaly("schema_breaking", "schema", "breaking drift"))

    return anomalies
