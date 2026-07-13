"""Unit tests for PartitionVersionManager (acde.db replaced with a mock)."""

from unittest.mock import MagicMock

import pytest

from acde.dataplane import partitions
from acde.dataplane.partitions import PartitionVersionManager, table_name


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(partitions, "db", fake)
    return fake


class TestTableName:
    def test_slug_is_identifier_safe(self):
        assert table_name("tpcds daily", "2026-01", 3) == "tpcds_daily__2026_01__v3"


class TestVersioning:
    def test_next_version_increments_max(self, fake_db):
        fake_db.fetch_one.return_value = {"v": 4}
        assert PartitionVersionManager().next_version("d", "p") == 5

    def test_next_version_starts_at_one(self, fake_db):
        fake_db.fetch_one.return_value = {"v": 0}
        assert PartitionVersionManager().next_version("d", "p") == 1

    def test_create_version_materializes_and_registers(self, fake_db):
        fake_db.fetch_one.return_value = {"v": 0}  # next_version -> 1
        mgr = PartitionVersionManager(experiment_run="run-1")
        version = mgr.create_version(
            "tpcds",
            "2026-01",
            "d date, revenue double precision",
            rows=[("2026-01-01", 10.0), ("2026-01-02", 20.0)],
            insert_columns="d, revenue",
            activate=True,
        )
        assert version == 1
        # created the physical table and bulk-inserted rows
        create_calls = [c.args[0] for c in fake_db.execute.call_args_list]
        assert any("CREATE TABLE warehouse.tpcds__2026_01__v1" in s for s in create_calls)
        fake_db.execute_many.assert_called_once()
        # registered the version row
        assert any("INSERT INTO warehouse.partition_versions" in s for s in create_calls)

    def test_create_version_without_rows_skips_insert(self, fake_db):
        fake_db.fetch_one.return_value = {"v": 0}
        PartitionVersionManager().create_version(
            "d",
            "p",
            "x int",
            rows=[],
            insert_columns="x",
            activate=False,
        )
        fake_db.execute_many.assert_not_called()


class TestRollback:
    def test_rollback_activates_prior_version(self, fake_db):
        fake_db.fetch_one.return_value = {"version": 3}  # current active
        fake_db.fetch_all.return_value = [
            {"version": 1},
            {"version": 2},
            {"version": 3},
        ]
        target = PartitionVersionManager().rollback("d", "p")
        assert target == 2

    def test_rollback_without_prior_returns_none(self, fake_db):
        fake_db.fetch_one.return_value = {"version": 1}
        fake_db.fetch_all.return_value = [{"version": 1}]
        assert PartitionVersionManager().rollback("d", "p") is None


class TestActivate:
    def test_activate_flips_pointer_transactionally(self, fake_db):
        conn = fake_db.get_pool.return_value.connection.return_value.__enter__.return_value
        PartitionVersionManager().activate("d", "p", 2)
        statements = [c.args[0] for c in conn.execute.call_args_list]
        assert len(statements) == 2
        # first clears all active for the partition, second sets the target version active
        assert "active = FALSE" in statements[0]
        assert "active = TRUE" in statements[1] and "version = %s" in statements[1]
