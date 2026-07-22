"""Prefect connector: attach ACDE to a company's Prefect Server/Cloud (T2.4, D-073).

Second `Connector` implementation, proving the abstraction (`connectors/base.py`) generalizes
beyond Airflow. Prefect's orchestration API is REST (unlike Dagster, whose primary control surface
is GraphQL), so it maps onto the same protocol shape with one honest gap: Prefect has no per-task
"clear failed tasks" concept the way Airflow does — a flow run either succeeds or doesn't, so
``clear_tasks`` retries the *whole* flow run via a state transition (``task_ids`` is accepted for
protocol compatibility but ignored). This is documented, not silently faked.

``pipeline_id`` throughout maps to a Prefect **deployment id**.
"""

from __future__ import annotations

import httpx

from acde.config import get_settings
from acde.connectors.base import ConnectorHealth, TaskRun
from acde.logging import get_logger

log = get_logger("connectors.prefect")


class PrefectConnector:
    """A `Connector` backed by the Prefect REST API (Server or Cloud)."""

    name = "prefect"
    can_act = True

    def __init__(self, is_production: bool = True) -> None:
        self.is_production = is_production

    def _client(self) -> httpx.Client:  # pragma: no cover - network
        s = get_settings()
        headers = {}
        if s.prefect_api_key:  # Prefect Cloud; self-hosted Server typically needs no auth
            headers["Authorization"] = f"Bearer {s.prefect_api_key}"
        return httpx.Client(base_url=s.prefect_api_url, headers=headers, timeout=30)

    def health(self) -> ConnectorHealth:  # pragma: no cover - network
        try:
            with self._client() as c:
                r = c.get("/health")
                ok = r.status_code == 200
                return ConnectorHealth("prefect", ok, f"HTTP {r.status_code}", can_act=True)
        except Exception as exc:
            return ConnectorHealth("prefect", False, str(exc)[:120], can_act=True)

    def get_task_runs(self, pipeline_id: str) -> list[TaskRun]:  # pragma: no cover - network
        """Recent flow runs for a deployment (Prefect has no separate "task run" list API here)."""
        with self._client() as c:
            r = c.post(
                "/flow_runs/filter",
                json={
                    "flow_runs": {"deployment_id": {"any_": [pipeline_id]}},
                    "sort": "START_TIME_DESC",
                    "limit": 25,
                },
            )
            r.raise_for_status()
            runs = r.json()
        return [
            TaskRun(pipeline_id, run.get("id", ""), (run.get("state") or {}).get("type", "UNKNOWN"))
            for run in runs
        ]

    def trigger_pipeline(self, pipeline_id: str) -> str:  # pragma: no cover - network
        with self._client() as c:
            r = c.post(f"/deployments/{pipeline_id}/create_flow_run", json={})
            r.raise_for_status()
            return str(r.json()["id"])

    def clear_tasks(self, pipeline_id: str, task_ids: list[str]) -> None:  # pragma: no cover
        """Retry the most recent flow run for this deployment (no per-task clear in Prefect)."""
        runs = self.get_task_runs(pipeline_id)
        if not runs:
            return
        with self._client() as c:
            c.post(
                f"/flow_runs/{runs[0].task_id}/set_state",
                json={"state": {"type": "SCHEDULED", "name": "AwaitingRetry"}},
            ).raise_for_status()

    def set_pool_slots(self, pool: str, slots: int) -> None:  # pragma: no cover - network
        """Resize a Prefect work pool's concurrency limit (Airflow "pool slots" equivalent)."""
        with self._client() as c:
            c.patch(f"/work_pools/{pool}", json={"concurrency_limit": slots}).raise_for_status()
