"""Integration test for the experiment runner (live stack, MOCK_LLM=1).

Runs the tiny `smoke` profile (baseline + full on one scenario), then asserts the outputs and
resumability, and that the agent config recovers faster than the human baseline.
"""

from __future__ import annotations

import csv

import pytest

from acde.dataplane.datasets import tpcds_gen
from acde.experiments import runner
from acde.experiments.scenarios import TIMINGS

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _restore_source():
    yield
    tpcds_gen.write()


def _rows(csv_path):
    with csv_path.open() as fh:
        return list(csv.DictReader(fh))


def test_smoke_profile_writes_results_and_is_resumable(tmp_path):
    ran = runner.run_profile("smoke", results_dir=tmp_path)
    assert ran == 2  # baseline + full

    raw = tmp_path / "raw.csv"
    manifest = tmp_path / "manifest.jsonl"
    assert raw.exists() and manifest.exists()

    rows = _rows(raw)
    run_ids = {r["run_id"] for r in rows}
    assert run_ids == {"baseline__upstream_delay__r0", "full__upstream_delay__r0"}
    metrics = {r["metric"] for r in rows}
    assert {"mttr_s", "cost_units", "manual_interventions", "llm_tokens", "wall_clock_s"} <= metrics

    # resumability: a second call skips both completed runs
    assert runner.load_completed(manifest) == run_ids
    assert runner.run_profile("smoke", results_dir=tmp_path) == 0


def test_agents_recover_faster_than_human_baseline(tmp_path):
    runner.run_profile("smoke", results_dir=tmp_path)
    rows = _rows(tmp_path / "raw.csv")
    mttr = {r["run_id"]: float(r["value"]) for r in rows if r["metric"] == "mttr_s"}
    # upstream_delay is recovery's scenario: the full config resolves in seconds,
    # the baseline waits on the human simulator (~360s median).
    assert mttr["full__upstream_delay__r0"] < mttr["baseline__upstream_delay__r0"]


def test_reset_isolates_reruns():
    # run_one twice for the same cell → the second reset clears the first, so exactly one fault
    from acde import db
    from acde.experiments.configs import Run

    run = Run("full", "upstream_delay", 0)
    runner.run_one(run, TIMINGS["smoke"], __import__("pathlib").Path("results"))
    n1 = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.failure_events WHERE experiment_run = %s",
        ("full__upstream_delay__r0",),
    )["n"]
    runner.run_one(run, TIMINGS["smoke"], __import__("pathlib").Path("results"))
    n2 = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.failure_events WHERE experiment_run = %s",
        ("full__upstream_delay__r0",),
    )["n"]
    assert n1 == n2 == 1  # reset prevents accumulation across reruns
