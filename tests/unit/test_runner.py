"""Unit tests for the experiment runner (I/O + db mocked; no stack)."""

import json
from unittest.mock import MagicMock

from acde.experiments import runner
from acde.experiments.configs import Run
from acde.experiments.scenarios import TIMINGS


class TestManifest:
    def test_load_completed_reads_run_ids(self, tmp_path):
        m = tmp_path / "manifest.jsonl"
        m.write_text(
            json.dumps({"run_id": "a__x__r0"}) + "\n" + json.dumps({"run_id": "b__x__r0"}) + "\n"
        )
        assert runner.load_completed(m) == {"a__x__r0", "b__x__r0"}

    def test_load_completed_missing_file(self, tmp_path):
        assert runner.load_completed(tmp_path / "nope.jsonl") == set()

    def test_write_rows_and_manifest(self, tmp_path):
        run = Run("full", "upstream_delay", 0)
        metrics = {"mttr_s": 3.0, "cost_units": 1.0, "wall_clock_s": 9.0}
        runner._write_rows(tmp_path / "raw.csv", run, 42, metrics)
        runner._append_manifest(tmp_path / "manifest.jsonl", run, 42, metrics)
        csv_text = (tmp_path / "raw.csv").read_text()
        assert "run_id,config,scenario,replicate,seed,metric,value" in csv_text
        assert "full__upstream_delay__r0,full,upstream_delay,0,42,mttr_s,3.0" in csv_text
        line = json.loads((tmp_path / "manifest.jsonl").read_text().strip())
        assert line["run_id"] == "full__upstream_delay__r0" and line["status"] == "ok"


class TestHarvest:
    def test_computes_metrics(self, monkeypatch):
        fake = MagicMock()
        # fetch_all is called twice: mttr events, then executed agent actions.
        fake.fetch_all.side_effect = [
            [{"mttr": 10.0}, {"mttr": 20.0}, {"mttr": 30.0}],
            [{"action_type": "replay"}],
        ]
        fake.fetch_one.side_effect = [{"c": 5.0}, {"n": 2}, {"t": 800}, {"value": 25.0}]
        monkeypatch.setattr(runner, "db", fake)
        m = runner.harvest_metrics("run", wall_s=12.5, scenario="upstream_delay")
        assert m["mttr_s"] == 20.0  # median
        assert m["cost_units"] == 5.0
        assert m["manual_interventions"] == 2.0
        assert m["llm_tokens"] == 800.0
        assert m["freshness_s"] == 25.0
        assert m["decision_correct"] == 1.0  # replay is a valid upstream_delay mitigation
        assert m["wall_clock_s"] == 12.5

    def test_no_events_zero_mttr(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.side_effect = [[], []]
        fake.fetch_one.side_effect = [{"c": 0}, {"n": 0}, {"t": 0}, None]
        monkeypatch.setattr(runner, "db", fake)
        m = runner.harvest_metrics("run", 1.0, scenario="upstream_delay")
        assert m["mttr_s"] == 0.0
        assert m["decision_correct"] == 0.0  # no executed action → incorrect


class TestRunOne:
    def test_writes_row_and_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "_reset_run", lambda r: None)
        monkeypatch.setattr(runner, "_sample_resources", lambda r: None)
        monkeypatch.setattr(runner, "_respond", lambda run, seed, timings: None)
        monkeypatch.setattr(runner.time, "sleep", lambda s: None)
        monkeypatch.setattr(
            runner, "harvest_metrics", lambda r, w, s="": {"mttr_s": 4.0, "wall_clock_s": w}
        )
        monkeypatch.setattr("acde.chaos.injector.FaultInjector", MagicMock())
        monkeypatch.setattr("acde.telemetry.cost.compute_cost_windows", lambda **k: 0)

        run = Run("baseline", "upstream_delay", 0)
        metrics = runner.run_one(run, TIMINGS["smoke"], tmp_path)
        assert metrics["mttr_s"] == 4.0
        assert (tmp_path / "raw.csv").exists()
        assert runner.load_completed(tmp_path / "manifest.jsonl") == {
            "baseline__upstream_delay__r0"
        }


class TestRunProfileResumability:
    def test_skips_completed_runs(self, tmp_path, monkeypatch):
        ran: list[str] = []
        monkeypatch.setattr(runner, "run_one", lambda run, t, d: ran.append(runner.run_id_for(run)))
        # pre-populate the manifest with one of the two smoke runs
        (tmp_path / "manifest.jsonl").write_text(
            json.dumps({"run_id": "baseline__upstream_delay__r0"}) + "\n"
        )
        count = runner.run_profile("smoke", results_dir=tmp_path)
        assert count == 1  # only the not-yet-done run executed
        assert ran == ["full__upstream_delay__r0"]
