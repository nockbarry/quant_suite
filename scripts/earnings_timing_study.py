#!/usr/bin/env python3
"""Earnings Event Timing Study.

Analyzes whether pre-earnings signals predict post-earnings returns.

Key Questions:
1. Does pre-earnings drift predict post-earnings direction?
2. Do earnings surprises persist (PEAD - Post Earnings Announcement Drift)?
3. Can we predict surprise direction from pre-earnings behavior?
4. Which signals before earnings are most predictive?

Data Sources:
- yfinance: Historical earnings dates and surprises
- yfinance: Price data for return calculations

Usage:
    PYTHONPATH=. python scripts/earnings_timing_study.py
    PYTHONPATH=. python scripts/earnings_timing_study.py --symbols AAPL MSFT GOOGL --years 3
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
from scipy import stats

from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Default universe for study
DEFAULT_SYMBOLS = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Semiconductors
    "AMD", "INTC", "QCOM", "MU", "AVGO",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY",
    # Consumer
    "WMT", "HD", "NKE", "MCD", "SBUX", "TGT",
    # Energy
    "XOM", "CVX", "SLB", "COP",
    # Industrials
    "CAT", "BA", "UPS", "HON",
    # Communication
    "DIS", "NFLX", "CMCSA", "VZ", "T",
]


@dataclass
class EarningsEvent:
    """Single earnings event with returns data."""

    symbol: str
    earnings_date: datetime
    eps_estimate: float | None
    eps_actual: float | None
    surprise_pct: float | None

    # Pre-earnings returns
    return_5d_pre: float | None = None
    return_10d_pre: float | None = None
    return_20d_pre: float | None = None

    # Post-earnings returns
    return_1d_post: float | None = None
    return_5d_post: float | None = None
    return_10d_post: float | None = None
    return_20d_post: float | None = None

    # Benchmark comparison
    spy_return_pre_20d: float | None = None
    spy_return_post_20d: float | None = None

    # Derived
    pre_earnings_momentum: str = ""  # "positive", "negative", "neutral"
    surprise_direction: str = ""  # "beat", "miss", "inline"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "earnings_date": self.earnings_date.isoformat() if self.earnings_date else None,
            "eps_estimate": self.eps_estimate,
            "eps_actual": self.eps_actual,
            "surprise_pct": self.surprise_pct,
            "return_5d_pre": self.return_5d_pre,
            "return_10d_pre": self.return_10d_pre,
            "return_20d_pre": self.return_20d_pre,
            "return_1d_post": self.return_1d_post,
            "return_5d_post": self.return_5d_post,
            "return_10d_post": self.return_10d_post,
            "return_20d_post": self.return_20d_post,
            "spy_return_pre_20d": self.spy_return_pre_20d,
            "spy_return_post_20d": self.spy_return_post_20d,
            "pre_earnings_momentum": self.pre_earnings_momentum,
            "surprise_direction": self.surprise_direction,
        }


def get_earnings_history(symbol: str, limit: int = 40) -> pd.DataFrame:
    """Get historical earnings dates and surprises for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        earnings = ticker.get_earnings_dates(limit=limit)

        if earnings is None or earnings.empty:
            return pd.DataFrame()

        # Filter to only past earnings with actual results
        now = datetime.now()
        earnings = earnings[
            (earnings.index.tz_localize(None) < now) &
            (earnings["Reported EPS"].notna())
        ]

        return earnings
    except Exception as e:
        logger.debug(f"Error getting earnings for {symbol}: {e}")
        return pd.DataFrame()


def get_price_data(symbols: list[str], start_date: datetime, end_date: datetime) -> dict[str, pd.DataFrame]:
    """Fetch price data for multiple symbols."""
    price_data = {}

    # Add buffer for pre/post analysis
    buffered_start = start_date - timedelta(days=60)
    buffered_end = end_date + timedelta(days=60)

    # Always include SPY for benchmark
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
        logger.warning(f"Batch download failed: {e}")

    logger.info(f"Got price data for {len(price_data)} symbols")
    return price_data


def get_return(prices: pd.DataFrame, start_date: datetime, days: int) -> float | None:
    """Calculate return from start_date over N days."""
    if prices.empty:
        return None

    try:
        target_date = pd.Timestamp(start_date.date())
        end_date = target_date + pd.Timedelta(days=days)

        # Find closest available dates
        start_idx = prices.index.get_indexer([target_date], method="nearest")[0]
        end_idx = prices.index.get_indexer([end_date], method="nearest")[0]

        if start_idx >= 0 and end_idx >= 0 and start_idx != end_idx:
            start_price = prices.iloc[start_idx]["Close"]
            end_price = prices.iloc[end_idx]["Close"]

            if start_price > 0:
                return (end_price - start_price) / start_price * 100
    except Exception:
        pass

    return None


def analyze_earnings_events(
    symbols: list[str],
    years_back: int = 5,
) -> list[EarningsEvent]:
    """Collect and analyze earnings events for all symbols."""

    all_events = []
    min_date = datetime.now() - timedelta(days=years_back * 365)
    max_date = datetime.now() - timedelta(days=30)  # Exclude very recent

    # Collect earnings history
    logger.info(f"Collecting earnings history for {len(symbols)} symbols...")
    earnings_by_symbol = {}

    for symbol in symbols:
        earnings = get_earnings_history(symbol, limit=years_back * 4 + 10)
        if not earnings.empty:
            earnings_by_symbol[symbol] = earnings
            logger.debug(f"  {symbol}: {len(earnings)} earnings events")

    logger.info(f"Found earnings data for {len(earnings_by_symbol)} symbols")

    # Get date range
    all_dates = []
    for symbol, earnings in earnings_by_symbol.items():
        all_dates.extend([d.replace(tzinfo=None) for d in earnings.index])

    if not all_dates:
        return []

    start_date = max(min(all_dates), min_date)
    end_date = min(max(all_dates), max_date)

    # Fetch price data
    price_data = get_price_data(list(earnings_by_symbol.keys()), start_date, end_date)

    # Analyze each earnings event
    logger.info("Analyzing earnings events...")

    for symbol, earnings in earnings_by_symbol.items():
        if symbol not in price_data:
            continue

        prices = price_data[symbol]
        spy_prices = price_data.get("SPY", pd.DataFrame())

        for earnings_date, row in earnings.iterrows():
            try:
                # Convert to naive datetime
                if hasattr(earnings_date, 'tz_localize'):
                    earnings_dt = earnings_date.replace(tzinfo=None)
                else:
                    earnings_dt = pd.Timestamp(earnings_date).to_pydatetime()

                # Skip if outside our range
                if earnings_dt < min_date or earnings_dt > max_date:
                    continue

                event = EarningsEvent(
                    symbol=symbol,
                    earnings_date=earnings_dt,
                    eps_estimate=row.get("EPS Estimate"),
                    eps_actual=row.get("Reported EPS"),
                    surprise_pct=row.get("Surprise(%)"),
                )

                # Pre-earnings returns (negative days = before earnings)
                event.return_5d_pre = get_return(prices, earnings_dt - timedelta(days=5), 5)
                event.return_10d_pre = get_return(prices, earnings_dt - timedelta(days=10), 10)
                event.return_20d_pre = get_return(prices, earnings_dt - timedelta(days=20), 20)

                # Post-earnings returns
                event.return_1d_post = get_return(prices, earnings_dt, 1)
                event.return_5d_post = get_return(prices, earnings_dt, 5)
                event.return_10d_post = get_return(prices, earnings_dt, 10)
                event.return_20d_post = get_return(prices, earnings_dt, 20)

                # SPY benchmark
                if not spy_prices.empty:
                    event.spy_return_pre_20d = get_return(spy_prices, earnings_dt - timedelta(days=20), 20)
                    event.spy_return_post_20d = get_return(spy_prices, earnings_dt, 20)

                # Classify momentum
                if event.return_20d_pre is not None:
                    if event.return_20d_pre > 2:
                        event.pre_earnings_momentum = "positive"
                    elif event.return_20d_pre < -2:
                        event.pre_earnings_momentum = "negative"
                    else:
                        event.pre_earnings_momentum = "neutral"

                # Classify surprise
                if event.surprise_pct is not None:
                    if event.surprise_pct > 2:
                        event.surprise_direction = "beat"
                    elif event.surprise_pct < -2:
                        event.surprise_direction = "miss"
                    else:
                        event.surprise_direction = "inline"

                all_events.append(event)

            except Exception as e:
                logger.debug(f"Error processing {symbol} earnings: {e}")

    logger.info(f"Analyzed {len(all_events)} earnings events")
    return all_events


def calculate_statistics(events: list[EarningsEvent]) -> dict[str, Any]:
    """Calculate comprehensive earnings statistics."""

    df = pd.DataFrame([e.to_dict() for e in events])

    if df.empty:
        return {"error": "No events to analyze"}

    stats_dict = {
        "total_events": len(df),
        "unique_symbols": df["symbol"].nunique(),
        "date_range": {
            "start": df["earnings_date"].min(),
            "end": df["earnings_date"].max(),
        }
    }

    # Overall statistics
    for col in ["return_5d_pre", "return_10d_pre", "return_20d_pre",
                "return_1d_post", "return_5d_post", "return_10d_post", "return_20d_post"]:
        values = df[col].dropna()
        if len(values) > 0:
            stats_dict[f"{col}_mean"] = values.mean()
            stats_dict[f"{col}_median"] = values.median()
            stats_dict[f"{col}_std"] = values.std()

    # Surprise statistics
    surprises = df["surprise_pct"].dropna()
    if len(surprises) > 0:
        stats_dict["avg_surprise_pct"] = surprises.mean()
        stats_dict["beat_rate"] = (surprises > 0).mean()
        stats_dict["miss_rate"] = (surprises < 0).mean()

    # Pre-earnings momentum vs Post-earnings returns
    # Does running into earnings predict post-earnings?
    for momentum in ["positive", "negative", "neutral"]:
        subset = df[df["pre_earnings_momentum"] == momentum]
        if len(subset) > 20:
            post_5d = subset["return_5d_post"].dropna()
            if len(post_5d) > 0:
                stats_dict[f"momentum_{momentum}_post_5d"] = post_5d.mean()

    # Surprise direction vs PEAD
    for direction in ["beat", "miss", "inline"]:
        subset = df[df["surprise_direction"] == direction]
        if len(subset) > 20:
            for period in ["5d", "10d", "20d"]:
                col = f"return_{period}_post"
                values = subset[col].dropna()
                if len(values) > 0:
                    stats_dict[f"surprise_{direction}_pead_{period}"] = values.mean()

    # Correlation: pre-earnings momentum vs surprise
    pre_20d = df["return_20d_pre"].dropna()
    surprise = df.loc[pre_20d.index, "surprise_pct"].dropna()
    common_idx = pre_20d.index.intersection(surprise.index)
    if len(common_idx) > 30:
        corr, p_val = stats.pearsonr(pre_20d.loc[common_idx], surprise.loc[common_idx])
        stats_dict["pre_momentum_surprise_correlation"] = corr
        stats_dict["pre_momentum_surprise_pvalue"] = p_val

    # Correlation: surprise vs post-earnings drift
    surprise_valid = df["surprise_pct"].dropna()
    post_20d = df.loc[surprise_valid.index, "return_20d_post"].dropna()
    common_idx = surprise_valid.index.intersection(post_20d.index)
    if len(common_idx) > 30:
        corr, p_val = stats.pearsonr(surprise_valid.loc[common_idx], post_20d.loc[common_idx])
        stats_dict["surprise_pead_correlation"] = corr
        stats_dict["surprise_pead_pvalue"] = p_val

    # Pre-earnings run-up predicts post-earnings?
    pre_valid = df["return_20d_pre"].dropna()
    post_valid = df.loc[pre_valid.index, "return_20d_post"].dropna()
    common_idx = pre_valid.index.intersection(post_valid.index)
    if len(common_idx) > 30:
        corr, p_val = stats.pearsonr(pre_valid.loc[common_idx], post_valid.loc[common_idx])
        stats_dict["pre_post_correlation"] = corr
        stats_dict["pre_post_pvalue"] = p_val

    return stats_dict


def analyze_by_symbol(events: list[EarningsEvent]) -> pd.DataFrame:
    """Analyze earnings performance by symbol."""

    symbol_stats = []
    df = pd.DataFrame([e.to_dict() for e in events])

    for symbol in df["symbol"].unique():
        symbol_df = df[df["symbol"] == symbol]

        if len(symbol_df) < 4:
            continue

        # Beat rate
        surprises = symbol_df["surprise_pct"].dropna()
        beat_rate = (surprises > 0).mean() if len(surprises) > 0 else 0

        # Average surprise
        avg_surprise = surprises.mean() if len(surprises) > 0 else 0

        # PEAD strength
        post_20d = symbol_df["return_20d_post"].dropna()
        avg_pead = post_20d.mean() if len(post_20d) > 0 else 0

        # Pre-earnings run-up
        pre_20d = symbol_df["return_20d_pre"].dropna()
        avg_runup = pre_20d.mean() if len(pre_20d) > 0 else 0

        symbol_stats.append({
            "symbol": symbol,
            "events": len(symbol_df),
            "beat_rate": beat_rate * 100,
            "avg_surprise": avg_surprise,
            "avg_pead_20d": avg_pead,
            "avg_runup_20d": avg_runup,
        })

    return pd.DataFrame(symbol_stats).sort_values("avg_pead_20d", ascending=False)


def generate_report(
    stats: dict[str, Any],
    symbol_df: pd.DataFrame,
    events: list[EarningsEvent],
    output_dir: Path,
) -> str:
    """Generate comprehensive earnings timing study report."""

    events_df = pd.DataFrame([e.to_dict() for e in events])

    report = f"""
# Earnings Event Timing Study

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Total Events Analyzed:** {stats.get('total_events', 0):,}
**Unique Symbols:** {stats.get('unique_symbols', 0)}

---

## Executive Summary

### Pre-Earnings Behavior

| Window | Mean Return | Median Return | Std Dev |
|--------|-------------|---------------|---------|
| 5 days pre | {stats.get('return_5d_pre_mean', 0):+.3f}% | {stats.get('return_5d_pre_median', 0):+.3f}% | {stats.get('return_5d_pre_std', 0):.2f}% |
| 10 days pre | {stats.get('return_10d_pre_mean', 0):+.3f}% | {stats.get('return_10d_pre_median', 0):+.3f}% | {stats.get('return_10d_pre_std', 0):.2f}% |
| 20 days pre | {stats.get('return_20d_pre_mean', 0):+.3f}% | {stats.get('return_20d_pre_median', 0):+.3f}% | {stats.get('return_20d_pre_std', 0):.2f}% |

### Post-Earnings Behavior (PEAD)

| Window | Mean Return | Median Return | Std Dev |
|--------|-------------|---------------|---------|
| 1 day post | {stats.get('return_1d_post_mean', 0):+.3f}% | {stats.get('return_1d_post_median', 0):+.3f}% | {stats.get('return_1d_post_std', 0):.2f}% |
| 5 days post | {stats.get('return_5d_post_mean', 0):+.3f}% | {stats.get('return_5d_post_median', 0):+.3f}% | {stats.get('return_5d_post_std', 0):.2f}% |
| 10 days post | {stats.get('return_10d_post_mean', 0):+.3f}% | {stats.get('return_10d_post_median', 0):+.3f}% | {stats.get('return_10d_post_std', 0):.2f}% |
| 20 days post | {stats.get('return_20d_post_mean', 0):+.3f}% | {stats.get('return_20d_post_median', 0):+.3f}% | {stats.get('return_20d_post_std', 0):.2f}% |

### Surprise Statistics

| Metric | Value |
|--------|-------|
| Average Surprise | {stats.get('avg_surprise_pct', 0):+.2f}% |
| Beat Rate | {stats.get('beat_rate', 0)*100:.1f}% |
| Miss Rate | {stats.get('miss_rate', 0)*100:.1f}% |

---

## 1. Pre-Earnings Momentum Analysis

**Question:** Does pre-earnings momentum predict post-earnings returns?

| Pre-Earnings Momentum | Avg 5-day Post Return |
|-----------------------|----------------------|
| Positive (>+2%) | {stats.get('momentum_positive_post_5d', 0):+.3f}% |
| Neutral (-2% to +2%) | {stats.get('momentum_neutral_post_5d', 0):+.3f}% |
| Negative (<-2%) | {stats.get('momentum_negative_post_5d', 0):+.3f}% |

**Correlation (Pre-20d vs Post-20d):** {stats.get('pre_post_correlation', 0):.3f} (p={stats.get('pre_post_pvalue', 1):.4f})

"""

    pre_post_corr = stats.get('pre_post_correlation', 0)
    if abs(pre_post_corr) > 0.1 and stats.get('pre_post_pvalue', 1) < 0.05:
        if pre_post_corr > 0:
            report += """
**FINDING: Momentum Continuation**
Stocks with positive pre-earnings momentum tend to continue outperforming after earnings.
This suggests a momentum continuation strategy may work around earnings.
"""
        else:
            report += """
**FINDING: Mean Reversion**
Stocks with positive pre-earnings momentum tend to underperform after earnings.
This suggests expectations get priced in and then reverse.
"""
    else:
        report += """
**FINDING: No Significant Relationship**
Pre-earnings momentum does not reliably predict post-earnings returns.
"""

    report += f"""
---

## 2. Post-Earnings Announcement Drift (PEAD)

**Question:** Do earnings surprises predict future returns?

| Surprise Direction | 5-day PEAD | 10-day PEAD | 20-day PEAD |
|-------------------|------------|-------------|-------------|
| Beat (>+2%) | {stats.get('surprise_beat_pead_5d', 0):+.3f}% | {stats.get('surprise_beat_pead_10d', 0):+.3f}% | {stats.get('surprise_beat_pead_20d', 0):+.3f}% |
| Inline (-2% to +2%) | {stats.get('surprise_inline_pead_5d', 0):+.3f}% | {stats.get('surprise_inline_pead_10d', 0):+.3f}% | {stats.get('surprise_inline_pead_20d', 0):+.3f}% |
| Miss (<-2%) | {stats.get('surprise_miss_pead_5d', 0):+.3f}% | {stats.get('surprise_miss_pead_10d', 0):+.3f}% | {stats.get('surprise_miss_pead_20d', 0):+.3f}% |

**Correlation (Surprise % vs 20d PEAD):** {stats.get('surprise_pead_correlation', 0):.3f} (p={stats.get('surprise_pead_pvalue', 1):.4f})

"""

    surprise_pead_corr = stats.get('surprise_pead_correlation', 0)
    if surprise_pead_corr > 0.1 and stats.get('surprise_pead_pvalue', 1) < 0.05:
        report += """
**FINDING: PEAD Exists**
Earnings surprises predict post-earnings returns. Stocks that beat estimates continue to outperform,
while misses continue to underperform. This is consistent with academic PEAD literature.

**Exploitable Strategy:**
- Buy on positive surprises, hold 10-20 days
- Short on negative surprises, hold 10-20 days
"""
    else:
        report += """
**FINDING: Limited PEAD**
Earnings surprises do not strongly predict post-earnings returns in this sample.
The market appears to efficiently price earnings information.
"""

    report += f"""
---

## 3. Pre-Earnings Run-up vs Surprise

**Question:** Does pre-earnings price action predict the surprise direction?

**Correlation (Pre-20d Return vs Surprise %):** {stats.get('pre_momentum_surprise_correlation', 0):.3f} (p={stats.get('pre_momentum_surprise_pvalue', 1):.4f})

"""

    pre_surprise_corr = stats.get('pre_momentum_surprise_correlation', 0)
    if abs(pre_surprise_corr) > 0.1 and stats.get('pre_momentum_surprise_pvalue', 1) < 0.05:
        if pre_surprise_corr > 0:
            report += """
**FINDING: Market Anticipates Surprises**
Stocks running up before earnings tend to beat estimates. This suggests:
- Smart money (options flow, insiders) may have information
- Pre-earnings momentum is a valid signal for expected surprise direction
- Consider buying stocks with positive pre-earnings momentum
"""
        else:
            report += """
**FINDING: Inverse Relationship**
Stocks running up before earnings tend to disappoint. This suggests:
- Expectations get too high
- Consider fading extreme pre-earnings moves
"""
    else:
        report += """
**FINDING: No Predictive Relationship**
Pre-earnings price action does not reliably predict surprise direction.
The market is efficient at pricing expected earnings.
"""

    report += """
---

## 4. Top Symbols by PEAD Strength

| Rank | Symbol | Events | Beat Rate | Avg Surprise | Avg 20d PEAD | Avg 20d Run-up |
|------|--------|--------|-----------|--------------|--------------|----------------|
"""

    for i, (_, row) in enumerate(symbol_df.head(15).iterrows(), 1):
        report += f"| {i} | {row['symbol']} | {row['events']} | {row['beat_rate']:.0f}% | {row['avg_surprise']:+.1f}% | {row['avg_pead_20d']:+.2f}% | {row['avg_runup_20d']:+.2f}% |\n"

    report += """
---

## 5. Trading System Integration

### Recommended Signal Implementation

1. **Pre-Earnings Signal**
   - Monitor 20-day momentum into earnings
   - Cross-reference with options implied move
   - Check insider/congressional activity

2. **Post-Earnings Signal (PEAD)**
   - On positive surprise (>2%), initiate long position
   - Hold for 10-20 trading days
   - Use 20-day ATR for position sizing

3. **Run-up Fade Strategy**
   - If pre-earnings run-up is extreme (>10%) and options IV is very high
   - Consider selling volatility or fading the move

### Data Collection Requirements

- Daily archive of upcoming earnings with estimates
- Track actual vs estimate on report
- Archive pre/post returns for each event
- Monitor options implied moves

"""

    return report


def run_earnings_study(
    symbols: list[str] | None = None,
    years_back: int = 5,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run complete earnings timing study."""

    symbols = symbols or DEFAULT_SYMBOLS
    output_dir = output_dir or paths.base / "earnings_study"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting earnings study for {len(symbols)} symbols, {years_back} years back")

    # Collect and analyze events
    events = analyze_earnings_events(symbols, years_back)

    if not events:
        logger.error("No earnings events found!")
        return {"error": "No events found"}

    # Calculate statistics
    stats = calculate_statistics(events)

    # Analyze by symbol
    symbol_df = analyze_by_symbol(events)

    # Generate report
    report = generate_report(stats, symbol_df, events, output_dir)

    # Save outputs
    report_path = output_dir / "earnings_timing_study_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    results_path = output_dir / "earnings_timing_study_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "statistics": stats,
            "symbol_stats": symbol_df.to_dict("records"),
        }, f, indent=2, default=str)

    # Save detailed events
    events_df = pd.DataFrame([e.to_dict() for e in events])
    events_df.to_parquet(output_dir / "earnings_events.parquet")

    # Print summary
    print("\n" + "=" * 70)
    print("EARNINGS TIMING STUDY - SUMMARY")
    print("=" * 70)
    print(f"\nEvents analyzed: {len(events):,}")
    print(f"Unique symbols: {stats.get('unique_symbols', 0)}")
    print(f"Beat rate: {stats.get('beat_rate', 0)*100:.1f}%")

    print("\n📊 KEY FINDINGS:")
    print(f"  Avg surprise: {stats.get('avg_surprise_pct', 0):+.2f}%")
    print(f"  Pre-20d vs Post-20d correlation: {stats.get('pre_post_correlation', 0):.3f}")
    print(f"  Surprise vs PEAD correlation: {stats.get('surprise_pead_correlation', 0):.3f}")

    beat_pead = stats.get('surprise_beat_pead_20d', 0)
    miss_pead = stats.get('surprise_miss_pead_20d', 0)
    if beat_pead > 0.5 and miss_pead < -0.5:
        print("\n  ✅ PEAD EXISTS - Earnings surprises predict future returns")

    print(f"\n📁 Full report: {report_path}")

    return {
        "events_analyzed": len(events),
        "statistics": stats,
        "report_path": str(report_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Earnings Event Timing Study")
    parser.add_argument("--symbols", nargs="+", help="Symbols to analyze")
    parser.add_argument("--years", type=int, default=5, help="Years of history")
    parser.add_argument("--output", type=str, help="Output directory")

    args = parser.parse_args()

    symbols = args.symbols if args.symbols else None
    output_dir = Path(args.output) if args.output else None

    run_earnings_study(symbols=symbols, years_back=args.years, output_dir=output_dir)


if __name__ == "__main__":
    main()
