"""Pure statistics for the analysis pipeline (§6).

Median/IQR, seeded bootstrap CIs, paired Wilcoxon signed-rank, Holm-Bonferroni correction, and
Cliff's delta effect size. No I/O — unit-tested against hand-computed fixtures.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from scipy import stats as scipy_stats


def median(data: Sequence[float]) -> float:
    return float(np.median(data)) if len(data) else math.nan


def iqr(data: Sequence[float]) -> float:
    """Interquartile range (Q3 - Q1)."""
    if len(data) < 2:
        return 0.0
    q1, q3 = np.percentile(data, [25, 75])
    return float(q3 - q1)


def bootstrap_ci(
    data: Sequence[float],
    stat: Callable[[np.ndarray], float] = np.median,
    n_resamples: int = 10000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    """Seeded bootstrap ``(lo, hi)`` CI for ``stat`` at confidence ``1 - alpha``."""
    arr = np.asarray(data, dtype=float)
    if arr.size == 0:
        return (math.nan, math.nan)
    if arr.size == 1:
        return (float(arr[0]), float(arr[0]))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(n_resamples, arr.size))
    estimates = np.apply_along_axis(stat, 1, arr[idx])
    lo, hi = np.percentile(estimates, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def paired_wilcoxon(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Paired Wilcoxon signed-rank test; returns (statistic, p-value).

    Returns ``(nan, 1.0)`` when the test is undefined (too few pairs or all-zero differences).
    """
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.size != b_arr.size or a_arr.size == 0 or np.allclose(a_arr, b_arr):
        return (math.nan, 1.0)
    try:
        result = scipy_stats.wilcoxon(a_arr, b_arr)
    except ValueError:
        return (math.nan, 1.0)
    return (float(result.statistic), float(result.pvalue))


def holm_bonferroni(pvalues: Sequence[float], alpha: float = 0.05) -> list[tuple[float, bool]]:
    """Holm-Bonferroni step-down correction.

    Returns ``[(adjusted_p, reject), ...]`` in the original order.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        adj = min(1.0, (m - rank) * pvalues[i])
        running = max(running, adj)  # enforce monotone non-decreasing
        adjusted[i] = running
    return [(adjusted[i], adjusted[i] < alpha) for i in range(m)]


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's delta effect size in [-1, 1]: P(a>b) - P(a<b)."""
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.size == 0 or b_arr.size == 0:
        return 0.0
    diff = a_arr[:, None] - b_arr[None, :]
    greater = int(np.sum(diff > 0))
    less = int(np.sum(diff < 0))
    return (greater - less) / (a_arr.size * b_arr.size)
