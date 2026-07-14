"""Soak driver: inject two overlapping chaos scenarios, then run the control loop (§8 Phase 6).

Used by ``make soak`` and (short version) the integration test. The 20-min soak with two
overlapping faults is the Phase 6 manual-verification target.
"""

from __future__ import annotations

import argparse
import asyncio

from acde.chaos.injector import FaultInjector
from acde.chaos.scenarios import run_seed
from acde.config import get_settings
from acde.logging import get_logger
from acde.orchestrator.loop import ControlLoop

log = get_logger("orchestrator.soak")

# Two overlapping scenarios: a batch schema drift and a streaming upstream delay.
DEFAULT_SCENARIOS = ("schema_drift", "upstream_delay")


async def run_soak(
    experiment_run: str,
    config: str = "full",
    duration_s: float | None = None,
    scenarios: tuple[str, ...] = DEFAULT_SCENARIOS,
    replicate: int = 0,
) -> None:
    """Inject the scenarios then run the loop for ``duration_s``."""
    settings = get_settings()
    duration_s = settings.soak_duration_s if duration_s is None else duration_s
    injector = FaultInjector(experiment_run=experiment_run)
    for scenario in scenarios:
        injector.inject(scenario, run_seed(config, scenario, replicate))
        log.info(
            "soak_fault_injected", extra={"scenario": scenario, "experiment_run": experiment_run}
        )
    await ControlLoop(experiment_run=experiment_run, config=config).run(duration_s)


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE soak (chaos + control loop)")
    parser.add_argument("--config", default="full")
    parser.add_argument("--experiment-run", default=None)
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args()
    run = args.experiment_run or get_settings().experiment_run
    asyncio.run(run_soak(experiment_run=run, config=args.config, duration_s=args.duration))


if __name__ == "__main__":  # pragma: no cover
    main()
