"""Monitoring agent: triage anomalies (MODEL_FAST) and stamp failure_events.detected_ts.

D-091: ``observe()`` now also runs ``detection.detect_anomalies()`` — a deterministic, no-LLM
pre-filter (§5.6) that existed with full test coverage but had zero callers anywhere in the
codebase. Previously, ``telemetry.failure_events`` was written *only* by the chaos injector
(research/experiment runs); a genuinely detected production anomaly reached the audit trail
(``agent_actions``) but never became a ``failure_events`` row at all, so MTTR, incident counts,
and decision-quality scoring were structurally incapable of reflecting real production incidents.
Now a newly-detected anomaly gets a real row, the same tick it's found — closing that gap for real
deployments, not just chaos/research runs.
"""

from __future__ import annotations

from acde import db
from acde.agents import detection
from acde.agents.base import BaseAgent
from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.tenancy import current_scope

# detect_anomalies() echoes already-open faults back as "open_fault:<kind>" entries (from
# snapshot.open_anomalies itself) — those are not new detections, never create a row for them.
_ECHOED_PREFIX = "open_fault:"


class MonitoringAgent(BaseAgent):
    agent = "monitoring"

    def observe(self) -> TelemetrySnapshot:
        snapshot = super().observe()
        already_open = {(f["fault_type"], f.get("scenario")) for f in snapshot.open_anomalies}
        seen_this_tick: set[tuple[str, str]] = set()
        tenant_id, environment = current_scope()
        new_entries: list[dict[str, str]] = []
        for anomaly in detection.detect_anomalies(snapshot):
            if anomaly.kind.startswith(_ECHOED_PREFIX):
                continue
            key = (anomaly.kind, anomaly.target)
            if key in already_open or key in seen_this_tick:
                continue
            seen_this_tick.add(key)
            row = db.fetch_one(
                "INSERT INTO telemetry.failure_events "
                "(event_id, experiment_run, scenario, fault_type, injected_ts, "
                " tenant_id, environment) "
                "VALUES (gen_random_uuid(), %s, %s, %s, now(), %s, %s) RETURNING event_id",
                (self.experiment_run, anomaly.target, anomaly.kind, tenant_id, environment),
            )
            if row:
                # Same-tick visibility: the LLM sees this anomaly now, not one tick later once a
                # fresh observe() re-queries failure_events.
                new_entries.append(
                    {
                        "event_id": str(row["event_id"]),
                        "scenario": anomaly.target,
                        "fault_type": anomaly.kind,
                    }
                )
        if new_entries:
            snapshot.open_anomalies = [*snapshot.open_anomalies, *new_entries]
        return snapshot

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
