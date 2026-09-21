"""Unit tests for campaign-level statistics (synthetic frames; no results dirs needed)."""

import json

import numpy as np
import pandas as pd
import pytest

from acde.analysis import paper_stats as ps

SCENARIOS = ("schema_drift", "upstream_delay")


def _rows(config, arm, metric, values, scenarios=SCENARIOS):
    rows = []
    i = 0
    for sc in scenarios:
        for rep in range(len(values) // len(scenarios)):
            rows.append(
                {
                    "run_id": f"{config}__{sc}__r{rep}",
                    "config": config,
                    "scenario": sc,
                    "replicate": rep,
                    "seed": 1,
                    "metric": metric,
                    "value": values[i],
                    "arm": arm,
                }
            )
            i += 1
    return rows


def _frame():
    rng = np.random.default_rng(0)
    rows = []
    rows += _rows("baseline", "static", "mttr_s", list(rng.normal(390, 20, 20)))
    rows += _rows("full", "live", "mttr_s", list(rng.normal(60, 10, 20)))
    rows += _rows("full", "mock", "mttr_s", list(rng.normal(0.1, 0.01, 20)))
    rows += _rows("rule_based", "static", "mttr_s", list(rng.normal(30, 1, 20)))
    costs = (("baseline", "static", 5.0), ("full", "live", 4.0), ("full", "mock", 3.0))
    for cfg, arm, val in costs:
        rows += _rows(cfg, arm, "cost_units", [val + 0.01 * k for k in range(20)])
    return pd.DataFrame(rows)


class TestLoad:
    def _write_arm(self, root, sub, config, mttr):
        d = root / sub
        d.mkdir(parents=True)
        lines = ["run_id,config,scenario,replicate,seed,metric,value"]
        lines += [f"{config}__s__r{i},{config},s,{i},1,mttr_s,{mttr + i}" for i in range(3)]
        (d / "raw.csv").write_text("\n".join(lines) + "\n")
        recs = [{"run_id": f"{config}__s__r{i}", "provenance": {"git_sha": "a"}} for i in range(3)]
        (d / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")

    def test_arms_are_tagged_and_kept_separate(self, tmp_path):
        self._write_arm(tmp_path, "paper-live", "full", 60)
        self._write_arm(tmp_path, "paper-mock", "full", 0)
        df = ps.load_campaign(tmp_path)
        assert set(df["arm"]) == {"live", "mock"}
        assert len(ps.load_manifests(tmp_path)) == 6

    def test_missing_everything_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ps.load_campaign(tmp_path)


class TestProvenanceGate:
    def _rec(self, arm, mode, **prov):
        base = {
            "git_sha": "a",
            "timings": {"loop_s": 300},
            "human_latency": {"median_s": 360},
            "provisioning": {"static_units": 8},
            "llm_budget": {"max_calls": 60},
            "git_dirty": False,
        }
        return {"arm": arm, "llm_mode": mode, "provenance": {**base, **prov}}

    def test_clean_dataset_has_no_problems(self):
        recs = [self._rec("live", "live"), self._rec("mock", "mock"), self._rec("static", "none")]
        assert ps.provenance_problems(recs) == []

    def test_detects_mixed_code_versions(self):
        recs = [self._rec("live", "live"), self._rec("live", "live", git_sha="b")]
        assert any("git_sha" in p for p in ps.provenance_problems(recs))

    def test_detects_mixed_human_models(self):
        recs = [self._rec("static", "none"), self._rec("static", "none", human_latency={"m": 1})]
        assert any("human_latency" in p for p in ps.provenance_problems(recs))

    def test_detects_a_mock_run_in_the_live_arm(self):
        problems = ps.provenance_problems([self._rec("live", "mock")])
        assert any("llm_mode" in p for p in problems)

    def test_detects_dirty_tree_and_missing_provenance(self):
        dirty = ps.provenance_problems([self._rec("live", "live", git_dirty=True)])
        assert any("dirty" in p for p in dirty)
        legacy = {"arm": "live", "llm_mode": "live"}
        assert any("no provenance" in p for p in ps.provenance_problems([legacy]))


class TestCompare:
    def test_compare_samples_reports_direction_and_intervals(self):
        r = ps.compare_samples([1.0, 2, 3, 4, 5, 6], [10.0, 11, 12, 13, 14, 15], n_resamples=200)
        assert r["median_diff"] < 0 and r["cliffs_delta"] == -1.0
        assert r["median_diff_ci"][1] < 0 and r["relative_change_pct"] < 0
        assert r["p_mannwhitney"] < 0.01 and r["n_matched"] == 0

    def test_zero_control_median_has_no_relative_change(self):
        r = ps.compare_samples([1.0, 2.0], [0.0, 0.0], n_resamples=50)
        assert r["relative_change_pct"] is None

    def test_compare_to_baseline_holm_family(self):
        rows = ps.compare_to_baseline(
            _frame(), ["mttr_s", "cost_units"], ["full", "rule_based", "baseline"], n_resamples=100
        )
        got = {(r["metric"], r["config"]) for r in rows}
        assert got >= {("mttr_s", "full"), ("mttr_s", "rule_based")}
        assert all(r["control"] == "baseline" and "p_holm" in r for r in rows)
        big = next(r for r in rows if r["metric"] == "mttr_s" and r["config"] == "full")
        assert big["significant"] and big["cliffs_delta"] == -1.0
        assert big["n_matched"] == 20  # live arm only: the mock twin must not be pooled in
        assert all(r["p_holm"] >= r["p_mannwhitney"] for r in rows)  # Holm never lowers a p

    def test_skips_configs_without_data(self):
        assert ps.compare_to_baseline(_frame(), ["mttr_s"], ["ghost"], n_resamples=50) == []

    def test_live_vs_mock_separates_arms(self):
        rows = ps.live_vs_mock(_frame(), ["mttr_s", "cost_units"], n_resamples=100)
        mttr = next(r for r in rows if r["metric"] == "mttr_s")
        assert mttr["median_treat"] > 30 and mttr["median_control"] < 1  # live >> mock
        assert mttr["significant"]

    def test_deterministic_under_seed(self):
        a = ps.compare_to_baseline(_frame(), ["mttr_s"], ["full"], seed=3, n_resamples=100)
        b = ps.compare_to_baseline(_frame(), ["mttr_s"], ["full"], seed=3, n_resamples=100)
        assert a == b


class TestTables:
    def test_per_scenario_medians_shape(self):
        t = ps.per_scenario_medians(_frame(), "mttr_s", ["baseline", "full", "rule_based"])
        assert set(t.columns) == set(SCENARIOS)
        assert list(t.index) == ["baseline", "full", "rule_based"]

    def test_llm_accounting_and_degraded_fraction(self):
        rows = []
        for metric, val in (("llm_calls", 30.0), ("llm_degraded", 10.0), ("api_tokens", 900.0)):
            rows += _rows("full", "live", metric, [val] * 4)
        t = ps.llm_accounting(pd.DataFrame(rows), ["full", "baseline"])
        assert t.loc["full", "degraded_fraction"] == pytest.approx(0.25)
        assert t.loc["full", "api_tokens"] == 900.0
        assert pd.isna(t.loc["baseline", "degraded_fraction"])
