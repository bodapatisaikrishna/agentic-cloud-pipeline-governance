"""Postgres access layer: shared connection pool + retrying execute helpers.

All DB traffic goes through these helpers so retry behaviour, row shape
(dict rows) and pool lifecycle are uniform across components.
"""

from typing import Any, cast

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("db")

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Return the process-wide connection pool, creating it lazily."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.postgres_dsn,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        log.info("db_pool_opened", extra={"max_size": settings.db_pool_max_size})
    return _pool


def close_pool() -> None:
    """Close the pool (graceful shutdown); safe to call when never opened."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        log.info("db_pool_closed")


def _db_retry() -> Any:
    settings = get_settings()
    return retry(
        retry=retry_if_exception_type(psycopg.OperationalError),
        stop=stop_after_attempt(settings.db_retry_attempts),
        wait=wait_exponential(multiplier=settings.db_retry_backoff_s, max=5),
        reraise=True,
    )


def execute(sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> None:
    """Run a statement with bounded retry on transient connection errors."""

    @_db_retry()
    def _run() -> None:
        with get_pool().connection() as conn:
            conn.execute(sql, params)

    _run()


def execute_many(sql: str, rows: list[tuple[Any, ...]] | list[dict[str, Any]]) -> None:
    """Run one statement over many parameter sets, with bounded retry."""
    if not rows:
        return

    @_db_retry()
    def _run() -> None:
        with get_pool().connection() as conn:
            conn.cursor().executemany(sql, rows)

    _run()


def fetch_all(
    sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None
) -> list[dict[str, Any]]:
    """Run a query and return all rows as dicts, with bounded retry."""

    @_db_retry()
    def _run() -> list[dict[str, Any]]:
        with get_pool().connection() as conn:
            # row shape is dict via the pool-level dict_row factory
            return cast(list[dict[str, Any]], conn.execute(sql, params).fetchall())

    return _run()


def fetch_one(
    sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None
) -> dict[str, Any] | None:
    """Run a query and return the first row as a dict (or None), with bounded retry."""

    @_db_retry()
    def _run() -> dict[str, Any] | None:
        with get_pool().connection() as conn:
            # row shape is dict via the pool-level dict_row factory
            return cast("dict[str, Any] | None", conn.execute(sql, params).fetchone())

    return _run()
