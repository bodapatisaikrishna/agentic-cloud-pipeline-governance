"""Versioned warehouse partitions — the substrate for rollback (§5.2).

Each (dataset, partition_key, version) is a physical table in the ``warehouse`` schema,
registered in ``warehouse.partition_versions`` with an ``active`` pointer. Rollback is a
transactional pointer flip (no data movement), reused by the recovery agent in later phases.
"""

from __future__ import annotations

import re
from typing import Any

from acde import db
from acde.logging import get_logger

log = get_logger("dataplane.partitions")

_SAFE = re.compile(r"[^a-z0-9_]+")


def _slug(text: str) -> str:
    """Lowercase identifier-safe slug for physical table names."""
    return _SAFE.sub("_", text.lower()).strip("_")


def table_name(dataset: str, partition_key: str, version: int) -> str:
    """Deterministic physical table name for a partition version."""
    return f"{_slug(dataset)}__{_slug(partition_key)}__v{version}"


class PartitionVersionManager:
    """Create, activate, and roll back versioned partition tables."""

    def __init__(self, experiment_run: str | None = None) -> None:
        self.experiment_run = experiment_run

    def next_version(self, dataset: str, partition_key: str) -> int:
        row = db.fetch_one(
            "SELECT COALESCE(MAX(version), 0) AS v FROM warehouse.partition_versions "
            "WHERE dataset = %s AND partition_key = %s",
            (dataset, partition_key),
        )
        return int(row["v"]) + 1 if row else 1

    def create_version(
        self,
        dataset: str,
        partition_key: str,
        columns_ddl: str,
        rows: list[tuple[Any, ...]],
        insert_columns: str,
        activate: bool = True,
    ) -> int:
        """Materialize a new version table, insert ``rows``, register it, optionally activate.

        ``columns_ddl`` is the column definition for the new table (e.g. ``"d date, revenue
        double precision"``); ``insert_columns`` names the columns for the multi-row insert.
        """
        version = self.next_version(dataset, partition_key)
        tname = table_name(dataset, partition_key, version)
        qualified = f"warehouse.{tname}"
        db.execute(f"DROP TABLE IF EXISTS {qualified}")
        db.execute(f"CREATE TABLE {qualified} ({columns_ddl})")
        if rows:
            placeholders = ", ".join(["%s"] * len(rows[0]))
            db.execute_many(
                f"INSERT INTO {qualified} ({insert_columns}) VALUES ({placeholders})", rows
            )
        db.execute(
            "INSERT INTO warehouse.partition_versions "
            "(dataset, partition_key, version, table_name, active) VALUES (%s, %s, %s, %s, %s)",
            (dataset, partition_key, version, tname, False),
        )
        log.info(
            "partition_version_created",
            extra={
                "dataset": dataset,
                "partition_key": partition_key,
                "version": version,
                "rows": len(rows),
                "experiment_run": self.experiment_run,
            },
        )
        if activate:
            self.activate(dataset, partition_key, version)
        return version

    def activate(self, dataset: str, partition_key: str, version: int) -> None:
        """Transactionally flip the active pointer to ``version``."""
        with db.get_pool().connection() as conn, conn.transaction():
            conn.execute(
                "UPDATE warehouse.partition_versions SET active = FALSE "
                "WHERE dataset = %s AND partition_key = %s",
                (dataset, partition_key),
            )
            conn.execute(
                "UPDATE warehouse.partition_versions SET active = TRUE "
                "WHERE dataset = %s AND partition_key = %s AND version = %s",
                (dataset, partition_key, version),
            )
        log.info(
            "partition_activated",
            extra={
                "dataset": dataset,
                "partition_key": partition_key,
                "version": version,
                "experiment_run": self.experiment_run,
            },
        )

    def get_active(self, dataset: str, partition_key: str) -> dict[str, Any] | None:
        return db.fetch_one(
            "SELECT * FROM warehouse.partition_versions "
            "WHERE dataset = %s AND partition_key = %s AND active",
            (dataset, partition_key),
        )

    def list_versions(self, dataset: str, partition_key: str) -> list[dict[str, Any]]:
        return db.fetch_all(
            "SELECT * FROM warehouse.partition_versions "
            "WHERE dataset = %s AND partition_key = %s ORDER BY version",
            (dataset, partition_key),
        )

    def rollback(self, dataset: str, partition_key: str) -> int | None:
        """Activate the highest version below the current active one. Returns it, or None."""
        current = self.get_active(dataset, partition_key)
        versions = [v["version"] for v in self.list_versions(dataset, partition_key)]
        if current is None:
            prior = [v for v in versions]
        else:
            prior = [v for v in versions if v < current["version"]]
        if not prior:
            log.warning(
                "rollback_no_prior_version",
                extra={
                    "dataset": dataset,
                    "partition_key": partition_key,
                    "experiment_run": self.experiment_run,
                },
            )
            return None
        target = max(prior)
        self.activate(dataset, partition_key, target)
        return target
