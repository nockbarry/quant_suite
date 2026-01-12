#!/usr/bin/env python3
"""Congressional Cluster Buying Study.

Tests whether CLUSTER BUYING (3+ politicians buying the same stock within a window)
has predictive value, separate from aggregate congressional trades.

Hypothesis: When multiple politicians buy the same stock around the same time,
they may be acting on shared information (committee briefings, legislation, etc.)

Key Questions:
1. Do cluster buys outperform individual buys?
2. Do cluster buys outperform the market?
3. Does cluster size matter (3 vs 5+ politicians)?
4. Do notable trader clusters perform better?

Usage:
    PYTHONPATH=. python scripts/congressional_cluster_study.py
    PYTHONPATH=. python scripts/congressional_cluster_study.py --min-traders 3 --window 30
"""

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Notable traders with historically good performance
NOTABLE_TRADERS = {
    "Nancy Pelosi", "Dan Crenshaw", "Tommy Tuberville", "Josh Gottheimer",
    "Ro Khanna", "Austin Scott", "Michael McCaul", "Mark Green",
}


@dataclass
class ClusterEvent:
    """A cluster of congressional buys in the same symbol."""

    symbol: str
    cluster_start: datetime
    cluster_end: datetime
    unique_traders: int
    total_trades: int
    notable_trader_count: int
    total_volume: float  # Estimated dollar volume
    traders: list[str] = field(default_factory=list)

    # Returns after cluster formation
    return_5d: float | None = None
    return_10d: float | None = None
    return_20d: float | None = None
    return_30d: float | None = None
    return_60d: float | None = None

    # Benchmark
    spy_return_30d: float | None = None
    excess_return_30d: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "cluster_start": self.cluster_start.isoformat(),
            "cluster_end": self.cluster_end.isoformat(),
            "unique_traders": self.unique_traders,
            "total_trades": self.total_trades,
            "notable_trader_count": self.notable_trader_count,
            "total_volume": self.total_volume,
            "traders": self.traders,
            "return_5d": self.return_5d,
            "return_10d": self.return_10d,
            "return_20d": self.return_20d,
            "return_30d": self.return_30d,
            "return_60d": self.return_60d,
            "spy_return_30d": self.spy_return_30d,
            "excess_return_30d": self.excess_return_30d,
        }


@dataclass
class IndividualTrade:
    """Individual congressional trade for comparison."""

    symbol: str
    politician: str
    transaction_date: datetime
    amount_estimate: float
    is_notable: bool

    return_30d: float | None = None
    spy_return_30d: float | None = None
    excess_return_30d: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "politician": self.politician,
            "transaction_date": self.transaction_date.isoformat(),
            "amount_estimate": self.amount_estimate,
            "is_notable": self.is_notable,
            "return_30d": self.return_30d,
            "spy_return_30d": self.spy_return_30d,
            "excess_return_30d": self.excess_return_30d,
        }


def load_congressional_trades() -> pd.DataFrame:
    """Load archived congressional trades."""
    parquet_path = paths.base / "congressional_archive" / "processed" / "all_trades.parquet"

    if not parquet_path.exists():
        raise FileNotFoundError(f"Archive not found at {parquet_path}. Run backfill first.")

    df = pd.read_parquet(parquet_path)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])

    return df


def detect_clusters(
    trades_df: pd.DataFrame,
    min_traders: int = 3,
    window_days: int = 30,
) -> list[ClusterEvent]:
    """Detect cluster buying events."""

    # Filter to purchases only
    purchases = trades_df[trades_df["trade_type"] == "purchase"].copy()

    # Filter valid symbols
    purchases = purchases[
        (purchases["symbol"].notna()) &
        (purchases["symbol"] != "--") &
        (purchases["symbol"].str.len() <= 5)
    ]

    logger.info(f"Analyzing {len(purchases)} purchase trades for clusters")

    clusters = []
    symbols = purchases["symbol"].unique()

    for symbol in symbols:
        symbol_trades = purchases[purchases["symbol"] == symbol].sort_values("transaction_date")

        if len(symbol_trades) < min_traders:
            continue

        # Sliding window to detect clusters
        i = 0
        while i < len(symbol_trades):
            window_start = symbol_trades.iloc[i]["transaction_date"]
            window_end = window_start + timedelta(days=window_days)

            # Find all trades in this window
            window_trades = symbol_trades[
                (symbol_trades["transaction_date"] >= window_start) &
                (symbol_trades["transaction_date"] <= window_end)
            ]

            unique_traders = window_trades["politician"].nunique()

            if unique_traders >= min_traders:
                # Found a cluster
                traders = window_trades["politician"].unique().tolist()
                notable_count = sum(1 for t in traders if t in NOTABLE_TRADERS)

                cluster = ClusterEvent(
                    symbol=symbol,
                    cluster_start=window_trades["transaction_date"].min(),
                    cluster_end=window_trades["transaction_date"].max(),
                    unique_traders=unique_traders,
                    total_trades=len(window_trades),
                    notable_trader_count=notable_count,
                    total_volume=window_trades["amount_estimate"].sum(),
                    traders=traders,
                )
                clusters.append(cluster)

                # Skip past this cluster
                i += len(window_trades)
            else:
                i += 1

    logger.info(f"Detected {len(clusters)} cluster events")
    return clusters


def get_individual_trades(
    trades_df: pd.DataFrame,
    cluster_symbols: set[str],
) -> list[IndividualTrade]:
    """Get individual (non-cluster) trades for comparison."""

    purchases = trades_df[
        (trades_df["trade_type"] == "purchase") &
        (~trades_df["symbol"].isin(cluster_symbols)) &
        (trades_df["symbol"].notna()) &
        (trades_df["symbol"] != "--") &
        (trades_df["symbol"].str.len() <= 5)
    ]

    individuals = []
    for _, row in purchases.iterrows():
        trade = IndividualTrade(
            symbol=row["symbol"],
            politician=row["politician"],
            transaction_date=row["transaction_date"],
            amount_estimate=row["amount_estimate"],
            is_notable=row["politician"] in NOTABLE_TRADERS,
        )
        individuals.append(trade)

    return individuals


def get_price_data(symbols: list[str], start_date: datetime, end_date: datetime) -> dict[str, pd.DataFrame]:
    """Fetch price data for symbols."""
    price_data = {}

    buffered_start = start_date - timedelta(days=10)
    buffered_end = end_date + timedelta(days=90)

    all_symbols = list(set(symbols + ["SPY"]))

    logger.info(f"Downloading price data for {len(all_symbols)} symbols...")

    try:
        data = yf.download(
            all_symbols,
            start=buffered_start,
            end=buffered_end,
            progress=False,
            group_by="ticker",
            threads=True,
            auto_adjust=True,
        )

        if len(all_symbols) == 1:
            symbol = all_symbols[0]
            if not data.empty:
                price_data[symbol] = data[["Close"]].dropna()
        else:
            for symbol in all_symbols:
                try:
                    if symbol in data.columns.get_level_values(0):
                        symbol_data = data[symbol][["Close"]].dropna()
                        if not symbol_data.empty:
                            price_data[symbol] = symbol_data
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"Download failed: {e}")

    logger.info(f"Got price data for {len(price_data)} symbols")
    return price_data


def calculate_return(prices: pd.DataFrame, start_date: datetime, days: int) -> float | None:
    """Calculate return from start_date over N days."""
    if prices.empty:
        return None

    try:
        target = pd.Timestamp(start_date.date())
        start_idx = prices.index.get_indexer([target], method="bfill")[0]
        end_idx = start_idx + days

        if start_idx >= 0 and end_idx < len(prices):
            start_price = prices.iloc[start_idx]["Close"]
            end_price = prices.iloc[end_idx]["Close"]

            if start_price > 0:
                return (end_price - start_price) / start_price * 100
    except Exception:
        pass

    return None


def analyze_clusters(
    clusters: list[ClusterEvent],
    individuals: list[IndividualTrade],
    price_data: dict[str, pd.DataFrame],
) -> tuple[list[ClusterEvent], list[IndividualTrade]]:
    """Calculate returns for clusters and individuals."""

    spy_prices = price_data.get("SPY", pd.DataFrame())

    # Analyze clusters
    for cluster in clusters:
        if cluster.symbol not in price_data:
            continue

        prices = price_data[cluster.symbol]
        start_date = cluster.cluster_end  # Measure from end of cluster formation

        cluster.return_5d = calculate_return(prices, start_date, 5)
        cluster.return_10d = calculate_return(prices, start_date, 10)
        cluster.return_20d = calculate_return(prices, start_date, 20)
        cluster.return_30d = calculate_return(prices, start_date, 30)
        cluster.return_60d = calculate_return(prices, start_date, 60)

        if not spy_prices.empty:
            cluster.spy_return_30d = calculate_return(spy_prices, start_date, 30)
            if cluster.return_30d is not None and cluster.spy_return_30d is not None:
                cluster.excess_return_30d = cluster.return_30d - cluster.spy_return_30d

    # Analyze individuals (sample for efficiency)
    sample_individuals = individuals[:2000] if len(individuals) > 2000 else individuals

    for trade in sample_individuals:
        if trade.symbol not in price_data:
            continue

        prices = price_data[trade.symbol]
        trade.return_30d = calculate_return(prices, trade.transaction_date, 30)

        if not spy_prices.empty:
            trade.spy_return_30d = calculate_return(spy_prices, trade.transaction_date, 30)
            if trade.return_30d is not None and trade.spy_return_30d is not None:
                trade.excess_return_30d = trade.return_30d - trade.spy_return_30d

    return clusters, sample_individuals


def calculate_statistics(
    clusters: list[ClusterEvent],
    individuals: list[IndividualTrade],
) -> dict[str, Any]:
    """Calculate comprehensive statistics."""

    stats_dict = {
        "total_clusters": len(clusters),
        "total_individuals_sampled": len(individuals),
    }

    # Cluster statistics
    cluster_df = pd.DataFrame([c.to_dict() for c in clusters])

    if not cluster_df.empty:
        valid_30d = cluster_df["return_30d"].dropna()
        valid_excess = cluster_df["excess_return_30d"].dropna()

        stats_dict["clusters_with_data"] = len(valid_30d)
        stats_dict["cluster_avg_return_30d"] = valid_30d.mean()
        stats_dict["cluster_median_return_30d"] = valid_30d.median()
        stats_dict["cluster_std_return_30d"] = valid_30d.std()
        stats_dict["cluster_positive_rate"] = (valid_30d > 0).mean()

        if len(valid_excess) > 0:
            stats_dict["cluster_avg_excess_30d"] = valid_excess.mean()
            stats_dict["cluster_excess_positive_rate"] = (valid_excess > 0).mean()

        # By cluster size
        for size in [3, 4, 5]:
            size_clusters = cluster_df[cluster_df["unique_traders"] >= size]["return_30d"].dropna()
            if len(size_clusters) > 5:
                stats_dict[f"cluster_{size}plus_avg_return"] = size_clusters.mean()
                stats_dict[f"cluster_{size}plus_count"] = len(size_clusters)

        # Notable trader clusters
        notable_clusters = cluster_df[cluster_df["notable_trader_count"] > 0]["return_30d"].dropna()
        if len(notable_clusters) > 5:
            stats_dict["notable_cluster_avg_return"] = notable_clusters.mean()
            stats_dict["notable_cluster_count"] = len(notable_clusters)

        non_notable = cluster_df[cluster_df["notable_trader_count"] == 0]["return_30d"].dropna()
        if len(non_notable) > 5:
            stats_dict["non_notable_cluster_avg_return"] = non_notable.mean()

    # Individual statistics
    individual_df = pd.DataFrame([i.to_dict() for i in individuals])

    if not individual_df.empty:
        valid_30d = individual_df["return_30d"].dropna()
        valid_excess = individual_df["excess_return_30d"].dropna()

        stats_dict["individual_with_data"] = len(valid_30d)
        stats_dict["individual_avg_return_30d"] = valid_30d.mean()
        stats_dict["individual_median_return_30d"] = valid_30d.median()
        stats_dict["individual_positive_rate"] = (valid_30d > 0).mean()

        if len(valid_excess) > 0:
            stats_dict["individual_avg_excess_30d"] = valid_excess.mean()

    # Statistical comparison: clusters vs individuals
    cluster_returns = cluster_df["return_30d"].dropna()
    individual_returns = individual_df["return_30d"].dropna()

    if len(cluster_returns) > 10 and len(individual_returns) > 30:
        t_stat, p_value = stats.ttest_ind(cluster_returns, individual_returns)
        stats_dict["cluster_vs_individual_t_stat"] = t_stat
        stats_dict["cluster_vs_individual_p_value"] = p_value

    # Test if cluster returns are significantly > 0
    if len(cluster_returns) > 10:
        t_stat, p_value = stats.ttest_1samp(cluster_returns, 0)
        stats_dict["cluster_vs_zero_t_stat"] = t_stat
        stats_dict["cluster_vs_zero_p_value"] = p_value

    return stats_dict


def generate_report(
    stats: dict[str, Any],
    clusters: list[ClusterEvent],
    individuals: list[IndividualTrade],
    output_dir: Path,
) -> str:
    """Generate cluster study report."""

    cluster_df = pd.DataFrame([c.to_dict() for c in clusters])

    report = f"""
# Congressional Cluster Buying Study

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Total Cluster Events:** {stats.get('total_clusters', 0)}
**Individual Trades Sampled:** {stats.get('total_individuals_sampled', 0)}

---

## Executive Summary

This study tests whether **cluster buying** (3+ politicians buying the same stock)
outperforms individual congressional trades and the market.

### Key Metrics

| Metric | Clusters | Individual Trades | Difference |
|--------|----------|-------------------|------------|
| Avg 30-day Return | {stats.get('cluster_avg_return_30d', 0):+.2f}% | {stats.get('individual_avg_return_30d', 0):+.2f}% | {stats.get('cluster_avg_return_30d', 0) - stats.get('individual_avg_return_30d', 0):+.2f}% |
| Median 30-day Return | {stats.get('cluster_median_return_30d', 0):+.2f}% | {stats.get('individual_median_return_30d', 0):+.2f}% | - |
| Win Rate (>0%) | {stats.get('cluster_positive_rate', 0)*100:.1f}% | {stats.get('individual_positive_rate', 0)*100:.1f}% | - |
| Avg Excess vs SPY | {stats.get('cluster_avg_excess_30d', 0):+.2f}% | {stats.get('individual_avg_excess_30d', 0):+.2f}% | - |

### Statistical Significance

| Test | T-Statistic | P-Value | Significant? |
|------|-------------|---------|--------------|
| Clusters vs Individual | {stats.get('cluster_vs_individual_t_stat', 0):.2f} | {stats.get('cluster_vs_individual_p_value', 1):.4f} | {"Yes" if stats.get('cluster_vs_individual_p_value', 1) < 0.05 else "No"} |
| Clusters vs Zero | {stats.get('cluster_vs_zero_t_stat', 0):.2f} | {stats.get('cluster_vs_zero_p_value', 1):.4f} | {"Yes" if stats.get('cluster_vs_zero_p_value', 1) < 0.05 else "No"} |

---

## 1. Cluster Size Analysis

**Question:** Do larger clusters (more politicians) perform better?

| Cluster Size | Count | Avg 30-day Return |
|--------------|-------|-------------------|
| 3+ politicians | {stats.get('cluster_3plus_count', 0)} | {stats.get('cluster_3plus_avg_return', 0):+.2f}% |
| 4+ politicians | {stats.get('cluster_4plus_count', 0)} | {stats.get('cluster_4plus_avg_return', 0):+.2f}% |
| 5+ politicians | {stats.get('cluster_5plus_count', 0)} | {stats.get('cluster_5plus_avg_return', 0):+.2f}% |

"""

    # Determine if larger clusters perform better
    size_3 = stats.get('cluster_3plus_avg_return', 0)
    size_5 = stats.get('cluster_5plus_avg_return', 0)

    if stats.get('cluster_5plus_count', 0) >= 5:
        if size_5 > size_3 + 1:
            report += """
**FINDING: Larger Clusters Outperform**
Clusters with 5+ politicians show stronger returns than smaller clusters.
This suggests consensus among many politicians may be a stronger signal.
"""
        elif size_5 < size_3 - 1:
            report += """
**FINDING: Smaller Clusters Outperform**
Larger clusters (5+) actually underperform smaller ones.
This may indicate crowding or that smaller coordinated groups have better information.
"""
        else:
            report += """
**FINDING: Cluster Size Has Limited Impact**
Returns are similar across cluster sizes.
"""

    report += f"""
---

## 2. Notable Trader Clusters

**Question:** Do clusters with notable traders (Pelosi, Tuberville, etc.) perform better?

| Type | Count | Avg 30-day Return |
|------|-------|-------------------|
| Clusters with Notable Traders | {stats.get('notable_cluster_count', 0)} | {stats.get('notable_cluster_avg_return', 0):+.2f}% |
| Clusters without Notable Traders | {len(clusters) - stats.get('notable_cluster_count', 0)} | {stats.get('non_notable_cluster_avg_return', 0):+.2f}% |

"""

    notable_return = stats.get('notable_cluster_avg_return', 0)
    non_notable_return = stats.get('non_notable_cluster_avg_return', 0)

    if stats.get('notable_cluster_count', 0) >= 5:
        if notable_return > non_notable_return + 1:
            report += """
**FINDING: Notable Trader Clusters Outperform**
When notable traders like Pelosi or Tuberville participate in cluster buying,
returns are significantly higher. Consider extra weight for these signals.
"""
        else:
            report += """
**FINDING: Notable Traders Don't Add Edge**
Clusters perform similarly regardless of notable trader participation.
"""

    # Top performing clusters
    if not cluster_df.empty:
        valid_clusters = cluster_df[cluster_df["return_30d"].notna()].copy()
        top_clusters = valid_clusters.nlargest(15, "return_30d")

        report += """
---

## 3. Top Performing Clusters

| Symbol | Traders | Notable | Est. Volume | 30d Return | 60d Return |
|--------|---------|---------|-------------|------------|------------|
"""

        for _, row in top_clusters.iterrows():
            traders_str = str(row['unique_traders'])
            notable_str = str(row['notable_trader_count'])
            vol_str = f"${row['total_volume']/1000:.0f}K" if row['total_volume'] > 0 else "N/A"
            ret_30 = f"{row['return_30d']:+.1f}%" if pd.notna(row['return_30d']) else "N/A"
            ret_60 = f"{row['return_60d']:+.1f}%" if pd.notna(row['return_60d']) else "N/A"
            report += f"| {row['symbol']} | {traders_str} | {notable_str} | {vol_str} | {ret_30} | {ret_60} |\n"

    # Conclusion
    report += """
---

## 4. Conclusions and Trading Recommendations

"""

    cluster_excess = stats.get('cluster_avg_excess_30d', 0)
    cluster_vs_ind = stats.get('cluster_avg_return_30d', 0) - stats.get('individual_avg_return_30d', 0)
    p_value = stats.get('cluster_vs_individual_p_value', 1)

    if cluster_excess > 1 and p_value < 0.1:
        report += f"""
### CLUSTER SIGNAL HAS VALUE

Cluster buying shows promise as a trading signal:
- **Excess return vs SPY:** {cluster_excess:+.2f}%
- **Outperformance vs individual trades:** {cluster_vs_ind:+.2f}%
- **Statistical significance:** {"Strong" if p_value < 0.05 else "Marginal"} (p={p_value:.4f})

### Recommended Implementation

1. **Alert on New Clusters**
   - Trigger when 3+ politicians buy same stock within 30 days
   - Higher priority for 4+ or 5+ politician clusters
   - Extra weight if notable traders participate

2. **Position Sizing**
   - 3 politician cluster: Standard position
   - 4+ politician cluster: 1.5x standard
   - 5+ with notable: 2x standard

3. **Holding Period**
   - Target 30-60 day hold based on analysis
   - Use 20-day ATR for stop placement

4. **Integration**
   - Add cluster signal to unified state
   - Cross-reference with sector thesis
   - Combine with technical confirmation
"""
    elif cluster_excess > 0:
        report += f"""
### CLUSTER SIGNAL SHOWS MARGINAL EDGE

Cluster buying has a slight edge but not statistically significant:
- **Excess return vs SPY:** {cluster_excess:+.2f}%
- **P-value:** {p_value:.4f} (not significant at 5%)

### Recommended Approach

1. Use as confirmatory signal, not primary driver
2. Combine with other signals (technicals, options flow)
3. Focus on larger clusters (4+) and notable traders
4. Continue collecting data for more statistical power
"""
    else:
        report += f"""
### CLUSTER SIGNAL HAS LIMITED VALUE

Cluster buying does not show meaningful edge in this analysis:
- **Excess return vs SPY:** {cluster_excess:+.2f}%
- **P-value:** {p_value:.4f}

### Recommendation

Do not weight cluster buying heavily in trading decisions.
The "wisdom of crowds" does not appear to work for congressional traders.
"""

    report += """
---

## Technical Notes

- Cluster defined as 3+ unique politicians buying within 30-day window
- Returns measured from end of cluster formation period
- Individual trades exclude symbols that had clusters
- Notable traders: Pelosi, Tuberville, Gottheimer, McCaul, Crenshaw, Khanna, Scott, Green

"""

    return report


def run_cluster_study(
    min_traders: int = 3,
    window_days: int = 30,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run complete cluster buying study."""

    output_dir = output_dir or paths.base / "congressional_cluster_study"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting cluster study (min_traders={min_traders}, window={window_days} days)")

    # Load trades
    trades_df = load_congressional_trades()
    logger.info(f"Loaded {len(trades_df)} trades")

    # Filter date range
    trades_df = trades_df[
        (trades_df["transaction_date"] >= "2015-01-01") &
        (trades_df["transaction_date"] <= "2022-06-30")
    ]

    # Detect clusters
    clusters = detect_clusters(trades_df, min_traders, window_days)

    if not clusters:
        return {"error": "No clusters found"}

    # Get individual trades for comparison
    cluster_symbols = {c.symbol for c in clusters}
    individuals = get_individual_trades(trades_df, cluster_symbols)
    logger.info(f"Got {len(individuals)} individual trades for comparison")

    # Get date range
    all_dates = [c.cluster_end for c in clusters]
    start_date = min(all_dates)
    end_date = max(all_dates)

    # Get price data
    all_symbols = list({c.symbol for c in clusters} | {i.symbol for i in individuals[:1000]})
    price_data = get_price_data(all_symbols, start_date, end_date)

    # Analyze returns
    logger.info("Calculating returns...")
    clusters, individuals = analyze_clusters(clusters, individuals, price_data)

    # Calculate statistics
    stats = calculate_statistics(clusters, individuals)

    # Generate report
    report = generate_report(stats, clusters, individuals, output_dir)

    # Save outputs
    report_path = output_dir / "cluster_study_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    results_path = output_dir / "cluster_study_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "parameters": {"min_traders": min_traders, "window_days": window_days},
            "statistics": stats,
        }, f, indent=2, default=str)

    # Save cluster details
    cluster_df = pd.DataFrame([c.to_dict() for c in clusters])
    cluster_df.to_parquet(output_dir / "cluster_events.parquet")

    # Print summary
    print("\n" + "=" * 70)
    print("CONGRESSIONAL CLUSTER BUYING STUDY - SUMMARY")
    print("=" * 70)
    print(f"\nClusters detected: {len(clusters)}")
    print(f"Individual trades compared: {len(individuals)}")

    print("\n📊 KEY FINDINGS:")
    print(f"  Cluster avg 30d return: {stats.get('cluster_avg_return_30d', 0):+.2f}%")
    print(f"  Individual avg 30d return: {stats.get('individual_avg_return_30d', 0):+.2f}%")
    print(f"  Cluster excess vs SPY: {stats.get('cluster_avg_excess_30d', 0):+.2f}%")

    p_val = stats.get('cluster_vs_individual_p_value', 1)
    if p_val < 0.05:
        print(f"\n  ✅ CLUSTERS SIGNIFICANTLY OUTPERFORM (p={p_val:.4f})")
    elif p_val < 0.1:
        print(f"\n  ⚠️  Marginal significance (p={p_val:.4f})")
    else:
        print(f"\n  ❌ Not statistically significant (p={p_val:.4f})")

    print(f"\n📁 Full report: {report_path}")

    return {
        "clusters_detected": len(clusters),
        "statistics": stats,
        "report_path": str(report_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Congressional Cluster Buying Study")
    parser.add_argument("--min-traders", type=int, default=3, help="Minimum politicians for cluster")
    parser.add_argument("--window", type=int, default=30, help="Window in days for cluster detection")
    parser.add_argument("--output", type=str, help="Output directory")

    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else None
    run_cluster_study(min_traders=args.min_traders, window_days=args.window, output_dir=output_dir)


if __name__ == "__main__":
    main()
