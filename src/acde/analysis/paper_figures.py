"""Vector, colour-blind-safe manuscript figures (D-104). Pure over the campaign frame + sensitivity.

Every figure is a PDF with fixed metadata and embedded fonts, so regenerating from the same data is
byte-identical (the reproduction check hashes them). Palette: Okabe-Ito, distinguishable under the
common colour-vision deficiencies and in greyscale print.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from acde.analysis import sensitivity as sens

# Okabe-Ito
BLUE, ORANGE, GREEN, VERMILION, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#666666"
ARM_COLOUR = {"static": GREY, "live": BLUE, "mock": ORANGE}
_META = {"Creator": None, "Producer": None, "CreationDate": None}

plt.rcParams.update(
    {
        "pdf.fonttype": 42,  # embed TrueType, not Type 3
        "font.family": "serif",
        "font.size": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 100,
    }
)


def _save(fig: Any, out: Path) -> None:
    fig.tight_layout()
    fig.savefig(out, format="pdf", metadata=_META)
    plt.close(fig)


def _label(config: str) -> str:
    return config.replace("_", "\n", 1) if len(config) > 11 else config


def mttr_distribution(df: pd.DataFrame, configs: Sequence[str], out: Path) -> None:
    """Per-run MTTR by config on a log axis; live vs mock ``full`` shown side by side."""
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    rng = np.random.default_rng(0)  # jitter only; fixed so the PDF is reproducible
    slots: list[tuple[str, str, str]] = []
    for c in configs:
        arm = "static" if (df[(df["config"] == c) & (df["arm"] == "static")].shape[0]) else "live"
        slots.append((c, arm, c))
        if c == "full" and (df["arm"] == "mock").any():
            slots.append(("full", "mock", "full\n(mock)"))
    for i, (cfg, arm, _) in enumerate(slots):
        v = df[(df["config"] == cfg) & (df["arm"] == arm) & (df["metric"] == "mttr_s")]["value"]
        v = v.dropna().clip(lower=0.01)
        ax.scatter(
            i + rng.uniform(-0.18, 0.18, len(v)),
            v,
            s=6,
            alpha=0.5,
            color=ARM_COLOUR[arm],
            linewidths=0,
        )
        if len(v):
            ax.hlines(v.median(), i - 0.3, i + 0.3, color="black", linewidth=1.2)
    ax.set_yscale("log")
    ax.set_xticks(range(len(slots)))
    ax.set_xticklabels([_label(s[2]) for s in slots], fontsize=6.5)
    ax.set_ylabel("MTTR (s, log scale)")
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=col, label=name)
        for name, col in (("no LLM", GREY), ("live LLM", BLUE), ("mock LLM", ORANGE))
    ]
    ax.legend(handles=handles, frameon=False, fontsize=6.5, loc="upper right")
    _save(fig, out)


def effect_forest(rows: Sequence[dict[str, Any]], metrics: Sequence[str], out: Path) -> None:
    """Cliff's delta with bootstrap 95% CI per config, one panel per metric (vs baseline)."""
    fig, axes = plt.subplots(1, len(metrics), figsize=(6.4, 2.8), sharey=True, squeeze=False)
    for ax, metric in zip(axes[0], metrics, strict=True):
        sel = [r for r in rows if r["metric"] == metric]
        for y, r in enumerate(sel):
            lo, hi = r["cliffs_delta_ci"]
            colour = BLUE if r.get("significant") else GREY
            ax.hlines(y, lo, hi, color=colour, linewidth=1.5)
            ax.plot(r["cliffs_delta"], y, "o", color=colour, markersize=3.5)
        ax.axvline(0, color="black", linewidth=0.6)
        ax.set_xlim(-1.05, 1.05)
        ax.set_yticks(range(len(sel)))
        ax.set_yticklabels([r["config"] for r in sel], fontsize=6.5)
        ax.set_title(metric.replace("_", " "), fontsize=7.5)
        ax.set_xlabel("Cliff's $\\delta$ vs baseline")
    _save(fig, out)


def human_sensitivity(
    mttrs_by_config: Mapping[str, Sequence[float]], out: Path, sigma: float = 0.5
) -> None:
    """P(automation faster than a human) as the assumed human median latency varies."""
    fig, ax = plt.subplots(figsize=(3.4, 2.8))
    medians = np.geomspace(20, 3600, 60)
    palette = [BLUE, ORANGE, GREEN, VERMILION, GREY, "#CC79A7", "#56B4E9"]
    for (cfg, mttrs), colour in zip(mttrs_by_config.items(), palette, strict=False):
        curve = [sens.win_probability(mttrs, float(m), sigma) for m in medians]
        ax.plot(medians, curve, label=cfg, color=colour, linewidth=1.1)
    ax.axvline(360, color="black", linestyle=":", linewidth=0.8)
    ax.set_xscale("log")
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("assumed human median latency (s)")
    ax.set_ylabel("P(automation faster)")
    ax.legend(frameon=False, fontsize=5.5, loc="lower right")
    _save(fig, out)


def cost_sensitivity(sweep: Sequence[dict[str, float]], breakeven: float | None, out: Path) -> None:
    """Cost reduction of ``full`` vs baseline as the static over-provisioning assumption varies."""
    fig, ax = plt.subplots(figsize=(3.4, 2.8))
    for r_units, colour in zip(
        sorted({s["rightsized_units"] for s in sweep}),
        [BLUE, ORANGE, GREEN, VERMILION, GREY],
        strict=False,
    ):
        pts = sorted(
            (s["static_units"], s["cost_reduction_pct"])
            for s in sweep
            if s["rightsized_units"] == r_units
        )
        ax.plot(
            [p[0] for p in pts],
            [p[1] for p in pts],
            marker="o",
            markersize=3,
            color=colour,
            label=f"right-sized = {r_units:g}",
            linewidth=1.1,
        )
    ax.axhline(0, color="black", linewidth=0.6)
    if breakeven is not None:
        ax.axvline(breakeven, color=VERMILION, linestyle="--", linewidth=0.8)
    ax.set_xlabel("static provisioned units (baseline)")
    ax.set_ylabel("cost reduction of full (%)")
    ax.legend(frameon=False, fontsize=6)
    _save(fig, out)


def scenario_heatmap(table: pd.DataFrame, out: Path) -> None:
    """Median MTTR per (config, scenario), log-coloured: where an aggregate hides a scenario."""
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    data = np.log10(table.clip(lower=0.01).to_numpy(dtype=float))
    im = ax.imshow(data, cmap="viridis", aspect="auto")
    ax.set_xticks(range(table.shape[1]))
    ax.set_xticklabels([str(c).replace("_", "\n") for c in table.columns], fontsize=6.5)
    ax.set_yticks(range(table.shape[0]))
    ax.set_yticklabels(list(table.index), fontsize=6.5)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            ax.text(
                j, i, f"{table.iloc[i, j]:.0f}", ha="center", va="center", fontsize=6, color="white"
            )
    fig.colorbar(im, ax=ax, label="log$_{10}$ median MTTR (s)")
    _save(fig, out)
