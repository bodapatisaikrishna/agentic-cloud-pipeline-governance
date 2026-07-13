"""Unit tests for pure batch-pipeline stages."""

import pandas as pd
import pytest

from acde.dataplane.batch import pipeline
from acde.dataplane.batch.pipeline import SchemaValidationError


def _sales() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ss_sold_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "ss_item_sk": [1, 2, 1],
            "ss_quantity": [2, 3, 4],
            "ss_net_paid": [10.0, 20.0, 5.0],
        }
    )


class TestValidate:
    def test_passes_on_good_frame(self):
        pipeline.validate(_sales(), ["ss_sold_date", "ss_net_paid"], ["ss_net_paid"])

    def test_missing_column_raises(self):
        df = _sales().drop(columns=["ss_net_paid"])
        with pytest.raises(SchemaValidationError, match="missing columns"):
            pipeline.validate(df, ["ss_sold_date", "ss_net_paid"], [])

    def test_null_in_non_null_column_raises(self):
        df = _sales()
        df.loc[0, "ss_net_paid"] = None
        with pytest.raises(SchemaValidationError, match="nulls"):
            pipeline.validate(df, ["ss_net_paid"], ["ss_net_paid"])


class TestTransform:
    def test_daily_revenue_aggregates_and_sorts(self):
        out = pipeline.transform_daily_revenue(_sales())
        assert list(out.columns) == ["d", "revenue", "quantity"]
        assert list(out["d"]) == ["2026-01-01", "2026-01-02"]
        assert out.loc[out["d"] == "2026-01-01", "revenue"].iloc[0] == 30.0
        assert out.loc[out["d"] == "2026-01-01", "quantity"].iloc[0] == 5

    def test_daily_complaints_counts(self):
        df = pd.DataFrame(
            {
                "unique_key": [1, 2, 3],
                "created_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
                "complaint_type": ["Noise", "Rodent", "Noise"],
            }
        )
        out = pipeline.transform_daily_complaints(df)
        assert list(out.columns) == ["d", "complaints"]
        assert out.loc[out["d"] == "2026-01-01", "complaints"].iloc[0] == 2


class TestMaterialize:
    def test_materialize_delegates_to_partition_manager(self, monkeypatch):
        captured = {}

        class FakeManager:
            def __init__(self, experiment_run=None):
                captured["run"] = experiment_run

            def create_version(self, **kwargs):
                captured.update(kwargs)
                return 7

        monkeypatch.setattr(pipeline, "PartitionVersionManager", FakeManager)
        version = pipeline.materialize(
            "ds",
            "2026-01",
            pipeline.transform_daily_revenue(_sales()),
            columns_ddl="d date, revenue double precision, quantity bigint",
            experiment_run="run-9",
        )
        assert version == 7
        assert captured["run"] == "run-9"
        assert captured["dataset"] == "ds"
        assert captured["insert_columns"] == "d, revenue, quantity"
        assert len(captured["rows"]) == 2  # two distinct days


class TestComposedPipelines:
    def test_run_tpcds_reads_csv_and_materializes(self, tmp_path, monkeypatch):
        from acde.dataplane.datasets import tpcds_gen

        tpcds_gen.write(out_dir=tmp_path / "tpcds", seed=1)
        captured = {}
        monkeypatch.setattr(
            pipeline,
            "materialize",
            lambda *a, **k: captured.setdefault("called", True) or 1,
        )
        version = pipeline.run_tpcds(str(tmp_path), experiment_run="run-1")
        assert version == 1
        assert captured["called"]

    def test_run_opengov_reads_csv_and_materializes(self, tmp_path, monkeypatch):
        from acde.dataplane.datasets import opengov_fetch

        opengov_fetch.write(out_dir=tmp_path / "opengov", seed=1)
        monkeypatch.setattr(pipeline, "materialize", lambda *a, **k: 1)
        assert pipeline.run_opengov(str(tmp_path)) == 1
