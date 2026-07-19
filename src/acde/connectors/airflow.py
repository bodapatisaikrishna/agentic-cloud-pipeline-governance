"""Airflow connector: attach ACDE to a company's Apache Airflow (P2).

Generalizes the Airflow REST calls previously inline in the executor/collector into a configurable
connector — arbitrary base URL, basic **or** bearer-token auth, and a TLS-verify toggle for their
endpoint. This is the first-class "point ACDE at your Airflow" integration.
"""

from __future__ import annotations

import time

import httpx

from acde.config import get_settings
from acde.connectors.base import ConnectorHealth, TaskRun
from acde.logging import get_logger

log = get_logger("connectors.airflow")


class AirflowConnector:
    """A `Connector` backed by an Airflow 2.x REST API."""

    name = "airflow"
    can_act = True

    def __init__(self, is_production: bool = True) -> None:
        self.is_production = is_production

    def _client(self) -> httpx.Client:  # pragma: no cover - network
        s = get_settings()
        headers = {}
        auth = None
        if s.airflow_auth_token:
            headers["Authorization"] = f"Bearer {s.airflow_auth_token}"
        else:
            auth = (s.airflow_user, s.airflow_password)
        return httpx.Client(
            base_url=s.airflow_url, auth=auth, headers=headers,
            timeout=30, verify=s.airflow_verify_tls,
        )

    def health(self) -> ConnectorHealth:  # pragma: no cover - network
        try:
            with self._client() as c:
                r = c.get("/health")
                ok = r.status_code == 200
                return ConnectorHealth("airflow", ok, f"HTTP {r.status_code}", can_act=True)
        except Exception as exc:
            return ConnectorHealth("airflow", False, str(exc)[:120], can_act=True)

    def get_task_runs(self, pipeline_id: str) -> list[TaskRun]:  # pragma: no cover - network
        with self._client() as c:
            r = c.get(f"/dags/{pipeline_id}/dagRuns", params={"order_by": "-execution_date"})
            r.raise_for_status()
            runs = r.json().get("dag_runs", [])
        return [
            TaskRun(pipeline_id, run.get("dag_run_id", ""), run.get("state", "unknown"))
            for run in runs
        ]

    def trigger_pipeline(self, pipeline_id: str) -> str:  # pragma: no cover - network
        run_id = f"acde__{int(time.time() * 1000)}"
        with self._client() as c:
            c.post(f"/dags/{pipeline_id}/dagRuns", json={"dag_run_id": run_id}).raise_for_status()
        return run_id

    def clear_tasks(self, pipeline_id: str, task_ids: list[str]) -> None:  # pragma: no cover
        body: dict = {"dry_run": False, "reset_dag_runs": True, "only_failed": True}
        if task_ids:
            body["task_ids"] = task_ids
        with self._client() as c:
            c.post(f"/dags/{pipeline_id}/clearTaskInstances", json=body).raise_for_status()

    def set_pool_slots(self, pool: str, slots: int) -> None:  # pragma: no cover - network
        with self._client() as c:
            c.patch(f"/pools/{pool}", json={"name": pool, "slots": slots}).raise_for_status()
