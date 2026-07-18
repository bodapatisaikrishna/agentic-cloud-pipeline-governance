"""Resumable experiment runner: config x scenario x seed matrix (§8 Phase 7).

Per run: reset run-scoped telemetry → warmup sample → inject the seeded fault → respond (control
loop for agent configs, human simulator for baseline) → fallback human for anything unresolved →
sample resources + aggregate cost → harvest the §5.4 metrics → append one CSV row per metric and a
manifest checkpoint. ``run_profile`` skips run_ids already in the manifest, so kill + re-run resumes
(DEVIATIONS D-043).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import statistics
import time
from pathlib import Path

from acde import db
from acde.config import get_settings
from acde.experiments.baseline import resolve_via_human
from acde.experiments.configs import Run, profile_runs
from acde.experiments.decision_quality import is_correct
from acde.experiments.scenarios import TIMINGS, RunTimings, run_seed
from acde.logging import get_logger

log = get_logger("experiments.runner")

CSV_HEADER = ["run_id", "config", "scenario", "replicate", "seed", "metric", "value"]
# Run-scoped telemetry cleared before each run so a rerun is isolated.
_RUN_TABLES = (
    "telemetry.failure_events",
    "telemetry.agent_actions",
    "telemetry.manual_interventions",
    "telemetry.resource_usage",
    "telemetry.cost_ledger",
    "telemetry.pipeline_metrics",
)


def run_id_for(run: Run) -> str:
    return f"{run.config}__{run.scenario}__r{run.replicate}"


def _reset_run(experiment_run: str) -> None:
    for table in _RUN_TABLES:
        db.execute(f"DELETE FROM {table} WHERE experiment_run = %s", (experiment_run,))


def _sample_resources(experiment_run: str) -> None:  # pragma: no cover - docker/airflow I/O
    from acde.telemetry.collector import TelemetryCollector

    TelemetryCollector(experiment_run=experiment_run).collect_resource_usage()


def _respond(run: Run, seed: int, timings: RunTimings) -> None:  # pragma: no cover - live loop
    from acde.experiments.baselines import resolve_via_autoscale, resolve_via_rules
    from acde.orchestrator.loop import ControlLoop

    if run.config == "baseline":
        resolve_via_human(run_id_for(run), seed)
        return
    if run.config == "rule_based":
        resolve_via_rules(run_id_for(run), seed)
        return
    if run.config == "autoscale":
        resolve_via_autoscale(run_id_for(run), seed)
        return
    loop = ControlLoop(experiment_run=run_id_for(run), config=run.config)
    loop.interval_s = min(2.0, timings.loop_s / 3)
    asyncio.run(loop.run(timings.loop_s))
    resolve_via_human(run_id_for(run), seed)  # fallback for faults no agent resolved


FRESHNESS_FAULTS = frozenset({"upstream_delay", "ingress_burst"})


def harvest_metrics(
    experiment_run: str, wall_s: float, scenario: str = "", config: str = ""
) -> dict[str, float]:
    """Compute the §5.4 metrics for a completed run from the telemetry tables."""
    from acde.telemetry.cost import provisioning_cost

    events = db.fetch_all(
        "SELECT EXTRACT(EPOCH FROM (resolved_ts - detected_ts)) AS mttr, "
        "EXTRACT(EPOCH FROM (resolved_ts - injected_ts)) AS stall, fault_type "
        "FROM telemetry.failure_events "
        "WHERE experiment_run = %s AND detected_ts IS NOT NULL AND resolved_ts IS NOT NULL",
        (experiment_run,),
    )
    mttrs = [float(e["mttr"]) for e in events if e["mttr"] is not None]
    cost = db.fetch_one(
        "SELECT COALESCE(SUM(cost_units), 0) AS c FROM telemetry.cost_ledger "
        "WHERE experiment_run = %s",
        (experiment_run,),
    )
    interventions = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.manual_interventions WHERE experiment_run = %s",
        (experiment_run,),
    )
    tokens = db.fetch_one(
        "SELECT COALESCE(SUM(llm_tokens_in + llm_tokens_out), 0) AS t "
        "FROM telemetry.agent_actions WHERE experiment_run = %s",
        (experiment_run,),
    )
    # Freshness (A3, D-060): for streaming (ingestion-stall) faults, data-freshness lag equals how
    # long ingestion was stalled = the fault's open duration (resolved - injected). Batch faults
    # don't degrade streaming freshness → 0. Derived from independently-measured resolution timing.
    stalls = [
        float(e["stall"])
        for e in events
        if e["stall"] is not None and e["fault_type"] in FRESHNESS_FAULTS
    ]
    freshness_s = statistics.median(stalls) if stalls else 0.0
    executed = db.fetch_all(
        "SELECT action_type FROM telemetry.agent_actions "
        "WHERE experiment_run = %s AND executed = TRUE",
        (experiment_run,),
    )
    decision_correct = is_correct(scenario, [r["action_type"] for r in executed])
    return {
        "mttr_s": statistics.median(mttrs) if mttrs else 0.0,
        # cost v2: measured compute/storage + the held-allocation (provisioning) cost (D-061).
        "cost_units": (float(cost["c"]) if cost else 0.0) + provisioning_cost(config),
        "manual_interventions": float(interventions["n"]) if interventions else 0.0,
        "llm_tokens": float(tokens["t"]) if tokens else 0.0,
        "freshness_s": freshness_s,
        "decision_correct": 1.0 if decision_correct else 0.0,
        "wall_clock_s": wall_s,
    }


def _write_rows(csv_path: Path, run: Run, seed: int, metrics: dict[str, float]) -> None:
    new = not csv_path.exists()
    with csv_path.open("a", newline="") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(CSV_HEADER)
        for metric, value in metrics.items():
            writer.writerow(
                [run_id_for(run), run.config, run.scenario, run.replicate, seed, metric, value]
            )


def _append_manifest(manifest_path: Path, run: Run, seed: int, metrics: dict[str, float]) -> None:
    with manifest_path.open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id_for(run),
                    "config": run.config,
                    "scenario": run.scenario,
                    "replicate": run.replicate,
                    "seed": seed,
                    "mttr_s": metrics["mttr_s"],
                    "wall_s": metrics["wall_clock_s"],
                    "status": "ok",
                    "ts": dt.datetime.now(dt.UTC).isoformat(),
                }
            )
            + "\n"
        )


def load_completed(manifest_path: Path) -> set[str]:
    """Run_ids already recorded in the manifest (for resumability)."""
    if not manifest_path.exists():
        return set()
    done: set[str] = set()
    for line in manifest_path.read_text().splitlines():
        if line.strip():
            done.add(json.loads(line)["run_id"])
    return done


def run_one(run: Run, timings: RunTimings, results_dir: Path) -> dict[str, float]:
    """Execute one matrix cell end-to-end and persist its metrics."""
    experiment_run = run_id_for(run)
    seed = run_seed(run.config, run.scenario, run.replicate)
    _reset_run(experiment_run)
    t0 = time.monotonic()

    time.sleep(timings.warmup_s)
    _sample_resources(experiment_run)

    from acde.chaos.injector import FaultInjector

    FaultInjector(experiment_run=experiment_run).inject(run.scenario, seed)
    _respond(run, seed, timings)

    time.sleep(timings.settle_s)
    _sample_resources(experiment_run)
    from acde.telemetry.cost import compute_cost_windows

    compute_cost_windows(experiment_run=experiment_run, window_s=5)

    metrics = harvest_metrics(experiment_run, time.monotonic() - t0, run.scenario, run.config)
    _write_rows(results_dir / "raw.csv", run, seed, metrics)
    _append_manifest(results_dir / "manifest.jsonl", run, seed, metrics)
    log.info("run_complete", extra={"experiment_run": experiment_run, **metrics})
    return metrics


def run_profile(profile: str, results_dir: Path | None = None) -> int:
    """Run each cell of a profile, skipping ones already in the manifest. Returns runs this call."""
    settings = get_settings()
    results_dir = results_dir or Path(settings.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    timings = TIMINGS.get(profile, TIMINGS["quick"])
    runs = profile_runs(profile)
    completed = load_completed(results_dir / "manifest.jsonl")

    ran = 0
    for i, run in enumerate(runs, 1):
        if run_id_for(run) in completed:
            continue
        log.info("run_start", extra={"experiment_run": run_id_for(run), "i": i, "total": len(runs)})
        run_one(run, timings, results_dir)
        ran += 1
    log.info("profile_complete", extra={"profile": profile, "ran": ran, "total": len(runs)})
    return ran


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE experiment runner")
    parser.add_argument("--profile", default="quick")
    parser.add_argument("--results-dir", default=None)
    args = parser.parse_args()
    results = Path(args.results_dir) if args.results_dir else None
    run_profile(args.profile, results)


if __name__ == "__main__":  # pragma: no cover
    main()
