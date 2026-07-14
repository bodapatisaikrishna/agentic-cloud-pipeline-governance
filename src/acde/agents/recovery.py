"""Recovery agent: propose remediation and stamp failure_events.resolved_ts on success."""

from __future__ import annotations

from acde import db
from acde.agents.base import BaseAgent
from acde.contracts import ProposedAction, TelemetrySnapshot

_REMEDIATING = {"retry_with_backoff", "replay", "rollback", "partial_recompute"}


class RecoveryAgent(BaseAgent):
    agent = "recovery"

    def on_after_act(
        self, action: ProposedAction, executed: bool, snapshot: TelemetrySnapshot
    ) -> None:
        """A successful remediating action resolves the detected fault (sets MTTR's end)."""
        if executed and action.action_type in _REMEDIATING:
            db.execute(
                "UPDATE telemetry.failure_events SET resolved_ts = now(), resolution = %s "
                "WHERE experiment_run = %s AND detected_ts IS NOT NULL AND resolved_ts IS NULL",
                (action.action_type, self.experiment_run),
            )
