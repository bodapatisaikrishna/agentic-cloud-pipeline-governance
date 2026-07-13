"""Data-freshness metrics (§5.4) → ``telemetry.pipeline_metrics``.

- Streaming freshness (exact, SLA-relevant): ``materialized_ts - event_ts`` of the latest
  window per pipeline. SLA is ``freshness_sla_streaming_s`` (default 60s).
- Batch freshness: staleness of the freshest available partition, ``now - created_ts``
  (our synthetic sources lack a distinct arrival timestamp; DEVIATIONS D-019).
"""

from __future__ import annotations

import datetime as dt

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("telemetry.freshness")


def _record(pipeline_id: str, metric: str, value: float, experiment_run: str) -> None:
    db.execute(
        "INSERT INTO telemetry.pipeline_metrics (pipeline_id, metric, value, experiment_run) "
        "VALUES (%s, %s, %s, %s)",
        (pipeline_id, metric, value, experiment_run),
    )


def streaming_freshness(experiment_run: str | None = None) -> list[tuple[str, float]]:
    """Record ``freshness_s`` for the latest window of each streaming pipeline.

    Returns the (pipeline_id, freshness_s) pairs recorded.
    """
    settings = get_settings()
    experiment_run = settings.experiment_run if experiment_run is None else experiment_run
    # Latest window per streaming pipeline (freshness is a point-in-time snapshot); the metric
    # is tagged with the collector's experiment_run regardless of the source rows' tag.
    rows = db.fetch_all(
        "SELECT DISTINCT ON (pipeline_id) pipeline_id, "
        "  EXTRACT(EPOCH FROM (materialized_ts - event_ts)) AS freshness_s "
        "FROM warehouse.stream_aggregates "
        "ORDER BY pipeline_id, window_start DESC"
    )
    recorded: list[tuple[str, float]] = []
    for row in rows:
        freshness = float(row["freshness_s"])
        _record(row["pipeline_id"], "freshness_s", freshness, experiment_run)
        recorded.append((row["pipeline_id"], freshness))
    log.info(
        "streaming_freshness_recorded",
        extra={"experiment_run": experiment_run, "pipelines": len(recorded)},
    )
    return recorded


def batch_freshness(experiment_run: str | None = None) -> list[tuple[str, float]]:
    """Record ``batch_freshness_s`` (staleness) for each active partition."""
    settings = get_settings()
    experiment_run = settings.experiment_run if experiment_run is None else experiment_run
    now = dt.datetime.now(dt.UTC)
    rows = db.fetch_all("SELECT dataset, created_ts FROM warehouse.partition_versions WHERE active")
    recorded: list[tuple[str, float]] = []
    for row in rows:
        staleness = (now - row["created_ts"]).total_seconds()
        _record(row["dataset"], "batch_freshness_s", staleness, experiment_run)
        recorded.append((row["dataset"], staleness))
    log.info(
        "batch_freshness_recorded",
        extra={"experiment_run": experiment_run, "partitions": len(recorded)},
    )
    return recorded


def collect(experiment_run: str | None = None) -> None:
    """Record all freshness metrics."""
    streaming_freshness(experiment_run)
    batch_freshness(experiment_run)
