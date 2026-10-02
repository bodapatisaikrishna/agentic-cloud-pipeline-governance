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
        ax.set_xlim(-1.12, 1.12)
        ax.set_yticks(range(len(sel)))
        ax.set_yticklabels([r["config"] for r in sel], fontsize=6.5)
        ax.set_title(_METRIC_LABEL.get(metric, metric.replace("_", " ")), fontsize=7.5)
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
    ax.legend(frameon=False, fontsize=6.5, loc="lower right")
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
        ax.axvline(
            breakeven,
            color="black",
            linestyle=":",
            linewidth=0.9,
            label=f"break-even ({breakeven:.2g})",
        )
    ax.set_xlabel("static provisioned units (baseline)")
    ax.set_ylabel("cost reduction of full (%)")
    ax.legend(frameon=False, fontsize=6.5)
    _save(fig, out)


def live_mock_comparison(rows: Sequence[dict[str, Any]], out: Path) -> None:
    """Live vs. mock ``full``, one small panel per metric: a dumbbell from mock to live, annotated.

    Linear (not log) axes per panel deliberately -- several metrics here are exactly 0 for one arm
    (manual interventions, decision correct), which a shared log axis cannot represent.
    """
    fig, axes = plt.subplots(1, len(rows), figsize=(6.4, 2.0), squeeze=False)
    for ax, r in zip(axes[0], rows, strict=True):
        live, mock = r["median_treat"], r["median_control"]
        ax.plot([0, 1], [mock, live], color=GREY, linewidth=1.0, zorder=1)
        ax.scatter([0], [mock], color=ORANGE, s=26, zorder=2, label="mock")
        ax.scatter([1], [live], color=BLUE, s=26, zorder=2, label="live")
        for x, v in ((0, mock), (1, live)):
            ax.annotate(
                f"{v:.3g}",
                (x, v),
                textcoords="offset points",
                xytext=(0, 5),
                ha="center",
                fontsize=6,
            )
        pad = max(abs(live), abs(mock), 1e-6) * 0.35
        ax.set_ylim(min(live, mock) - pad, max(live, mock) + pad)
        ax.set_xlim(-0.4, 1.4)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["mock", "live"], fontsize=6.5)
        ax.set_title(_METRIC_LABEL.get(r["metric"], r["metric"]), fontsize=6.8)
        ax.tick_params(axis="y", labelsize=6)
    _save(fig, out)


_METRIC_LABEL = {
    "mttr_s": "MTTR (s)",
    "cost_units": "cost (units)",
    "manual_interventions": "manual interv.",
    "decision_correct": "decision correct",
    "freshness_s": "freshness (s)",
}


def architecture_diagram(out: Path) -> None:
    """Static box-and-arrow summary of the three planes (\\S3): data -> agentic control -> policy ->
    execution/audit, with the contract boundary and the simulated-human escalation path made
    explicit.
    """
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    def box(xy, w, h, text, colour, fontsize=6.3):
        x, y = xy
        rect = plt.Rectangle(
            (x, y), w, h, facecolor=colour, edgecolor="black", linewidth=0.8, alpha=0.18, zorder=1
        )
        ax.add_patch(rect)
        rect_edge = plt.Rectangle(
            (x, y), w, h, facecolor="none", edgecolor=colour, linewidth=1.3, zorder=2
        )
        ax.add_patch(rect_edge)
        ax.text(
            x + w / 2,
            y + h / 2,
            text,
            ha="center",
            va="center",
            fontsize=fontsize,
            zorder=3,
            wrap=True,
        )

    def arrow(p0, p1, label="", colour="black", style="-|>", ls="-"):
        ax.annotate(
            "",
            xy=p1,
            xytext=p0,
            arrowprops={
                "arrowstyle": style,
                "color": colour,
                "lw": 1.1,
                "linestyle": ls,
                "shrinkA": 2,
                "shrinkB": 2,
            },
            zorder=2,
        )
        if label:
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            ax.text(mx, my + 0.16, label, ha="center", va="bottom", fontsize=5.6, zorder=3)

    # Data plane
    data_text = "Data plane\nbatch (Airflow) +\nstreaming (Redpanda) +\ntelemetry (Postgres)"
    box((0.2, 3.6), 1.9, 1.7, data_text, BLUE)
    # Agentic control plane
    control_text = (
        "Agentic control\nmonitoring, optimization,\nschema, recovery\n(observe-reason-propose-act)"
    )
    box((2.6, 3.6), 2.1, 1.7, control_text, ORANGE)
    box((2.75, 1.9), 1.8, 1.0, "LLM\nlive or mock,\ntemperature = 0", ORANGE, fontsize=6.0)
    # Contract
    box((5.15, 3.85), 1.35, 1.2, "Contract\nProposedAction\n(validated)", GREY, fontsize=6.0)
    # Policy plane
    policy_text = "Policy plane\nOPA gate,\n4 Rego packs\nallow / deny / escalate"
    box((7.0, 3.6), 1.9, 1.7, policy_text, GREEN)
    # Execution and audit
    exec_text = "Execution + audit\nwrite-ahead intent row,\nthen outcome"
    box((7.0, 1.6), 1.9, 1.3, exec_text, GREEN, fontsize=6.0)
    # Simulated human
    human_text = "Simulated human\nlog-normal escalation\ndelay"
    box((5.15, 0.2), 1.9, 0.8, human_text, VERMILION, fontsize=6.0)

    arrow((2.1, 4.45), (2.6, 4.45), "telemetry\nsnapshot")
    arrow((3.65, 2.9), (3.65, 3.6), style="<|-|>")
    arrow((4.7, 4.3), (5.15, 4.3), "propose")
    arrow((6.5, 4.45), (7.0, 4.45), "policy\ndecision")
    arrow((7.95, 3.6), (7.95, 2.9), "allow")
    arrow((7.0, 1.6), (7.0, 1.0), "escalate")
    arrow((5.15, 0.05), (0.2, 0.05), colour=VERMILION, ls=":")
    arrow((0.9, 0.05), (0.9, 3.6), "resolves\nfault", colour=VERMILION, ls=":")

    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=c, edgecolor=c, alpha=0.5, label=n)
        for n, c in (
            ("data plane", BLUE),
            ("agentic control", ORANGE),
            ("policy + execution", GREEN),
            ("contract", GREY),
            ("simulated human", VERMILION),
        )
    ]
    ax.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=5,
        frameon=False,
        fontsize=6.0,
    )
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
