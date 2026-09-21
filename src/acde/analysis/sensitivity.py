"""Sensitivity of the headline claims to the two modelled assumptions (D-104).

ACDE's MTTR and cost claims each rest on a parameter the paper *chose*, not measured: the simulated
on-call human's latency (lognormal, median 360 s) and the provisioning term of cost model v2
(static 8 vs right-sized 3 units over a 300 s horizon). A reviewer's first question is "what if
you'd chosen differently?". These are closed-form answers over the recorded per-run data -- no
re-simulation -- so the paper can state exactly where each claim flips instead of asserting
robustness.

Human latency is a **scale family**: ``sample_latency`` draws ``exp(ln(median) + sigma * Z)`` from a
seeded generator, i.e. ``median * exp(sigma * Z)`` with ``Z`` fixed by the seed. Every all-human
outcome (the baseline's MTTR) therefore scales *exactly* linearly with the median, which gives a
closed-form break-even (:func:`break_even_human_median`); ``tests/unit/test_sensitivity.py``
verifies the linearity against the real sampler rather than assuming it.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from scipy import stats as scipy_stats

from acde.analysis import stats


@dataclass(frozen=True)
class ModelParams:
    """The modelled-environment parameters the recorded runs were produced under."""

    human_median_s: float = 360.0
    human_sigma: float = 0.5
    static_units: float = 8.0
    rightsized_units: float = 3.0
    horizon_s: float = 300.0
    compute_rate: float = 0.05
    rightsizing_configs: frozenset[str] = frozenset({"autoscale", "optimization_only", "full"})

    @classmethod
    def from_settings(cls) -> ModelParams:
        """Parameters currently configured (what a fresh run would record)."""
        from acde.config import get_settings
        from acde.telemetry.cost import RIGHTSIZING_CONFIGS

        s = get_settings()
        return cls(
            human_median_s=s.human_latency_median_s,
            human_sigma=s.human_latency_sigma,
            static_units=s.provisioned_units_static,
            rightsized_units=s.provisioned_units_rightsized,
            horizon_s=s.provisioning_horizon_s,
            compute_rate=s.cost_rate_compute_unit_second,
            rightsizing_configs=frozenset(RIGHTSIZING_CONFIGS),
        )

    @classmethod
    def from_provenance(cls, provenance: dict[str, Any]) -> ModelParams:
        """Parameters a run *recorded* in its manifest (authoritative over current settings)."""
        return cls(
            human_median_s=float(provenance["human_latency"]["median_s"]),
            human_sigma=float(provenance["human_latency"]["sigma"]),
            static_units=float(provenance["provisioning"]["static_units"]),
            rightsized_units=float(provenance["provisioning"]["rightsized_units"]),
            horizon_s=float(provenance["provisioning"]["horizon_s"]),
            compute_rate=cls.from_settings().compute_rate,
            rightsizing_configs=cls.from_settings().rightsizing_configs,
        )

    def provisioning(
        self,
        config: str,
        *,
        static: float | None = None,
        rightsized: float | None = None,
        horizon_s: float | None = None,
    ) -> float:
        """Provisioning cost of ``config`` (optionally under swept parameters)."""
        if config in self.rightsizing_configs:
            units = self.rightsized_units if rightsized is None else rightsized
        else:
            units = self.static_units if static is None else static
        horizon = self.horizon_s if horizon_s is None else horizon_s
        return units * horizon * self.compute_rate


# --- human-latency sensitivity --------------------------------------------------------------------


def break_even_human_median(mttr_auto: float, mttr_baseline: float, median_s: float) -> float:
    """Human median latency at which the baseline's MTTR equals the automation's.

    Baseline MTTR is all-human, so it scales linearly with the median (scale family): at median
    ``m`` it is ``mttr_baseline * m / median_s``. Solving ``that == mttr_auto`` gives
    ``m* = median_s * mttr_auto / mttr_baseline``. Automation is faster whenever the true human
    median exceeds ``m*``; ``m* < median_s`` means the claim survives a *faster* human.
    """
    if mttr_baseline <= 0:
        return math.inf
    return median_s * mttr_auto / mttr_baseline


def win_probability(mttrs: Sequence[float], median_s: float, sigma: float) -> float:
    """P(a human would have been slower than the automation), averaged over the automation's runs.

    For each automation MTTR ``t`` the human latency ``L ~ LogNormal(ln median, sigma)`` exceeds it
    with probability ``1 - Phi((ln t - ln median) / sigma)``; a zero-time resolution beats any
    human (probability 1). Unlike a comparison against one fixed baseline draw this is a smooth
    function of *both* human parameters.
    """
    if not mttrs:
        return 0.0
    log_median = math.log(median_s)
    probs = [
        1.0 if t <= 0 else 1.0 - float(scipy_stats.norm.cdf((math.log(t) - log_median) / sigma))
        for t in mttrs
    ]
    return sum(probs) / len(probs)


def human_latency_grid(
    mttrs: Sequence[float], medians: Sequence[float], sigmas: Sequence[float]
) -> list[dict[str, float]]:
    """``win_probability`` over a (median, sigma) grid."""
    return [
        {"human_median_s": m, "human_sigma": s, "p_automation_faster": win_probability(mttrs, m, s)}
        for m in medians
        for s in sigmas
    ]


# --- cost-model sensitivity -----------------------------------------------------------------------


def measured_cost(df: pd.DataFrame, config: str, params: ModelParams) -> list[float]:
    """Per-run *measured* cost: the recorded total minus the provisioning term it embeds."""
    sel = df[(df["config"] == config) & (df["metric"] == "cost_units")]["value"].dropna()
    return [float(v) - params.provisioning(config) for v in sel]


def cost_reduction(
    measured_auto: float,
    measured_base: float,
    auto_config: str,
    base_config: str,
    params: ModelParams,
    *,
    static: float | None = None,
    rightsized: float | None = None,
    horizon_s: float | None = None,
) -> float:
    """Percent cost reduction of ``auto_config`` vs ``base_config`` (positive = cheaper)."""
    kw = {"static": static, "rightsized": rightsized, "horizon_s": horizon_s}
    auto = measured_auto + params.provisioning(auto_config, **kw)
    base = measured_base + params.provisioning(base_config, **kw)
    return (base - auto) / base * 100.0 if base else 0.0


def cost_sweep(
    df: pd.DataFrame,
    params: ModelParams,
    static_grid: Sequence[float],
    rightsized_grid: Sequence[float],
    horizon_grid: Sequence[float],
    auto_config: str = "full",
    base_config: str = "baseline",
) -> list[dict[str, float]]:
    """Cost reduction of ``auto_config`` vs ``base_config`` over the provisioning-parameter grid."""
    m_auto = stats.median(measured_cost(df, auto_config, params) or [0.0])
    m_base = stats.median(measured_cost(df, base_config, params) or [0.0])
    return [
        {
            "static_units": s,
            "rightsized_units": r,
            "horizon_s": h,
            "cost_reduction_pct": cost_reduction(
                m_auto,
                m_base,
                auto_config,
                base_config,
                params,
                static=s,
                rightsized=r,
                horizon_s=h,
            ),
        }
        for s in static_grid
        for r in rightsized_grid
        for h in horizon_grid
    ]


def cost_break_even_static_units(
    measured_auto: float, measured_base: float, params: ModelParams, rightsized: float | None = None
) -> float:
    """Static-provisioning units at which the automation stops being cheaper (0% reduction).

    Cost parity: ``M_a + R*H*r = M_b + S*H*r``  =>  ``S* = R + (M_a - M_b) / (H * r)``.
    Automation is
    cheaper for any static allocation above ``S*``. This is the number that makes the paper's
    "~25% cost reduction" honest: it is contingent on the baseline over-provisioning, and the
    measured (non-provisioning) cost alone tells the opposite story if agents add work.
    """
    r_units = params.rightsized_units if rightsized is None else rightsized
    return r_units + (measured_auto - measured_base) / (params.horizon_s * params.compute_rate)


# --- report ---------------------------------------------------------------------------------------

MEDIAN_GRID = (60.0, 120.0, 180.0, 240.0, 360.0, 480.0, 720.0, 1200.0)
SIGMA_GRID = (0.25, 0.5, 1.0)


def sensitivity_report(
    df: pd.DataFrame, params: ModelParams, *, baseline: str = "baseline"
) -> dict[str, Any]:
    """Break-even human latency + win-probability grid per config, and the cost sweep/break-even."""
    configs = sorted(c for c in df["config"].unique() if c != baseline)
    mttr = df[df["metric"] == "mttr_s"]
    base_vals = mttr[mttr["config"] == baseline]["value"].dropna().tolist()
    base_med = stats.median(base_vals) if base_vals else 0.0
    human: dict[str, Any] = {"baseline_median_mttr_s": base_med, "per_config": {}}
    for cfg in configs:
        vals = mttr[mttr["config"] == cfg]["value"].dropna().tolist()
        if not vals:
            continue
        med = stats.median(vals)
        human["per_config"][cfg] = {
            "median_mttr_s": med,
            "break_even_human_median_s": break_even_human_median(
                med, base_med, params.human_median_s
            ),
            "win_probability_grid": human_latency_grid(vals, MEDIAN_GRID, SIGMA_GRID),
        }
    cost: dict[str, Any] = {}
    for cfg in configs:
        m_auto = stats.median(measured_cost(df, cfg, params) or [0.0])
        m_base = stats.median(measured_cost(df, baseline, params) or [0.0])
        cost[cfg] = {
            "measured_median": m_auto,
            "baseline_measured_median": m_base,
            "reduction_pct_at_recorded_params": cost_reduction(
                m_auto, m_base, cfg, baseline, params
            ),
            "break_even_static_units": cost_break_even_static_units(m_auto, m_base, params)
            if cfg in params.rightsizing_configs
            else None,
        }
    full_sweep = (
        cost_sweep(df, params, (4.0, 6.0, 8.0, 10.0, 12.0), (1.0, 2.0, 3.0, 5.0, 8.0), (300.0,))
        if "full" in configs
        else []
    )
    return {
        "params": params.__dict__ | {"rightsizing_configs": sorted(params.rightsizing_configs)},
        "human_latency": human,
        "cost_by_config": cost,
        "cost_sweep_full_vs_baseline": full_sweep,
    }


def main() -> None:  # pragma: no cover - CLI
    from acde.analysis.analyze import load_raw

    parser = argparse.ArgumentParser(description="ACDE sensitivity analysis")
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()
    d = Path(args.results_dir)
    report = sensitivity_report(load_raw(d), ModelParams.from_settings())
    (d / "sensitivity.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(f"wrote {d / 'sensitivity.json'}")


if __name__ == "__main__":  # pragma: no cover
    main()
