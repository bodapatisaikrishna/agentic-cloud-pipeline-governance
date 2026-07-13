"""Telemetry collector: Airflow REST + ``docker stats`` → ``telemetry`` tables (§8 Phase 2).

Runs host-side (uses the docker CLI and the Airflow REST API over localhost, DEVIATIONS D-020).
Pure parsers (``parse_docker_stats``, ``task_instance_to_row``, ``component_workers``) are
unit-tested; the polling loop and subprocess/HTTP calls are integration-verified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import time
from typing import Any

import httpx

from acde import db
from acde.config import get_settings
from acde.dataplane.streaming.workers import read_desired_workers
from acde.logging import get_logger
from acde.telemetry import freshness

log = get_logger("telemetry.collector")

ACDE_DAGS = ("tpcds_ingest", "opengov_ingest")


# --- Pure parsers ---------------------------------------------------------------------------


def _parse_mem_mb(mem_usage: str) -> float:
    """Parse the used side of docker's ``123MiB / 4GiB`` memory column to MB."""
    used = mem_usage.split("/")[0].strip()
    units = {"B": 1e-6, "KIB": 1e-3, "MIB": 1.0, "GIB": 1e3, "KB": 1e-3, "MB": 1.0, "GB": 1e3}
    for suffix, factor in sorted(units.items(), key=lambda kv: -len(kv[0])):
        if used.upper().endswith(suffix):
            return float(used[: -len(suffix)]) * factor
    return float(used)  # bytes, unit-less


def parse_docker_stats(text: str) -> list[dict[str, Any]]:
    """Parse ``docker stats`` lines formatted ``Name|CPUPerc|MemUsage``."""
    out: list[dict[str, Any]] = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        name, cpu, mem = (part.strip() for part in line.split("|"))
        out.append(
            {"component": name, "cpu_pct": float(cpu.rstrip("%")), "mem_mb": _parse_mem_mb(mem)}
        )
    return out


def task_instance_to_row(ti: dict[str, Any], experiment_run: str) -> tuple[Any, ...]:
    """Map an Airflow task-instance JSON object to a ``task_runs`` upsert tuple."""
    return (
        ti.get("dag_run_id"),
        ti.get("dag_id"),
        ti.get("task_id"),
        ti.get("state"),
        ti.get("start_date"),
        ti.get("end_date"),
        ti.get("duration"),
        ti.get("try_number") or 0,
        None,
        experiment_run,
    )


def component_workers(component: str, running_slots: int, streaming_workers: int) -> int:
    """Resource-unit count attributed to a component for the cost model (D-018)."""
    if component == "streaming":
        return streaming_workers
    if component == "batch":
        return running_slots
    return 1  # single-node docker services


# --- Collector ------------------------------------------------------------------------------


class TelemetryCollector:
    """Polls Airflow + docker into the telemetry tables."""

    def __init__(self, experiment_run: str | None = None) -> None:
        settings = get_settings()
        self.experiment_run = experiment_run or settings.experiment_run
        self.airflow_url = settings.airflow_url
        self.auth = (settings.airflow_user, settings.airflow_password)

    def collect_task_runs(self) -> int:  # pragma: no cover - Airflow REST
        written = 0
        with httpx.Client(base_url=self.airflow_url, auth=self.auth, timeout=30) as client:
            for dag_id in ACDE_DAGS:
                resp = client.get(f"/dags/{dag_id}/dagRuns/~/taskInstances", params={"limit": 100})
                if resp.status_code != 200:
                    continue
                for ti in resp.json().get("task_instances", []):
                    row = task_instance_to_row(ti, self.experiment_run)
                    db.execute(
                        "INSERT INTO telemetry.task_runs (run_id, dag_id, task_id, state, "
                        " start_ts, end_ts, duration_s, try_number, error, experiment_run) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (dag_id, run_id, task_id, try_number) DO UPDATE SET "
                        "  state = EXCLUDED.state, end_ts = EXCLUDED.end_ts, "
                        "  duration_s = EXCLUDED.duration_s, "
                        "  experiment_run = EXCLUDED.experiment_run",
                        row,
                    )
                    written += 1
        return written

    def _running_slots(self) -> int:  # pragma: no cover - Airflow REST
        try:
            with httpx.Client(base_url=self.airflow_url, auth=self.auth, timeout=15) as client:
                pools = client.get("/pools").json().get("pools", [])
            return sum(int(p.get("running_slots", 0)) for p in pools)
        except Exception:  # telemetry must never crash the loop
            return 0

    def collect_resource_usage(self) -> int:  # pragma: no cover - docker CLI
        proc = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        containers = [
            c for c in parse_docker_stats(proc.stdout) if c["component"].startswith("acde-")
        ]
        running_slots = self._running_slots()
        streaming_workers = read_desired_workers()
        ts = dt.datetime.now(dt.UTC)
        rows: list[tuple[Any, ...]] = [
            (c["component"], c["cpu_pct"], c["mem_mb"], 1, ts, self.experiment_run)
            for c in containers
        ]
        # Logical resource-unit rows that drive the cost model.
        for logical in ("streaming", "batch"):
            rows.append(
                (
                    logical,
                    0.0,
                    0.0,
                    component_workers(logical, running_slots, streaming_workers),
                    ts,
                    self.experiment_run,
                )
            )
        db.execute_many(
            "INSERT INTO telemetry.resource_usage "
            "(component, cpu_pct, mem_mb, workers, ts, experiment_run) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            rows,
        )
        return len(rows)

    def tick(self) -> None:  # pragma: no cover - orchestrates I/O
        self.collect_task_runs()
        self.collect_resource_usage()
        freshness.collect(self.experiment_run)

    def run(self, duration_s: float, interval_s: float | None = None) -> None:  # pragma: no cover
        settings = get_settings()
        interval_s = settings.telemetry_interval_s if interval_s is None else interval_s
        deadline = time.monotonic() + duration_s
        log.info(
            "telemetry_started",
            extra={"experiment_run": self.experiment_run, "duration_s": duration_s},
        )
        while time.monotonic() < deadline:
            try:
                self.tick()
            except Exception:  # a bad tick must not kill the collector
                log.warning("telemetry_tick_failed", extra={"experiment_run": self.experiment_run})
            time.sleep(interval_s)
        log.info("telemetry_stopped", extra={"experiment_run": self.experiment_run})


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE telemetry collector")
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--experiment-run", default=None)
    args = parser.parse_args()
    TelemetryCollector(experiment_run=args.experiment_run).run(args.duration, args.interval)


if __name__ == "__main__":  # pragma: no cover
    main()
