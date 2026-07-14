"""Seeded failure injector (§8 Phase 4).

``plan_timeline(scenario, seed)`` is a pure, deterministic function — the headline guarantee is
that the same seed yields the same fault plan (DEVIATIONS D-030). ``FaultInjector.inject`` writes
a ``telemetry.failure_events`` row and applies the degradation per the plan. Each applier has a
pure builder (unit-tested) and a thin I/O edge (integration-verified).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from acde import db
from acde.chaos import stressor
from acde.chaos.scenarios import Scenario, get_scenario
from acde.config import get_settings
from acde.dataplane.streaming.producer import generate_events, rebase_to_end
from acde.logging import get_logger

log = get_logger("chaos.injector")

DRIFT_COLUMNS = ("ss_net_paid", "ss_quantity", "ss_sales_price")


@dataclasses.dataclass(frozen=True)
class FaultPlan:
    """The deterministic plan for one fault injection."""

    scenario: str
    fault_type: str
    seed: int
    at_offset_s: float
    params: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def plan_timeline(scenario: Scenario, seed: int) -> FaultPlan:
    """Deterministically derive the fault plan for ``scenario`` at ``seed`` (pure)."""
    settings = get_settings()
    rng = np.random.default_rng(seed)
    # Fire somewhere in the first half of the fault window (after warmup).
    at_offset_s = float(scenario.warmup_s + rng.uniform(0, scenario.fault_window_s * 0.5))

    params: dict[str, Any]
    if scenario.name == "schema_drift":
        params = {
            "op": str(rng.choice(["drop", "retype"])),
            "column": str(rng.choice(DRIFT_COLUMNS)),
        }
    elif scenario.name == "upstream_delay":
        params = {
            "delay_ms": int(rng.integers(500, settings.chaos_delay_ms_max)),
            "drop_pct": round(float(rng.uniform(0.1, settings.chaos_drop_pct_max)), 3),
            "events": int(rng.integers(500, 1500)),
        }
    elif scenario.name == "resource_contention":
        params = {
            "cpu_workers": int(rng.integers(1, settings.chaos_cpu_workers_max + 1)),
            "duration_s": float(min(scenario.fault_window_s, settings.chaos_hard_cap_s)),
        }
    elif scenario.name == "ingress_burst":
        params = {
            "burst_factor": round(
                float(rng.uniform(settings.chaos_burst_min, settings.chaos_burst_max)), 2
            ),
            "events": int(rng.integers(2000, 6000)),
        }
    else:  # pragma: no cover - guarded by get_scenario
        params = {}

    return FaultPlan(
        scenario=scenario.name,
        fault_type=scenario.fault_type,
        seed=seed,
        at_offset_s=at_offset_s,
        params=params,
    )


# --- Pure builders --------------------------------------------------------------------------


def corrupt_frame(df: pd.DataFrame, op: str, column: str) -> pd.DataFrame:
    """Return a schema-drifted copy of ``df``: drop or retype ``column`` (breaking change)."""
    out = df.copy()
    if op == "drop":
        return out.drop(columns=[column], errors="ignore")
    out[column] = "CORRUPT"  # retype numeric -> string breaks validate/transform
    return out


def build_delayed_records(
    records: list[dict[str, Any]], delay_ms: int, drop_pct: float, seed: int
) -> list[dict[str, Any]]:
    """Drop ``drop_pct`` of records and shift the rest older by ``delay_ms`` (staler stream)."""
    rng = np.random.default_rng(seed + 101)
    kept = [r for r in records if rng.random() >= drop_pct]
    shift = dt.timedelta(milliseconds=delay_ms)
    return [
        {**r, "event_ts": (dt.datetime.fromisoformat(r["event_ts"]) - shift).isoformat()}
        for r in kept
    ]


# --- Injector -------------------------------------------------------------------------------


class FaultInjector:
    """Writes failure_events and applies seeded degradations."""

    def __init__(self, experiment_run: str | None = None) -> None:
        self.experiment_run = experiment_run or get_settings().experiment_run

    def _record(self, plan: FaultPlan) -> str:
        event_id = str(uuid4())
        db.execute(
            "INSERT INTO telemetry.failure_events "
            "(event_id, experiment_run, scenario, fault_type, injected_ts) "
            "VALUES (%s, %s, %s, %s, now())",
            (event_id, self.experiment_run, plan.scenario, plan.fault_type),
        )
        log.info(
            "fault_injected",
            extra={
                "event_id": event_id,
                "scenario": plan.scenario,
                "fault_type": plan.fault_type,
                "params": plan.params,
                "experiment_run": self.experiment_run,
            },
        )
        return event_id

    def _apply_schema_drift(self, plan: FaultPlan) -> None:
        path = Path(get_settings().data_dir) / "tpcds" / "store_sales.csv"
        df = pd.read_csv(path)
        corrupt_frame(df, plan.params["op"], plan.params["column"]).to_csv(path, index=False)

    def _publish(self, records: list[dict[str, Any]]) -> int:  # pragma: no cover - broker
        from acde.dataplane.streaming.kafka_io import JsonProducer, ensure_topic

        ensure_topic()
        producer = JsonProducer()
        for rec in records:
            producer.send(rec, key=rec["key"])
        producer.flush()
        return len(records)

    def _apply_upstream_delay(self, plan: FaultPlan) -> None:  # pragma: no cover - broker
        now = dt.datetime.now(dt.UTC)
        base = rebase_to_end(generate_events(plan.seed, plan.params["events"], now), now)
        degraded = build_delayed_records(
            base, plan.params["delay_ms"], plan.params["drop_pct"], plan.seed
        )
        self._publish(degraded)

    def _apply_ingress_burst(self, plan: FaultPlan) -> None:  # pragma: no cover - broker
        now = dt.datetime.now(dt.UTC)
        records = rebase_to_end(
            generate_events(
                plan.seed,
                plan.params["events"],
                now,
                burst_factor=plan.params["burst_factor"],
                burst_frac=0.6,
            ),
            now,
        )
        self._publish(records)

    def _apply_resource_contention(self, plan: FaultPlan) -> None:  # pragma: no cover - stressor
        stressor.cpu_stress(plan.params["cpu_workers"], plan.params["duration_s"])

    def inject(self, scenario_name: str, seed: int) -> str:
        """Record and apply one fault; returns the failure_events event_id."""
        scenario = get_scenario(scenario_name)
        plan = plan_timeline(scenario, seed)
        event_id = self._record(plan)
        applier = {
            "schema_drift": self._apply_schema_drift,
            "upstream_delay": self._apply_upstream_delay,
            "ingress_burst": self._apply_ingress_burst,
            "resource_contention": self._apply_resource_contention,
        }[scenario_name]
        applier(plan)
        return event_id


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE failure injector")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--experiment-run", default=None)
    parser.add_argument("--plan-only", action="store_true", help="print the plan and exit")
    args = parser.parse_args()
    scenario = get_scenario(args.scenario)
    seed = args.seed if args.seed is not None else get_settings().default_seed
    if args.plan_only:
        print(json.dumps(plan_timeline(scenario, seed).as_dict(), indent=2))
        return
    event_id = FaultInjector(experiment_run=args.experiment_run).inject(args.scenario, seed)
    log.info("injection_complete", extra={"event_id": event_id, "scenario": args.scenario})


if __name__ == "__main__":  # pragma: no cover
    main()
