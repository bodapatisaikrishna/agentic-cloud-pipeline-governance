"""Optimization agent: propose resource/scheduling adjustments (MODEL_REASONING).

A successful scaling/adjustment resolves the load fault it addresses, so it stamps
``failure_events.resolved_ts`` for the ingress_burst / resource_contention scenarios (DEVIATIONS
D-045) — mirroring recovery — to make MTTR well-defined under this agent.
"""

from __future__ import annotations

from acde import db
from acde.agents.base import BaseAgent
from acde.contracts import ProposedAction, TelemetrySnapshot

_RESOLVING = {"scale_workers", "adjust_pool_slots", "reprioritize_pipeline"}
_LOAD_FAULTS = ("ingress_burst", "resource_contention")


class OptimizationAgent(BaseAgent):
    agent = "optimization"

    def on_after_act(
        self, action: ProposedAction, executed: bool, snapshot: TelemetrySnapshot
    ) -> None:
        if executed and action.action_type in _RESOLVING:
            db.execute(
                "UPDATE telemetry.failure_events SET resolved_ts = now(), resolution = %s "
                "WHERE experiment_run = %s AND fault_type = ANY(%s) "
                "AND detected_ts IS NOT NULL AND resolved_ts IS NULL",
                (action.action_type, self.experiment_run, list(_LOAD_FAULTS)),
            )
