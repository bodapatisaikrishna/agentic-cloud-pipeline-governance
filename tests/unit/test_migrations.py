"""Unit tests for the versioned migration runner (D-083)."""

from unittest.mock import MagicMock

import pytest

from acde.migrations import Migration, MigrationError, discover


def _write(tmp_path, name, sql):
    (tmp_path / name).write_text(sql)


class TestDiscover:
    def test_orders_by_version_not_filename_sort_quirks(self, tmp_path):
        _write(tmp_path, "002_second.sql", "SELECT 2;")
        _write(tmp_path, "001_first.sql", "SELECT 1;")
        _write(tmp_path, "010_tenth.sql", "SELECT 10;")
        found = discover(tmp_path)
        assert [m.label for m in found] == ["001_first", "002_second", "010_tenth"]

    def test_rejects_bad_filename(self, tmp_path):
        _write(tmp_path, "not_versioned.sql", "SELECT 1;")
        with pytest.raises(MigrationError, match="NNN_lower_snake"):
            discover(tmp_path)

    def test_rejects_duplicate_version(self, tmp_path):
        _write(tmp_path, "001_a.sql", "SELECT 1;")
        _write(tmp_path, "001_b.sql", "SELECT 2;")
        with pytest.raises(MigrationError, match="duplicate migration version"):
            discover(tmp_path)

    def test_no_transaction_marker_detected(self, tmp_path):
        _write(tmp_path, "001_a.sql", "SELECT 1;")
        _write(tmp_path, "002_b.sql", "-- acde:no-transaction\nCREATE INDEX CONCURRENTLY x;")
        found = {m.version: m for m in discover(tmp_path)}
        assert found["001"].transactional is True
        assert found["002"].transactional is False

    def test_checksum_changes_with_content(self, tmp_path):
        _write(tmp_path, "001_a.sql", "SELECT 1;")
        one = discover(tmp_path)[0].checksum
        _write(tmp_path, "001_a.sql", "SELECT 2;")
        two = discover(tmp_path)[0].checksum
        assert one != two


class TestApply:
    """These exercise the module's logic against a mocked pool, not a real database — the real-DB
    path (advisory lock actually serialising, transaction actually committing) is proven by the
    integration test."""

    def _fake_pool(self, monkeypatch, applied_rows):
        import acde.migrations as mig_mod

        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = applied_rows
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        pool = MagicMock()
        pool.connection.return_value = conn
        monkeypatch.setattr(mig_mod.db, "get_pool", lambda: pool)
        monkeypatch.setattr(mig_mod.db, "execute", MagicMock())
        return conn

    def test_apply_skips_already_applied_by_version(self, tmp_path, monkeypatch):
        _write(tmp_path, "001_a.sql", "CREATE TABLE a (x int);")
        conn = self._fake_pool(monkeypatch, applied_rows=[{"version": "001", "checksum": "x"}])
        # Force the checksum to match what's "recorded" so no drift is detected.
        import acde.migrations as mig_mod

        monkeypatch.setattr(mig_mod, "_checksum", lambda sql: "x")
        done = mig_mod.apply(tmp_path)
        assert done == []
        # only the tracking-table DDL + lock/unlock ran, never the migration SQL itself
        executed_sql = [c.args[0] for c in conn.execute.call_args_list]
        assert not any("CREATE TABLE a" in s for s in executed_sql)

    def test_apply_runs_pending_and_records_it(self, tmp_path, monkeypatch):
        _write(tmp_path, "001_a.sql", "CREATE TABLE a (x int);")
        conn = self._fake_pool(monkeypatch, applied_rows=[])
        import acde.migrations as mig_mod

        done = mig_mod.apply(tmp_path)
        assert done == ["001_a"]
        executed_sql = [c.args[0] for c in conn.execute.call_args_list]
        assert any("CREATE TABLE a" in s for s in executed_sql)
        assert any("INSERT INTO control.schema_migrations" in s for s in executed_sql)

    def test_drifted_migration_refuses_to_run(self, tmp_path, monkeypatch):
        _write(tmp_path, "001_a.sql", "CREATE TABLE a (x int);")
        self._fake_pool(monkeypatch, applied_rows=[{"version": "001", "checksum": "stale-hash"}])
        import acde.migrations as mig_mod

        with pytest.raises(MigrationError, match="already applied but its content changed"):
            mig_mod.apply(tmp_path)


class TestStatus:
    def test_reports_pending_and_current_version(self, tmp_path, monkeypatch):
        _write(tmp_path, "001_a.sql", "SELECT 1;")
        _write(tmp_path, "002_b.sql", "SELECT 2;")
        import acde.migrations as mig_mod

        migrations = discover(tmp_path)
        applied_checksum = migrations[0].checksum
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            {"version": "001", "checksum": applied_checksum}
        ]
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        pool = MagicMock()
        pool.connection.return_value = conn
        monkeypatch.setattr(mig_mod.db, "get_pool", lambda: pool)

        result = mig_mod.status(tmp_path)
        assert result["applied"] == ["001"]
        assert result["pending"] == ["002_b"]
        assert result["current_version"] == "001"


class TestBaselineOnDisk:
    """The actual shipped baseline must be self-consistent, independent of any mocking above."""

    def test_baseline_is_discoverable_and_idempotent_looking(self):
        migrations = discover()
        assert migrations[0].version == "001"
        baseline = migrations[0]
        # every CREATE in the real baseline must be guarded (D-083's core promise: safe on a
        # database that already has these tables from the old infra/postgres/init/ path).
        creates = [line for line in baseline.sql.splitlines() if line.strip().startswith("CREATE")]
        assert creates, "expected the baseline to actually create something"
        assert all("IF NOT EXISTS" in line for line in creates)


def test_migration_dataclass_label():
    m = Migration(version="007", name="add_thing", sql="", checksum="", transactional=True)
    assert m.label == "007_add_thing"
