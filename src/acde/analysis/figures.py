"""Publication figures (headless matplotlib, Agg) → results/figures/*.png (§6).

Fig 2/3 equivalents (MTTR + cost bars with bootstrap-CI error bars), an interventions bar, a CDF,
and the ablation heatmap (config x metric % change vs baseline). Pure over the analysis summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless; no display
import matplotlib.pyplot as plt
import numpy as np

from acde.logging import get_logger

log = get_logger("analysis.figures")


def _bar_with_ci(summary: dict[str, Any], metric: str, title: str, ylabel: str, out: Path) -> None:
    configs = summary["configs"]
    per = summary["by_metric"][metric]["per_config"]
    medians = [per[c]["median"] for c in configs]
    lo = [max(0.0, per[c]["median"] - per[c]["ci_lo"]) for c in configs]
    hi = [max(0.0, per[c]["ci_hi"] - per[c]["median"]) for c in configs]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(configs, medians, yerr=[lo, hi], capsize=4, color="#4c72b0")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels(configs, rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def _heatmap(summary: dict[str, Any], out: Path) -> None:
    ablation = summary["ablation"]
    configs = list(ablation)
    metrics = summary["metrics"]
    if not configs:
        return
    grid = np.array([[ablation[c].get(m, 0.0) for m in metrics] for c in configs])
    fig, ax = plt.subplots(figsize=(1.6 * len(metrics) + 2, 0.6 * len(configs) + 2))
    im = ax.imshow(grid, cmap="RdYlGn_r", aspect="auto", vmin=-100, vmax=100)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics, rotation=30, ha="right")
    ax.set_yticks(range(len(configs)))
    ax.set_yticklabels(configs)
    for i in range(len(configs)):
        for j in range(len(metrics)):
            ax.text(j, i, f"{grid[i, j]:.0f}%", ha="center", va="center", fontsize=8)
    ax.set_title("Ablation: % change of median vs baseline (green = improvement)")
    fig.colorbar(im, ax=ax, label="% vs baseline")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def _cdf(summary: dict[str, Any], metric: str, out: Path, raw_by_config=None) -> None:
    """CDF of a metric's medians across configs (or raw values if provided)."""
    fig, ax = plt.subplots(figsize=(7, 4))
    for config in summary["configs"]:
        vals = (raw_by_config or {}).get(config)
        if not vals:
            vals = [summary["by_metric"][metric]["per_config"][config]["median"]]
        xs = np.sort(np.asarray(vals, dtype=float))
        ys = np.arange(1, len(xs) + 1) / len(xs)
        ax.step(xs, ys, where="post", label=config)
    ax.set_title(f"{metric} CDF by config")
    ax.set_xlabel(metric)
    ax.set_ylabel("cumulative fraction")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def build_all(summary: dict[str, Any], figures_dir: Path) -> list[Path]:
    """Render every figure the report embeds; returns the written paths."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _emit(name: str, fn) -> None:
        path = figures_dir / name
        fn(path)
        written.append(path)

    metrics = summary["metrics"]
    if "mttr_s" in metrics:
        _emit(
            "mttr_bar.png",
            lambda p: _bar_with_ci(summary, "mttr_s", "MTTR by config", "MTTR (s)", p),
        )
        _emit("mttr_cdf.png", lambda p: _cdf(summary, "mttr_s", p))
    if "cost_units" in metrics:
        _emit(
            "cost_bar.png",
            lambda p: _bar_with_ci(
                summary, "cost_units", "Operational cost by config", "cost units", p
            ),
        )
    if "manual_interventions" in metrics:
        _emit(
            "interventions_bar.png",
            lambda p: _bar_with_ci(
                summary, "manual_interventions", "Manual interventions by config", "count", p
            ),
        )
    _emit("ablation_heatmap.png", lambda p: _heatmap(summary, p))
    log.info("figures_written", extra={"count": len(written)})
    return written
