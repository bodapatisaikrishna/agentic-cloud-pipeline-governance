"""Unit tests for paper-artifact generation on a synthetic three-arm campaign."""

import json

import numpy as np
import pytest

from acde.analysis import paper_artifacts as pa

SCENARIOS = ("schema_drift", "upstream_delay")
PROV = {
    "git_sha": "abc",
    "git_dirty": False,
    "profile": "paper",
    "timings": {"warmup_s": 120.0, "loop_s": 300.0, "settle_s": 5.0},
    "human_latency": {"median_s": 360.0, "sigma": 0.5},
    "provisioning": {"static_units": 8.0, "rightsized_units": 3.0, "horizon_s": 300.0},
    "llm_budget": {"max_calls_per_run": 60, "max_tokens_per_run": 150000},
}


def _arm(root, sub, mode, specs, prov=PROV):
    """specs: {config: {metric: base_value}}; 6 replicates x 2 scenarios per config."""
    d = root / sub
    d.mkdir(parents=True)
    rng = np.random.default_rng(len(sub))
    rows, recs = ["run_id,config,scenario,replicate,seed,metric,value"], []
    for cfg, metrics in specs.items():
        for sc in SCENARIOS:
            for rep in range(6):
                rid = f"{cfg}__{sc}__r{rep}"
                for metric, base in metrics.items():
                    value = base * (1 + rng.uniform(0, 0.2))
                    rows.append(f"{rid},{cfg},{sc},{rep},1,{metric},{value}")
                recs.append({"run_id": rid, "llm_mode": mode, "provenance": prov})
    (d / "raw.csv").write_text("\n".join(rows) + "\n")
    (d / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def _campaign(root, prov=PROV):
    base = {
        "mttr_s": 390,
        "cost_units": 126,
        "manual_interventions": 1,
        "decision_correct": 0.0,
        "freshness_s": 100,
    }
    live = {
        "mttr_s": 60,
        "cost_units": 50,
        "manual_interventions": 1.5,
        "decision_correct": 1.0,
        "freshness_s": 40,
        "llm_calls": 30,
        "llm_cache_hits": 12,
        "llm_degraded": 2,
        "llm_invalid": 1,
        "api_tokens": 9000,
        "llm_latency_s": 4.0,
    }
    statics = {
        "baseline": base,
        "rule_based": {**base, "mttr_s": 30},
        "autoscale": {**base, "cost_units": 48},
    }
    _arm(root, "paper-baselines", "none", statics, prov)
    _arm(root, "paper-live", "live", {"full": live, "recovery_only": {**live, "mttr_s": 200}}, prov)
    _arm(root, "paper-mock", "mock", {"full": {**live, "mttr_s": 0.1}}, prov)


@pytest.fixture
def campaign(tmp_path):
    _campaign(tmp_path / "res")
    return tmp_path / "res"


class TestFormatting:
    def test_tex_escapes_specials(self):
        assert pa.tex("a_b & 5%") == r"a\_b \& 5\%"

    @pytest.mark.parametrize(
        ("x", "out"),
        [
            (0.0, "0"),
            (None, "--"),
            (390.2, "390"),
            (12.34, "12.3"),
            (1.234, "1.23"),
            (0.01234, "0.0123"),
        ],
    )
    def test_fnum(self, x, out):
        assert pa.fnum(x) == out

    def test_fnum_thousands_and_nan(self):
        assert pa.fnum(12345.0) == "12{,}345"
        assert pa.fnum(float("nan")) == "--"

    def test_fp(self):
        assert pa.fp(0.0004) == "<0.001" and pa.fp(0.0456) == "0.046" and pa.fp(None) == "--"

    def test_macro_names_are_letters_only(self):
        name = pa.macro_name("mttr", "full", "median", 2)
        assert name == "NMttrFullMedianTwo"
        assert pa.macro_name("pHolm", "mttr_s", "recovery_only") == "NPHolmMttrSRecoveryOnly"
        assert pa.macro_name("x")[1:].isalpha()

    def test_numbers_render(self):
        n = pa.Numbers()
        n.add("12.3", "a", "b")
        assert r"\newcommand{\NAB}{12.3}" in n.render()


class TestBuild:
    def test_builds_every_artifact(self, campaign, tmp_path):
        out = tmp_path / "gen"
        hashes = pa.build(campaign, out, n_resamples=100)
        expected = {
            "tab_main.tex",
            "tab_effects.tex",
            "tab_live_mock.tex",
            "tab_llm.tex",
            "tab_scenarios.tex",
            "tab_sensitivity.tex",
            "numbers.tex",
            "fig_mttr.pdf",
            "fig_effects.pdf",
            "fig_human_sensitivity.pdf",
            "fig_cost.pdf",
            "fig_scenarios.pdf",
        }
        assert expected <= set(hashes)
        for f in expected:
            assert (out / f).stat().st_size > 0
        assert (out / "fig_mttr.pdf").read_bytes().startswith(b"%PDF")
        assert (out / "SHA256SUMS").read_text().count("\n") == len(hashes)

    def test_deterministic_byte_for_byte(self, campaign, tmp_path):
        a = pa.build(campaign, tmp_path / "g1", n_resamples=100)
        b = pa.build(campaign, tmp_path / "g2", n_resamples=100)
        assert a == b

    def test_numbers_contain_headline_statistics(self, campaign, tmp_path):
        pa.build(campaign, tmp_path / "gen", n_resamples=100)
        text = (tmp_path / "gen" / "numbers.tex").read_text()
        assert r"\newcommand{\NMttrBaselineMedian}" in text
        assert r"\newcommand{\NDeltaMttrSFull}" in text
        assert r"\newcommand{\NLiveVsMockMttrSLive}" in text
        assert r"\newcommand{\NProvenanceProblems}{0}" in text

    def test_tables_are_booktabs_and_escaped(self, campaign, tmp_path):
        pa.build(campaign, tmp_path / "gen", n_resamples=100)
        main = (tmp_path / "gen" / "tab_main.tex").read_text()
        assert main.startswith("\\begin{tabular}") and "\\toprule" in main
        assert "rule\\_based" in main and "rule_based" not in main.replace("rule\\_based", "")

    def test_refuses_mixed_provenance(self, tmp_path):
        root = tmp_path / "res"
        _campaign(root)
        # corrupt one arm to a different code version
        p = root / "paper-live" / "manifest.jsonl"
        p.write_text(p.read_text().replace('"abc"', '"zzz"', 3))
        with pytest.raises(pa.ProvenanceError, match="git_sha"):
            pa.build(root, tmp_path / "gen", n_resamples=50)

    def test_unclean_allowed_when_asked(self, tmp_path):
        root = tmp_path / "res"
        _campaign(root, prov={**PROV, "git_dirty": True})
        pa.build(root, tmp_path / "gen", strict=False, n_resamples=50)
        assert r"\NProvenanceProblems}{1}" in (tmp_path / "gen" / "numbers.tex").read_text()

    def test_adversarial_tables_and_numbers(self, campaign, tmp_path):
        from acde.eval import adversarial_corpus as ac

        result = ac.run_corpus(ac.build_corpus(), ac.expected_verdict)
        adv = tmp_path / "adv.json"
        adv.write_text(json.dumps(result))
        pa.build(campaign, tmp_path / "gen", adv, adv, n_resamples=50)
        table = (tmp_path / "gen" / "tab_adversarial.tex").read_text()
        assert "boundary\\_grid" in table and "overall" in table
        nums = (tmp_path / "gen" / "numbers.tex").read_text()
        assert r"\NAdversarialFailOpen}{0}" in nums and "NAdversarialBeforeCases" in nums

    def test_no_mock_arm_is_fine(self, campaign, tmp_path):
        import shutil

        shutil.rmtree(campaign / "paper-mock")
        pa.build(campaign, tmp_path / "gen", n_resamples=50)
        assert (tmp_path / "gen" / "tab_live_mock.tex").exists()
