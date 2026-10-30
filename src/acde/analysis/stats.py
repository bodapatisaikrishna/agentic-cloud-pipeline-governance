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


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because containment rates sit at or near 1.0, where the
    Wald interval collapses to a zero-width [1, 1] and claims certainty the sample cannot support.
    Wilson gives, e.g., [0.9906, 1.0] for 400/400 -- the honest "at least ~99%" statement.
    """
    if n <= 0:
        return (0.0, 1.0)
    if not 0 <= successes <= n:
        raise ValueError(f"successes={successes} outside [0, n={n}]")
    z = float(scipy_stats.norm.ppf(0.5 + confidence / 2))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Two-sided Mann-Whitney U test (independent samples): ``(U, p)``.

    The campaign's runs are matched by (scenario, replicate) *index*, but the seed policy hashes the
    config name into every run's seed, so matched runs share no fault or human-latency randomness.
    The samples are therefore effectively independent and the rank-sum test is the assumption-true
    one; the signed-rank test on the same pairs is kept alongside for continuity with the earlier
    (mock-only) analysis.
    """
    if len(a) == 0 or len(b) == 0:
        return (0.0, 1.0)
    try:
        res = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
    except ValueError:
        return (0.0, 1.0)
    return (float(res.statistic), float(res.pvalue))


def cliffs_delta_ci(
    a: Sequence[float],
    b: Sequence[float],
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile-bootstrap CI for Cliff's delta, resampling each group independently.

    A point estimate of delta without an interval overstates what N=20 supports; the paper reports
    the interval and never a bare "large effect".
    """
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.size == 0 or b_arr.size == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    deltas = np.empty(n_resamples)
    for i in range(n_resamples):
        ra = rng.choice(a_arr, size=a_arr.size, replace=True)
        rb = rng.choice(b_arr, size=b_arr.size, replace=True)
        diff = ra[:, None] - rb[None, :]
        deltas[i] = (np.sum(diff > 0) - np.sum(diff < 0)) / (ra.size * rb.size)
    tail = (1 - confidence) / 2 * 100
    return (float(np.percentile(deltas, tail)), float(np.percentile(deltas, 100 - tail)))


def median_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile-bootstrap CI for ``median(a) - median(b)`` (independent resampling)."""
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.size == 0 or b_arr.size == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_resamples)
    for i in range(n_resamples):
        ma = np.median(rng.choice(a_arr, a_arr.size))
        mb = np.median(rng.choice(b_arr, b_arr.size))
        diffs[i] = ma - mb
    tail = (1 - confidence) / 2 * 100
    return (float(np.percentile(diffs, tail)), float(np.percentile(diffs, 100 - tail)))


def tost_median_diff(
    a: Sequence[float],
    b: Sequence[float],
    margin: float,
    n_resamples: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, bool]:
    """Two one-sided tests for equivalence of medians within ``±margin`` (bootstrap form).

    Equivalence at level ``alpha`` holds when the ``1 - 2*alpha`` percentile-bootstrap interval of
    ``median(a) - median(b)`` lies inside ``(-margin, margin)``. Returns ``(lo, hi, equivalent)``.
    A non-significant difference test is not evidence of no difference; this is.
    """
    lo, hi = median_diff_ci(a, b, n_resamples, confidence=1 - 2 * alpha, seed=seed)
    return (lo, hi, -margin < lo and hi < margin)


def stratified_permutation_test(
    a_by_stratum: dict[str, Sequence[float]],
    b_by_stratum: dict[str, Sequence[float]],
    n_permutations: int = 5000,
    seed: int = 0,
) -> float:
    """Two-sided p-value for a difference between ``a`` and ``b`` that respects strata.

    Within each stratum (scenario) the pooled values are ranked and the statistic is the mean rank
    of ``a`` minus that of ``b``, scaled by the stratum size and summed over strata. Group labels
    are permuted *within* strata only, so a scenario where both groups are slow cannot stand in for
    a treatment effect, which a pooled rank-sum test allows.
    """
    strata = [s for s in a_by_stratum if len(a_by_stratum[s]) and len(b_by_stratum.get(s, ()))]
    if not strata:
        return 1.0
    rng = np.random.default_rng(seed)
    blocks = []
    for s in strata:
        a_arr = np.asarray(a_by_stratum[s], dtype=float)
        b_arr = np.asarray(b_by_stratum[s], dtype=float)
        ranks = scipy_stats.rankdata(np.concatenate([a_arr, b_arr]))
        blocks.append((ranks, a_arr.size))

    def statistic(perms: list[np.ndarray] | None) -> float:
        total = 0.0
        for i, (ranks, n_a) in enumerate(blocks):
            r = ranks if perms is None else ranks[perms[i]]
            total += (r[:n_a].mean() - r[n_a:].mean()) / ranks.size
        return total

    observed = abs(statistic(None))
    hits = 0
    for _ in range(n_permutations):
        perms = [rng.permutation(ranks.size) for ranks, _ in blocks]
        if abs(statistic(perms)) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (n_permutations + 1)


def tost_proportion_diff(
    a: Sequence[float],
    b: Sequence[float],
    margin: float,
    n_resamples: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, bool]:
    """TOST like :func:`tost_median_diff`, on the difference in means of a 0/1 metric."""
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.size == 0 or b_arr.size == 0:
        return (math.nan, math.nan, False)
    rng = np.random.default_rng(seed)
    diffs = np.array(
        [
            rng.choice(a_arr, a_arr.size).mean() - rng.choice(b_arr, b_arr.size).mean()
            for _ in range(n_resamples)
        ]
    )
    lo, hi = np.percentile(diffs, [100 * alpha, 100 * (1 - alpha)])
    return (float(lo), float(hi), -margin < lo and hi < margin)
