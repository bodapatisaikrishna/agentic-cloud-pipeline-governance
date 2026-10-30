"""Power analysis for the v2 campaign from the v1 distributions (docs/preregistration-v2.md).

v2 fixes n at 20 per (config, scenario), 80 per config. This module answers what that n can
detect: for a metric's v1 baseline distribution, the smallest proportional reduction a config
must achieve to be detected with the target power. Simulated with the rank-sum test on resampled
v1 values, which ignores the pairing v2 adds, so the figures are conservative.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from acde.analysis import paper_stats as ps
from acde.analysis import stats


def power_at_ratio(
    control: Sequence[float],
    ratio: float,
    n: int,
    alpha: float,
    n_sim: int = 400,
    seed: int = 0,
) -> float:
    """Share of simulated studies that reject when treatment = control x ``(1 - ratio)``."""
    base = np.asarray(control, dtype=float)
    rng = np.random.default_rng(seed)
    rejections = 0
    for _ in range(n_sim):
        c = rng.choice(base, n)
        t = rng.choice(base, n) * (1 - ratio)
        if stats.mann_whitney(t, c)[1] < alpha:
            rejections += 1
    return rejections / n_sim


def min_detectable_ratio(
    control: Sequence[float],
    n: int,
    alpha: float,
    target_power: float = 0.8,
    grid: Sequence[float] = tuple(round(0.05 * i, 2) for i in range(1, 20)),
    n_sim: int = 400,
    seed: int = 0,
) -> float | None:
    """Smallest reduction on ``grid`` reaching ``target_power``; None if none does."""
    for ratio in grid:
        if power_at_ratio(control, ratio, n, alpha, n_sim, seed) >= target_power:
            return ratio
    return None


def report(
    root: Path, n: int = 80, family_size: int = 32, seed: int = 20261030
) -> dict[str, Any]:
    """MDEs for the v1 baseline's MTTR and cost at the nominal and the Bonferroni-worst alpha."""
    prim = ps.primary(ps.load_campaign(root))
    out: dict[str, Any] = {"n_per_config": n, "family_size": family_size, "metrics": {}}
    for metric in ("mttr_s", "cost_units"):
        control = ps._values(prim, "baseline", metric)
        out["metrics"][metric] = {
            "baseline_median": stats.median(control),
            "mde_alpha_0.05": min_detectable_ratio(control, n, 0.05, seed=seed),
            "mde_alpha_bonferroni": min_detectable_ratio(control, n, 0.05 / family_size, seed=seed),
        }
    return out


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="v2 power analysis from v1 data")
    parser.add_argument("--root", default="results")
    parser.add_argument("--out", default="results/power_v1.json")
    args = parser.parse_args()
    result = report(Path(args.root))
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
