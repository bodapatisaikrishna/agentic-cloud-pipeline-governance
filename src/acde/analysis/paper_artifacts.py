"""Generate every table, figure, and quoted number in the manuscript (D-104).

The paper contains **no hand-typed results**. This module reads the campaign arms, the adversarial
JSON, and the sensitivity analysis, and writes into ``paper/generated/``: booktabs ``tab_*.tex``,
vector ``fig_*.pdf``, and ``numbers.tex`` -- a ``\\newcommand`` for each statistic the prose
quotes. Output is deterministic (fixed seeds/metadata), so ``make paper-artifacts`` twice yields
identical hashes and a reviewer can regenerate exactly what is printed.

By default it **refuses** to build from a dataset whose provenance is not homogeneous (mixed code
versions, dirty tree, a mock run in the live arm ...): such numbers cannot be presented as one
experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from acde.analysis import paper_figures as figs
from acde.analysis import paper_stats as ps
from acde.analysis import paper_v2 as v2
from acde.analysis import sensitivity as sens
from acde.analysis import stats
from acde.analysis.paper_tables import (
    Numbers,
    adversarial_table,
    cost_split_table,
    effects_table,
    fnum,
    fp,
    human_check_table,
    live_mock_table,
    llm_table,
    main_table,
    scenario_table,
    sensitivity_table,
    side_by_side_table,
    taxonomy_table,
    true_minus,
    v2_effects_table,
)
from acde.experiments.configs import ALL_CONFIGS

EFFECT_METRICS = ("mttr_s", "cost_units", "manual_interventions", "decision_correct")


class ProvenanceError(RuntimeError):
    """The merged dataset mixes experimental conditions and must not be presented as one."""


# --- orchestration --------------------------------------------------------------------------------


def _headline_numbers(
    nums: Numbers,
    prim: pd.DataFrame,
    comps: Sequence[dict[str, Any]],
    lvm: Sequence[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    for cfg in sorted(set(prim["config"])):
        for metric, key in (
            ("mttr_s", "Mttr"),
            ("cost_units", "Cost"),
            ("manual_interventions", "Interv"),
            ("decision_correct", "Decision"),
        ):
            vals = ps._values(prim, cfg, metric)
            if vals:
                nums.add(fnum(stats.median(vals)), key, cfg, "median")
        nums.add(len(ps._values(prim, cfg, "mttr_s")), "n", cfg)
    for r in comps:
        tag = (r["metric"], r["config"])
        nums.add(fnum(r["median_diff"]), "diff", *tag)
        nums.add(true_minus(f"{r['cliffs_delta']:.2f}"), "delta", *tag)
        lo, hi = r["cliffs_delta_ci"]
        nums.add(true_minus(f"{lo:.2f}"), "deltaLo", *tag)
        nums.add(true_minus(f"{hi:.2f}"), "deltaHi", *tag)
        nums.add(fp(r["p_holm"]), "pHolm", *tag)
        if r["relative_change_pct"] is not None:
            nums.add(true_minus(f"{r['relative_change_pct']:.0f}"), "relpct", *tag)
    for r in lvm:
        nums.add(fnum(r["median_treat"]), "LiveVsMock", r["metric"], "live")
        nums.add(fnum(r["median_control"]), "LiveVsMock", r["metric"], "mock")
        if r["median_treat"] > 0 and r["median_control"] > 0:
            ratio = r["median_treat"] / r["median_control"]
            nums.add(f"{ratio:.0f}", "LiveVsMock", r["metric"], "ratio")
    hl = report["human_latency"]
    nums.add(fnum(hl["baseline_median_mttr_s"]), "baselineMttr")
    for cfg, v in hl["per_config"].items():
        nums.add(fnum(v["break_even_human_median_s"]), "breakEvenHuman", cfg)
    for cfg, v in report["cost_by_config"].items():
        nums.add(fnum(v["reduction_pct_at_recorded_params"]), "costReduction", cfg)
        if v["break_even_static_units"] is not None:
            nums.add(fnum(v["break_even_static_units"], 3), "breakEvenStatic", cfg)


def _usage_numbers(nums: Numbers, df: pd.DataFrame, prov: dict[str, Any] | None) -> None:
    """Live-arm LLM usage totals and the per-run budget caps, for the overhead paragraph."""
    live = df[df["arm"] == "live"]

    def group_thousands(n: float) -> str:
        return f"{int(n):,}".replace(",", "{,}")

    for arm, tag in (("live", "runsArmA"), ("static", "runsArmB"), ("mock", "runsArmC")):
        n_runs = df[(df["arm"] == arm) & (df["metric"] == "mttr_s")]["run_id"].nunique()
        nums.add(n_runs, tag)
    tokens = live[live["metric"] == "api_tokens"]["value"]
    calls = live[live["metric"] == "llm_calls"]["value"]
    if len(tokens):
        nums.add(len(tokens), "runsLive")
        nums.add(group_thousands(tokens.sum()), "apiTokensTotal")
        nums.add(group_thousands(tokens.max()), "apiTokensMaxRun")
        nums.add(group_thousands(calls.sum()), "llmCallsTotal")
        nums.add(int(calls.max()), "llmCallsMaxRun")
    budget = (prov or {}).get("llm_budget")
    if budget:
        nums.add(int(budget["max_calls_per_run"]), "budgetCalls")
        nums.add(group_thousands(budget["max_tokens_per_run"]), "budgetTokens")


def _human_numbers(nums: Numbers, human: pd.DataFrame, params: sens.ModelParams) -> None:
    """Macros for the v1 human-simulator check (D-106)."""
    nums.add(int(v2.HUMAN_RESOLVED_MIN_S), "humanResolvedMin")
    k_max = int(human["median_escalations"].max()) if len(human) else 1
    p_fast = v2.prob_fastest_below(
        v2.HUMAN_RESOLVED_MIN_S, k_max, params.human_median_s, params.human_sigma
    )
    nums.add(k_max, "humanEscalationsMax")
    nums.add(f"{p_fast:.3f}", "humanFastBelowMinProb")
    for cfg, r in human.iterrows():
        nums.add(int(r["n_human"]), "humanResolved", cfg)
        nums.add(int(r["median_escalations"]), "humanEscalations", cfg)
        if r["median_mttr_human"] is not None:
            nums.add(fnum(r["median_mttr_human"]), "humanMttr", cfg)
        if r["predicted_min_draw"] is not None:
            nums.add(fnum(r["predicted_min_draw"]), "humanFastestDraw", cfg)


def _write_and_hash(out_dir: Path, files: dict[str, str]) -> dict[str, str]:
    for name, content in files.items():
        (out_dir / name).write_text(content)
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out_dir.iterdir())
        if p.suffix in (".tex", ".pdf")
    }
    (out_dir / "SHA256SUMS").write_text("".join(f"{h}  {n}\n" for n, h in hashes.items()))
    return hashes


def build(
    root: Path,
    out_dir: Path,
    adversarial: Path | None = None,
    adversarial_before: Path | None = None,
    *,
    strict: bool = True,
    seed: int = 20260921,
    n_resamples: int = 2000,
) -> dict[str, str]:
    """Write all generated artifacts under ``out_dir``; returns ``{filename: sha256}``."""
    df = ps.load_campaign(root)
    records = ps.load_manifests(root)
    problems = ps.provenance_problems(records)
    if problems and strict:
        raise ProvenanceError("; ".join(problems))
    out_dir.mkdir(parents=True, exist_ok=True)

    prim = ps.primary(df)
    configs = [c for c in ALL_CONFIGS if c in set(prim["config"])]
    comps = ps.compare_to_baseline(df, EFFECT_METRICS, configs, seed=seed, n_resamples=n_resamples)
    lvm = ps.live_vs_mock(df, (*EFFECT_METRICS, "freshness_s"), seed=seed, n_resamples=n_resamples)
    agent_cfgs = [c for c in configs if ((prim["config"] == c) & (prim["arm"] == "live")).any()]
    acct = ps.llm_accounting(df, agent_cfgs)
    scen = ps.per_scenario_medians(prim, "mttr_s", configs)
    prov = next((r["provenance"] for r in records if "provenance" in r), None)
    params = sens.ModelParams.from_provenance(prov) if prov else sens.ModelParams.from_settings()
    report = sens.sensitivity_report(prim, params)

    nums = Numbers()
    nums.add(len(records), "runsTotal")
    nums.add(len(problems), "provenanceProblems")
    nums.add(int(params.human_median_s), "humanMedian")
    nums.add(params.human_sigma, "humanSigma")
    _usage_numbers(nums, df, prov)
    cost_scen = ps.per_scenario_medians(prim, "cost_units", configs)
    for cfg in ("baseline", "full"):
        if cfg in cost_scen.index:
            for scenario, value in cost_scen.loc[cfg].items():
                nums.add(fnum(value), "costScen", cfg, scenario)
    _headline_numbers(nums, prim, comps, lvm, report)

    human = v2.human_draw_check(prim, configs, params.human_median_s, params.human_sigma, seed=seed)
    _human_numbers(nums, human, params)

    files: dict[str, str] = {
        "tab_main.tex": main_table(prim, configs),
        "tab_human_check.tex": human_check_table(human),
        "tab_effects.tex": effects_table(comps),
        "tab_live_mock.tex": live_mock_table(lvm),
        "tab_llm.tex": llm_table(acct),
        "tab_scenarios.tex": scenario_table(scen),
        "tab_sensitivity.tex": sensitivity_table(report),
    }
    for tag, path in (("adversarial", adversarial), ("adversarial_before", adversarial_before)):
        if path is not None and path.exists():
            result = json.loads(path.read_text())
            files[f"tab_{tag}.tex"] = adversarial_table(result)
            o = result["overall"]
            nums.add(result["n_cases"], tag, "cases")
            nums.add(o["containment"]["k"], tag, "contained")
            nums.add(o["containment"]["n"], tag, "unsafe")
            nums.add(o["fail_open_total"], tag, "failOpen")
            nums.add(o["gate_errors_total"], tag, "gateErrors")
            nums.add(f"{o['containment']['wilson95'][0]:.4f}", tag, "wilsonLo")
    files["numbers.tex"] = nums.render()

    figs.mttr_distribution(df, configs, out_dir / "fig_mttr.pdf")
    figs.effect_forest(comps, ("mttr_s", "cost_units"), out_dir / "fig_effects.pdf")
    figs.human_sensitivity(
        {c: ps._values(prim, c, "mttr_s") for c in configs if c != "baseline"},
        out_dir / "fig_human_sensitivity.pdf",
        sigma=params.human_sigma,
    )
    if report["cost_sweep_full_vs_baseline"]:
        be = report["cost_by_config"].get("full", {}).get("break_even_static_units")
        figs.cost_sensitivity(report["cost_sweep_full_vs_baseline"], be, out_dir / "fig_cost.pdf")
    figs.scenario_heatmap(scen, out_dir / "fig_scenarios.pdf")
    figs.architecture_diagram(out_dir / "fig_arch.pdf")
    if lvm:
        figs.live_mock_comparison(lvm, out_dir / "fig_live_mock.pdf")
    return _write_and_hash(out_dir, files)


V2_MAIN_HEADER = ("MTTR from inj. (s)", "Escalated inc.", "Cost", "Decision correct")


def _v2_numbers(
    nums: Numbers,
    prim: pd.DataFrame,
    family_a: Sequence[dict[str, Any]],
    family_b: Sequence[dict[str, Any]],
    family_c: Sequence[dict[str, Any]],
) -> None:
    """``\\NVTwo...`` macros for the v2 prose; the prefix keeps them apart from v1's."""
    for cfg in sorted(set(prim["config"])):
        nums.add(len(ps._values(prim, cfg, "mttr_injection_s")), "v2", "n", cfg)
        for metric in (*v2.V2_PRIMARY, "cost_compute_units", "manual_interventions"):
            vals = ps._values(prim, cfg, metric)
            if vals:
                nums.add(fnum(stats.median(vals)), "v2", metric, cfg, "median")
    for family, rows in (("A", family_a), ("B", family_b)):
        for r in rows:
            tag = ("v2", family, r["metric"], r["config"])
            nums.add(fnum(r["median_diff"]), *tag, "diff")
            nums.add(fp(r["p_holm"]), *tag, "pHolm")
            nums.add(v2.verdict(r), *tag, "verdict")
            if r["relative_change_pct"] is not None:
                nums.add(true_minus(f"{r['relative_change_pct']:.0f}"), *tag, "relpct")
    for r in family_c:
        nums.add(fnum(r["median_treat"]), "v2", "LiveVsMock", r["metric"], "live")
        nums.add(fnum(r["median_control"]), "v2", "LiveVsMock", r["metric"], "mock")
        nums.add(fp(r["p_holm"]), "v2", "LiveVsMock", r["metric"], "pHolm")


def build_v2(
    root: Path,
    out_dir: Path,
    *,
    strict: bool = True,
    seed: int = 20260921,
    n_resamples: int = 2000,
    n_permutations: int = 5000,
) -> dict[str, str]:
    """The pre-registered v2 analysis (docs/preregistration-v2.md) into ``out_dir``."""
    df_all = ps.load_campaign(root, "v2")
    records = ps.load_manifests(root, "v2")
    problems = ps.provenance_problems(records)
    if problems and strict:
        raise ProvenanceError("; ".join(problems))
    out_dir.mkdir(parents=True, exist_ok=True)

    excluded = ps.excluded_pairs(df_all)
    df = ps.apply_exclusions(df_all, excluded)
    prim = ps.primary(df)
    configs = [c for c in ALL_CONFIGS if c in set(prim["config"])]
    kw: dict[str, Any] = {"seed": seed, "n_resamples": n_resamples, "paired": True}
    family_a = ps.compare_to_baseline(df, v2.V2_PRIMARY, configs, **kw)
    v2.add_robustness(prim, family_a, seed=seed, n_permutations=n_permutations)
    family_b = v2.add_robustness(
        prim, v2.rules_vs_agents(df, **kw), seed=seed, n_permutations=n_permutations
    )
    family_c = ps.live_vs_mock(df, (*v2.V2_PRIMARY, "freshness_s"), **kw)
    # Sensitivity analysis (preregistration §6): also drop degraded live runs and their pairs.
    excluded_deg = ps.excluded_pairs(df_all, drop_degraded=True)
    df_deg = ps.apply_exclusions(df_all, excluded_deg)
    family_a_deg = ps.compare_to_baseline(df_deg, v2.V2_PRIMARY, configs, **kw)

    nums = Numbers()
    nums.add(len(records), "v2", "runsTotal")
    nums.add(len(problems), "v2", "provenanceProblems")
    nums.add(len(excluded), "v2", "excludedPairs")
    nums.add(len(excluded_deg), "v2", "excludedPairsDegraded")
    _v2_numbers(nums, prim, family_a, family_b, family_c)

    agent_cfgs = [c for c in configs if ((prim["config"] == c) & (prim["arm"] == "live")).any()]
    scen = ps.per_scenario_medians(prim, "mttr_injection_s", configs)
    files: dict[str, str] = {
        "tab_v2_main.tex": main_table(prim, configs, v2.V2_PRIMARY, V2_MAIN_HEADER),
        "tab_v2_effects.tex": v2_effects_table(family_a),
        "tab_v2_effects_sensitivity.tex": effects_table(family_a_deg),
        "tab_v2_rules.tex": v2_effects_table(family_b),
        "tab_v2_live_mock.tex": live_mock_table(family_c),
        "tab_v2_cost_split.tex": cost_split_table(v2.cost_split(prim, configs)),
        "tab_v2_scenarios.tex": scenario_table(scen),
        "tab_v2_llm.tex": llm_table(ps.llm_accounting(df, agent_cfgs)),
        "tab_v2_taxonomy.tex": taxonomy_table(v2.decision_taxonomy(root, df)),
    }
    try:
        v1 = ps.primary(ps.load_campaign(root, "v1"))
    except FileNotFoundError:
        v1 = None
    if v1 is not None:
        files["tab_v1_v2.tex"] = side_by_side_table(v2.side_by_side(v1, prim, configs))
    files["numbers_v2.tex"] = nums.render()
    (out_dir / "v2_effects.json").write_text(
        json.dumps({"A": family_a, "B": family_b, "C": family_c}, indent=2, default=str)
    )

    figs.mttr_distribution(df, configs, out_dir / "fig_v2_mttr.pdf", metric="mttr_injection_s")
    figs.effect_forest(family_a, ("mttr_injection_s", "cost_units"), out_dir / "fig_v2_effects.pdf")
    figs.scenario_heatmap(scen, out_dir / "fig_v2_scenarios.pdf")
    return _write_and_hash(out_dir, files)


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="Generate paper tables/figures/numbers")
    parser.add_argument("--root", default="results")
    parser.add_argument("--out", default="paper/generated")
    parser.add_argument("--adversarial", default=None)
    parser.add_argument("--adversarial-before", default=None)
    parser.add_argument("--allow-unclean", action="store_true")
    parser.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    args = parser.parse_args()
    if args.protocol == "v2":
        out = Path(args.out if args.out != "paper/generated" else "paper/generated-v2")
        hashes = build_v2(Path(args.root), out, strict=not args.allow_unclean)
        print(f"wrote {len(hashes)} v2 artifacts to {out}")
        return
    hashes = build(
        Path(args.root),
        Path(args.out),
        Path(args.adversarial) if args.adversarial else None,
        Path(args.adversarial_before) if args.adversarial_before else None,
        strict=not args.allow_unclean,
    )
    print(f"wrote {len(hashes)} artifacts to {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()
