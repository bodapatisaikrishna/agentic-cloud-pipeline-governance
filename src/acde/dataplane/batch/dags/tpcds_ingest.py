"""Airflow DAG: TPC-DS batch ingest (validate → transform → materialize versioned partition).

Thin wrapper over :mod:`acde.dataplane.batch.pipeline`; all logic is tested there without
Airflow. Runs on the LocalExecutor in the ``apache/airflow`` container where ``acde`` is
installed and ``DATA_DIR`` is mounted.
"""

from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task

from acde.config import get_settings
from acde.dataplane.batch import pipeline


@dag(
    dag_id="tpcds_ingest",
    schedule=None,
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    tags=["acde", "batch", "tpcds"],
)
def tpcds_ingest():
    @task()
    def ingest() -> int:
        settings = get_settings()
        return pipeline.run_tpcds(settings.data_dir)

    ingest()


tpcds_ingest()
