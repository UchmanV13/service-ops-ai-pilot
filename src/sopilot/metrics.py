"""Metrics, exact binomial intervals, cluster bootstrap, calibration error."""
from __future__ import annotations

import numpy as np
from scipy.stats import beta, binom


def clopper_pearson(k: int, n: int, conf: float = 0.95):
    """Two-sided exact interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    a = 1 - conf
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return (float(lo), float(hi))


def cp_upper(k: int, n: int, conf: float = 0.95) -> float:
    """One-sided upper bound."""
    if n == 0:
        return float("nan")
    return 1.0 if k == n else float(beta.ppf(conf, k + 1, n - k))


def cp_lower(k: int, n: int, conf: float = 0.95) -> float:
    """One-sided lower bound."""
    if n == 0:
        return float("nan")
    return 0.0 if k == 0 else float(beta.ppf(1 - conf, k, n - k + 1))


def binom_pvalue_risk_above(k_err: int, n: int, alpha: float) -> float:
    """p-value for H0: true error rate > alpha, given k_err errors in n (small = evidence risk <= alpha)."""
    if n == 0:
        return 1.0
    return float(binom.cdf(k_err, n, alpha))


def aurc(conf: np.ndarray, err: np.ndarray) -> float:
    """Area under the risk-coverage curve (lower is better)."""
    order = np.argsort(-conf, kind="stable")
    e = np.asarray(err, dtype=float)[order]
    risk = np.cumsum(e) / np.arange(1, len(e) + 1)
    return float(risk.mean())


def risk_coverage(conf: np.ndarray, err: np.ndarray, points: int = 50):
    order = np.argsort(-conf, kind="stable")
    e = np.asarray(err, dtype=float)[order]
    n = len(e)
    out = []
    for c in np.linspace(1 / points, 1, points):
        k = max(1, int(round(c * n)))
        out.append({"coverage": round(k / n, 4), "risk": round(float(e[:k].mean()), 5),
                    "threshold": round(float(np.asarray(conf)[order][k - 1]), 5)})
    return out


def ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10):
    """Expected calibration error with equal-width bins, plus the reliability table."""
    conf = np.asarray(conf, dtype=float)
    correct = np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    table, total = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        gap = abs(conf[m].mean() - correct[m].mean())
        total += m.mean() * gap
        table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "confidence": round(float(conf[m].mean()), 4),
                      "accuracy": round(float(correct[m].mean()), 4)})
    return float(total), table


def cluster_bootstrap(values_by_cluster: dict, stat, B: int = 2000, seed: int = 0):
    """Resample clusters (template families) with replacement; return (lo, hi) 95% percentile CI."""
    rng = np.random.default_rng(seed)
    keys = list(values_by_cluster)
    stats = []
    for _ in range(B):
        pick = rng.integers(0, len(keys), len(keys))
        rows = [r for i in pick for r in values_by_cluster[keys[i]]]
        stats.append(stat(rows))
    stats = np.array([s for s in stats if s == s])
    if len(stats) == 0:
        return (float("nan"), float("nan"))
    return (float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5)))
