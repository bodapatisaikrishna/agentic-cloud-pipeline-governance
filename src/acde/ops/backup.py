"""Database backup & restore (D-099) — shells out to the real ``pg_dump``/``pg_restore``, the
Postgres-native tools for this, rather than reimplementing a dump format. Custom format (``-Fc``):
compressed, and the only format ``pg_restore`` can selectively/parallel-restore from.

Connection is passed via environment variables (``PGHOST``/``PGPORT``/``PGUSER``/``PGPASSWORD``/
``PGDATABASE``), never as a command-line argument -- an argv-embedded password is visible to any
other process on the host via ``ps aux``; environment variables of a child process are not.

CLI-only (``acde backup``/``acde restore`` in ``cli.py``) -- deliberately no HTTP route. A
network-reachable restore endpoint is a meaningfully larger attack surface for no real benefit: an
operator invoking this already has shell access to the container/pod, the same trust boundary
every other ``acde`` CLI command assumes.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("ops.backup")


def _pg_env(dbname: str) -> dict[str, str]:
    s = get_settings()
    return {
        **os.environ,
        "PGHOST": s.postgres_host,
        "PGPORT": str(s.postgres_port),
        "PGUSER": s.postgres_user,
        "PGPASSWORD": s.postgres_password.get_secret_value(),
        "PGDATABASE": dbname,
    }


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(
            f"'{name}' not found on PATH -- install the postgresql-client package "
            "(the production image does from D-099 onward; a local checkout needs it too)"
        )
    return path


def backup(output_dir: Path | None = None) -> Path:
    """Dump the configured database to a timestamped ``.dump`` file. Returns the file path."""
    pg_dump = _require_tool("pg_dump")
    s = get_settings()
    out_dir = output_dir or Path(s.backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"acde_backup_{ts}.dump"
    result = subprocess.run(
        [pg_dump, "-Fc", "-f", str(out_path)],
        env=_pg_env(s.postgres_db),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}")
    log.info("backup_written", extra={"path": str(out_path), "bytes": out_path.stat().st_size})
    return out_path


def restore(dump_path: Path, target_db: str | None = None) -> None:
    """Restore ``dump_path`` into ``target_db`` (default: the configured live database --
    destructive, drops and recreates every object the dump captured). Pass a different
    ``target_db`` to run a restore drill without touching the live database."""
    pg_restore = _require_tool("pg_restore")
    if not dump_path.exists():
        raise RuntimeError(f"no such dump file: {dump_path}")
    s = get_settings()
    db_name = target_db or s.postgres_db
    result = subprocess.run(
        [pg_restore, "--clean", "--if-exists", "--no-owner", "-d", db_name, str(dump_path)],
        env=_pg_env(db_name),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore failed (exit {result.returncode}): {result.stderr.strip()}")
    log.info("restore_complete", extra={"path": str(dump_path), "target_db": db_name})
