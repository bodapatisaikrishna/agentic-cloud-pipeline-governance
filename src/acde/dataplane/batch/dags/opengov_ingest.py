"""Airflow DAG: open-gov (NYC 311-shaped) batch ingest.

Thin wrapper over :mod:`acde.dataplane.batch.pipeline`.
"""

from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task

from acde.config import get_settings
from acde.dataplane.batch import pipeline


@dag(
    dag_id="opengov_ingest",
    schedule=None,
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    tags=["acde", "batch", "opengov"],
)
def opengov_ingest():
    @task()
    def ingest() -> int:
        settings = get_settings()
        return pipeline.run_opengov(settings.data_dir)

    ingest()


opengov_ingest()
