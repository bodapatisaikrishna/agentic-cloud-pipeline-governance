"""Unit tests for the DB access layer (pool mocked; no real database)."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import psycopg
import pytest

from acde import db


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    """Zero out retry sleeps so failure-path tests run instantly."""
    from acde.config import Settings

    settings = Settings(_env_file=None, db_retry_backoff_s=0.0)
    monkeypatch.setattr(db, "get_settings", lambda: settings)


def _pool_with(conn: MagicMock) -> MagicMock:
    pool = MagicMock()

    @contextmanager
    def connection():
        yield conn

    pool.connection = connection
    return pool


def _install_pool(monkeypatch, execute_side_effect):
    conn = MagicMock()
    conn.execute.side_effect = execute_side_effect
    monkeypatch.setattr(db, "get_pool", lambda: _pool_with(conn))
    return conn


class TestRetry:
    def test_transient_failures_then_success(self, monkeypatch):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"n": 1}]
        conn = _install_pool(
            monkeypatch,
            [psycopg.OperationalError("gone"), psycopg.OperationalError("gone"), cursor],
        )
        assert db.fetch_all("SELECT 1") == [{"n": 1}]
        assert conn.execute.call_count == 3

    def test_persistent_failure_raises_after_max_attempts(self, monkeypatch):
        conn = _install_pool(monkeypatch, psycopg.OperationalError("down"))
        with pytest.raises(psycopg.OperationalError):
            db.execute("SELECT 1")
        assert conn.execute.call_count == 3

    def test_non_operational_errors_not_retried(self, monkeypatch):
        conn = _install_pool(monkeypatch, psycopg.errors.UndefinedTable("no table"))
        with pytest.raises(psycopg.errors.UndefinedTable):
            db.execute("SELECT * FROM nope")
        assert conn.execute.call_count == 1


class TestHelpers:
    def test_fetch_one_returns_row(self, monkeypatch):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"key": "streaming.workers"}
        _install_pool(monkeypatch, [cursor])
        assert db.fetch_one("SELECT ...") == {"key": "streaming.workers"}

    def test_execute_passes_params(self, monkeypatch):
        conn = _install_pool(monkeypatch, [MagicMock()])
        db.execute("INSERT INTO t VALUES (%s)", ("v",))
        conn.execute.assert_called_once_with("INSERT INTO t VALUES (%s)", ("v",))


class TestPoolLifecycle:
    def test_close_pool_when_never_opened_is_safe(self):
        db._pool = None
        db.close_pool()

    def test_close_pool_closes_and_resets(self):
        fake = MagicMock()
        db._pool = fake
        db.close_pool()
        fake.close.assert_called_once()
        assert db._pool is None
