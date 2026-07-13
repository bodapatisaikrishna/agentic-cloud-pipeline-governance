"""Operational cost ledger (§5.5) — disclosed, normalized cost model.

    cost_units = compute_unit_seconds * rate_compute + storage_gb_hours * rate_storage
    compute_unit_seconds = sum over components: (active workers or pool slots) * wall seconds

The compute driver is the two logical resource-unit series the collector records into
``telemetry.resource_usage`` (``component='streaming'`` = streaming worker pool,
``component='batch'`` = Airflow running slots); storage is the live ``warehouse``-schema size
(see DEVIATIONS D-018). The integration math is pure and unit-verified against a hand fixture.
"""

from __future__ import annotations

import argparse
import datetime as dt

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("telemetry.cost")

# Components whose worker/slot counts drive compute cost.
COMPUTE_COMPONENTS = ("streaming", "batch")
STORAGE_COMPONENT = "postgres"


def integrate_worker_seconds(
    samples: list[tuple[dt.datetime, float]],
    window_start: dt.datetime,
    window_end: dt.datetime,
) -> float:
    """Step-integrate a worker-count series over [window_start, window_end].

    ``samples`` is ``(ts, workers)`` sorted by ts. Each sample's count holds until the next
    sample; the series is clamped to the window. A sample at or before ``window_start``
    establishes the count entering the window.
    """
    if window_end <= window_start or not samples:
        return 0.0
    ordered = sorted(samples, key=lambda s: s[0])
    total = 0.0
    # Count in effect at window_start = the last sample at or before it (else the first sample).
    current = None
    for ts, workers in ordered:
        if ts <= window_start:
            current = workers
    cursor = window_start
    for ts, workers in ordered:
        if ts <= window_start or ts >= window_end:
            continue
        if current is not None:
            total += current * (ts - cursor).total_seconds()
        cursor = ts
        current = workers
    if current is not None:
        total += current * (window_end - cursor).total_seconds()
    return total


def cost_units(
    compute_unit_seconds: float,
    storage_gb_hours: float,
    rate_compute: float | None = None,
    rate_storage: float | None = None,
) -> float:
    """Combine compute + storage into cost units at the disclosed rates."""
    settings = get_settings()
    rate_compute = settings.cost_rate_compute_unit_second if rate_compute is None else rate_compute
    rate_storage = settings.cost_rate_storage_gb_hour if rate_storage is None else rate_storage
    return compute_unit_seconds * rate_compute + storage_gb_hours * rate_storage


def warehouse_size_gb() -> float:
    """Total on-disk size of the ``warehouse`` schema, in gigabytes."""
    row = db.fetch_one(
        "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0) AS bytes "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'warehouse'"
    )
    # pg_total_relation_size sums to a numeric → psycopg returns Decimal; coerce to float.
    return (float(row["bytes"]) / 1e9) if row else 0.0


def _worker_samples(
    experiment_run: str, component: str, window_start: dt.datetime, window_end: dt.datetime
) -> list[tuple[dt.datetime, float]]:
    rows = db.fetch_all(
        "SELECT ts, workers FROM telemetry.resource_usage "
        "WHERE experiment_run = %s AND component = %s AND ts <= %s ORDER BY ts",
        (experiment_run, component, window_end),
    )
    return [(r["ts"], float(r["workers"] or 0)) for r in rows]


def compute_cost_windows(experiment_run: str | None = None, window_s: float | None = None) -> int:
    """Aggregate ``resource_usage`` into per-component 1-min ``cost_ledger`` rows.

    Returns the number of ledger rows written. Idempotent per (experiment_run, component,
    window_start) via delete-then-insert of the run's ledger.
    """
    settings = get_settings()
    experiment_run = settings.experiment_run if experiment_run is None else experiment_run
    window_s = settings.cost_window_s if window_s is None else window_s

    span = db.fetch_one(
        "SELECT MIN(ts) AS lo, MAX(ts) AS hi FROM telemetry.resource_usage "
        "WHERE experiment_run = %s",
        (experiment_run,),
    )
    if not span or span["lo"] is None:
        log.warning("cost_no_samples", extra={"experiment_run": experiment_run})
        return 0

    db.execute("DELETE FROM telemetry.cost_ledger WHERE experiment_run = %s", (experiment_run,))
    storage_gb = warehouse_size_gb()
    delta = dt.timedelta(seconds=window_s)
    written = 0
    start = span["lo"]
    while start < span["hi"] + delta:
        end = start + delta
        for component in COMPUTE_COMPONENTS:
            samples = _worker_samples(experiment_run, component, start, end)
            cus = integrate_worker_seconds(samples, start, end)
            if cus <= 0:
                continue
            db.execute(
                "INSERT INTO telemetry.cost_ledger (experiment_run, component, "
                "compute_unit_seconds, storage_gb_hours, cost_units, window_start, window_end) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (experiment_run, component, cus, 0.0, cost_units(cus, 0.0), start, end),
            )
            written += 1
        # storage cost for the window, attributed to the storage component
        sgh = storage_gb * (window_s / 3600.0)
        db.execute(
            "INSERT INTO telemetry.cost_ledger (experiment_run, component, "
            "compute_unit_seconds, storage_gb_hours, cost_units, window_start, window_end) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (experiment_run, STORAGE_COMPONENT, 0.0, sgh, cost_units(0.0, sgh), start, end),
        )
        written += 1
        start = end
    log.info("cost_windows_written", extra={"experiment_run": experiment_run, "rows": written})
    return written


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE cost-ledger aggregator")
    parser.add_argument("--experiment-run", default=None)
    args = parser.parse_args()
    compute_cost_windows(experiment_run=args.experiment_run)


if __name__ == "__main__":  # pragma: no cover
    main()
