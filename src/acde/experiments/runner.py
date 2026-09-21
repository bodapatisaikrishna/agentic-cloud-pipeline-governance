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
import faulthandler
import json
import os
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from acde import db
from acde.config import Settings, get_settings
from acde.experiments.baseline import resolve_via_human
from acde.experiments.configs import ALL_CONFIGS, Run, profile_runs
from acde.experiments.decision_quality import is_correct
from acde.experiments.scenarios import TIMINGS, RunTimings, run_seed
from acde.llm.client import LLMStats
from acde.logging import get_logger
from acde.orchestrator.configs import AGENT_CONFIGS

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
    # D-091 wired agents/detection.py's task_failed check into the live monitoring path, reading
    # telemetry.task_runs -- a table this reset never cleared. A stale row surviving from an
    # earlier run of the same experiment_run could then be (re-)detected as a real anomaly on the
    # very next run_one() call, creating extra failure_events beyond the one this run actually
    # injects -- the exact intermittent test_reset_isolates_reruns failure (assert n1 == n2 == 1
    # seeing 3 instead) this fixes at the root, rather than in the test alone.
    "telemetry.task_runs",
)


def run_id_for(run: Run) -> str:
    return f"{run.config}__{run.scenario}__r{run.replicate}"


def _reset_run(experiment_run: str) -> None:
    for table in _RUN_TABLES:
        db.execute(f"DELETE FROM {table} WHERE experiment_run = %s", (experiment_run,))


def _sample_resources(experiment_run: str) -> None:  # pragma: no cover - docker/airflow I/O
    from acde.telemetry.collector import TelemetryCollector

    TelemetryCollector(experiment_run=experiment_run).collect_resource_usage()


def _respond(  # pragma: no cover - live loop
    run: Run, seed: int, timings: RunTimings
) -> LLMStats | None:
    """Drive the run's response; returns the LLM client's stats for agent configs (D-104)."""
    from acde.experiments.baselines import resolve_via_autoscale, resolve_via_rules
    from acde.orchestrator.loop import ControlLoop

    if run.config == "baseline":
        resolve_via_human(run_id_for(run), seed)
        return None
    if run.config == "rule_based":
        resolve_via_rules(run_id_for(run), seed)
        return None
    if run.config == "autoscale":
        resolve_via_autoscale(run_id_for(run), seed)
        return None
    loop = ControlLoop(experiment_run=run_id_for(run), config=run.config)
    loop.interval_s = min(2.0, timings.loop_s / 3)
    asyncio.run(loop.run(timings.loop_s))
    resolve_via_human(run_id_for(run), seed)  # fallback for faults no agent resolved
    return loop.llm.stats


FRESHNESS_FAULTS = frozenset({"upstream_delay", "ingress_burst"})


def harvest_metrics(
    experiment_run: str,
    wall_s: float,
    scenario: str = "",
    config: str = "",
    llm_stats: LLMStats | None = None,
) -> dict[str, float]:
    """Compute the §5.4 metrics for a completed run from the telemetry tables.

    ``llm_stats`` (D-104) adds the billing-accurate LLM accounting the agent_actions rows cannot
    give (they replay cached tokens); a run with no LLM (baselines) reports all zeros for those
    columns so every run shares one metric set.
    """
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
        **(llm_stats or LLMStats()).as_metrics(),
    }


def _drop_run_rows(csv_path: Path, run_id: str) -> None:
    """Remove any rows already written for ``run_id`` (atomic rewrite).

    ``_write_rows`` and ``_append_manifest`` are two separate writes, so a process killed between
    them leaves rows in ``raw.csv`` for a run the manifest doesn't list -- and resuming re-runs that
    run and would append a *second* copy of its rows, silently double-counting it in the statistics.
    Clearing first makes a re-run idempotent regardless of where the previous attempt died.
    """
    if not csv_path.exists():
        return
    with csv_path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    kept = [r for i, r in enumerate(rows) if i == 0 or (r and r[0] != run_id)]
    if len(kept) == len(rows):
        return
    fd, tmp = tempfile.mkstemp(dir=csv_path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as fh:
        csv.writer(fh).writerows(kept)
    os.replace(tmp, csv_path)


def _write_rows(csv_path: Path, run: Run, seed: int, metrics: dict[str, float]) -> None:
    _drop_run_rows(csv_path, run_id_for(run))
    new = not csv_path.exists()
    with csv_path.open("a", newline="") as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(CSV_HEADER)
        for metric, value in metrics.items():
            writer.writerow(
                [run_id_for(run), run.config, run.scenario, run.replicate, seed, metric, value]
            )


def uses_llm(config: str) -> bool:
    """True if the config runs LLM-driven agents (the baselines never call a model)."""
    return bool(AGENT_CONFIGS.get(config))


# Paths whose contents can change an experiment's outcome. Editing the manuscript -- or the
# post-hoc analysis code, which only reads finished results -- while a multi-day campaign runs must
# not mark (or abort) the runs, so "dirty" is judged on these alone (git pathspec syntax).
CODE_PATHS = ("src", "infra", "pyproject.toml", "uv.lock", ":(exclude)src/acde/analysis")


def _git_state() -> dict[str, Any]:
    """Commit SHA and whether experiment code had uncommitted changes when the run started."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no", "--", *CODE_PATHS],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return {"git_sha": "unknown", "git_dirty": None}
    return {"git_sha": sha, "git_dirty": dirty}


def _llm_models(settings: Settings) -> dict[str, str]:
    """Model ids only -- never credentials -- for the provenance record."""
    if settings.mock_llm:
        return {}
    if settings.llm_provider == "gemini":
        return {
            "reasoning": settings.gemini_model_reasoning,
            "fast": settings.gemini_model_fast,
        }
    if settings.llm_provider == "openai_compatible":
        return {"reasoning": settings.oai_model_reasoning, "fast": settings.oai_model_fast}
    return {"reasoning": settings.model_reasoning, "fast": settings.model_fast}


def build_provenance(profile: str, timings: RunTimings) -> dict[str, Any]:
    """Everything needed to say *exactly* what produced a run's numbers (D-104).

    Recorded in every manifest line so a merged dataset can never silently mix conditions (the
    D-081 near-miss: a shared manifest made a whole rerun look already done). Contains model ids
    and modelled-environment parameters, never a secret.
    """
    s = get_settings()
    return {
        "profile": profile,
        "timings": {
            "warmup_s": timings.warmup_s,
            "loop_s": timings.loop_s,
            "settle_s": timings.settle_s,
        },
        "llm_provider": "mock" if s.mock_llm else s.llm_provider,
        "llm_models": _llm_models(s),
        "human_latency": {"median_s": s.human_latency_median_s, "sigma": s.human_latency_sigma},
        "provisioning": {
            "static_units": s.provisioned_units_static,
            "rightsized_units": s.provisioned_units_rightsized,
            "horizon_s": s.provisioning_horizon_s,
        },
        "llm_budget": {
            "max_calls_per_run": s.llm_max_calls_per_run,
            "max_tokens_per_run": s.llm_max_tokens_per_run,
        },
        **_git_state(),
    }


def _append_manifest(
    manifest_path: Path,
    run: Run,
    seed: int,
    metrics: dict[str, float],
    provenance: dict[str, Any] | None = None,
) -> None:
    record: dict[str, Any] = {
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
    if provenance is not None:
        s = get_settings()
        mode = "none" if not uses_llm(run.config) else ("mock" if s.mock_llm else "live")
        record["llm_mode"] = mode
        record["provenance"] = provenance
    with manifest_path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def load_completed(manifest_path: Path) -> set[str]:
    """Run_ids already recorded in the manifest (for resumability)."""
    if not manifest_path.exists():
        return set()
    done: set[str] = set()
    for line in manifest_path.read_text().splitlines():
        if line.strip():
            done.add(json.loads(line)["run_id"])
    return done


def run_one(
    run: Run,
    timings: RunTimings,
    results_dir: Path,
    provenance: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Execute one matrix cell end-to-end and persist its metrics."""
    experiment_run = run_id_for(run)
    seed = run_seed(run.config, run.scenario, run.replicate)
    _reset_run(experiment_run)
    t0 = time.monotonic()
    # Hang watchdog: if a run overruns twice its nominal length, dump every thread's Python stack to
    # stderr (the campaign log) so a stuck run diagnoses itself instead of failing silently.
    nominal_s = timings.warmup_s + timings.loop_s + timings.settle_s
    faulthandler.dump_traceback_later(2 * nominal_s + 120, repeat=False)

    time.sleep(timings.warmup_s)
    _sample_resources(experiment_run)

    from acde.chaos.injector import FaultInjector

    FaultInjector(experiment_run=experiment_run).inject(run.scenario, seed)
    llm_stats = _respond(run, seed, timings)

    time.sleep(timings.settle_s)
    _sample_resources(experiment_run)
    from acde.telemetry.cost import compute_cost_windows

    compute_cost_windows(experiment_run=experiment_run, window_s=5)

    metrics = harvest_metrics(
        experiment_run, time.monotonic() - t0, run.scenario, run.config, llm_stats=llm_stats
    )
    _write_rows(results_dir / "raw.csv", run, seed, metrics)
    _append_manifest(results_dir / "manifest.jsonl", run, seed, metrics, provenance)
    faulthandler.cancel_dump_traceback_later()
    log.info("run_complete", extra={"experiment_run": experiment_run, **metrics})
    return metrics


def remaining_runs(
    profile: str, results_dir: Path, configs: frozenset[str] | None = None
) -> list[Run]:
    """The profile's not-yet-completed runs, optionally restricted to a subset of configs."""
    completed = load_completed(results_dir / "manifest.jsonl")
    return [
        r
        for r in profile_runs(profile)
        if run_id_for(r) not in completed and (configs is None or r.config in configs)
    ]


def run_profile(
    profile: str,
    results_dir: Path | None = None,
    configs: frozenset[str] | None = None,
    max_runs: int | None = None,
) -> int:
    """Run each cell of a profile, skipping ones already in the manifest. Returns runs this call.

    ``configs`` restricts the run to a subset of configs (D-104: the live agent arm and the
    LLM-free baseline arm of the paper campaign are separate, independently resumable invocations
    into one results dir). Unknown config names are rejected rather than silently matching nothing.
    ``max_runs`` caps how many cells this call executes; the campaign supervisor uses 1 so it can
    health-check, budget-check and heartbeat between every run.
    """
    if configs is not None:
        unknown = configs - set(ALL_CONFIGS)
        if unknown:
            raise ValueError(f"unknown config(s) {sorted(unknown)}; choose from {ALL_CONFIGS}")
    settings = get_settings()
    results_dir = results_dir or Path(settings.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    timings = TIMINGS.get(profile, TIMINGS["quick"])
    provenance = build_provenance(profile, timings)
    todo = remaining_runs(profile, results_dir, configs)
    if max_runs is not None:
        todo = todo[:max_runs]
    total = len(todo)

    ran = 0
    for i, run in enumerate(todo, 1):
        log.info("run_start", extra={"experiment_run": run_id_for(run), "i": i, "total": total})
        run_one(run, timings, results_dir, provenance)
        ran += 1
    log.info("profile_complete", extra={"profile": profile, "ran": ran, "total": total})
    return ran


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE experiment runner")
    parser.add_argument("--profile", default="quick")
    parser.add_argument("--results-dir", default=None)
    parser.add_argument(
        "--configs", default=None, help="comma-separated subset of configs (default: all)"
    )
    parser.add_argument("--max-runs", type=int, default=None, help="stop after this many runs")
    args = parser.parse_args()
    results = Path(args.results_dir) if args.results_dir else None
    subset = frozenset(c.strip() for c in args.configs.split(",")) if args.configs else None
    run_profile(args.profile, results, subset, args.max_runs)


if __name__ == "__main__":  # pragma: no cover
    main()
