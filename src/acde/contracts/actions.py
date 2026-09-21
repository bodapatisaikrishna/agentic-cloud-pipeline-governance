"""Agent I/O contract (spec §5.2) — the single source of truth for agent output.

Agents may ONLY emit a ``ProposedAction``; they never execute anything and
never generate code. Any LLM output that fails validation here is rejected,
logged, and counted as ``agent_output_invalid``.
"""

import math
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


# The one numeric parameter each scaling action prices and executes on (D-104).
SCALE_TARGET_PARAM = {"scale_workers": "n_workers", "adjust_pool_slots": "slots"}


def _positive_int(value: Any) -> int | None:
    """``value`` as an int >= 1, or None. Accepts ints and integral finite floats (6.0)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not (math.isfinite(value) and value.is_integer()):
        return None
    n = int(value)
    return n if n >= 1 else None


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

    @model_validator(mode="after")
    def _scale_target_is_a_positive_integer(self) -> "ProposedAction":
        """Scaling targets must be integers >= 1 (D-104).

        The cost policy only prices a target against the budget, so ``n_workers=0`` (halting
        ingestion) or a negative "scale-down" was budget-legal, and an unparseable value crashed the
        gate *before* the write-ahead audit row. Rejecting here keeps the invalid output on the
        normal ``agent_output_invalid`` path: rejected, logged, counted, and never priced.
        """
        key = SCALE_TARGET_PARAM.get(self.action_type)
        if key is None or key not in self.params:
            return self
        n = _positive_int(self.params[key])
        if n is None:
            raise ValueError(
                f"{self.action_type} param {key!r}={self.params[key]!r} must be an integer >= 1"
            )
        self.params[key] = n
        return self


class PolicyDecision(BaseModel):
    """Verdict from the OPA policy gate for one ProposedAction."""

    allowed: bool
    escalate: bool
    reason: str
    policy_id: str
