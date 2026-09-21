"""Campaign-level statistics for the paper (D-104).

``analyze.py`` summarises one mock-LLM results directory. The paper's evidence is three separately
run *arms* -- live-LLM agent configs, LLM-free baselines, and a mock-LLM ``full`` -- that must be
merged without ever letting live and mock conditions blur together. This module loads them with an
``arm`` tag, refuses to merge silently across mismatched provenance, and computes the comparisons
the manuscript reports: effect sizes with bootstrap intervals, Holm-corrected tests, per-scenario
stratification, LLM accounting, and the live-vs-mock comparison of the same config.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from acde.analysis import stats
from acde.analysis.analyze import load_raw

# results sub-directory -> arm label. "live" agents call a real model; "static" configs call none;
# "mock" is the deterministic-mock counterpart of live ``full``.
ARM_DIRS = {"paper-live": "live", "paper-baselines": "static", "paper-mock": "mock"}

LLM_METRICS = (
    "api_tokens",
    "llm_calls",
    "llm_cache_hits",
    "llm_degraded",
    "llm_invalid",
    "llm_latency_s",
)
HEADLINE_METRICS = (
    "mttr_s",
    "cost_units",
    "manual_interventions",
    "decision_correct",
    "freshness_s",
)
_PROVENANCE_KEYS = ("git_sha", "timings", "human_latency", "provisioning", "llm_budget")


def load_campaign(root: Path) -> pd.DataFrame:
    """Load every arm under ``root`` into one long frame with an ``arm`` column."""
    frames = []
    for sub, arm in ARM_DIRS.items():
        if (root / sub / "raw.csv").exists():
            df = load_raw(root / sub)
            df["arm"] = arm
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no arm results under {root} (looked for {sorted(ARM_DIRS)})")
    return pd.concat(frames, ignore_index=True)


def load_manifests(root: Path) -> list[dict[str, Any]]:
    """Every manifest record under ``root``, each tagged with its arm."""
    records: list[dict[str, Any]] = []
    for sub, arm in ARM_DIRS.items():
        path = root / sub / "manifest.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    records.append({**json.loads(line), "arm": arm})
    return records


def provenance_problems(records: Sequence[dict[str, Any]]) -> list[str]:
    """Reasons the merged dataset is *not* a single homogeneous experiment (empty == clean).

    Every arm must share code version, timings, human model, cost-model parameters, and budgets;
    the live arm must have run live and the mock/static arms must not have. Anything else means the
    numbers mix conditions and the paper cannot present them as one comparison.
    """
    problems: list[str] = []
    for key in _PROVENANCE_KEYS:
        seen = {
            json.dumps(r["provenance"][key], sort_keys=True) for r in records if "provenance" in r
        }
        if len(seen) > 1:
            problems.append(f"provenance field {key!r} varies across runs: {len(seen)} values")
    if any("provenance" not in r for r in records):
        problems.append("some runs carry no provenance (produced before D-104 instrumentation)")
    if any(r["provenance"].get("git_dirty") for r in records if "provenance" in r):
        problems.append("some runs were produced from a dirty working tree")
    expected = {"live": {"live"}, "mock": {"mock"}, "static": {"none"}}
    for arm, modes in expected.items():
        got = {str(r.get("llm_mode")) for r in records if r["arm"] == arm}
        if got - modes:
            problems.append(
                f"arm {arm!r} contains llm_mode {sorted(got - modes)}, expected {sorted(modes)}"
            )
    return problems


def primary(df: pd.DataFrame) -> pd.DataFrame:
    """The primary comparison set: live agent configs + static baselines, never the mock arm.

    A config name can exist in both the live and the mock arm (``full``); pooling them would blend
    exactly the two conditions the paper contrasts, so anything comparing against the baseline goes
    through this filter.
    """
    return df[df["arm"].isin(("live", "static"))] if "arm" in df.columns else df


def _values(df: pd.DataFrame, config: str, metric: str, arm: str | None = None) -> list[float]:
    sel = df[(df["config"] == config) & (df["metric"] == metric)]
    if arm is not None:
        sel = sel[sel["arm"] == arm]
    return [float(v) for v in sel["value"].dropna()]


def _matched(
    df_a: pd.DataFrame, df_b: pd.DataFrame, metric: str
) -> tuple[list[float], list[float]]:
    """Values aligned on (scenario, replicate) index (nominal pairing; see stats.mann_whitney)."""
    a = df_a[df_a["metric"] == metric].set_index(["scenario", "replicate"])["value"]
    b = df_b[df_b["metric"] == metric].set_index(["scenario", "replicate"])["value"]
    both = a.index.intersection(b.index)
    return ([float(x) for x in a.loc[both]], [float(x) for x in b.loc[both]])


def compare_samples(
    treat: Sequence[float],
    control: Sequence[float],
    matched: tuple[Sequence[float], Sequence[float]] | None = None,
    *,
    seed: int = 0,
    n_resamples: int = 2000,
) -> dict[str, Any]:
    """Effect summary of ``treat`` vs ``control`` (negative diff / delta = treat lower)."""
    med_t, med_c = stats.median(treat), stats.median(control)
    _, p_mw = stats.mann_whitney(treat, control)
    p_wx = stats.paired_wilcoxon(matched[0], matched[1])[1] if matched and len(matched[0]) else 1.0
    return {
        "n_treat": len(treat),
        "n_control": len(control),
        "median_treat": med_t,
        "median_control": med_c,
        "median_diff": med_t - med_c,
        "median_diff_ci": stats.median_diff_ci(treat, control, n_resamples, seed=seed),
        "relative_change_pct": (med_t - med_c) / med_c * 100.0 if med_c else None,
        "cliffs_delta": stats.cliffs_delta(treat, control),
        "cliffs_delta_ci": stats.cliffs_delta_ci(treat, control, n_resamples, seed=seed),
        "p_mannwhitney": p_mw,
        "p_wilcoxon_matched": p_wx,
        "n_matched": len(matched[0]) if matched else 0,
    }


def compare_to_baseline(
    df: pd.DataFrame,
    metrics: Sequence[str],
    configs: Sequence[str],
    control: str = "baseline",
    *,
    seed: int = 0,
    n_resamples: int = 2000,
) -> list[dict[str, Any]]:
    """Every (metric, config) comparison against ``control``, Holm-corrected as one family."""
    df = primary(df)
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        for config in configs:
            if config == control:
                continue
            t, c = _values(df, config, metric), _values(df, control, metric)
            if not t or not c:
                continue
            matched = _matched(df[df["config"] == config], df[df["config"] == control], metric)
            rows.append(
                {
                    "metric": metric,
                    "config": config,
                    "control": control,
                    **compare_samples(t, c, matched, seed=seed, n_resamples=n_resamples),
                }
            )
    for row, (adj, reject) in zip(
        rows, stats.holm_bonferroni([r["p_mannwhitney"] for r in rows]), strict=True
    ):
        row["p_holm"], row["significant"] = adj, reject
    return rows


def live_vs_mock(
    df: pd.DataFrame,
    metrics: Sequence[str],
    config: str = "full",
    *,
    seed: int = 0,
    n_resamples: int = 2000,
) -> list[dict[str, Any]]:
    """Live-LLM ``config`` vs its mock-LLM twin: the paper's mock-vs-live divergence, measured."""
    live = df[(df["arm"] == "live") & (df["config"] == config)]
    mock = df[(df["arm"] == "mock") & (df["config"] == config)]
    rows = []
    for metric in metrics:
        t = [float(v) for v in live[live["metric"] == metric]["value"].dropna()]
        c = [float(v) for v in mock[mock["metric"] == metric]["value"].dropna()]
        if t and c:
            rows.append(
                {
                    "metric": metric,
                    "config": config,
                    **compare_samples(
                        t, c, _matched(live, mock, metric), seed=seed, n_resamples=n_resamples
                    ),
                }
            )
    for row, (adj, reject) in zip(
        rows, stats.holm_bonferroni([r["p_mannwhitney"] for r in rows]), strict=True
    ):
        row["p_holm"], row["significant"] = adj, reject
    return rows


def per_scenario_medians(df: pd.DataFrame, metric: str, configs: Sequence[str]) -> pd.DataFrame:
    """Median of ``metric`` per (config, scenario): shows where an aggregate hides a scenario."""
    sel = df[(df["metric"] == metric) & (df["config"].isin(configs))]
    table = sel.pivot_table(index="config", columns="scenario", values="value", aggfunc="median")
    return table.reindex([c for c in configs if c in table.index])


def llm_accounting(df: pd.DataFrame, configs: Sequence[str]) -> pd.DataFrame:
    """Per-config median LLM accounting from the live arm, plus the degraded-call fraction."""
    live = df[df["arm"] == "live"]
    rows = []
    for config in configs:
        row: dict[str, Any] = {"config": config}
        for metric in LLM_METRICS:
            vals = _values(live, config, metric)
            row[metric] = stats.median(vals) if vals else None
        calls, degraded = row.get("llm_calls") or 0.0, row.get("llm_degraded") or 0.0
        row["degraded_fraction"] = degraded / (calls + degraded) if calls + degraded else None
        rows.append(row)
    return pd.DataFrame(rows).set_index("config")
