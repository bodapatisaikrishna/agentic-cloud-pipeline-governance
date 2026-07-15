"""Unit tests for analyze + figures + report on a synthetic raw.csv."""

import csv

import pytest

from acde.analysis import figures, report
from acde.analysis.analyze import analyze


@pytest.fixture
def synthetic_results(tmp_path):
    rows = [["run_id", "config", "scenario", "replicate", "seed", "metric", "value"]]
    for scenario in ("upstream_delay", "schema_drift"):
        for r in range(4):
            for cfg, mttr, cost, inter in (("baseline", 350 + r, 3.0, 1), ("full", 0.5, 4.5, 0)):
                rid = f"{cfg}__{scenario}__r{r}"
                for metric, val in (
                    ("mttr_s", mttr),
                    ("cost_units", cost),
                    ("manual_interventions", inter),
                    ("freshness_s", 30 + r),
                ):
                    rows.append([rid, cfg, scenario, r, 42, metric, val])
    with (tmp_path / "raw.csv").open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return tmp_path


class TestAnalyze:
    def test_per_config_medians(self, synthetic_results):
        s = analyze(synthetic_results)
        mttr = s["by_metric"]["mttr_s"]["per_config"]
        assert mttr["full"]["median"] == 0.5
        assert mttr["baseline"]["median"] > 350

    def test_mttr_significant_and_positive_delta(self, synthetic_results):
        s = analyze(synthetic_results)
        m = s["by_metric"]["mttr_s"]
        assert m["p_value"] < 0.05
        assert m["cliffs_delta"] == 1.0  # baseline always > full
        assert m["significant"] is True  # survives Holm-Bonferroni

    def test_ablation_shows_full_improvement(self, synthetic_results):
        s = analyze(synthetic_results)
        # full's MTTR is ~100% below baseline (negative % change)
        assert s["ablation"]["full"]["mttr_s"] < -90

    def test_writes_analysis_json(self, synthetic_results):
        analyze(synthetic_results)
        assert (synthetic_results / "analysis.json").exists()


class TestReportAndFigures:
    def test_build_report_produces_md_and_figures(self, synthetic_results):
        out = report.build_report(synthetic_results)
        assert out.exists()
        text = out.read_text()
        assert "Comparison to the paper's claims" in text
        assert "Deviations from the paper" in text  # DEVIATIONS appended
        assert "Cliff's delta" in text
        # figures rendered
        figs = synthetic_results / "figures"
        for name in ("mttr_bar.png", "cost_bar.png", "ablation_heatmap.png"):
            assert (figs / name).exists() and (figs / name).stat().st_size > 0

    def test_figures_build_all_returns_paths(self, synthetic_results):
        s = analyze(synthetic_results)
        written = figures.build_all(s, synthetic_results / "figures")
        assert len(written) >= 4
        assert all(p.exists() for p in written)
