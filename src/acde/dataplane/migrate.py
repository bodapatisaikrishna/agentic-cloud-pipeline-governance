"""Apply the idempotent init SQL to a running database.

Postgres only runs ``/docker-entrypoint-initdb.d`` on first volume init, so new tables added
in later phases need a way to reach existing volumes without ``make clean``. This re-applies
every ``infra/postgres/init/*.sql`` (all ``IF NOT EXISTS``) — see DEVIATIONS D-017.
"""

from __future__ import annotations

from pathlib import Path

from acde import db
from acde.logging import get_logger

log = get_logger("dataplane.migrate")

INIT_DIR = Path(__file__).resolve().parents[3] / "infra" / "postgres" / "init"


def apply() -> None:
    """Run each init SQL file in order (idempotent)."""
    if not INIT_DIR.is_dir():  # pragma: no cover - only outside the source tree
        log.warning("migrate_no_init_dir", extra={"path": str(INIT_DIR)})
        return
    for sql_file in sorted(INIT_DIR.glob("*.sql")):
        db.execute(sql_file.read_text())
        log.info("migration_applied", extra={"file": sql_file.name})


if __name__ == "__main__":  # pragma: no cover
    apply()
