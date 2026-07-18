"""Load results/raw.csv and compute the §6 statistics.

Produces, per metric: per-config median / IQR / bootstrap CI (across scenarios x replicates), a
paired baseline-vs-full Wilcoxon test + Cliff's delta (paired by scenario+replicate), a
Holm-Bonferroni correction across metrics, and an ablation table (config x metric, % vs baseline).
Written to ``results/analysis.json`` and returned for the figures/report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acde.analysis import stats
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("analysis.analyze")

METRICS = [
    "mttr_s",
    "cost_units",
    "manual_interventions",
    "llm_tokens",
    "freshness_s",
    "decision_correct",
]


def load_raw(results_dir: Path) -> pd.DataFrame:
    """Load the long-format raw.csv into a typed DataFrame."""
    df = pd.read_csv(results_dir / "raw.csv")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["replicate"] = pd.to_numeric(df["replicate"], errors="coerce").astype("Int64")
    return df


def _metric_values(df: pd.DataFrame, config: str, metric: str) -> list[float]:
    sel = df[(df["config"] == config) & (df["metric"] == metric)]["value"].dropna()
    return [float(v) for v in sel]


def _paired(df: pd.DataFrame, metric: str, a: str, b: str) -> tuple[list[float], list[float]]:
    """Return value vectors for configs ``a`` and ``b`` aligned on (scenario, replicate)."""
    wide = (
        df[df["metric"] == metric]
        .pivot_table(index=["scenario", "replicate"], columns="config", values="value")
        .dropna(subset=[a, b] if a in df["config"].values and b in df["config"].values else [])
    )
    if a not in wide.columns or b not in wide.columns:
        return ([], [])
    pairs = wide[[a, b]].dropna()
    return (list(pairs[a]), list(pairs[b]))


def analyze(results_dir: Path | None = None) -> dict[str, Any]:
    """Compute the full statistical summary from raw.csv."""
    settings = get_settings()
    results_dir = results_dir or Path(settings.results_dir)
    df = load_raw(results_dir)
    configs = sorted(df["config"].unique())
    present_metrics = [m for m in METRICS if m in set(df["metric"])]

    summary: dict[str, Any] = {"configs": configs, "metrics": present_metrics, "by_metric": {}}
    raw_pvalues: list[float] = []
    pval_index: list[str] = []

    for metric in present_metrics:
        per_config = {}
        for config in configs:
            vals = _metric_values(df, config, metric)
            lo, hi = stats.bootstrap_ci(
                vals, n_resamples=settings.bootstrap_resamples, seed=settings.default_seed
            )
            per_config[config] = {
                "median": stats.median(vals),
                "iqr": stats.iqr(vals),
                "ci_lo": lo,
                "ci_hi": hi,
                "n": len(vals),
            }
        base, full = _paired(df, metric, "baseline", "full")
        stat, pval = stats.paired_wilcoxon(base, full)
        delta = stats.cliffs_delta(base, full)
        summary["by_metric"][metric] = {
            "per_config": per_config,
            "wilcoxon_stat": stat,
            "p_value": pval,
            "cliffs_delta": delta,
            "n_pairs": len(base),
        }
        raw_pvalues.append(pval)
        pval_index.append(metric)

    for metric, (adj, reject) in zip(pval_index, stats.holm_bonferroni(raw_pvalues), strict=True):
        summary["by_metric"][metric]["p_holm"] = adj
        summary["by_metric"][metric]["significant"] = reject

    summary["ablation"] = _ablation_table(summary, configs, present_metrics)
    _write_json(results_dir / "analysis.json", summary)
    log.info("analysis_complete", extra={"configs": len(configs), "metrics": len(present_metrics)})
    return summary


def _ablation_table(
    summary: dict[str, Any], configs: list[str], metrics: list[str]
) -> dict[str, dict[str, float]]:
    """Percent change of each config's median vs baseline, per metric (negative = improvement)."""
    table: dict[str, dict[str, float]] = {}
    for config in configs:
        if config == "baseline":
            continue
        row: dict[str, float] = {}
        for metric in metrics:
            base = summary["by_metric"][metric]["per_config"].get("baseline", {}).get("median", 0.0)
            cur = summary["by_metric"][metric]["per_config"][config]["median"]
            row[metric] = ((cur - base) / base * 100.0) if base else 0.0
        table[config] = row
    return table


def _write_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, default=str))


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE analysis")
    parser.add_argument("--results-dir", default=None)
    args = parser.parse_args()
    analyze(Path(args.results_dir) if args.results_dir else None)


if __name__ == "__main__":  # pragma: no cover
    main()
