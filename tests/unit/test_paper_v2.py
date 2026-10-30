"""Unit tests for the v2 analysis (preregistration-v2) on a synthetic paired campaign."""

import json

import numpy as np
import pandas as pd
import pytest

from acde.analysis import paper_artifacts as pa
from acde.analysis import paper_stats as ps
from acde.analysis import paper_v2 as v2

SCENARIOS = ("schema_drift", "upstream_delay")
PROV = {
    "git_sha": "abc",
    "code_tree": "tree1",
    "git_dirty": False,
    "profile": "paper_v2",
    "measurement_protocol": "v2",
    "seed_policy": "paired",
    "pool_baseline_slots": {"default_pool": 128},
    "timings": {"warmup_s": 120.0, "loop_s": 300.0, "settle_s": 5.0},
    "human_latency": {"median_s": 360.0, "sigma": 0.5},
    "provisioning": {"static_units": 8.0, "rightsized_units": 3.0, "horizon_s": 300.0},
    "llm_budget": {"max_calls_per_run": 60, "max_tokens_per_run": 150000},
}
BASE = {
    "mttr_injection_s": 380,
    "mttr_s": 380,
    "escalated_incidents": 1,
    "manual_interventions": 1,
    "cost_units": 150,
    "cost_compute_units": 5,
    "cost_storage_units": 1,
    "cost_provisioning_units": 144,
    "decision_correct": 0.0,
    "freshness_s": 100,
    "state_reset_ok": 1.0,
}
LLM = {
    "llm_calls": 30,
    "llm_cache_hits": 10,
    "llm_degraded": 1,
    "llm_invalid": 0,
    "api_tokens": 9000,
    "llm_latency_s": 3.0,
}


def _arm(root, sub, mode, specs, prov=PROV, reps=8):
    d = root / sub
    d.mkdir(parents=True)
    rng = np.random.default_rng(len(sub))
    rows, recs = ["run_id,config,scenario,replicate,seed,metric,value"], []
    for cfg, metrics in specs.items():
        for sc in SCENARIOS:
            for rep in range(reps):
                rid = f"{cfg}__{sc}__r{rep}"
                for metric, base in metrics.items():
                    noisy = metric not in ("state_reset_ok", "decision_correct")
                    value = base * (1 + rng.uniform(0, 0.2)) if noisy else base
                    rows.append(f"{rid},{cfg},{sc},{rep},1,{metric},{value}")
                recs.append({"run_id": rid, "llm_mode": mode, "provenance": prov})
    (d / "raw.csv").write_text("\n".join(rows) + "\n")
    (d / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return d


def _campaign(root, prov=PROV, bad_reset=False):
    statics = {
        "baseline": BASE,
        "rule_based": {**BASE, "mttr_injection_s": 30, "escalated_incidents": 0},
        "autoscale": {**BASE, "cost_units": 60},
    }
    if bad_reset:
        statics["autoscale"] = {**statics["autoscale"], "state_reset_ok": 0.0}
    _arm(root, "paper-v2-baselines", "none", statics, prov)
    full = {**BASE, **LLM, "mttr_injection_s": 360, "cost_units": 60}
    live = _arm(root, "paper-v2-live", "live", {"full": full, "hybrid": {**full, "mttr_s": 30}})
    _arm(root, "paper-v2-mock", "mock", {"full": {**full, "mttr_injection_s": 0.2}}, prov)
    actions = live / "actions"
    actions.mkdir()
    (actions / "full__schema_drift__r0.jsonl").write_text(
        json.dumps({"agent": "monitoring", "action_type": "raise_anomaly"})
        + "\n"
        + json.dumps(
            {
                "agent": "schema",
                "action_type": "block_ingestion",
                "policy_decision": "denied",
                "executed": False,
            }
        )
        + "\n"
    )


@pytest.fixture
def campaign(tmp_path):
    _campaign(tmp_path / "res")
    return tmp_path / "res"


class TestProtocolLoading:
    def test_v2_dirs_are_loaded_separately_from_v1(self, campaign):
        df = ps.load_campaign(campaign, "v2")
        assert set(df["arm"]) == {"live", "static", "mock"}
        with pytest.raises(FileNotFoundError):
            ps.load_campaign(campaign, "v1")

    def test_code_tree_lets_commits_differ(self, campaign):
        records = ps.load_manifests(campaign, "v2")
        records[0]["provenance"] = {**PROV, "git_sha": "later-docs-commit"}
        assert ps.provenance_problems(records) == []
        records[0]["provenance"] = {**PROV, "code_tree": "tree2"}
        assert any("code_tree" in p for p in ps.provenance_problems(records))

    def test_v2_fields_must_match(self, campaign):
        records = ps.load_manifests(campaign, "v2")
        records[0]["provenance"] = {**PROV, "seed_policy": "per_config"}
        assert any("seed_policy" in p for p in ps.provenance_problems(records))


class TestExclusions:
    def test_failed_reset_drops_the_whole_pair(self, tmp_path):
        _campaign(tmp_path / "res", bad_reset=True)
        df = ps.load_campaign(tmp_path / "res", "v2")
        pairs = ps.excluded_pairs(df)
        assert len(pairs) == 16  # every (scenario, replicate) had a failed autoscale reset
        assert ps.apply_exclusions(df, pairs).empty

    def test_degraded_runs_only_in_the_sensitivity_analysis(self, campaign):
        df = ps.load_campaign(campaign, "v2")
        assert ps.excluded_pairs(df) == set()
        df.loc[(df["metric"] == "llm_degraded") & (df["replicate"] == 0), "value"] = 50
        assert ps.excluded_pairs(df) == set()
        assert ps.excluded_pairs(df, drop_degraded=True) == {
            ("schema_drift", 0),
            ("upstream_delay", 0),
        }

    def test_no_exclusions_returns_the_frame(self, campaign):
        df = ps.load_campaign(campaign, "v2")
        assert ps.apply_exclusions(df, set()) is df


class TestPairedComparison:
    def test_paired_uses_signed_rank_as_primary(self, campaign):
        df = ps.load_campaign(campaign, "v2")
        rows = ps.compare_to_baseline(df, ("cost_units",), ["full"], paired=True)
        assert rows[0]["test"] == "wilcoxon_signed_rank"
        assert rows[0]["p_primary"] == rows[0]["p_wilcoxon_matched"]
        assert rows[0]["n_matched"] == 16


class TestRobustnessAndVerdicts:
    def _rows(self, campaign):
        prim = ps.primary(ps.load_campaign(campaign, "v2"))
        rows = ps.compare_to_baseline(
            prim, v2.V2_PRIMARY, ["full", "rule_based"], paired=True, n_resamples=200
        )
        return {
            (r["metric"], r["config"]): r for r in v2.add_robustness(prim, rows, n_permutations=199)
        }

    def test_large_effect_is_different(self, campaign):
        rows = self._rows(campaign)
        assert v2.verdict(rows[("mttr_injection_s", "rule_based")]) == "different"

    def test_null_effect_is_equivalent_within_the_margin(self, campaign):
        # full's MTTR (360 s) is within 30 s of baseline's (380 s); decision is 0 vs 0.
        rows = self._rows(campaign)
        assert rows[("decision_correct", "rule_based")]["equivalent"] is True
        assert v2.verdict(rows[("decision_correct", "rule_based")]) == "equivalent"

    def test_cost_margin_is_relative_to_the_baseline(self):
        assert v2.margin_for("cost_units", [100.0, 200.0]) == pytest.approx(15.0)
        assert v2.margin_for("freshness_s", [1.0]) is None

    def test_verdicts(self):
        assert v2.verdict({"significant": True, "p_stratified": 0.2}) == "scenario-dependent"
        assert v2.verdict({"significant": False, "equivalent": None}) == "inconclusive"


class TestDerivedTables:
    def test_cost_split_terms(self, campaign):
        prim = ps.primary(ps.load_campaign(campaign, "v2"))
        table = v2.cost_split(prim, ["baseline", "nope"])
        assert list(table.columns) == list(v2.COST_TERMS)
        assert table.loc["nope"].isna().all()

    def test_taxonomy_counts_runs_and_skips_monitoring_acks(self, campaign):
        df = ps.load_campaign(campaign, "v2")
        tax = v2.decision_taxonomy(campaign, df)
        assert tax.to_dict("records") == [
            {
                "scenario": "schema_drift",
                "agent": "schema",
                "action_type": "block_ingestion",
                "policy_decision": "denied",
                "executed": False,
                "runs": 1,
            }
        ]

    def test_empty_taxonomy(self, campaign):
        df = ps.load_campaign(campaign, "v2")
        assert v2.decision_taxonomy(campaign, df[df["metric"] == "nothing"]).empty

    def test_human_draw_check_on_v1_style_data(self):
        rows = []
        for i in range(20):
            for metric, value in (("mttr_s", 200.0 + i), ("manual_interventions", 6.0)):
                rows.append(("full", f"full__x__r{i}", metric, value))
        rows += [
            ("full", "full__x__r99", "mttr_s", 0.5),
            ("full", "full__x__r99", "manual_interventions", 0.0),
        ]
        prim = pd.DataFrame(rows, columns=["config", "run_id", "metric", "value"])
        table = v2.human_draw_check(prim, ["full", "absent"], 360.0, 0.5)
        r = table.loc["full"]
        assert (r["n"], r["n_human"], r["median_escalations"]) == (21, 20, 6)
        assert 170 < r["predicted_min_draw"] < 220  # the fastest of six draws
        assert "absent" not in table.index

    def test_expected_min_draw_falls_with_k(self):
        one = v2.expected_min_draw_median(1, 360.0, 0.5)
        six = v2.expected_min_draw_median(6, 360.0, 0.5)
        assert 340 < one < 380 and six < 0.6 * one


class TestBuildV2:
    def test_builds_every_v2_artifact(self, campaign, tmp_path):
        out = tmp_path / "gen"
        hashes = pa.build_v2(campaign, out, n_resamples=100, n_permutations=99)
        for name in (
            "tab_v2_main.tex",
            "tab_v2_effects.tex",
            "tab_v2_effects_sensitivity.tex",
            "tab_v2_rules.tex",
            "tab_v2_live_mock.tex",
            "tab_v2_cost_split.tex",
            "tab_v2_taxonomy.tex",
            "numbers_v2.tex",
            "fig_v2_mttr.pdf",
            "fig_v2_effects.pdf",
        ):
            assert name in hashes
        assert "tab_v1_v2.tex" not in hashes  # no v1 data in this root
        numbers = (out / "numbers_v2.tex").read_text()
        assert "\\NVTwoExcludedPairs}{0}" in numbers
        assert "NVTwoAMttrInjectionSRuleBasedVerdict" in numbers

    def test_side_by_side_when_v1_is_present(self, campaign, tmp_path):
        from tests.unit.test_paper_artifacts import _campaign as v1_campaign

        v1_campaign(campaign)
        hashes = pa.build_v2(campaign, tmp_path / "gen", n_resamples=50, n_permutations=49)
        assert "tab_v1_v2.tex" in hashes

    def test_refuses_mixed_code(self, tmp_path):
        _campaign(tmp_path / "res")
        live = tmp_path / "res" / "paper-v2-live" / "manifest.jsonl"
        recs = [json.loads(ln) for ln in live.read_text().splitlines()]
        recs[0]["provenance"] = {**PROV, "code_tree": "other"}
        live.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        with pytest.raises(pa.ProvenanceError):
            pa.build_v2(tmp_path / "res", tmp_path / "gen")


def test_prob_fastest_below_grows_with_k():
    one = v2.prob_fastest_below(60.0, 1, 360.0, 0.5)
    six = v2.prob_fastest_below(60.0, 6, 360.0, 0.5)
    assert 1e-4 < one < six < 2e-3
