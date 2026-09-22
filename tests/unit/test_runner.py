"""Unit tests for the experiment runner (I/O + db mocked; no stack)."""

import json
from unittest.mock import MagicMock

import pytest

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
        from acde.telemetry.cost import provisioning_cost

        fake = MagicMock()
        # fetch_all is called twice: failure events (mttr+stall+fault_type), then executed actions.
        fake.fetch_all.side_effect = [
            [
                {"mttr": 10.0, "stall": 100.0, "fault_type": "upstream_delay"},
                {"mttr": 20.0, "stall": 120.0, "fault_type": "upstream_delay"},
                {"mttr": 30.0, "stall": 140.0, "fault_type": "upstream_delay"},
            ],
            [{"action_type": "replay"}],
        ]
        # fetch_one: cost, interventions, tokens (freshness now derived from event stalls).
        fake.fetch_one.side_effect = [{"c": 5.0}, {"n": 2}, {"t": 800}]
        monkeypatch.setattr(runner, "db", fake)
        m = runner.harvest_metrics("run", wall_s=12.5, scenario="upstream_delay", config="baseline")
        assert m["mttr_s"] == 20.0  # median
        assert m["cost_units"] == 5.0 + provisioning_cost("baseline")  # measured + provisioning
        assert m["manual_interventions"] == 2.0
        assert m["llm_tokens"] == 800.0
        assert m["freshness_s"] == 120.0  # median ingestion-stall of the streaming fault
        assert m["decision_correct"] == 1.0  # replay is a valid upstream_delay mitigation
        assert m["wall_clock_s"] == 12.5

    def test_llm_stats_flow_into_metrics(self, monkeypatch):
        from acde.llm.client import LLMStats

        fake = MagicMock()
        fake.fetch_all.side_effect = [[], []]
        fake.fetch_one.side_effect = [{"c": 0}, {"n": 0}, {"t": 999}]
        monkeypatch.setattr(runner, "db", fake)
        stats = LLMStats(
            real_calls=3, cache_hits=5, tokens_in=100, tokens_out=40, invalid_outputs=1
        )
        m = runner.harvest_metrics("run", 1.0, "upstream_delay", "full", llm_stats=stats)
        assert m["api_tokens"] == 140.0  # billing-accurate, not the row-level 999
        assert m["llm_tokens"] == 999.0  # legacy row-level figure kept for continuity
        assert (m["llm_calls"], m["llm_cache_hits"], m["llm_invalid"]) == (3.0, 5.0, 1.0)

    def test_no_llm_config_reports_zeros(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.side_effect = [[], []]
        fake.fetch_one.side_effect = [{"c": 0}, {"n": 0}, {"t": 0}]
        monkeypatch.setattr(runner, "db", fake)
        m = runner.harvest_metrics("run", 1.0, "upstream_delay", "baseline")
        assert m["api_tokens"] == m["llm_calls"] == m["llm_degraded"] == 0.0

    def test_rightsizing_config_costs_less(self, monkeypatch):
        from acde.telemetry.cost import provisioning_cost

        assert provisioning_cost("full") < provisioning_cost("baseline")
        assert provisioning_cost("autoscale") == provisioning_cost("optimization_only")

    def test_no_events_zero_mttr(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.side_effect = [[], []]
        fake.fetch_one.side_effect = [{"c": 0}, {"n": 0}, {"t": 0}]
        monkeypatch.setattr(runner, "db", fake)
        m = runner.harvest_metrics("run", 1.0, scenario="upstream_delay", config="baseline")
        assert m["mttr_s"] == 0.0
        assert m["freshness_s"] == 0.0  # no resolved streaming faults
        assert m["decision_correct"] == 0.0  # no executed action → incorrect


class TestRunOne:
    def test_writes_row_and_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "_reset_run", lambda r: None)
        monkeypatch.setattr(runner, "_sample_resources", lambda r: None)
        monkeypatch.setattr(runner, "_respond", lambda run, seed, timings: None)
        monkeypatch.setattr(runner.time, "sleep", lambda s: None)
        monkeypatch.setattr(
            runner,
            "harvest_metrics",
            lambda r, w, s="", c="", llm_stats=None: {"mttr_s": 4.0, "wall_clock_s": w},
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
        monkeypatch.setattr(
            runner, "run_one", lambda run, t, d, p=None: ran.append(runner.run_id_for(run))
        )
        # pre-populate the manifest with one of the two smoke runs
        (tmp_path / "manifest.jsonl").write_text(
            json.dumps({"run_id": "baseline__upstream_delay__r0"}) + "\n"
        )
        count = runner.run_profile("smoke", results_dir=tmp_path)
        assert count == 1  # only the not-yet-done run executed
        assert ran == ["full__upstream_delay__r0"]


class TestAtomicRowReplacement:
    def test_rewriting_a_run_does_not_duplicate_rows(self, tmp_path):
        """A crash between the raw.csv and manifest writes must not double-count on resume."""
        run = Run("full", "upstream_delay", 0)
        other = Run("baseline", "upstream_delay", 0)
        csv_path = tmp_path / "raw.csv"
        runner._write_rows(csv_path, other, 1, {"mttr_s": 9.0})
        runner._write_rows(csv_path, run, 2, {"mttr_s": 3.0, "cost_units": 1.0})
        runner._write_rows(csv_path, run, 2, {"mttr_s": 5.0, "cost_units": 1.0})  # the re-run
        lines = csv_path.read_text().splitlines()
        assert lines[0].startswith("run_id,")
        full = [ln for ln in lines if ln.startswith("full__")]
        assert sorted(full) == [
            "full__upstream_delay__r0,full,upstream_delay,0,2,cost_units,1.0",
            "full__upstream_delay__r0,full,upstream_delay,0,2,mttr_s,5.0",
        ]
        assert sum(ln.startswith("baseline__") for ln in lines) == 1  # neighbours untouched

    def test_drop_is_noop_without_file_or_match(self, tmp_path):
        runner._drop_run_rows(tmp_path / "missing.csv", "x")  # no error
        csv_path = tmp_path / "raw.csv"
        runner._write_rows(csv_path, Run("full", "upstream_delay", 0), 2, {"mttr_s": 1.0})
        before = csv_path.read_text()
        runner._drop_run_rows(csv_path, "nope__x__r0")
        assert csv_path.read_text() == before
        assert not list(tmp_path.glob("*.tmp"))


class TestProvenance:
    def test_manifest_records_llm_mode_and_provenance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runner, "_git_state", lambda: {"git_sha": "abc", "git_dirty": False})
        prov = runner.build_provenance("smoke", TIMINGS["smoke"])
        assert prov["profile"] == "smoke" and prov["git_sha"] == "abc"
        assert prov["timings"]["loop_s"] == TIMINGS["smoke"].loop_s
        metrics = {"mttr_s": 1.0, "wall_clock_s": 2.0}
        runner._append_manifest(
            tmp_path / "m.jsonl", Run("baseline", "upstream_delay", 0), 1, metrics, prov
        )
        runner._append_manifest(
            tmp_path / "m.jsonl", Run("full", "upstream_delay", 0), 1, metrics, prov
        )
        recs = [json.loads(ln) for ln in (tmp_path / "m.jsonl").read_text().splitlines()]
        assert recs[0]["llm_mode"] == "none"  # baselines never call a model
        assert recs[1]["llm_mode"] == "mock"  # test env is MOCK_LLM=1
        assert recs[1]["provenance"]["git_sha"] == "abc"

    def test_provenance_never_contains_credentials(self, monkeypatch):
        monkeypatch.setattr(runner, "_git_state", lambda: {"git_sha": "abc", "git_dirty": True})
        dumped = json.dumps(runner.build_provenance("paper", TIMINGS["paper"])).lower()
        assert "key" not in dumped and "secret" not in dumped and "token_value" not in dumped

    def test_live_provenance_lists_model_ids(self, monkeypatch):
        from acde.config import Settings

        live = Settings(_env_file=None, mock_llm=False, llm_provider="openai_compatible")
        monkeypatch.setattr(runner, "get_settings", lambda: live)
        monkeypatch.setattr(runner, "_git_state", lambda: {"git_sha": "abc", "git_dirty": False})
        prov = runner.build_provenance("paper", TIMINGS["paper"])
        assert prov["llm_provider"] == "openai_compatible"
        assert set(prov["llm_models"]) == {"reasoning", "fast"}

    def test_git_state_reports_sha(self):
        state = runner._git_state()
        assert set(state) == {"git_sha", "git_dirty"}

    def test_git_state_survives_missing_git(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no git")

        monkeypatch.setattr(runner.subprocess, "run", boom)
        assert runner._git_state() == {"git_sha": "unknown", "git_dirty": None}


class TestConfigFilter:
    def test_subset_runs_only_selected_configs(self, tmp_path, monkeypatch):
        ran: list[str] = []
        monkeypatch.setattr(runner, "run_one", lambda run, t, d, p=None: ran.append(run.config))
        runner.run_profile("smoke", tmp_path, configs=frozenset({"full"}))
        assert ran == ["full"]

    def test_max_runs_caps_a_call(self, tmp_path, monkeypatch):
        ran: list[str] = []
        monkeypatch.setattr(runner, "run_one", lambda run, t, d, p=None: ran.append(run.config))
        assert runner.run_profile("smoke", tmp_path, max_runs=1) == 1
        assert ran == ["baseline"]

    def test_pilot2_covers_the_gaps_pilot_left(self):
        from acde.experiments.configs import profile_runs

        pilot1 = {(r.config, r.scenario) for r in profile_runs("pilot")}
        pilot2 = {(r.config, r.scenario) for r in profile_runs("pilot2")}
        assert pilot1.isdisjoint(pilot2)
        configs = {c for c, _ in pilot1 | pilot2}
        scenarios = {s for _, s in pilot1 | pilot2}
        assert configs == {
            "full",
            "recovery_only",
            "optimization_only",
            "schema_only",
            "monitor_only",
        }
        assert scenarios == {
            "schema_drift",
            "resource_contention",
            "upstream_delay",
            "ingress_burst",
        }

    def test_pilot_profile_uses_paper_timings(self):
        from acde.experiments.configs import profile_runs

        runs = profile_runs("pilot")
        assert len(runs) == 8 and {r.config for r in runs} == {"full", "recovery_only"}
        assert TIMINGS["pilot"] == TIMINGS["paper"]

    def test_unknown_config_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="unknown config"):
            runner.run_profile("smoke", tmp_path, configs=frozenset({"ful"}))

    def test_remaining_runs_excludes_completed_and_filters(self, tmp_path):
        (tmp_path / "manifest.jsonl").write_text(
            json.dumps({"run_id": "baseline__upstream_delay__r0"}) + "\n"
        )
        assert [r.config for r in runner.remaining_runs("smoke", tmp_path)] == ["full"]
        assert runner.remaining_runs("smoke", tmp_path, frozenset({"baseline"})) == []

    def test_uses_llm(self):
        assert runner.uses_llm("full") and not runner.uses_llm("baseline")
