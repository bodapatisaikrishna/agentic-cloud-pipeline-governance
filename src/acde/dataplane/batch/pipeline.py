"""Pure batch-pipeline stages: validate → transform → materialize.

No Airflow import — the DAGs (``batch/dags/*.py``) are thin wrappers that call these so the
logic is unit-testable without a scheduler. ``materialize`` writes a versioned partition via
:class:`acde.dataplane.partitions.PartitionVersionManager`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from acde.dataplane.partitions import PartitionVersionManager
from acde.logging import get_logger

log = get_logger("dataplane.batch")


class SchemaValidationError(ValueError):
    """Raised when a source frame violates its expected schema (breaking drift)."""


def validate(df: pd.DataFrame, required_columns: list[str], non_null: list[str]) -> None:
    """Assert required columns exist and key columns are non-null. Raises on violation."""
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise SchemaValidationError(f"missing columns: {missing}")
    for col in non_null:
        if df[col].isna().any():
            raise SchemaValidationError(f"nulls in non-null column: {col}")
    log.info("batch_validated", extra={"rows": len(df), "columns": list(df.columns)})


def transform_daily_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate store_sales into daily revenue + quantity (deterministic ordering)."""
    grouped = (
        df.groupby("ss_sold_date", as_index=False)
        .agg(revenue=("ss_net_paid", "sum"), quantity=("ss_quantity", "sum"))
        .sort_values("ss_sold_date")
        .reset_index(drop=True)
    )
    grouped["revenue"] = grouped["revenue"].round(2)
    return grouped.rename(columns={"ss_sold_date": "d"})


def transform_daily_complaints(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate open-gov 311 into daily complaint counts."""
    grouped = (
        df.groupby("created_date", as_index=False)
        .agg(complaints=("unique_key", "count"))
        .sort_values("created_date")
        .reset_index(drop=True)
    )
    return grouped.rename(columns={"created_date": "d"})


def materialize(
    dataset: str,
    partition_key: str,
    df: pd.DataFrame,
    columns_ddl: str,
    experiment_run: str | None = None,
) -> int:
    """Write ``df`` as a new active version of (dataset, partition_key). Returns the version."""
    manager = PartitionVersionManager(experiment_run=experiment_run)
    insert_columns = ", ".join(df.columns)
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
    version = manager.create_version(
        dataset=dataset,
        partition_key=partition_key,
        columns_ddl=columns_ddl,
        rows=rows,
        insert_columns=insert_columns,
        activate=True,
    )
    log.info(
        "batch_materialized",
        extra={
            "dataset": dataset,
            "partition_key": partition_key,
            "version": version,
            "rows": len(df),
            "experiment_run": experiment_run,
        },
    )
    return version


# --- Composed pipelines used by the DAGs ---------------------------------------------------


def run_tpcds(
    data_dir: str, partition_key: str = "2026-01", experiment_run: str | None = None
) -> int:
    """Full TPC-DS batch pipeline from CSV to a versioned partition."""
    df = pd.read_csv(Path(data_dir) / "tpcds" / "store_sales.csv")
    validate(
        df,
        required_columns=[
            "ss_sold_date",
            "ss_item_sk",
            "ss_quantity",
            "ss_net_paid",
        ],
        non_null=["ss_sold_date", "ss_net_paid"],
    )
    daily = transform_daily_revenue(df)
    return materialize(
        "tpcds_daily_revenue",
        partition_key,
        daily,
        columns_ddl="d date, revenue double precision, quantity bigint",
        experiment_run=experiment_run,
    )


def run_opengov(
    data_dir: str, partition_key: str = "2026-01", experiment_run: str | None = None
) -> int:
    """Full open-gov batch pipeline from CSV to a versioned partition."""
    df = pd.read_csv(Path(data_dir) / "opengov" / "opengov.csv")
    validate(
        df,
        required_columns=["unique_key", "created_date", "complaint_type"],
        non_null=["unique_key", "created_date"],
    )
    daily = transform_daily_complaints(df)
    return materialize(
        "opengov_daily_complaints",
        partition_key,
        daily,
        columns_ddl="d date, complaints bigint",
        experiment_run=experiment_run,
    )
