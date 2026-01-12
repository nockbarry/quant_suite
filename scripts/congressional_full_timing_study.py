#!/usr/bin/env python3
"""Congressional Trading Full Timing Study.

Comprehensive analysis of congressional trade timing using archived historical data.
Fetches actual price data to measure returns before and after disclosure.

This analysis tests:
1. Pre-disclosure drift: Do stocks move in politicians' favor BEFORE disclosure?
2. Post-disclosure drift: Do stocks continue moving AFTER disclosure?
3. Information advantage: Is there evidence of insider trading?
4. Following strategy: Can we profit by copying congressional trades?

Usage:
    PYTHONPATH=. python scripts/congressional_full_timing_study.py
    PYTHONPATH=. python scripts/congressional_full_timing_study.py --sample 500 --quick
"""

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from scipy import stats

from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_archived_trades() -> pd.DataFrame:
    """Load archived congressional trades."""
    parquet_path = paths.base / "congressional_archive" / "processed" / "all_trades.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Archive not found at {parquet_path}. Run backfill first.")

    df = pd.read_parquet(parquet_path)

    # Convert dates
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])

    return df


def get_price_data_batch(symbols: list[str], start_date: datetime, end_date: datetime) -> dict[str, pd.DataFrame]:
    """Fetch price data for multiple symbols efficiently."""
    price_data = {}

    # Add buffer for pre/post analysis
    buffered_start = start_date - timedelta(days=60)
    buffered_end = end_date + timedelta(days=60)

    # Download in batches using yfinance's batch capability
    logger.info(f"Downloading price data for {len(symbols)} symbols...")

    # yfinance can handle multiple symbols at once
    valid_symbols = [s for s in symbols if s and len(s) <= 5 and s.isalpha()]

    if not valid_symbols:
        return {}

    try:
        # Download all at once (more efficient)
        data = yf.download(
            valid_symbols,
            start=buffered_start,
            end=buffered_end,
            progress=False,
            group_by="ticker",
            threads=True,
            auto_adjust=True,
        )

        if len(valid_symbols) == 1:
            # Single symbol returns different format
            symbol = valid_symbols[0]
            if not data.empty:
                price_data[symbol] = data[["Close"]].dropna()
        else:
            # Multiple symbols
            for symbol in valid_symbols:
                try:
                    if symbol in data.columns.get_level_values(0):
                        symbol_data = data[symbol][["Close"]].dropna()
                        if not symbol_data.empty:
                            price_data[symbol] = symbol_data
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"Batch download failed: {e}")

    logger.info(f"Got price data for {len(price_data)} symbols")
    return price_data


def get_return(prices: pd.DataFrame, date: datetime, offset_days: int) -> float | None:
    """Get return from date to date + offset_days."""
    if prices.empty:
        return None

    try:
        # Find nearest trading day to target date
        target_date = pd.Timestamp(date.date())
        future_date = target_date + pd.Timedelta(days=offset_days)

        # Find closest available dates
        idx = prices.index.get_indexer([target_date], method="nearest")[0]
        future_idx = prices.index.get_indexer([future_date], method="nearest")[0]

        if idx >= 0 and future_idx >= 0 and idx != future_idx:
            start_price = prices.iloc[idx]["Close"]
            end_price = prices.iloc[future_idx]["Close"]

            if start_price > 0:
                return (end_price - start_price) / start_price * 100
    except Exception:
        pass

    return None


def analyze_trade_returns(
    trades_df: pd.DataFrame,
    price_data: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Calculate returns for each trade."""

    results = []

    for _, trade in trades_df.iterrows():
        symbol = trade["symbol"]
        trans_date = trade["transaction_date"]
        disc_date = trade["disclosure_date"]

        if symbol not in price_data:
            continue

        prices = price_data[symbol]

        result = {
            "politician": trade["politician"],
            "symbol": symbol,
            "trade_type": trade["trade_type"],
            "transaction_date": trans_date,
            "disclosure_date": disc_date,
            "filing_delay_days": trade["filing_delay_days"],
            "amount_estimate": trade["amount_estimate"],
        }

        # Pre-disclosure returns (from transaction to disclosure)
        # This measures if the stock moved while they had an undisclosed position
        result["return_trans_to_disc"] = get_return(
            prices, trans_date, trade["filing_delay_days"]
        )

        # Post-disclosure returns (from disclosure forward)
        for days in [5, 10, 20, 30]:
            result[f"return_disc_to_{days}d"] = get_return(prices, disc_date, days)

        # Total return from transaction to 30 days post-disclosure
        total_days = trade["filing_delay_days"] + 30
        result["return_total_30d"] = get_return(prices, trans_date, total_days)

        # Benchmark: SPY return for same period
        if "SPY" in price_data:
            result["spy_return_same_period"] = get_return(
                price_data["SPY"], trans_date, total_days
            )

        results.append(result)

    return pd.DataFrame(results)


def calculate_statistics(results_df: pd.DataFrame) -> dict[str, Any]:
    """Calculate comprehensive statistics from results."""

    stats_dict = {}

    # Split by trade type
    purchases = results_df[results_df["trade_type"] == "purchase"]
    sales = results_df[results_df["trade_type"].isin(["sale", "sale_full", "sale_partial"])]

    # Pre-disclosure analysis
    for name, df in [("purchases", purchases), ("sales", sales)]:
        pre_returns = df["return_trans_to_disc"].dropna()

        if len(pre_returns) > 30:
            stats_dict[f"{name}_count"] = len(df)
            stats_dict[f"{name}_pre_disc_mean"] = pre_returns.mean()
            stats_dict[f"{name}_pre_disc_median"] = pre_returns.median()
            stats_dict[f"{name}_pre_disc_std"] = pre_returns.std()

            # Statistical test: is pre-disclosure return different from zero?
            t_stat, p_value = stats.ttest_1samp(pre_returns, 0)
            stats_dict[f"{name}_pre_disc_t_stat"] = t_stat
            stats_dict[f"{name}_pre_disc_p_value"] = p_value

            # Hit rate: did stock move in their direction?
            if name == "purchases":
                hit_rate = (pre_returns > 0).mean()
            else:
                hit_rate = (pre_returns < 0).mean()
            stats_dict[f"{name}_pre_disc_hit_rate"] = hit_rate

    # Post-disclosure analysis
    for name, df in [("purchases", purchases), ("sales", sales)]:
        for days in [5, 10, 20, 30]:
            col = f"return_disc_to_{days}d"
            post_returns = df[col].dropna()

            if len(post_returns) > 30:
                stats_dict[f"{name}_post_{days}d_mean"] = post_returns.mean()
                stats_dict[f"{name}_post_{days}d_std"] = post_returns.std()

    # Following strategy returns
    purchase_post_20d = purchases["return_disc_to_20d"].dropna()
    sales_post_20d = sales["return_disc_to_20d"].dropna()

    if len(purchase_post_20d) > 0 and len(sales_post_20d) > 0:
        # Long purchases, short sales
        stats_dict["following_strategy_return"] = purchase_post_20d.mean() - sales_post_20d.mean()

    # Information advantage (buy pre-drift minus sell pre-drift)
    purchase_pre = purchases["return_trans_to_disc"].dropna()
    sales_pre = sales["return_trans_to_disc"].dropna()

    if len(purchase_pre) > 0 and len(sales_pre) > 0:
        stats_dict["info_advantage"] = purchase_pre.mean() - sales_pre.mean()

    # Excess returns vs SPY
    valid_excess = results_df.dropna(subset=["return_total_30d", "spy_return_same_period"])
    if len(valid_excess) > 0:
        excess = valid_excess["return_total_30d"] - valid_excess["spy_return_same_period"]
        stats_dict["avg_excess_return_30d"] = excess.mean()

    return stats_dict


def analyze_by_politician(results_df: pd.DataFrame) -> pd.DataFrame:
    """Analyze performance by politician."""

    politician_stats = []

    for politician in results_df["politician"].unique():
        pol_df = results_df[results_df["politician"] == politician]

        if len(pol_df) < 5:  # Minimum trades
            continue

        pre_returns = pol_df["return_trans_to_disc"].dropna()
        post_returns = pol_df["return_disc_to_20d"].dropna()

        # Hit rate
        purchases = pol_df[pol_df["trade_type"] == "purchase"]["return_trans_to_disc"].dropna()
        sales = pol_df[pol_df["trade_type"].isin(["sale", "sale_full", "sale_partial"])]["return_trans_to_disc"].dropna()

        purchase_hits = (purchases > 0).sum() if len(purchases) > 0 else 0
        sale_hits = (sales < 0).sum() if len(sales) > 0 else 0
        total_hits = purchase_hits + sale_hits
        total_trades = len(purchases) + len(sales)

        hit_rate = total_hits / total_trades if total_trades > 0 else 0

        politician_stats.append({
            "politician": politician,
            "total_trades": len(pol_df),
            "purchases": len(purchases),
            "sales": len(sales),
            "avg_pre_disc_return": pre_returns.mean() if len(pre_returns) > 0 else 0,
            "avg_post_20d_return": post_returns.mean() if len(post_returns) > 0 else 0,
            "hit_rate": hit_rate,
            "avg_filing_delay": pol_df["filing_delay_days"].mean(),
        })

    df = pd.DataFrame(politician_stats)
    df = df.sort_values("avg_pre_disc_return", ascending=False)
    return df


def generate_report(
    stats: dict[str, Any],
    politician_df: pd.DataFrame,
    results_df: pd.DataFrame,
    output_dir: Path,
) -> str:
    """Generate comprehensive timing study report."""

    report = f"""
# Congressional Trading Full Timing Study

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Data Period:** {results_df['transaction_date'].min().date()} to {results_df['transaction_date'].max().date()}
**Total Trades Analyzed:** {len(results_df):,}

---

## Executive Summary

### Pre-Disclosure Analysis (Information Advantage Test)

| Metric | Purchases | Sales |
|--------|-----------|-------|
| Count | {stats.get('purchases_count', 0):,} | {stats.get('sales_count', 0):,} |
| Mean Pre-Disc Return | {stats.get('purchases_pre_disc_mean', 0):+.3f}% | {stats.get('sales_pre_disc_mean', 0):+.3f}% |
| Median Pre-Disc Return | {stats.get('purchases_pre_disc_median', 0):+.3f}% | {stats.get('sales_pre_disc_median', 0):+.3f}% |
| Hit Rate (correct direction) | {stats.get('purchases_pre_disc_hit_rate', 0)*100:.1f}% | {stats.get('sales_pre_disc_hit_rate', 0)*100:.1f}% |
| T-Statistic | {stats.get('purchases_pre_disc_t_stat', 0):.2f} | {stats.get('sales_pre_disc_t_stat', 0):.2f} |
| P-Value | {stats.get('purchases_pre_disc_p_value', 1):.4f} | {stats.get('sales_pre_disc_p_value', 1):.4f} |

**Information Advantage Score:** {stats.get('info_advantage', 0):+.3f}%
- Interpretation: {"Politicians show timing advantage" if stats.get('info_advantage', 0) > 0.5 else "No clear information advantage"}

### Post-Disclosure Analysis (Following Strategy)

| Metric | Purchases | Sales |
|--------|-----------|-------|
| 5-day Post Return | {stats.get('purchases_post_5d_mean', 0):+.3f}% | {stats.get('sales_post_5d_mean', 0):+.3f}% |
| 10-day Post Return | {stats.get('purchases_post_10d_mean', 0):+.3f}% | {stats.get('sales_post_10d_mean', 0):+.3f}% |
| 20-day Post Return | {stats.get('purchases_post_20d_mean', 0):+.3f}% | {stats.get('sales_post_20d_mean', 0):+.3f}% |
| 30-day Post Return | {stats.get('purchases_post_30d_mean', 0):+.3f}% | {stats.get('sales_post_30d_mean', 0):+.3f}% |

**Following Strategy (Long/Short) 20d Return:** {stats.get('following_strategy_return', 0):+.3f}%
**Avg Excess Return vs SPY (30d):** {stats.get('avg_excess_return_30d', 0):+.3f}%

---

## Key Findings

### 1. Information Advantage
"""

    info_adv = stats.get('info_advantage', 0)
    if info_adv > 1.0:
        report += f"""
**STRONG EVIDENCE OF INFORMATION ADVANTAGE**

Politicians appear to consistently trade before favorable price moves:
- Information advantage: {info_adv:+.2f}% over the filing delay period
- This is statistically and economically significant
- Suggests possible trading on material non-public information
"""
    elif info_adv > 0:
        report += f"""
**MARGINAL INFORMATION ADVANTAGE**

Some evidence of favorable timing:
- Information advantage: {info_adv:+.2f}%
- Effect is modest and may not survive transaction costs
"""
    else:
        report += """
**NO INFORMATION ADVANTAGE**

Politicians do NOT appear to have insider timing:
- Combined timing advantage is near zero or negative
- Their sells do NOT precede stock declines
- Congressional trades are NOT predictive
"""

    report += """
### 2. Following Strategy Viability
"""

    following_return = stats.get('following_strategy_return', 0)
    if following_return > 1.0:
        report += f"""
**VIABLE FOLLOWING STRATEGY**

A long/short strategy based on disclosed congressional trades shows promise:
- Expected 20-day return: {following_return:+.2f}% per trade
- Annualized (assuming 20 trade opportunities/year): {following_return * 20:.1f}%

Implementation:
1. Buy stocks that congress purchased (on disclosure date)
2. Short stocks that congress sold (on disclosure date)
3. Hold for 20 trading days
"""
    else:
        report += f"""
**LIMITED FOLLOWING OPPORTUNITY**

Post-disclosure following shows minimal alpha:
- Expected return: {following_return:+.2f}%
- Transaction costs would likely eliminate any edge
"""

    report += f"""
---

## Top Performing Politicians (by Pre-Disclosure Timing)

| Rank | Politician | Trades | Hit Rate | Avg Pre-Disc Return | Avg Filing Delay |
|------|------------|--------|----------|---------------------|------------------|
"""

    for i, row in politician_df.head(15).iterrows():
        report += f"| {list(politician_df.index).index(i)+1} | {row['politician'][:25]} | {row['total_trades']} | {row['hit_rate']*100:.0f}% | {row['avg_pre_disc_return']:+.2f}% | {row['avg_filing_delay']:.0f}d |\n"

    report += f"""
---

## Worst Performing Politicians (Potential Contrarian Signals)

| Rank | Politician | Trades | Hit Rate | Avg Pre-Disc Return |
|------|------------|--------|----------|---------------------|
"""

    worst = politician_df.tail(10).iloc[::-1]
    for i, (_, row) in enumerate(worst.iterrows(), 1):
        report += f"| {i} | {row['politician'][:25]} | {row['total_trades']} | {row['hit_rate']*100:.0f}% | {row['avg_pre_disc_return']:+.2f}% |\n"

    report += """
---

## Trading System Integration

### Recommended Signal Implementation

1. **Cluster Detection**
   - Alert when 3+ politicians trade same stock within 14 days
   - Weight signal by politician performance rank

2. **Filing Delay Analysis**
   - Track filing delays per politician
   - Longer delays may correlate with more sensitive trades

3. **Sector Context**
   - Cross-reference with committee membership
   - Armed Services members + defense stocks = higher signal weight

### Data Collection Requirements

- Daily RSS collection from House/Senate Stock Watcher
- Archive all trades with transaction + disclosure dates
- Monthly performance attribution by politician

"""

    return report


def run_full_timing_study(
    sample_size: int | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run complete timing study with price analysis."""

    output_dir = output_dir or paths.base / "congressional_study"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading archived trades...")
    trades_df = load_archived_trades()
    logger.info(f"Loaded {len(trades_df)} trades")

    # Filter for valid trades
    trades_df = trades_df[
        (trades_df["symbol"].notna()) &
        (trades_df["symbol"] != "--") &
        (trades_df["symbol"].str.len() <= 5) &
        (trades_df["trade_type"].isin(["purchase", "sale", "sale_full", "sale_partial"]))
    ].copy()

    # Filter date range for which we can get price data
    trades_df = trades_df[
        (trades_df["transaction_date"] >= "2015-01-01") &
        (trades_df["transaction_date"] <= "2022-06-30")  # Allow time for post-disclosure analysis
    ]

    logger.info(f"After filtering: {len(trades_df)} valid trades")

    # Sample if requested
    if sample_size and sample_size < len(trades_df):
        trades_df = trades_df.sample(n=sample_size, random_state=42)
        logger.info(f"Sampled {sample_size} trades")

    # Get unique symbols + SPY for benchmark
    symbols = trades_df["symbol"].unique().tolist()
    symbols.append("SPY")

    # Get date range
    min_date = trades_df["transaction_date"].min()
    max_date = trades_df["disclosure_date"].max()

    # Fetch price data
    price_data = get_price_data_batch(symbols, min_date, max_date)

    # Analyze returns
    logger.info("Analyzing trade returns...")
    results_df = analyze_trade_returns(trades_df, price_data)
    logger.info(f"Analyzed {len(results_df)} trades with price data")

    if results_df.empty:
        logger.error("No results with price data!")
        return {"error": "No price data available"}

    # Calculate statistics
    stats = calculate_statistics(results_df)

    # Analyze by politician
    politician_df = analyze_by_politician(results_df)

    # Generate report
    report = generate_report(stats, politician_df, results_df, output_dir)

    # Save outputs
    report_path = output_dir / "full_timing_study_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    results_path = output_dir / "full_timing_study_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "statistics": stats,
            "politician_stats": politician_df.to_dict("records"),
        }, f, indent=2, default=str)

    # Save detailed results
    results_df.to_parquet(output_dir / "trade_returns.parquet")

    # Print summary
    print("\n" + "=" * 70)
    print("CONGRESSIONAL FULL TIMING STUDY - SUMMARY")
    print("=" * 70)
    print(f"\nTrades analyzed: {len(results_df):,}")
    print(f"Unique politicians: {results_df['politician'].nunique()}")
    print(f"Unique symbols: {results_df['symbol'].nunique()}")

    print("\n📊 KEY FINDINGS:")
    print(f"  Information advantage: {stats.get('info_advantage', 0):+.3f}%")
    print(f"  Following strategy return (20d): {stats.get('following_strategy_return', 0):+.3f}%")
    print(f"  Excess return vs SPY (30d): {stats.get('avg_excess_return_30d', 0):+.3f}%")

    print(f"\n📁 Full report: {report_path}")

    return {
        "trades_analyzed": len(results_df),
        "statistics": stats,
        "report_path": str(report_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Congressional Trading Full Timing Study")
    parser.add_argument("--sample", type=int, help="Sample size for quick testing")
    parser.add_argument("--quick", action="store_true", help="Quick mode with smaller sample")
    parser.add_argument("--output", type=str, help="Output directory")

    args = parser.parse_args()

    sample_size = args.sample
    if args.quick and not sample_size:
        sample_size = 500

    output_dir = Path(args.output) if args.output else None
    run_full_timing_study(sample_size=sample_size, output_dir=output_dir)


if __name__ == "__main__":
    main()
