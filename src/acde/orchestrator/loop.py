"""Async control loop that schedules the agents safely (§8 Phase 6).

Monitoring runs every tick (detects + stamps ``detected_ts``); the reactive agents run only when
open faults exist. Within one tick, all enabled reactive agents propose first (observe + reason,
no side effects), then proposals contending for the *same* target are resolved by bid before
anyone acts (DEVIATIONS D-038, corrected) -- this decides the winner deliberately, not by an
accident of act order and a lock that never actually overlaps within a single process's tick. Each
winning action is still guarded by a per-target advisory lock, which remains the real defense
against a *different process* acting on the same target concurrently (D-037). Agent cycles run in
worker threads (sync db/gate/executor) under the async scheduler; state lives entirely in Postgres
so kill+restart resumes cleanly (D-041).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from dataclasses import dataclass

from acde import db
from acde.agents.base import BaseAgent
from acde.agents.run import AGENTS
from acde.config import get_settings
from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.llm.client import LLMClient, LLMResult
from acde.logging import get_logger
from acde.orchestrator import control
from acde.orchestrator.configs import enabled_agents
from acde.orchestrator.locks import target_advisory_lock

log = get_logger("orchestrator.loop")

# Reactive agents propose in this order (deterministic logging only -- the bid decides winners,
# not this order). Monitoring is handled separately (it runs first every tick, never contends).
REACTIVE_ORDER = ["schema", "recovery", "optimization"]

# Static bid priority when two agents propose on the same target in one tick (D-038 correction):
# recovery is fixing a live failure -- the most time-critical action class in this system; schema
# is a data-integrity concern, real but rarely as urgent as an in-progress recovery; optimization
# is cost/performance, the least urgent by construction. `ProposedAction.confidence` breaks ties
# within the same priority tier (unreachable today -- each reactive slot proposes at most once per
# tick -- but the interface is correct if that ever changes).
AGENT_PRIORITY: dict[str, int] = {"recovery": 3, "schema": 2, "optimization": 1}


@dataclass
class Proposal:
    """One reactive agent's observe+reason output, before any lock or side effect."""

    agent: str
    action: ProposedAction
    result: LLMResult
    snapshot: TelemetrySnapshot


class ControlLoop:
    """Runs the enabled agents on a schedule with advisory-lock safety."""

    def __init__(
        self, experiment_run: str, config: str = "full", llm: LLMClient | None = None
    ) -> None:
        self.experiment_run = experiment_run
        self.config = config
        self.enabled = enabled_agents(config)
        self.llm = llm or LLMClient()  # shared across agents → shared budget + cache
        self.agents: dict[str, BaseAgent] = {
            name: AGENTS[name](experiment_run=experiment_run, llm=self.llm) for name in self.enabled
        }
        self.interval_s = get_settings().monitoring_interval_s
        self._stop = asyncio.Event()

    # --- one agent, guarded by a per-target advisory lock ---------------------------------

    def _act_on(
        self, name: str, action: ProposedAction, result: LLMResult, snapshot: TelemetrySnapshot
    ) -> str:
        """(lock target) → act, given an already-decided action. Short outcome string (sync)."""
        with target_advisory_lock(action.target) as acquired:
            if not acquired:
                log.info(
                    "target_locked",
                    extra={
                        "agent": name,
                        "target": action.target,
                        "experiment_run": self.experiment_run,
                    },
                )
                return f"skipped: {action.target} locked"
            if control.blast_radius_exceeded(self.experiment_run, action.target):
                return f"skipped: blast-radius cap reached for {action.target}"
            cycle = self.agents[name].act(action, result, snapshot)
            return cycle.outcome

    def _run_agent(self, name: str) -> str:
        """Observe → reason → (lock target) → act. Returns a short outcome string (sync)."""
        agent = self.agents[name]
        snapshot = agent.observe()
        action, result = agent.reason(snapshot)
        if action.action_type == "no_action":
            return "no_action"
        return self._act_on(name, action, result, snapshot)

    def _propose(self, name: str) -> Proposal | None:
        """Observe → reason for one reactive agent. None if it proposed no_action."""
        agent = self.agents[name]
        snapshot = agent.observe()
        action, result = agent.reason(snapshot)
        if action.action_type == "no_action":
            return None
        return Proposal(name, action, result, snapshot)

    def _resolve_conflicts(
        self, proposals: list[Proposal]
    ) -> tuple[list[Proposal], dict[str, str]]:
        """Group by target; the highest (agent priority, confidence) bid wins each contested
        target. Every losing proposal gets a distinguishable outcome string -- never a silent
        skip, and never confused with a lock-skip or a blast-radius skip (D-038 correction)."""
        by_target: dict[str, list[Proposal]] = {}
        for p in proposals:
            by_target.setdefault(p.action.target, []).append(p)

        winners: list[Proposal] = []
        losers: dict[str, str] = {}
        for target, contenders in by_target.items():
            if len(contenders) == 1:
                winners.append(contenders[0])
                continue
            ranked = sorted(
                contenders,
                key=lambda p: (AGENT_PRIORITY[p.agent], p.action.confidence),
                reverse=True,
            )
            winner = ranked[0]
            winners.append(winner)
            for loser in ranked[1:]:
                losers[loser.agent] = f"outbid by {winner.agent} on {target}"
                log.info(
                    "negotiation_outbid",
                    extra={
                        "agent": loser.agent,
                        "winner": winner.agent,
                        "target": target,
                        "experiment_run": self.experiment_run,
                    },
                )
        return winners, losers

    def _open_faults(self) -> int:
        row = db.fetch_one(
            "SELECT count(*) AS n FROM telemetry.failure_events "
            "WHERE experiment_run = %s AND resolved_ts IS NULL",
            (self.experiment_run,),
        )
        return int(row["n"]) if row else 0

    async def _tick(self) -> None:
        if control.is_paused():  # global kill switch — take no actions until resumed
            log.info("loop_paused", extra={"experiment_run": self.experiment_run})
            return
        if "monitoring" in self.enabled:
            await asyncio.to_thread(self._run_agent, "monitoring")
        # Reactive agents only when there is something to react to.
        if self._open_faults() > 0:
            proposals: list[Proposal] = []
            for name in REACTIVE_ORDER:
                if name in self.enabled:
                    proposal = await asyncio.to_thread(self._propose, name)
                    if proposal is not None:
                        proposals.append(proposal)
            winners, _losers = self._resolve_conflicts(proposals)
            for winner in winners:
                await asyncio.to_thread(
                    self._act_on, winner.agent, winner.action, winner.result, winner.snapshot
                )

    # --- lifecycle -------------------------------------------------------------------------

    async def run(self, duration_s: float) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):  # not available on some platforms
                loop.add_signal_handler(sig, self._stop.set)
        deadline = loop.time() + duration_s
        log.info(
            "control_loop_started",
            extra={
                "config": self.config,
                "enabled": sorted(self.enabled),
                "experiment_run": self.experiment_run,
                "duration_s": duration_s,
            },
        )
        while not self._stop.is_set() and loop.time() < deadline:
            try:
                await self._tick()
            except Exception:  # a bad tick must not kill the loop
                log.warning(
                    "control_loop_tick_failed", extra={"experiment_run": self.experiment_run}
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
        log.info("control_loop_stopped", extra={"experiment_run": self.experiment_run})

    def stop(self) -> None:
        self._stop.set()


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="ACDE control-loop orchestrator")
    parser.add_argument("--config", default="full")
    parser.add_argument("--experiment-run", default=None)
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args()
    settings = get_settings()
    run = args.experiment_run or settings.experiment_run
    duration = args.duration if args.duration is not None else settings.soak_duration_s
    asyncio.run(ControlLoop(experiment_run=run, config=args.config).run(duration))


if __name__ == "__main__":  # pragma: no cover
    main()
