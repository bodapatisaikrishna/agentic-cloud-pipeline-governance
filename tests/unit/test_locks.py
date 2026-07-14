"""Unit tests for the advisory-lock helper (mocked pooled connection)."""

from contextlib import contextmanager
from unittest.mock import MagicMock

from acde.orchestrator import locks
from acde.orchestrator.locks import _lock_key, target_advisory_lock


class TestLockKey:
    def test_deterministic(self):
        assert _lock_key("streaming") == _lock_key("streaming")

    def test_differs_by_target(self):
        assert _lock_key("streaming") != _lock_key("tpcds_ingest")

    def test_in_signed_int32_range(self):
        for t in ("a", "streaming", "tpcds_daily_revenue", "default_pool"):
            assert -(2**31) <= _lock_key(t) < 2**31


def _install_conn(monkeypatch, try_lock_result: bool):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {"pg_try_advisory_lock": try_lock_result}

    @contextmanager
    def connection():
        yield conn

    pool = MagicMock()
    pool.connection = connection
    monkeypatch.setattr(locks.db, "get_pool", lambda: pool)
    return conn


class TestTargetAdvisoryLock:
    def test_acquired_yields_true_and_unlocks(self, monkeypatch):
        conn = _install_conn(monkeypatch, True)
        with target_advisory_lock("streaming") as acquired:
            assert acquired is True
        # both try_lock and unlock ran
        sqls = [c.args[0] for c in conn.execute.call_args_list]
        assert any("pg_try_advisory_lock" in s for s in sqls)
        assert any("pg_advisory_unlock" in s for s in sqls)

    def test_not_acquired_yields_false_no_unlock(self, monkeypatch):
        conn = _install_conn(monkeypatch, False)
        with target_advisory_lock("streaming") as acquired:
            assert acquired is False
        sqls = [c.args[0] for c in conn.execute.call_args_list]
        assert not any("pg_advisory_unlock" in s for s in sqls)
