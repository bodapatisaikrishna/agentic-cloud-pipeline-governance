"""Run one observe→propose→act cycle for one or all agents (CLI).

The full async scheduler (advisory locks, conflict resolution) is Phase 6; this runs a single
cycle per agent, which is enough to drive the Phase 5 end-to-end verification.
"""

from __future__ import annotations

import argparse

from acde.agents.base import BaseAgent, CycleResult
from acde.agents.monitoring import MonitoringAgent
from acde.agents.optimization import OptimizationAgent
from acde.agents.recovery import RecoveryAgent
from acde.agents.schema import SchemaAgent
from acde.config import get_settings
from acde.llm.client import LLMClient
from acde.logging import get_logger

log = get_logger("agents.run")

AGENTS: dict[str, type[BaseAgent]] = {
    "monitoring": MonitoringAgent,
    "recovery": RecoveryAgent,
    "optimization": OptimizationAgent,
    "schema": SchemaAgent,
}

# Monitoring runs first (it stamps detected_ts), recovery last (it resolves).
DEFAULT_ORDER = ["monitoring", "schema", "optimization", "recovery"]


def run_cycle(
    experiment_run: str, agents: list[str] | None = None, llm: LLMClient | None = None
) -> dict[str, CycleResult]:
    """Run one cycle for each named agent (shared LLM client → shared budget/cache)."""
    llm = llm or LLMClient()
    names = agents or DEFAULT_ORDER
    results: dict[str, CycleResult] = {}
    for name in names:
        results[name] = AGENTS[name](experiment_run=experiment_run, llm=llm).run_once()
    return results


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE agent cycle")
    parser.add_argument("--agent", default=None, help="one agent, or all if omitted")
    parser.add_argument("--experiment-run", default=None)
    args = parser.parse_args()
    run = args.experiment_run or get_settings().experiment_run
    agents = [args.agent] if args.agent else None
    results = run_cycle(run, agents=agents)
    for name, res in results.items():
        log.info(
            "agent_cycle_result",
            extra={
                "agent": name,
                "action_type": res.action.action_type,
                "executed": res.executed,
                "outcome": res.outcome,
                "experiment_run": run,
            },
        )


if __name__ == "__main__":  # pragma: no cover
    main()
