"""Monitoring agent: triage anomalies (MODEL_FAST) and stamp failure_events.detected_ts."""

from __future__ import annotations

from acde import db
from acde.agents.base import BaseAgent
from acde.contracts import ProposedAction, TelemetrySnapshot


class MonitoringAgent(BaseAgent):
    agent = "monitoring"

    def on_after_act(
        self, action: ProposedAction, executed: bool, snapshot: TelemetrySnapshot
    ) -> None:
        """On raising an anomaly, mark open faults as detected (sets MTTR's start point)."""
        if action.action_type == "raise_anomaly":
            db.execute(
                "UPDATE telemetry.failure_events SET detected_ts = now() "
                "WHERE experiment_run = %s AND detected_ts IS NULL",
                (self.experiment_run,),
            )
