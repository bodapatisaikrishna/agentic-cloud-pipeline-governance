"""Analyses added for campaign v2 (docs/preregistration-v2.md, D-108).

``paper_stats`` holds the comparisons both protocols share. This module adds what the
pre-registration specifies on top -- robustness checks (stratified permutation test, equivalence
tests), the rules-vs-agents family, the cost split, the decision-quality failure taxonomy, the
v1-vs-v2 side-by-side table -- and the check of the v1 human-simulator artifact (D-106).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acde.analysis import paper_stats as ps
from acde.analysis import stats

# v2 primary outcomes (preregistration §3), in table order.
V2_PRIMARY = ("mttr_injection_s", "escalated_incidents", "cost_units", "decision_correct")
COST_TERMS = ("cost_compute_units", "cost_storage_units", "cost_provisioning_units", "cost_units")
# Equivalence margins (preregistration §5). Cost's margin is relative to the baseline median.
MARGINS_ABS = {"mttr_injection_s": 30.0, "escalated_incidents": 0.5, "decision_correct": 0.1}
COST_MARGIN_REL = 0.10
BINARY_METRICS = frozenset({"decision_correct"})
# A v1 run whose MTTR is at least this long was resolved by the simulated human: even the fastest
# of six lognormal(360 s, 0.5) draws falls below it with probability about 0.001 (D-106).
HUMAN_RESOLVED_MIN_S = 60.0


def _by_scenario(df: pd.DataFrame, config: str, metric: str) -> dict[str, list[float]]:
    sel = df[(df["config"] == config) & (df["metric"] == metric)]
    return {str(s): [float(v) for v in g["value"].dropna()] for s, g in sel.groupby("scenario")}


def margin_for(metric: str, control: Sequence[float]) -> float | None:
    """The pre-registered equivalence margin for ``metric`` (None if none was registered)."""
    if metric == "cost_units":
        return COST_MARGIN_REL * stats.median(control) if control else None
    return MARGINS_ABS.get(metric)


def add_robustness(
    df: pd.DataFrame, rows: list[dict[str, Any]], *, seed: int = 0, n_permutations: int = 5000
) -> list[dict[str, Any]]:
    """Add the stratified permutation p-value and the TOST verdict to each comparison row."""
    for row in rows:
        metric, config, control = row["metric"], row["config"], row["control"]
        row["p_stratified"] = stats.stratified_permutation_test(
            _by_scenario(df, config, metric),
            _by_scenario(df, control, metric),
            n_permutations=n_permutations,
            seed=seed,
        )
        t, c = ps._values(df, config, metric), ps._values(df, control, metric)
        margin = margin_for(metric, c)
        row["equivalence_margin"] = margin
        if margin is None or not t or not c:
            row["equivalence_ci90"], row["equivalent"] = None, None
            continue
        tost = stats.tost_proportion_diff if metric in BINARY_METRICS else stats.tost_median_diff
        lo, hi, eq = tost(t, c, margin, seed=seed)
        row["equivalence_ci90"], row["equivalent"] = (lo, hi), eq
    return rows


def verdict(row: dict[str, Any]) -> str:
    """The pre-registered reading of one comparison (preregistration §5)."""
    if row.get("significant"):
        p_strat = row.get("p_stratified")
        return "scenario-dependent" if p_strat is not None and p_strat >= 0.05 else "different"
    if row.get("equivalent"):
        return "equivalent"
    return "inconclusive"


def rules_vs_agents(
    df: pd.DataFrame, *, seed: int = 0, n_resamples: int = 2000, paired: bool = True
) -> list[dict[str, Any]]:
    """Family B: ``full`` and ``hybrid`` against ``rule_based`` (preregistration H5)."""
    configs = [c for c in ("full", "hybrid") if c in set(df["config"])]
    return ps.compare_to_baseline(
        df,
        ("mttr_injection_s", "escalated_incidents"),
        configs,
        control="rule_based",
        seed=seed,
        n_resamples=n_resamples,
        paired=paired,
    )


def cost_split(df: pd.DataFrame, configs: Sequence[str]) -> pd.DataFrame:
    """Median of each cost term per config; shows how much of a gap is the provisioning term."""
    rows = []
    for c in configs:
        row: dict[str, Any] = {"config": c}
        for term in COST_TERMS:
            vals = ps._values(df, c, term)
            row[term] = stats.median(vals) if vals else None
        rows.append(row)
    return pd.DataFrame(rows).set_index("config")


def side_by_side(v1: pd.DataFrame, v2: pd.DataFrame, configs: Sequence[str]) -> pd.DataFrame:
    """v1 and v2 medians next to each other for the three headline outcomes."""
    pairs = (
        ("mttr", "mttr_s", "mttr_injection_s"),
        ("escalations", "manual_interventions", "escalated_incidents"),
        ("cost", "cost_units", "cost_units"),
    )
    rows = []
    for c in configs:
        row: dict[str, Any] = {"config": c}
        for name, m1, m2 in pairs:
            a, b = ps._values(v1, c, m1), ps._values(v2, c, m2)
            row[f"{name}_v1"] = stats.median(a) if a else None
            row[f"{name}_v2"] = stats.median(b) if b else None
        rows.append(row)
    return pd.DataFrame(rows).set_index("config")


def expected_min_draw_median(
    k: int, median_s: float, sigma: float, n_sim: int = 20000, seed: int = 0
) -> float:
    """Median of the fastest of ``k`` simulated-human delays (the v1 per-row draw, D-106)."""
    rng = np.random.default_rng(seed)
    draws = rng.lognormal(np.log(median_s), sigma, size=(n_sim, max(k, 1)))
    return float(np.median(draws.min(axis=1)))


def prob_fastest_below(threshold_s: float, k: int, median_s: float, sigma: float) -> float:
    """Probability that the fastest of ``k`` lognormal human delays is under ``threshold_s``."""
    from scipy import stats as scipy_stats

    single = float(scipy_stats.norm.cdf((np.log(threshold_s) - np.log(median_s)) / sigma))
    return 1.0 - (1.0 - single) ** k


def human_draw_check(
    prim: pd.DataFrame, configs: Sequence[str], median_s: float, sigma: float, seed: int = 0
) -> pd.DataFrame:
    """v1 only: how many runs the human resolved, and what the per-row draws alone predict."""
    wide = prim.pivot_table(
        index=["config", "run_id"], columns="metric", values="value", aggfunc="first"
    ).reset_index()
    rows = []
    for c in configs:
        runs = wide[wide["config"] == c]
        if runs.empty or "mttr_s" not in runs:
            continue
        human = runs[runs["mttr_s"] >= HUMAN_RESOLVED_MIN_S]
        k = round(float(human["manual_interventions"].median())) if len(human) else 0
        rows.append(
            {
                "config": c,
                "n": len(runs),
                "n_human": len(human),
                "median_escalations": k,
                "median_mttr_human": float(human["mttr_s"].median()) if len(human) else None,
                "predicted_min_draw": expected_min_draw_median(k, median_s, sigma, seed=seed)
                if k
                else None,
            }
        )
    return pd.DataFrame(rows).set_index("config")


def decision_taxonomy(
    root: Path, df: pd.DataFrame, protocol: str = "v2", top: int = 3
) -> pd.DataFrame:
    """For runs with ``decision_correct = 0``: the most frequent (agent, action, verdict).

    Reads the per-run action exports (D-106). Returns one row per (scenario, agent, action_type,
    policy_decision, executed) with its run count, the ``top`` most frequent per scenario.
    """
    wrong = df[(df["metric"] == "decision_correct") & (df["value"] == 0) & (df["arm"] == "live")]
    counts: Counter[tuple[str, str, str, str, bool]] = Counter()
    for sub, arm in ps.PROTOCOL_ARMS[protocol].items():
        if arm != "live":
            continue
        for run_id, scenario in zip(wrong["run_id"], wrong["scenario"], strict=True):
            path = root / sub / "actions" / f"{run_id}.jsonl"
            if not path.exists():
                continue
            seen = set()
            for line in path.read_text().splitlines():
                a = json.loads(line)
                if a["action_type"] == "raise_anomaly":  # monitoring's acknowledgement
                    continue
                seen.add(
                    (
                        str(scenario),
                        a["agent"],
                        a["action_type"],
                        a["policy_decision"],
                        bool(a["executed"]),
                    )
                )
            counts.update(seen)  # count runs, not actions
    rows = [
        {
            "scenario": k[0],
            "agent": k[1],
            "action_type": k[2],
            "policy_decision": k[3],
            "executed": k[4],
            "runs": n,
        }
        for k, n in counts.items()
    ]
    if not rows:
        return pd.DataFrame(
            columns=["scenario", "agent", "action_type", "policy_decision", "executed", "runs"]
        )
    out = pd.DataFrame(rows).sort_values(["scenario", "runs"], ascending=[True, False])
    return out.groupby("scenario", sort=True).head(top).reset_index(drop=True)
