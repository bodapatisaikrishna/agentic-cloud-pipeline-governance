"""BaseAgent: the observe → reason → propose → act loop shared by all four agents.

Each cycle observes telemetry into a ``TelemetrySnapshot``, asks the LLM (or mock) to propose a
``ProposedAction``, validates it (invalid → ``no_action`` + ``agent_output_invalid``), runs it
through the Phase 3 gate → executor, and writes a ``telemetry.agent_actions`` row with the policy
decision, executor outcome, and token counts (DEVIATIONS D-033).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from importlib.resources import files
from uuid import uuid4

from pydantic import ValidationError

from acde import db
from acde.config import get_settings
from acde.contracts import AgentName, ProposedAction, SchemaCompat, TelemetrySnapshot
from acde.llm.client import LLMClient, LLMResult
from acde.logging import get_logger
from acde.policy import executor, gate

log = get_logger("agents.base")


def load_prompt(agent: AgentName) -> str:
    """Load an agent's system-prompt template from the packaged prompts."""
    return (files("acde.llm.prompts") / f"{agent}.md").read_text(encoding="utf-8")


@dataclass
class CycleResult:
    """Outcome of one agent cycle."""

    action: ProposedAction
    executed: bool
    outcome: str
    policy_id: str


class BaseAgent:
    """Common observe/reason/act machinery; subclasses set ``agent`` and may add hooks."""

    agent: AgentName

    def __init__(self, experiment_run: str | None = None, llm: LLMClient | None = None) -> None:
        self.experiment_run = experiment_run or get_settings().experiment_run
        self.llm = llm or LLMClient()
        self.system_prompt = load_prompt(self.agent)

    # --- observe ---------------------------------------------------------------------------

    def observe(self) -> TelemetrySnapshot:
        """Build a snapshot from the telemetry + warehouse tables for this run."""
        now = dt.datetime.now(dt.UTC)
        open_faults = db.fetch_all(
            "SELECT event_id, scenario, fault_type FROM telemetry.failure_events "
            "WHERE experiment_run = %s AND resolved_ts IS NULL",
            (self.experiment_run,),
        )
        metrics_rows = db.fetch_all(
            "SELECT DISTINCT ON (metric) metric, value FROM telemetry.pipeline_metrics "
            "WHERE experiment_run = %s ORDER BY metric, ts DESC",
            (self.experiment_run,),
        )
        resource_rows = db.fetch_all(
            "SELECT component, cpu_pct, mem_mb, workers, ts FROM telemetry.resource_usage "
            "WHERE experiment_run = %s ORDER BY ts DESC LIMIT 50",
            (self.experiment_run,),
        )
        schema_compat: SchemaCompat = (
            "breaking" if any(f["fault_type"] == "schema_drift" for f in open_faults) else "unknown"
        )
        from acde.contracts import ResourceUsage

        return TelemetrySnapshot(
            experiment_run=self.experiment_run,
            window_start=now - dt.timedelta(minutes=5),
            window_end=now,
            resource_usage=[
                ResourceUsage(
                    component=r["component"],
                    cpu_pct=r["cpu_pct"] or 0.0,
                    mem_mb=r["mem_mb"] or 0.0,
                    workers=r["workers"] or 1,
                    ts=r["ts"],
                )
                for r in resource_rows
            ],
            pipeline_metrics={r["metric"]: float(r["value"]) for r in metrics_rows},
            schema_compat=schema_compat,
            open_anomalies=[
                {
                    "event_id": str(f["event_id"]),
                    "scenario": f["scenario"],
                    "fault_type": f["fault_type"],
                }
                for f in open_faults
            ],
        )

    # --- reason ----------------------------------------------------------------------------

    def reason(self, snapshot: TelemetrySnapshot) -> tuple[ProposedAction, LLMResult]:
        """Get a proposal from the LLM and validate it; invalid → no_action."""
        result = self.llm.propose(self.agent, snapshot, self.system_prompt)
        payload = {**result.action_json, "agent": self.agent, "action_id": str(uuid4())}
        try:
            action = ProposedAction.model_validate(payload)
        except ValidationError as exc:
            log.warning(
                "agent_output_invalid",
                extra={
                    "agent": self.agent,
                    "error": str(exc),
                    "experiment_run": self.experiment_run,
                },
            )
            action = ProposedAction(
                agent=self.agent,
                action_type="no_action",
                target="none",
                justification="invalid LLM output; degraded to no_action",
                confidence=0.0,
            )
        return action, result

    # --- act -------------------------------------------------------------------------------

    def _current_workers(self, snapshot: TelemetrySnapshot) -> int:
        for usage in snapshot.resource_usage:
            if usage.component == "streaming":
                return usage.workers
        return get_settings().stream_default_workers

    def act(
        self, action: ProposedAction, result: LLMResult, snapshot: TelemetrySnapshot
    ) -> CycleResult:
        """Gate → execute → log agent_actions; run subclass hooks."""
        context = gate.build_context(
            action,
            experiment_run=self.experiment_run,
            current_workers=self._current_workers(snapshot),
            schema_compat=snapshot.schema_compat,
        )
        decision = gate.evaluate(action, context)
        outcome = executor.execute(action, decision, self.experiment_run)
        policy_state = (
            "escalated"
            if decision.escalate and not decision.allowed
            else "allowed"
            if decision.allowed
            else "denied"
        )
        db.execute(
            "INSERT INTO telemetry.agent_actions "
            "(action_id, experiment_run, agent, action_type, target, params, justification, "
            " confidence, policy_decision, policy_reason, executed, outcome, llm_model, "
            " llm_tokens_in, llm_tokens_out) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                str(action.action_id),
                self.experiment_run,
                self.agent,
                action.action_type,
                action.target,
                json.dumps(action.params),
                action.justification,
                action.confidence,
                policy_state,
                decision.reason,
                outcome.executed,
                outcome.outcome,
                result.model,
                result.tokens_in,
                result.tokens_out,
            ),
        )
        self.on_after_act(action, outcome.executed, snapshot)
        log.info(
            "agent_action_logged",
            extra={
                "agent": self.agent,
                "action_type": action.action_type,
                "policy": policy_state,
                "executed": outcome.executed,
                "experiment_run": self.experiment_run,
            },
        )
        return CycleResult(action, outcome.executed, outcome.outcome, decision.policy_id)

    def on_after_act(
        self, action: ProposedAction, executed: bool, snapshot: TelemetrySnapshot
    ) -> None:
        """Hook for subclasses (e.g. stamp detected_ts / resolved_ts). Default: nothing."""

    # --- cycle -----------------------------------------------------------------------------

    def run_once(self) -> CycleResult:
        snapshot = self.observe()
        action, result = self.reason(snapshot)
        return self.act(action, result, snapshot)
