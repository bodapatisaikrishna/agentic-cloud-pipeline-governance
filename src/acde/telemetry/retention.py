"""Delete telemetry older than a configured window (D-086).

Off by default (``RETENTION_DAYS=0``) so upgrading never silently deletes data — an operator opts
in explicitly. ``telemetry.agent_actions`` is deliberately exempt: it is the audit trail this whole
product's trust claim rests on, not disposable noise, and pruning it is a separate, more careful
feature (archival, not deletion) this does not attempt. The tables here are the ones the production
audit actually measured as the volume driver (``resource_usage`` alone: ~6.3M rows/year/component
at the default ``TELEMETRY_INTERVAL_S=5``).
"""

from __future__ import annotations

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("telemetry.retention")

# (schema.table, timestamp column) for every table retention is allowed to prune.
_RETAINABLE = (
    ("telemetry.resource_usage", "ts"),
    ("telemetry.pipeline_metrics", "ts"),
    ("telemetry.task_runs", "start_ts"),
)


def purge(days: int | None = None) -> dict[str, int]:
    """Delete rows older than ``days`` from the retainable tables. Returns rows deleted per table.

    ``days`` defaults to ``Settings.retention_days``; a value of 0 (the default) is a deliberate
    no-op, not an error — retention is opt-in.
    """
    window = days if days is not None else get_settings().retention_days
    if window <= 0:
        log.info("retention_disabled", extra={"retention_days": window})
        return {}
    deleted: dict[str, int] = {}
    for table, ts_column in _RETAINABLE:
        row = db.fetch_one(
            f"WITH deleted AS (DELETE FROM {table} WHERE {ts_column} < now() - %s * interval "
            "'1 day' RETURNING 1) SELECT count(*) AS n FROM deleted",
            (window,),
        )
        n = int(row["n"]) if row else 0
        deleted[table] = n
        log.info("retention_purged", extra={"table": table, "rows_deleted": n, "days": window})
    return deleted


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Delete telemetry older than N days")
    parser.add_argument("--days", type=int, default=None, help="override RETENTION_DAYS")
    args = parser.parse_args()
    print(json.dumps(purge(args.days), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
