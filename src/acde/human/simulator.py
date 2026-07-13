"""Simulated on-call human: resolves escalations after a seeded lognormal delay (§6).

Latency ~ lognormal(median=360s, sigma=0.5), seeded deterministically per
``(default_seed, intervention id)`` (DEVIATIONS D-024). The simulator assigns a latency to each
pending ``manual_interventions`` row once, then completes it when ``now >= requested_ts + latency``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import time

import numpy as np

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("human.simulator")


def sample_latency(seed: int, key: int, median_s: float, sigma: float) -> float:
    """Deterministic lognormal latency for intervention ``key`` (median_s at sigma)."""
    rng = np.random.default_rng((seed * 1_000_003 + key) % 2**32)
    mu = math.log(median_s)
    return float(rng.lognormal(mean=mu, sigma=sigma))


class HumanSimulator:
    """Assigns latencies to and resolves pending manual interventions."""

    def __init__(self, experiment_run: str | None = None, seed: int | None = None) -> None:
        settings = get_settings()
        self.experiment_run = experiment_run or settings.experiment_run
        self.seed = settings.default_seed if seed is None else seed
        self.median_s = settings.human_latency_median_s
        self.sigma = settings.human_latency_sigma

    def assign_latencies(self) -> int:
        """Assign a latency to each pending row that lacks one. Returns count assigned."""
        rows = db.fetch_all(
            "SELECT id FROM telemetry.manual_interventions "
            "WHERE experiment_run = %s AND simulated_latency_s IS NULL",
            (self.experiment_run,),
        )
        for row in rows:
            latency = sample_latency(self.seed, int(row["id"]), self.median_s, self.sigma)
            db.execute(
                "UPDATE telemetry.manual_interventions SET simulated_latency_s = %s WHERE id = %s",
                (latency, row["id"]),
            )
        return len(rows)

    def resolve_due(self, now: dt.datetime | None = None) -> int:
        """Complete interventions whose requested_ts + latency has passed. Returns count."""
        now = now or dt.datetime.now(dt.UTC)
        rows = db.fetch_all(
            "SELECT id, requested_ts, simulated_latency_s FROM telemetry.manual_interventions "
            "WHERE experiment_run = %s AND completed_ts IS NULL "
            "AND simulated_latency_s IS NOT NULL",
            (self.experiment_run,),
        )
        completed = 0
        for row in rows:
            due = row["requested_ts"] + dt.timedelta(seconds=float(row["simulated_latency_s"]))
            if now >= due:
                db.execute(
                    "UPDATE telemetry.manual_interventions SET completed_ts = %s WHERE id = %s",
                    (due, row["id"]),
                )
                completed += 1
        return completed

    def assign_and_resolve(self, now: dt.datetime | None = None) -> tuple[int, int]:
        """Assign latencies to new rows and resolve any that are due."""
        assigned = self.assign_latencies()
        resolved = self.resolve_due(now)
        log.info(
            "human_simulator_tick",
            extra={
                "experiment_run": self.experiment_run,
                "assigned": assigned,
                "resolved": resolved,
            },
        )
        return assigned, resolved

    def run(self, duration_s: float, interval_s: float = 5.0) -> None:  # pragma: no cover - loop
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            self.assign_and_resolve()
            time.sleep(interval_s)


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE human simulator")
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--experiment-run", default=None)
    args = parser.parse_args()
    HumanSimulator(experiment_run=args.experiment_run).run(args.duration, args.interval)


if __name__ == "__main__":  # pragma: no cover
    main()
