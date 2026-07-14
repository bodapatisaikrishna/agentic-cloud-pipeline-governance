"""Schema agent: contain schema drift (quarantine/block) or allow compatible changes.

A successful containment/mapping action resolves the schema fault, so it stamps
``failure_events.resolved_ts`` (DEVIATIONS D-045) — mirroring recovery — to make MTTR well-defined
for the schema_drift scenario under this agent.
"""

from __future__ import annotations

from acde import db
from acde.agents.base import BaseAgent
from acde.contracts import ProposedAction, TelemetrySnapshot

_RESOLVING = {"quarantine_partition", "block_ingestion", "apply_mapping"}


class SchemaAgent(BaseAgent):
    agent = "schema"

    def on_after_act(
        self, action: ProposedAction, executed: bool, snapshot: TelemetrySnapshot
    ) -> None:
        if executed and action.action_type in _RESOLVING:
            db.execute(
                "UPDATE telemetry.failure_events SET resolved_ts = now(), resolution = %s "
                "WHERE experiment_run = %s AND fault_type = 'schema_drift' "
                "AND detected_ts IS NOT NULL AND resolved_ts IS NULL",
                (action.action_type, self.experiment_run),
            )
