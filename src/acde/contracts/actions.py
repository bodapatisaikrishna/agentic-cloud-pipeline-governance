"""Agent I/O contract (spec §5.2) — the single source of truth for agent output.

Agents may ONLY emit a ``ProposedAction``; they never execute anything and
never generate code. Any LLM output that fails validation here is rejected,
logged, and counted as ``agent_output_invalid``.
"""

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

AgentName = Literal["monitoring", "optimization", "schema", "recovery"]

ACTION_TYPES: dict[AgentName, set[str]] = {
    "monitoring": {"raise_anomaly", "escalate", "no_action"},
    "optimization": {"scale_workers", "adjust_pool_slots", "reprioritize_pipeline", "no_action"},
    "schema": {
        "allow_compatible",
        "apply_mapping",
        "quarantine_partition",
        "block_ingestion",
        "no_action",
    },
    "recovery": {
        "retry_with_backoff",
        "replay",
        "rollback",
        "partial_recompute",
        "escalate_to_human",
        "no_action",
    },
}


class ProposedAction(BaseModel):
    """An operational action proposed by an agent, pending policy evaluation."""

    action_id: UUID = Field(default_factory=uuid4)
    agent: AgentName
    action_type: str
    target: str  # dag_id | pipeline_id | dataset/partition | component
    params: dict[str, Any] = Field(default_factory=dict)
    justification: str = Field(max_length=1200)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _action_type_allowed_for_agent(self) -> "ProposedAction":
        allowed = ACTION_TYPES[self.agent]
        if self.action_type not in allowed:
            raise ValueError(
                f"action_type {self.action_type!r} is not allowed for agent "
                f"{self.agent!r}; allowed: {sorted(allowed)}"
            )
        return self


class PolicyDecision(BaseModel):
    """Verdict from the OPA policy gate for one ProposedAction."""

    allowed: bool
    escalate: bool
    reason: str
    policy_id: str
