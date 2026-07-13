"""Unit test for the idempotent SQL migrator."""

from unittest.mock import MagicMock

from acde.dataplane import migrate


def test_apply_runs_each_sql_file_in_order(tmp_path, monkeypatch):
    (tmp_path / "01_a.sql").write_text("CREATE TABLE IF NOT EXISTS a (x int);")
    (tmp_path / "00_b.sql").write_text("CREATE SCHEMA IF NOT EXISTS s;")
    fake = MagicMock()
    monkeypatch.setattr(migrate, "db", fake)
    monkeypatch.setattr(migrate, "INIT_DIR", tmp_path)
    migrate.apply()
    applied = [c.args[0] for c in fake.execute.call_args_list]
    # sorted by filename → 00_b before 01_a
    assert applied[0].startswith("CREATE SCHEMA")
    assert applied[1].startswith("CREATE TABLE")
