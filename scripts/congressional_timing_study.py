#!/usr/bin/env python3
"""Congressional Trading Timing Study.

Analyzes whether congressional trades predict future market movements.

Key Questions:
1. Do politicians trade BEFORE positive/negative news?
2. Does the stock move between transaction_date and disclosure_date?
3. Does the move continue after disclosure?
4. Which politicians have the best timing?

Usage:
    PYTHONPATH=. python scripts/congressional_timing_study.py
    PYTHONPATH=. python scripts/congressional_timing_study.py --days 90 --min-trades 5
"""

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.data.sources.alternative.congressional_trades import (
    CongressionalTrade,
    CongressionalTradesSource,
    TradeType,
)
from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class TradeTimingResult:
    """Result of timing analysis for a single trade."""

    politician: str
    symbol: str
    trade_type: str
    transaction_date: datetime
    disclosure_date: datetime
    filing_delay_days: int
    amount_estimate: float
    is_notable: bool

    # Price data
    price_at_transaction: float | None = None
    price_at_disclosure: float | None = None
    price_5d_after_disclosure: float | None = None
    price_10d_after_disclosure: float | None = None
    price_20d_after_disclosure: float | None = None

    # Returns (as percentage)
    return_transaction_to_disclosure: float | None = None
    return_disclosure_to_5d: float | None = None
    return_disclosure_to_10d: float | None = None
    return_disclosure_to_20d: float | None = None
    return_transaction_to_20d: float | None = None

    # Benchmark comparison
    spy_return_same_period: float | None = None
    excess_return: float | None = None

    # Signal correctness
    signal_correct: bool | None = None  # Did the stock move in the direction they traded?

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "politician": self.politician,
            "symbol": self.symbol,
            "trade_type": self.trade_type,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "disclosure_date": self.disclosure_date.isoformat() if self.disclosure_date else None,
            "filing_delay_days": self.filing_delay_days,
            "amount_estimate": self.amount_estimate,
            "is_notable": self.is_notable,
            "price_at_transaction": self.price_at_transaction,
            "price_at_disclosure": self.price_at_disclosure,
            "price_5d_after_disclosure": self.price_5d_after_disclosure,
            "price_10d_after_disclosure": self.price_10d_after_disclosure,
            "price_20d_after_disclosure": self.price_20d_after_disclosure,
            "return_transaction_to_disclosure": self.return_transaction_to_disclosure,
            "return_disclosure_to_5d": self.return_disclosure_to_5d,
            "return_disclosure_to_10d": self.return_disclosure_to_10d,
            "return_disclosure_to_20d": self.return_disclosure_to_20d,
            "return_transaction_to_20d": self.return_transaction_to_20d,
            "spy_return_same_period": self.spy_return_same_period,
            "excess_return": self.excess_return,
            "signal_correct": self.signal_correct,
        }


@dataclass
class PoliticianStats:
    """Aggregate statistics for a politician."""

    politician: str
    total_trades: int = 0
    buys: int = 0
    sells: int = 0
    correct_signals: int = 0
    total_with_data: int = 0
    avg_filing_delay: float = 0.0
    avg_return_to_disclosure: float = 0.0
    avg_return_5d_post: float = 0.0
    avg_return_20d_post: float = 0.0
    avg_excess_return: float = 0.0
    hit_rate: float = 0.0  # % of trades that moved in their direction
    total_volume: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "politician": self.politician,
            "total_trades": self.total_trades,
            "buys": self.buys,
            "sells": self.sells,
            "correct_signals": self.correct_signals,
            "total_with_data": self.total_with_data,
            "avg_filing_delay": round(self.avg_filing_delay, 1),
            "avg_return_to_disclosure": round(self.avg_return_to_disclosure, 2),
            "avg_return_5d_post": round(self.avg_return_5d_post, 2),
            "avg_return_20d_post": round(self.avg_return_20d_post, 2),
            "avg_excess_return": round(self.avg_excess_return, 2),
            "hit_rate": round(self.hit_rate * 100, 1),
            "total_volume": self.total_volume,
        }


def get_price_data(symbols: list[str], start_date: datetime, end_date: datetime) -> dict[str, pd.DataFrame]:
    """Fetch historical price data for symbols."""
    price_data = {}

    # Add SPY for benchmark
    all_symbols = list(set(symbols + ["SPY"]))

    # Extend date range for post-disclosure analysis
    extended_end = end_date + timedelta(days=30)

    logger.info(f"Fetching price data for {len(all_symbols)} symbols from {start_date.date()} to {extended_end.date()}")

    for symbol in all_symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=extended_end, auto_adjust=True)
            if not df.empty:
                price_data[symbol] = df
        except Exception as e:
            logger.debug(f"Could not fetch {symbol}: {e}")

    logger.info(f"Successfully fetched {len(price_data)} symbols")
    return price_data


def get_price_on_date(price_data: dict[str, pd.DataFrame], symbol: str, target_date: datetime) -> float | None:
    """Get closing price on or near a date."""
    if symbol not in price_data:
        return None

    df = price_data[symbol]
    target = pd.Timestamp(target_date.date())

    # Try exact date first
    if target in df.index:
        return float(df.loc[target, "Close"])

    # Find nearest date within 5 days
    for offset in range(1, 6):
        for delta in [offset, -offset]:
            check_date = target + pd.Timedelta(days=delta)
            if check_date in df.index:
                return float(df.loc[check_date, "Close"])

    return None


def calculate_return(price_start: float | None, price_end: float | None) -> float | None:
    """Calculate percentage return."""
    if price_start and price_end and price_start > 0:
        return ((price_end - price_start) / price_start) * 100
    return None


def analyze_trade_timing(
    trade: CongressionalTrade,
    price_data: dict[str, pd.DataFrame],
) -> TradeTimingResult:
    """Analyze timing and returns for a single trade."""

    result = TradeTimingResult(
        politician=trade.politician,
        symbol=trade.symbol,
        trade_type=trade.trade_type.value,
        transaction_date=trade.transaction_date,
        disclosure_date=trade.disclosure_date,
        filing_delay_days=trade.filing_delay_days,
        amount_estimate=trade.amount_estimate,
        is_notable=trade.is_notable_trader,
    )

    # Get prices
    result.price_at_transaction = get_price_on_date(price_data, trade.symbol, trade.transaction_date)
    result.price_at_disclosure = get_price_on_date(price_data, trade.symbol, trade.disclosure_date)
    result.price_5d_after_disclosure = get_price_on_date(
        price_data, trade.symbol, trade.disclosure_date + timedelta(days=5)
    )
    result.price_10d_after_disclosure = get_price_on_date(
        price_data, trade.symbol, trade.disclosure_date + timedelta(days=10)
    )
    result.price_20d_after_disclosure = get_price_on_date(
        price_data, trade.symbol, trade.disclosure_date + timedelta(days=20)
    )

    # Calculate returns
    result.return_transaction_to_disclosure = calculate_return(
        result.price_at_transaction, result.price_at_disclosure
    )
    result.return_disclosure_to_5d = calculate_return(
        result.price_at_disclosure, result.price_5d_after_disclosure
    )
    result.return_disclosure_to_10d = calculate_return(
        result.price_at_disclosure, result.price_10d_after_disclosure
    )
    result.return_disclosure_to_20d = calculate_return(
        result.price_at_disclosure, result.price_20d_after_disclosure
    )
    result.return_transaction_to_20d = calculate_return(
        result.price_at_transaction, result.price_20d_after_disclosure
    )

    # Calculate SPY benchmark return for same period
    spy_at_transaction = get_price_on_date(price_data, "SPY", trade.transaction_date)
    spy_20d_after = get_price_on_date(price_data, "SPY", trade.disclosure_date + timedelta(days=20))
    result.spy_return_same_period = calculate_return(spy_at_transaction, spy_20d_after)

    # Excess return vs SPY
    if result.return_transaction_to_20d is not None and result.spy_return_same_period is not None:
        result.excess_return = result.return_transaction_to_20d - result.spy_return_same_period

    # Signal correctness: did it move in their direction?
    if result.return_transaction_to_disclosure is not None:
        is_buy = trade.trade_type == TradeType.PURCHASE
        moved_up = result.return_transaction_to_disclosure > 0
        result.signal_correct = (is_buy and moved_up) or (not is_buy and not moved_up)

    return result


def aggregate_politician_stats(results: list[TradeTimingResult]) -> list[PoliticianStats]:
    """Aggregate results by politician."""
    by_politician: dict[str, list[TradeTimingResult]] = {}

    for r in results:
        if r.politician not in by_politician:
            by_politician[r.politician] = []
        by_politician[r.politician].append(r)

    stats = []
    for politician, trades in by_politician.items():
        stat = PoliticianStats(politician=politician)
        stat.total_trades = len(trades)
        stat.buys = sum(1 for t in trades if t.trade_type == "purchase")
        stat.sells = stat.total_trades - stat.buys
        stat.total_volume = sum(t.amount_estimate for t in trades)

        # Calculate averages (only for trades with data)
        with_data = [t for t in trades if t.return_transaction_to_disclosure is not None]
        stat.total_with_data = len(with_data)

        if with_data:
            stat.avg_filing_delay = np.mean([t.filing_delay_days for t in trades])
            stat.avg_return_to_disclosure = np.mean([t.return_transaction_to_disclosure for t in with_data])

            with_5d = [t for t in with_data if t.return_disclosure_to_5d is not None]
            if with_5d:
                stat.avg_return_5d_post = np.mean([t.return_disclosure_to_5d for t in with_5d])

            with_20d = [t for t in with_data if t.return_transaction_to_20d is not None]
            if with_20d:
                stat.avg_return_20d_post = np.mean([t.return_transaction_to_20d for t in with_20d])

            with_excess = [t for t in with_data if t.excess_return is not None]
            if with_excess:
                stat.avg_excess_return = np.mean([t.excess_return for t in with_excess])

            stat.correct_signals = sum(1 for t in with_data if t.signal_correct)
            stat.hit_rate = stat.correct_signals / stat.total_with_data if stat.total_with_data > 0 else 0

        stats.append(stat)

    # Sort by excess return
    stats.sort(key=lambda x: x.avg_excess_return, reverse=True)
    return stats


def generate_report(
    results: list[TradeTimingResult],
    politician_stats: list[PoliticianStats],
    output_dir: Path,
) -> str:
    """Generate timing study report."""

    # Filter results with complete data
    complete_results = [r for r in results if r.return_transaction_to_disclosure is not None]

    # Overall statistics
    if complete_results:
        avg_delay = np.mean([r.filing_delay_days for r in results])
        avg_return_to_disclosure = np.mean([r.return_transaction_to_disclosure for r in complete_results])

        with_20d = [r for r in complete_results if r.return_transaction_to_20d is not None]
        avg_return_20d = np.mean([r.return_transaction_to_20d for r in with_20d]) if with_20d else 0

        with_excess = [r for r in complete_results if r.excess_return is not None]
        avg_excess = np.mean([r.excess_return for r in with_excess]) if with_excess else 0

        signal_correct_count = sum(1 for r in complete_results if r.signal_correct)
        overall_hit_rate = signal_correct_count / len(complete_results) if complete_results else 0

        buys = [r for r in complete_results if r.trade_type == "purchase"]
        sells = [r for r in complete_results if r.trade_type != "purchase"]

        buy_avg_return = np.mean([r.return_transaction_to_disclosure for r in buys]) if buys else 0
        sell_avg_return = np.mean([r.return_transaction_to_disclosure for r in sells]) if sells else 0
    else:
        avg_delay = avg_return_to_disclosure = avg_return_20d = avg_excess = 0
        overall_hit_rate = buy_avg_return = sell_avg_return = 0
        buys = sells = []

    report = f"""
# Congressional Trading Timing Study

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Total Trades Analyzed:** {len(results)}
**Trades with Price Data:** {len(complete_results)}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Average Filing Delay | {avg_delay:.1f} days |
| Avg Return (Transaction → Disclosure) | {avg_return_to_disclosure:.2f}% |
| Avg Return (Transaction → 20 days post) | {avg_return_20d:.2f}% |
| Avg Excess Return vs SPY | {avg_excess:.2f}% |
| Overall Hit Rate | {overall_hit_rate*100:.1f}% |

### By Trade Type

| Type | Count | Avg Return to Disclosure |
|------|-------|--------------------------|
| Purchases | {len(buys)} | {buy_avg_return:.2f}% |
| Sales | {len(sells)} | {sell_avg_return:.2f}% |

---

## Key Findings

### 1. Pre-Disclosure Information Advantage

Politicians appear to have **{"YES" if avg_return_to_disclosure > 0.5 else "MARGINAL" if avg_return_to_disclosure > 0 else "NO"}** information advantage.

The average stock moves **{avg_return_to_disclosure:.2f}%** between when they trade and when they disclose.
This represents a **{avg_delay:.0f} day** window where they have unreported positions.

### 2. Post-Disclosure Drift

After disclosure, positions continue to {"gain" if avg_return_20d > avg_return_to_disclosure else "mean revert"}.
- 5-day post-disclosure: Data in detailed results
- 20-day post-disclosure: {avg_return_20d:.2f}% total return from transaction

### 3. Signal Quality

Hit rate of {overall_hit_rate*100:.1f}% means politicians are {"better than random (50%)" if overall_hit_rate > 0.5 else "about random"}.

---

## Top Performing Politicians (by Excess Return)

| Rank | Politician | Trades | Hit Rate | Avg Excess Return | Avg Filing Delay |
|------|------------|--------|----------|-------------------|------------------|
"""

    for i, stat in enumerate(politician_stats[:15], 1):
        if stat.total_with_data >= 2:  # Minimum trades for inclusion
            report += f"| {i} | {stat.politician} | {stat.total_trades} | {stat.hit_rate:.1f}% | {stat.avg_excess_return:+.2f}% | {stat.avg_filing_delay:.0f}d |\n"

    report += """
---

## Worst Performing Politicians (Inverse Signals)

| Rank | Politician | Trades | Hit Rate | Avg Excess Return |
|------|------------|--------|----------|-------------------|
"""

    for i, stat in enumerate(reversed(politician_stats[-10:]), 1):
        if stat.total_with_data >= 2:
            report += f"| {i} | {stat.politician} | {stat.total_trades} | {stat.hit_rate:.1f}% | {stat.avg_excess_return:+.2f}% |\n"

    report += """
---

## Trading Implications

### If Politicians Have Edge:
1. **Follow notable traders** with high hit rates on PURCHASES
2. **Fade low hit-rate traders** - they may be contrarian indicators
3. **Monitor filing delays** - longer delays may indicate more sensitive trades

### Data Collection Recommendations:
1. Archive daily congressional trades for historical backtesting
2. Cross-reference with news events to identify information asymmetry
3. Track committee membership changes for sector rotation signals

---

## Data Quality Notes

- Price data from Yahoo Finance (adjusted close)
- Some symbols may be missing or delisted
- Filing delays calculated from RSS feed timestamps
- Notable traders defined in codebase configuration

"""

    return report


async def run_timing_study(
    days: int = 90,
    min_trades: int = 3,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the complete timing study."""

    output_dir = output_dir or paths.base / "congressional_study"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting congressional timing study ({days} days lookback)")

    # Fetch trades
    source = CongressionalTradesSource()
    try:
        trades = await source.fetch_recent_trades(days=days)
        logger.info(f"Fetched {len(trades)} congressional trades")
    finally:
        await source.close()

    if not trades:
        logger.warning("No trades found!")
        return {"error": "No trades found"}

    # Get unique symbols
    symbols = list(set(t.symbol for t in trades))
    logger.info(f"Unique symbols: {len(symbols)}")

    # Get date range
    earliest_transaction = min(t.transaction_date for t in trades)
    latest_disclosure = max(t.disclosure_date for t in trades)

    # Fetch price data
    price_data = get_price_data(symbols, earliest_transaction - timedelta(days=5), latest_disclosure)

    # Analyze each trade
    results = []
    for trade in trades:
        result = analyze_trade_timing(trade, price_data)
        results.append(result)

    # Aggregate by politician
    politician_stats = aggregate_politician_stats(results)

    # Filter politicians with minimum trades
    politician_stats = [p for p in politician_stats if p.total_trades >= min_trades]

    # Generate report
    report = generate_report(results, politician_stats, output_dir)

    # Save outputs
    report_path = output_dir / "timing_study_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")

    # Save detailed results as JSON
    results_path = output_dir / "timing_study_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "parameters": {"days": days, "min_trades": min_trades},
            "summary": {
                "total_trades": len(trades),
                "trades_with_data": len([r for r in results if r.return_transaction_to_disclosure]),
                "unique_symbols": len(symbols),
                "unique_politicians": len(set(t.politician for t in trades)),
            },
            "politician_stats": [p.to_dict() for p in politician_stats],
            "trade_results": [r.to_dict() for r in results],
        }, f, indent=2, default=str)
    logger.info(f"Detailed results saved to {results_path}")

    # Save trades for archival
    trades_archive_path = output_dir / f"trades_archive_{datetime.now().strftime('%Y%m%d')}.json"
    with open(trades_archive_path, "w") as f:
        json.dump([t.to_dict() for t in trades], f, indent=2, default=str)
    logger.info(f"Trades archived to {trades_archive_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("CONGRESSIONAL TIMING STUDY - SUMMARY")
    print("=" * 60)
    print(f"\nTotal trades analyzed: {len(trades)}")
    print(f"Trades with price data: {len([r for r in results if r.return_transaction_to_disclosure])}")

    complete = [r for r in results if r.return_transaction_to_disclosure is not None]
    if complete:
        avg_return = np.mean([r.return_transaction_to_disclosure for r in complete])
        hit_rate = sum(1 for r in complete if r.signal_correct) / len(complete)
        print(f"\nAvg return (transaction → disclosure): {avg_return:.2f}%")
        print(f"Hit rate (traded in right direction): {hit_rate*100:.1f}%")

    print("\n📊 Top 5 Politicians by Excess Return:")
    for i, stat in enumerate(politician_stats[:5], 1):
        print(f"  {i}. {stat.politician}: {stat.avg_excess_return:+.2f}% excess ({stat.total_trades} trades, {stat.hit_rate:.0f}% hit rate)")

    print(f"\n📁 Full report: {report_path}")

    return {
        "trades_count": len(trades),
        "trades_with_data": len(complete),
        "avg_return_to_disclosure": np.mean([r.return_transaction_to_disclosure for r in complete]) if complete else None,
        "politician_stats": politician_stats[:10],
        "report_path": str(report_path),
        "results_path": str(results_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Congressional Trading Timing Study")
    parser.add_argument("--days", type=int, default=90, help="Lookback period in days")
    parser.add_argument("--min-trades", type=int, default=3, help="Minimum trades per politician for stats")
    parser.add_argument("--output", type=str, help="Output directory")

    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else None
    asyncio.run(run_timing_study(days=args.days, min_trades=args.min_trades, output_dir=output_dir))


if __name__ == "__main__":
    main()
