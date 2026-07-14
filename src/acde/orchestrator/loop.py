"""Async control loop that schedules the agents safely (§8 Phase 6).

Monitoring runs every tick (detects + stamps ``detected_ts``); the reactive agents run only when
open faults exist, in ``schema → recovery → optimization`` order so recovery outranks optimization
on a shared target (advisory-lock contention, DEVIATIONS D-038). Each agent's action is guarded by
a per-target advisory lock. Agent cycles run in worker threads (sync db/gate/executor) under the
async scheduler; state lives entirely in Postgres so kill+restart resumes cleanly (D-041).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from acde import db
from acde.agents.base import BaseAgent
from acde.agents.run import AGENTS
from acde.config import get_settings
from acde.llm.client import LLMClient
from acde.logging import get_logger
from acde.orchestrator.configs import enabled_agents
from acde.orchestrator.locks import target_advisory_lock

log = get_logger("orchestrator.loop")

# Reactive agents run in this order; monitoring is handled separately (it runs first every tick).
REACTIVE_ORDER = ["schema", "recovery", "optimization"]


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

    def _run_agent(self, name: str) -> str:
        """Observe → reason → (lock target) → act. Returns a short outcome string (sync)."""
        agent = self.agents[name]
        snapshot = agent.observe()
        action, result = agent.reason(snapshot)
        if action.action_type == "no_action":
            return "no_action"
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
            cycle = agent.act(action, result, snapshot)
            return cycle.outcome

    def _open_faults(self) -> int:
        row = db.fetch_one(
            "SELECT count(*) AS n FROM telemetry.failure_events "
            "WHERE experiment_run = %s AND resolved_ts IS NULL",
            (self.experiment_run,),
        )
        return int(row["n"]) if row else 0

    async def _tick(self) -> None:
        if "monitoring" in self.enabled:
            await asyncio.to_thread(self._run_agent, "monitoring")
        # Reactive agents only when there is something to react to.
        if self._open_faults() > 0:
            for name in REACTIVE_ORDER:
                if name in self.enabled:
                    await asyncio.to_thread(self._run_agent, name)

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
