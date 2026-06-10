"""Correlation clustering for the TargetPortfolioBuilder (Fix #3, 2026-06-09 eval).

The FOMC week showed the 8 "diversified" theses are really ~1.5 correlated
bets: both books' invested sleeves fell ~4x SPY. Sector caps miss this —
CCJ (utilities), GLD (gold), MU (tech) all moved together on rates.

compute_clusters() groups symbols whose trailing daily-return correlation
exceeds a threshold into connected components, using price history. The
builder then caps each multi-symbol cluster's total weight (default 50%),
scaling members down proportionally. Pure-math clustering is separated from
the network fetch so it's unit-testable.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

DEFAULT_CORR_THRESHOLD = 0.60
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_MAX_CLUSTER_PCT = 0.50


def clusters_from_correlation(
    corr: dict[tuple[str, str], float],
    symbols: list[str],
    threshold: float = DEFAULT_CORR_THRESHOLD,
) -> list[set[str]]:
    """Connected components over the corr>threshold graph. Pure function.

    Returns only multi-symbol clusters (singletons are not a concentration).
    """
    parent = {s: s for s in symbols}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for (a, b), c in corr.items():
        if a in parent and b in parent and c >= threshold:
            union(a, b)

    groups: dict[str, set[str]] = {}
    for s in symbols:
        groups.setdefault(find(s), set()).add(s)
    return [g for g in groups.values() if len(g) > 1]


def compute_clusters(
    symbols: list[str],
    threshold: float = DEFAULT_CORR_THRESHOLD,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[set[str]] | None:
    """Fetch trailing closes and cluster correlated symbols.

    Returns None on data failure — callers treat None as "no cluster info,
    skip the cap" (graceful degradation; the position/sector caps still apply).
    """
    try:
        import yfinance as yf

        closes = {}
        for s in sorted(set(symbols)):
            h = yf.Ticker(s).history(period=f"{lookback_days + 10}d")["Close"].dropna()
            if len(h) >= 30:
                closes[s] = h.pct_change().dropna()
        if len(closes) < 2:
            return None

        syms = sorted(closes)
        corr: dict[tuple[str, str], float] = {}
        for i, a in enumerate(syms):
            for b in syms[i + 1:]:
                ra, rb = closes[a].align(closes[b], join="inner")
                if len(ra) < 30:
                    continue
                ca = ra.corr(rb)
                if ca is not None and not math.isnan(ca):
                    corr[(a, b)] = float(ca)

        clusters = clusters_from_correlation(corr, syms, threshold)
        if clusters:
            logger.info(f"Correlation clusters (>{threshold}): "
                        f"{[sorted(c) for c in clusters]}")
        return clusters
    except Exception as e:
        logger.warning(f"Cluster computation failed ({e}); cluster cap skipped")
        return None


def apply_cluster_cap(weights: dict, clusters: list[set[str]],
                      max_cluster_pct: float = DEFAULT_MAX_CLUSTER_PCT) -> None:
    """Scale down any cluster exceeding the cap, proportionally. Mutates weights.

    `weights` is the builder's dict[str, TargetWeight].
    """
    for cluster in clusters:
        members = [weights[s] for s in cluster if s in weights]
        total = sum(m.weight for m in members)
        if total > max_cluster_pct and total > 0:
            scale = max_cluster_pct / total
            for m in members:
                m.weight *= scale
                m.bounded_by = m.bounded_by or "correlation_cluster"
            logger.info(f"Cluster {sorted(cluster)} capped "
                        f"{total:.1%} -> {max_cluster_pct:.1%}")
