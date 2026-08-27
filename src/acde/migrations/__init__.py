"""Versioned, forward-only schema migrations (DEVIATIONS D-083).

Postgres runs ``/docker-entrypoint-initdb.d`` only on first volume init, and the previous
``dataplane.migrate`` resolved its SQL directory relative to the *repo root* — a path that does not
exist inside the installed wheel, so it silently no-opped in production. There was therefore no way
to get a schema change into an existing production database at all.

The SQL lives beside this module, **inside the package**, so it ships in the wheel and is reachable
wherever ACDE runs. Guarantees:

- **One transaction per migration**, with the version row written in the same transaction, so a
  failure leaves neither partial DDL nor a bogus version record. A migration needing
  ``CREATE INDEX CONCURRENTLY`` opts out with a ``-- acde:no-transaction`` marker.
- **A session advisory lock** around the whole run, so two servers starting at once cannot race.
- **A checksum guard**: an already-applied file that changed on disk stops the run. Silently
  skipping an edited migration is how environments drift apart.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acde import db
from acde.logging import get_logger

log = get_logger("migrations")

MIGRATIONS_DIR = Path(__file__).resolve().parent
# Distinct from the per-target lock in orchestrator.locks: this one serialises schema changes.
ADVISORY_LOCK_KEY = 0x_ACDE_5C4A
_FILENAME = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")
_NO_TRANSACTION = "-- acde:no-transaction"


class MigrationError(RuntimeError):
    """Raised when the migration set on disk cannot be trusted."""


@dataclass(frozen=True)
class Migration:
    """One versioned schema change."""

    version: str
    name: str
    sql: str
    checksum: str
    transactional: bool

    @property
    def label(self) -> str:
        return f"{self.version}_{self.name}"


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


def discover(directory: Path | None = None) -> list[Migration]:
    """Return every migration on disk, ordered by version. Rejects a duplicated version."""
    source = directory or MIGRATIONS_DIR
    found: dict[str, Migration] = {}
    for path in sorted(source.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if not match:
            raise MigrationError(
                f"migration filename must be NNN_lower_snake.sql, got {path.name!r}"
            )
        version, name = match.group(1), match.group(2)
        if version in found:
            raise MigrationError(f"duplicate migration version {version}: {found[version].label}")
        sql = path.read_text()
        found[version] = Migration(
            version=version,
            name=name,
            sql=sql,
            checksum=_checksum(sql),
            transactional=_NO_TRANSACTION not in sql,
        )
    return [found[v] for v in sorted(found)]


def _ensure_tracking_table(conn: Any) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS control")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS control.schema_migrations ("
        "  version TEXT PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  checksum TEXT NOT NULL,"
        "  applied_ts TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def _applied(conn: Any) -> dict[str, str]:
    rows = conn.execute("SELECT version, checksum FROM control.schema_migrations").fetchall()
    return {r["version"]: r["checksum"] for r in rows}


def _verify_no_drift(pending: list[Migration], applied: dict[str, str]) -> None:
    """Refuse to run if an already-applied migration's content changed on disk."""
    for migration in pending:
        recorded = applied.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise MigrationError(
                f"migration {migration.label} was already applied but its content changed on disk "
                f"(recorded {recorded[:12]}, found {migration.checksum[:12]}). "
                "Migrations are immutable once applied — add a new one instead."
            )


def status(directory: Path | None = None) -> dict[str, Any]:
    """Report which migrations are applied and which are pending, without changing anything."""
    migrations = discover(directory)
    with db.get_pool().connection() as conn:
        _ensure_tracking_table(conn)
        applied = _applied(conn)
    _verify_no_drift(migrations, applied)
    pending = [m.label for m in migrations if m.version not in applied]
    return {
        "applied": sorted(applied),
        "pending": pending,
        "current_version": max(applied) if applied else None,
    }


def apply(directory: Path | None = None) -> list[str]:
    """Apply every pending migration in order. Returns the labels actually applied."""
    migrations = discover(directory)
    done: list[str] = []
    with db.get_pool().connection() as lock_conn:
        # Session-scoped: held for the whole run so a second process waits rather than racing.
        lock_conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
        try:
            _ensure_tracking_table(lock_conn)
            lock_conn.commit()
            with db.get_pool().connection() as read_conn:
                applied = _applied(read_conn)
            _verify_no_drift(migrations, applied)
            for migration in migrations:
                if migration.version in applied:
                    continue
                _run_one(migration)
                done.append(migration.label)
                log.info(
                    "migration_applied",
                    extra={"version": migration.version, "migration_name": migration.name},
                )
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
    if not done:
        log.info("migrations_up_to_date", extra={"count": len(migrations)})
    return done


def _record_sql() -> str:
    return "INSERT INTO control.schema_migrations (version, name, checksum) VALUES (%s, %s, %s)"


def _run_one(migration: Migration) -> None:
    """Apply one migration, recording its version in the same transaction where possible."""
    params = (migration.version, migration.name, migration.checksum)
    if migration.transactional:
        with db.get_pool().connection() as conn:
            conn.execute(migration.sql)
            conn.execute(_record_sql(), params)
        return
    # CREATE INDEX CONCURRENTLY and friends cannot run inside a transaction block. The version row
    # is written in a separate transaction afterwards, so an interrupted run re-applies the file;
    # such migrations must therefore be independently idempotent (IF NOT EXISTS).
    with db.get_pool().connection() as conn:
        conn.autocommit = True
        conn.execute(migration.sql)
    db.execute(_record_sql(), params)


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Apply ACDE schema migrations")
    parser.add_argument("--status", action="store_true", help="report state without applying")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(status(), indent=2))
        return
    applied = apply()
    print(f"applied {len(applied)} migration(s)" + (": " + ", ".join(applied) if applied else ""))


if __name__ == "__main__":  # pragma: no cover
    main()
