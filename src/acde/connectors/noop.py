"""No-op connector: observe-only deployments (P2).

Selected with ``connector_kind=noop``. It reports healthy and never performs a side effect — used
when a company wants ACDE purely advisory (propose + gate + notify) with no write access to their
orchestrator, or during evaluation. Action methods are no-ops that log, never raise.
"""

from __future__ import annotations

from acde.connectors.base import ConnectorHealth, TaskRun
from acde.logging import get_logger

log = get_logger("connectors.noop")


class NoopConnector:
    """A `Connector` that observes nothing and acts on nothing (advisory-only)."""

    name = "noop"
    can_act = False
    is_production = False

    def health(self) -> ConnectorHealth:
        return ConnectorHealth("noop", True, "observe-only connector", can_act=False)

    def get_task_runs(self, pipeline_id: str) -> list[TaskRun]:
        return []

    def trigger_pipeline(self, pipeline_id: str) -> str:
        log.info("noop_trigger", extra={"pipeline_id": pipeline_id})
        return "noop"

    def clear_tasks(self, pipeline_id: str, task_ids: list[str]) -> None:
        log.info("noop_clear", extra={"pipeline_id": pipeline_id})

    def set_pool_slots(self, pool: str, slots: int) -> None:
        log.info("noop_set_pool", extra={"pool": pool, "slots": slots})
