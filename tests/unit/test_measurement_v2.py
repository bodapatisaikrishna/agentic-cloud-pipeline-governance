"""Unit tests for measurement protocol v2 (D-105): fair counting, timing, metering and seeding."""

import datetime as dt
import threading
from collections import Counter
from unittest.mock import MagicMock

import httpx
import pytest

from acde.chaos.scenarios import run_seed
from acde.experiments import campaign, isolation, metrics, provenance, runner
from acde.experiments.configs import ALL_CONFIGS, profile_runs
from acde.experiments.scenarios import TIMINGS
from acde.telemetry import cost

T0 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def _harvest(monkeypatch, events, cost_row, interventions, escalated, config="full"):
    fake = MagicMock()
    fake.fetch_all.side_effect = [events, []]
    fake.fetch_one.side_effect = [cost_row, {"n": interventions}, {"n": escalated}, {"t": 0}]
    monkeypatch.setattr(metrics, "db", fake)
    return metrics.harvest_metrics("run", 1.0, "upstream_delay", config), fake


class TestEscalatedIncidents:
    def test_counts_incidents_not_requests(self, monkeypatch):
        # Six escalation requests filed against one open fault are one incident.
        m, _ = _harvest(monkeypatch, [], {"c": 0}, interventions=6, escalated=1)
        assert m["manual_interventions"] == 6.0  # v1 metric kept unchanged
        assert m["escalated_incidents"] == 1.0

    def test_query_ties_requests_to_the_open_fault_window(self, monkeypatch):
        _, fake = _harvest(monkeypatch, [], {"c": 0}, interventions=0, escalated=0)
        sql = fake.fetch_one.call_args_list[2].args[0]
        assert "telemetry.failure_events" in sql and "EXISTS" in sql
        assert "m.requested_ts >= f.injected_ts" in sql
        assert "m.requested_ts <= f.resolved_ts" in sql


class TestRecoveryFromInjection:
    def test_mttr_from_injection_includes_detection_delay(self, monkeypatch):
        # An agent detects 8 s after injection and resolves 20 s after detection.
        events = [{"mttr": 20.0, "stall": 28.0, "detect": 8.0, "fault_type": "upstream_delay"}]
        m, _ = _harvest(monkeypatch, events, {"c": 0}, 0, 0)
        assert m["mttr_s"] == 20.0  # v1 definition, from detection
        assert m["mttr_injection_s"] == 28.0
        assert m["detection_delay_s"] == 8.0

    def test_non_agent_detection_at_injection_gives_equal_clocks(self, monkeypatch):
        events = [{"mttr": 360.0, "stall": 360.0, "detect": 0.0, "fault_type": "schema_drift"}]
        m, _ = _harvest(monkeypatch, events, {"c": 0}, 1, 1, config="baseline")
        assert m["mttr_s"] == m["mttr_injection_s"] == 360.0
        assert m["detection_delay_s"] == 0.0


class TestCostSplit:
    def test_terms_sum_to_the_total(self, monkeypatch):
        m, _ = _harvest(monkeypatch, [], {"c": 7.0, "storage": 2.0}, 0, 0, config="baseline")
        assert m["cost_storage_units"] == 2.0
        assert m["cost_compute_units"] == 5.0
        assert m["cost_provisioning_units"] == cost.provisioning_cost("baseline")
        parts = m["cost_compute_units"] + m["cost_storage_units"] + m["cost_provisioning_units"]
        assert parts == pytest.approx(m["cost_units"])


class TestFixedMeteringSpan:
    def _run(self, monkeypatch, sample_offsets_s, span_s):
        fake = MagicMock()
        fake.fetch_one.side_effect = [{"lo": T0}]

        def fetch_all(sql, params=None):
            if params[1] == "streaming":
                return [
                    {"ts": T0 + dt.timedelta(seconds=s), "workers": 2.0} for s in sample_offsets_s
                ]
            return []

        fake.fetch_all.side_effect = fetch_all
        monkeypatch.setattr(cost, "db", fake)
        monkeypatch.setattr(cost, "warehouse_size_gb", lambda: 0.0)
        cost.compute_cost_windows(experiment_run="r", window_s=5, span_s=span_s)
        return [c.args[1] for c in fake.execute.call_args_list if "INSERT" in c.args[0]]

    def test_short_and_long_runs_are_metered_over_the_same_window(self, monkeypatch):
        # Non-agent run: samples a few seconds apart. Agent run: samples across the whole loop.
        short = self._run(monkeypatch, [0, 3], span_s=305)
        long = self._run(monkeypatch, [0, 150, 305], span_s=305)
        for rows in (short, long):
            compute = sum(r[2] for r in rows if r[1] == "streaming")
            assert compute == pytest.approx(2.0 * 305)

    def test_no_window_passes_the_span_end(self, monkeypatch):
        rows = self._run(monkeypatch, [0], span_s=12)
        assert max(r[6] for r in rows) == T0 + dt.timedelta(seconds=12)


class TestRunStateReset:
    def test_deletes_agent_keys_but_not_operator_keys(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(isolation, "db", fake)
        isolation.reset_desired_state()
        sql, params = fake.execute.call_args.args
        assert sql.startswith("DELETE FROM control.desired_state")
        assert "streaming.workers" in params
        assert {"ingestion.blocked.%", "pipeline.priority.%", "schema.mapping.%"} <= set(params)
        assert not any("paused" in p or "heartbeat" in p for p in params)

    def test_pool_failure_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(isolation, "db", MagicMock())

        def boom() -> None:
            raise httpx.ConnectError("airflow down")

        assert isolation.reset_run_state(reset_pools=boom) is False
        assert isolation.reset_run_state(reset_pools=lambda: None) is True


class TestResourceSampler:
    def test_samples_repeatedly_and_survives_a_failing_sample(self):
        calls = []
        enough = threading.Event()

        def sample() -> None:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("docker stats hiccup")
            if len(calls) >= 3:
                enough.set()

        with isolation.ResourceSampler(sample, interval_s=0.01) as sampler:
            assert enough.wait(5)
        assert len(calls) >= 3
        assert sampler.taken >= 2  # the failed sample is not counted


class TestPairedSeeds:
    def test_v1_policy_unchanged(self):
        # Pinned so the v1 campaign stays reproducible from its manifest.
        assert run_seed("full", "schema_drift", 0) == 558707895
        assert run_seed("full", "schema_drift", 0) != run_seed("baseline", "schema_drift", 0)

    def test_paired_seed_is_shared_across_configs(self):
        seeds = {run_seed(c, "schema_drift", 3, paired=True) for c in ALL_CONFIGS}
        assert len(seeds) == 1

    def test_paired_seed_still_varies_by_scenario_and_replicate(self):
        base = run_seed("full", "schema_drift", 0, paired=True)
        assert run_seed("full", "ingress_burst", 0, paired=True) != base
        assert run_seed("full", "schema_drift", 1, paired=True) != base

    def test_profile_decides_the_policy(self):
        assert provenance.seed_policy("paper_v2") == "paired"
        assert provenance.seed_policy("paper") == "per_config"

    def test_run_profile_passes_paired_for_v2(self, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(runner, "run_one", lambda *a, paired=False, **k: seen.append(paired))
        runner.run_profile("paper_v2", results_dir=tmp_path, max_runs=1)
        runner.run_profile("smoke", results_dir=tmp_path, max_runs=1)
        assert seen == [True, False]

    def test_provenance_records_protocol_and_seed_policy(self, monkeypatch):
        monkeypatch.setattr(provenance, "git_state", lambda: {"git_sha": "abc", "git_dirty": False})
        prov = provenance.build_provenance("paper_v2", TIMINGS["paper_v2"])
        assert prov["measurement_protocol"] == "v2"
        assert prov["seed_policy"] == "paired"
        assert prov["pool_baseline_slots"] == {"default_pool": 128}


class TestPaperV2Profile:
    def test_every_config_has_equal_n(self):
        counts = Counter(r.config for r in profile_runs("paper_v2"))
        assert set(counts) == set(ALL_CONFIGS)
        assert set(counts.values()) == {80}  # 4 scenarios x 20 replicates

    def test_order_is_interleaved_and_deterministic(self):
        runs = profile_runs("paper_v2")
        assert len(set(runs)) == len(runs) == 720
        assert runs[:8] != sorted(runs[:8], key=lambda r: r.config)  # not config-major
        assert len({r.config for r in runs[:20]}) > 1


class TestInterleavedCampaign:
    def test_v2_arms_use_their_own_dirs(self, tmp_path):
        arms = campaign.arms_for("paper_v2", tmp_path)
        assert {a.profile for a in arms} == {"paper_v2"}
        assert all(a.results_dir.name.startswith("paper-v2-") for a in arms)

    def test_next_pending_follows_profile_order_across_arms(self, tmp_path):
        arms = campaign.arms_for("paper_v2", tmp_path)
        order = profile_runs("paper_v2")
        arm, pending = campaign.next_pending(arms, interleave=True)
        first_owned = next(r for r in order if any(r.config in a.configs for a in arms))
        assert pending[0] == first_owned and pending[0].config in arm.configs

    def test_without_interleave_first_arm_goes_first(self, tmp_path):
        arms = campaign.arms_for("paper_v2", tmp_path)
        arm, _ = campaign.next_pending(arms, interleave=False)
        assert arm is arms[0]

    def test_done_when_nothing_pending(self, tmp_path):
        assert campaign.next_pending([], interleave=True) == (None, [])
