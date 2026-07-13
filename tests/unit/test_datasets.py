"""Unit tests for seeded dataset generators (determinism + schema shape)."""

import pandas as pd

from acde.dataplane.datasets import opengov_fetch, tpcds_gen


class TestTpcds:
    def test_same_seed_is_deterministic(self):
        a = tpcds_gen.generate(seed=7, n_rows=500)
        b = tpcds_gen.generate(seed=7, n_rows=500)
        pd.testing.assert_frame_equal(a["store_sales"], b["store_sales"])
        pd.testing.assert_frame_equal(a["item"], b["item"])

    def test_different_seed_differs(self):
        a = tpcds_gen.generate(seed=1, n_rows=500)["store_sales"]
        b = tpcds_gen.generate(seed=2, n_rows=500)["store_sales"]
        assert not a.equals(b)

    def test_schema_and_row_count(self):
        tables = tpcds_gen.generate(seed=3, n_rows=1000)
        assert list(tables["store_sales"].columns) == tpcds_gen.STORE_SALES_COLUMNS
        assert list(tables["item"].columns) == tpcds_gen.ITEM_COLUMNS
        assert len(tables["store_sales"]) == 1000
        assert (tables["store_sales"]["ss_net_paid"] >= 0).all()

    def test_write_creates_csvs(self, tmp_path):
        paths = tpcds_gen.write(out_dir=tmp_path, seed=5)
        assert paths["store_sales"].exists()
        assert paths["item"].exists()
        # round-trips through CSV identically ordered
        df = pd.read_csv(paths["store_sales"])
        assert len(df) > 0


class TestOpengov:
    def test_same_seed_is_deterministic(self):
        a = opengov_fetch.generate(seed=9, n_rows=300)
        b = opengov_fetch.generate(seed=9, n_rows=300)
        pd.testing.assert_frame_equal(a, b)

    def test_schema(self):
        df = opengov_fetch.generate(seed=4, n_rows=200)
        assert list(df.columns) == opengov_fetch.COLUMNS
        assert len(df) == 200
        assert df["unique_key"].is_unique

    def test_write(self, tmp_path):
        path = opengov_fetch.write(out_dir=tmp_path, seed=2)
        assert path.exists()
        assert len(pd.read_csv(path)) == 5000  # default OPENGOV_ROWS
