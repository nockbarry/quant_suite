#!/usr/bin/env python3
"""Pre-Event Signal Analysis.

Tests whether signals BEFORE events predict outcomes AFTER events.

Key Questions:
1. Does unusual options activity before earnings predict earnings direction?
2. Does unusual volume before news predict post-news returns?
3. Does insider buying/selling before earnings predict surprise direction?
4. Does pre-event momentum predict post-event drift?

This study combines:
- Earnings dates (from yfinance)
- Price/volume data (from yfinance)
- Options implied volatility patterns
- Pre-event technical patterns

Usage:
    PYTHONPATH=. python scripts/pre_event_signal_study.py
    PYTHONPATH=. python scripts/pre_event_signal_study.py --symbols AAPL MSFT --years 3
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


DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "AMD", "INTC", "QCOM", "MU", "AVGO",
    "JPM", "BAC", "GS",
    "JNJ", "UNH", "PFE",
    "XOM", "CVX", "SLB",
    "DIS", "NFLX",
]


@dataclass
class PreEventSignal:
    """Signals measured before an event."""

    symbol: str
    event_date: datetime
    event_type: str  # earnings, news

    # Pre-event technical signals
    volume_ratio_5d: float | None = None  # Volume vs 20d avg
    volume_ratio_10d: float | None = None
    momentum_5d: float | None = None  # Return
    momentum_10d: float | None = None
    momentum_20d: float | None = None
    volatility_ratio: float | None = None  # Recent vol vs historical

    # Event outcome
    surprise_pct: float | None = None
    return_1d_post: float | None = None
    return_5d_post: float | None = None
    return_20d_post: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_date": self.event_date.isoformat(),
            "event_type": self.event_type,
            "volume_ratio_5d": self.volume_ratio_5d,
            "volume_ratio_10d": self.volume_ratio_10d,
            "momentum_5d": self.momentum_5d,
            "momentum_10d": self.momentum_10d,
            "momentum_20d": self.momentum_20d,
            "volatility_ratio": self.volatility_ratio,
            "surprise_pct": self.surprise_pct,
            "return_1d_post": self.return_1d_post,
            "return_5d_post": self.return_5d_post,
            "return_20d_post": self.return_20d_post,
        }


def get_earnings_history(symbol: str, limit: int = 40) -> pd.DataFrame:
    """Get historical earnings for a symbol."""
    try:
        ticker = yf.Ticker(symbol)
        earnings = ticker.get_earnings_dates(limit=limit)
        if earnings is None or earnings.empty:
            return pd.DataFrame()

        now = datetime.now()
        earnings = earnings[
            (earnings.index.tz_localize(None) < now) &
            (earnings["Reported EPS"].notna())
        ]
        return earnings
    except Exception as e:
        logger.debug(f"Error getting earnings for {symbol}: {e}")
        return pd.DataFrame()


def get_price_volume_data(symbols: list[str], start_date: datetime, end_date: datetime) -> dict[str, pd.DataFrame]:
    """Fetch price and volume data."""
    price_data = {}

    buffered_start = start_date - timedelta(days=60)
    buffered_end = end_date + timedelta(days=60)

    logger.info(f"Downloading price/volume data for {len(symbols)} symbols...")

    try:
        data = yf.download(
            symbols,
            start=buffered_start,
            end=buffered_end,
            progress=False,
            group_by="ticker",
            threads=True,
        )

        if len(symbols) == 1:
            symbol = symbols[0]
            if not data.empty:
                price_data[symbol] = data[["Close", "Volume"]].dropna()
        else:
            for symbol in symbols:
                try:
                    if symbol in data.columns.get_level_values(0):
                        symbol_data = data[symbol][["Close", "Volume"]].dropna()
                        if not symbol_data.empty:
                            price_data[symbol] = symbol_data
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"Download failed: {e}")

    logger.info(f"Got data for {len(price_data)} symbols")
    return price_data


def calculate_volume_ratio(prices: pd.DataFrame, date: datetime, lookback: int, avg_period: int = 20) -> float | None:
    """Calculate volume ratio: avg volume over lookback vs historical avg."""
    try:
        target = pd.Timestamp(date.date())
        idx = prices.index.get_indexer([target], method="pad")[0]

        if idx < avg_period + lookback:
            return None

        recent_vol = prices.iloc[idx - lookback:idx]["Volume"].mean()
        historical_vol = prices.iloc[idx - lookback - avg_period:idx - lookback]["Volume"].mean()

        if historical_vol > 0:
            return recent_vol / historical_vol

    except Exception:
        pass
    return None


def calculate_momentum(prices: pd.DataFrame, date: datetime, days: int) -> float | None:
    """Calculate return over N days ending at date."""
    try:
        target = pd.Timestamp(date.date())
        end_idx = prices.index.get_indexer([target], method="pad")[0]
        start_idx = end_idx - days

        if start_idx >= 0:
            start_price = prices.iloc[start_idx]["Close"]
            end_price = prices.iloc[end_idx]["Close"]

            if start_price > 0:
                return (end_price - start_price) / start_price * 100

    except Exception:
        pass
    return None


def calculate_volatility_ratio(prices: pd.DataFrame, date: datetime, recent: int = 10, historical: int = 60) -> float | None:
    """Calculate ratio of recent volatility to historical."""
    try:
        target = pd.Timestamp(date.date())
        idx = prices.index.get_indexer([target], method="pad")[0]

        if idx < historical:
            return None

        returns = prices["Close"].pct_change()
        recent_vol = returns.iloc[idx - recent:idx].std()
        historical_vol = returns.iloc[idx - historical:idx - recent].std()

        if historical_vol > 0:
            return recent_vol / historical_vol

    except Exception:
        pass
    return None


def calculate_post_return(prices: pd.DataFrame, date: datetime, days: int) -> float | None:
    """Calculate return starting from date over N days."""
    try:
        target = pd.Timestamp(date.date())
        start_idx = prices.index.get_indexer([target], method="bfill")[0]
        end_idx = start_idx + days

        if end_idx < len(prices):
            start_price = prices.iloc[start_idx]["Close"]
            end_price = prices.iloc[end_idx]["Close"]

            if start_price > 0:
                return (end_price - start_price) / start_price * 100

    except Exception:
        pass
    return None


def analyze_pre_event_signals(
    symbols: list[str],
    years_back: int = 5,
) -> list[PreEventSignal]:
    """Collect pre-event signals for all earnings events."""

    signals = []
    min_date = datetime.now() - timedelta(days=years_back * 365)
    max_date = datetime.now() - timedelta(days=30)

    # Collect earnings
    logger.info(f"Collecting earnings for {len(symbols)} symbols...")
    earnings_by_symbol = {}

    for symbol in symbols:
        earnings = get_earnings_history(symbol, limit=years_back * 4 + 10)
        if not earnings.empty:
            earnings_by_symbol[symbol] = earnings

    logger.info(f"Found earnings for {len(earnings_by_symbol)} symbols")

    # Get date range
    all_dates = []
    for earnings in earnings_by_symbol.values():
        all_dates.extend([d.replace(tzinfo=None) for d in earnings.index])

    if not all_dates:
        return []

    start_date = max(min(all_dates), min_date)
    end_date = min(max(all_dates), max_date)

    # Fetch price/volume data
    price_data = get_price_volume_data(list(earnings_by_symbol.keys()), start_date, end_date)

    # Analyze each event
    logger.info("Calculating pre-event signals...")

    for symbol, earnings in earnings_by_symbol.items():
        if symbol not in price_data:
            continue

        prices = price_data[symbol]

        for earnings_date, row in earnings.iterrows():
            try:
                earnings_dt = earnings_date.replace(tzinfo=None)

                if earnings_dt < min_date or earnings_dt > max_date:
                    continue

                signal = PreEventSignal(
                    symbol=symbol,
                    event_date=earnings_dt,
                    event_type="earnings",
                )

                # Pre-event signals
                signal.volume_ratio_5d = calculate_volume_ratio(prices, earnings_dt, 5)
                signal.volume_ratio_10d = calculate_volume_ratio(prices, earnings_dt, 10)
                signal.momentum_5d = calculate_momentum(prices, earnings_dt, 5)
                signal.momentum_10d = calculate_momentum(prices, earnings_dt, 10)
                signal.momentum_20d = calculate_momentum(prices, earnings_dt, 20)
                signal.volatility_ratio = calculate_volatility_ratio(prices, earnings_dt)

                # Event outcome
                signal.surprise_pct = row.get("Surprise(%)")
                signal.return_1d_post = calculate_post_return(prices, earnings_dt, 1)
                signal.return_5d_post = calculate_post_return(prices, earnings_dt, 5)
                signal.return_20d_post = calculate_post_return(prices, earnings_dt, 20)

                signals.append(signal)

            except Exception as e:
                logger.debug(f"Error processing {symbol}: {e}")

    logger.info(f"Analyzed {len(signals)} events")
    return signals


def calculate_statistics(signals: list[PreEventSignal]) -> dict[str, Any]:
    """Calculate predictive statistics."""

    df = pd.DataFrame([s.to_dict() for s in signals])

    if df.empty:
        return {"error": "No signals"}

    stats_dict = {
        "total_events": len(df),
        "unique_symbols": df["symbol"].nunique(),
    }

    # Test correlations between pre-event signals and post-event outcomes
    correlation_tests = [
        # (pre_signal, outcome, description)
        ("volume_ratio_5d", "return_1d_post", "Volume spike predicts earnings day return"),
        ("volume_ratio_5d", "surprise_pct", "Volume spike predicts surprise"),
        ("momentum_5d", "return_1d_post", "Momentum predicts earnings return"),
        ("momentum_5d", "surprise_pct", "Momentum predicts surprise"),
        ("momentum_20d", "return_20d_post", "Pre-earnings momentum predicts PEAD"),
        ("volatility_ratio", "return_1d_post", "Vol spike predicts earnings move"),
    ]

    for pre_signal, outcome, desc in correlation_tests:
        pre = df[pre_signal].dropna()
        post = df.loc[pre.index, outcome].dropna()
        common = pre.index.intersection(post.index)

        if len(common) > 30:
            corr, p_val = stats.pearsonr(pre.loc[common], post.loc[common])
            stats_dict[f"corr_{pre_signal}_vs_{outcome}"] = corr
            stats_dict[f"pval_{pre_signal}_vs_{outcome}"] = p_val

    # Quintile analysis: split by pre-signal, compare outcomes
    for pre_signal in ["volume_ratio_5d", "momentum_5d"]:
        valid = df[[pre_signal, "return_1d_post", "surprise_pct"]].dropna()

        if len(valid) > 100:
            valid["quintile"] = pd.qcut(valid[pre_signal], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])

            for q in ["Q1", "Q5"]:
                q_data = valid[valid["quintile"] == q]
                stats_dict[f"{pre_signal}_{q}_avg_return_1d"] = q_data["return_1d_post"].mean()
                stats_dict[f"{pre_signal}_{q}_avg_surprise"] = q_data["surprise_pct"].mean()

    # High volume events (top 20%)
    valid_vol = df[["volume_ratio_5d", "return_1d_post", "surprise_pct"]].dropna()
    if len(valid_vol) > 50:
        threshold = valid_vol["volume_ratio_5d"].quantile(0.8)
        high_vol = valid_vol[valid_vol["volume_ratio_5d"] > threshold]
        low_vol = valid_vol[valid_vol["volume_ratio_5d"] <= valid_vol["volume_ratio_5d"].quantile(0.2)]

        stats_dict["high_volume_events"] = len(high_vol)
        stats_dict["high_volume_avg_return"] = high_vol["return_1d_post"].mean()
        stats_dict["low_volume_avg_return"] = low_vol["return_1d_post"].mean()
        stats_dict["volume_spread"] = high_vol["return_1d_post"].mean() - low_vol["return_1d_post"].mean()

    return stats_dict


def generate_report(stats: dict[str, Any], signals: list[PreEventSignal], output_dir: Path) -> str:
    """Generate pre-event signal analysis report."""

    report = f"""
# Pre-Event Signal Analysis

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Total Events Analyzed:** {stats.get('total_events', 0):,}
**Unique Symbols:** {stats.get('unique_symbols', 0)}

---

## Executive Summary

This study tests whether observable signals BEFORE earnings events predict outcomes AFTER.

---

## 1. Volume-Based Signals

**Question:** Does unusual pre-earnings volume predict the earnings day move?

| Volume Signal | Correlation with Earnings Return | P-Value | Significant? |
|--------------|----------------------------------|---------|--------------|
| 5-day volume ratio | {stats.get('corr_volume_ratio_5d_vs_return_1d_post', 0):.4f} | {stats.get('pval_volume_ratio_5d_vs_return_1d_post', 1):.4f} | {"Yes" if stats.get('pval_volume_ratio_5d_vs_return_1d_post', 1) < 0.05 else "No"} |
| Volume vs Surprise | {stats.get('corr_volume_ratio_5d_vs_surprise_pct', 0):.4f} | {stats.get('pval_volume_ratio_5d_vs_surprise_pct', 1):.4f} | {"Yes" if stats.get('pval_volume_ratio_5d_vs_surprise_pct', 1) < 0.05 else "No"} |

### Volume Quintile Analysis

| Quintile | Avg Earnings Day Return | Avg Surprise |
|----------|------------------------|--------------|
| Q1 (Low Volume) | {stats.get('volume_ratio_5d_Q1_avg_return_1d', 0):+.3f}% | {stats.get('volume_ratio_5d_Q1_avg_surprise', 0):+.2f}% |
| Q5 (High Volume) | {stats.get('volume_ratio_5d_Q5_avg_return_1d', 0):+.3f}% | {stats.get('volume_ratio_5d_Q5_avg_surprise', 0):+.2f}% |

**Volume Spread (High - Low):** {stats.get('volume_spread', 0):+.3f}%

"""

    vol_corr = stats.get('corr_volume_ratio_5d_vs_return_1d_post', 0)
    vol_pval = stats.get('pval_volume_ratio_5d_vs_return_1d_post', 1)

    if abs(vol_corr) > 0.05 and vol_pval < 0.05:
        report += f"""
**FINDING: Volume Signal Detected**
Pre-earnings volume {"positively" if vol_corr > 0 else "negatively"} correlates with earnings returns.
{"High volume before earnings suggests larger moves." if vol_corr > 0 else "High volume may indicate informed selling."}
"""
    else:
        report += """
**FINDING: No Volume Signal**
Pre-earnings volume does not reliably predict earnings outcomes.
"""

    report += f"""
---

## 2. Momentum-Based Signals

**Question:** Does pre-earnings price momentum predict post-earnings returns?

| Momentum Signal | Correlation with Outcome | P-Value | Significant? |
|----------------|-------------------------|---------|--------------|
| 5d momentum vs earnings return | {stats.get('corr_momentum_5d_vs_return_1d_post', 0):.4f} | {stats.get('pval_momentum_5d_vs_return_1d_post', 1):.4f} | {"Yes" if stats.get('pval_momentum_5d_vs_return_1d_post', 1) < 0.05 else "No"} |
| 5d momentum vs surprise | {stats.get('corr_momentum_5d_vs_surprise_pct', 0):.4f} | {stats.get('pval_momentum_5d_vs_surprise_pct', 1):.4f} | {"Yes" if stats.get('pval_momentum_5d_vs_surprise_pct', 1) < 0.05 else "No"} |
| 20d momentum vs PEAD | {stats.get('corr_momentum_20d_vs_return_20d_post', 0):.4f} | {stats.get('pval_momentum_20d_vs_return_20d_post', 1):.4f} | {"Yes" if stats.get('pval_momentum_20d_vs_return_20d_post', 1) < 0.05 else "No"} |

### Momentum Quintile Analysis

| Quintile | Avg Earnings Day Return | Avg Surprise |
|----------|------------------------|--------------|
| Q1 (Worst Momentum) | {stats.get('momentum_5d_Q1_avg_return_1d', 0):+.3f}% | {stats.get('momentum_5d_Q1_avg_surprise', 0):+.2f}% |
| Q5 (Best Momentum) | {stats.get('momentum_5d_Q5_avg_return_1d', 0):+.3f}% | {stats.get('momentum_5d_Q5_avg_surprise', 0):+.2f}% |

"""

    mom_corr = stats.get('corr_momentum_5d_vs_surprise_pct', 0)
    if abs(mom_corr) > 0.05 and stats.get('pval_momentum_5d_vs_surprise_pct', 1) < 0.05:
        report += f"""
**FINDING: Momentum Predicts Surprise**
Pre-earnings momentum {"positively" if mom_corr > 0 else "negatively"} correlates with surprise.
{"Stocks running up tend to beat." if mom_corr > 0 else "Stocks running up tend to miss (expectations too high)."}
"""

    report += f"""
---

## 3. Volatility-Based Signals

**Question:** Does pre-earnings volatility spike predict the earnings move?

| Signal | Correlation | P-Value |
|--------|-------------|---------|
| Volatility ratio vs earnings return | {stats.get('corr_volatility_ratio_vs_return_1d_post', 0):.4f} | {stats.get('pval_volatility_ratio_vs_return_1d_post', 1):.4f} |

---

## 4. Trading System Integration

### Recommended Implementation

1. **Volume Monitoring**
   - Track 5-day volume ratio entering earnings
   - High volume (>1.5x normal) may indicate informed activity
   - Cross-reference with options unusual activity

2. **Momentum Filters**
   - Consider momentum context when positioning for earnings
   - Extreme pre-earnings moves may create reversal risk

3. **Combined Signal**
   - Best setups: normal volume + positive momentum + reasonable valuation
   - Avoid: high volume + extreme momentum (crowded trade)

### Data Collection Requirements

- Daily volume for all watchlist symbols
- 20-day average volume baseline
- Pre-earnings momentum calculation
- Options IV tracking for vol comparison

"""

    return report


def run_pre_event_study(
    symbols: list[str] | None = None,
    years_back: int = 5,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run complete pre-event signal analysis."""

    symbols = symbols or DEFAULT_SYMBOLS
    output_dir = output_dir or paths.base / "pre_event_study"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting pre-event signal study for {len(symbols)} symbols")

    # Collect signals
    signals = analyze_pre_event_signals(symbols, years_back)

    if not signals:
        return {"error": "No signals found"}

    # Calculate statistics
    stats = calculate_statistics(signals)

    # Generate report
    report = generate_report(stats, signals, output_dir)

    # Save outputs
    report_path = output_dir / "pre_event_signal_report.md"
    with open(report_path, "w") as f:
        f.write(report)

    results_path = output_dir / "pre_event_signal_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "statistics": stats,
        }, f, indent=2, default=str)

    # Save detailed signals
    df = pd.DataFrame([s.to_dict() for s in signals])
    df.to_parquet(output_dir / "pre_event_signals.parquet")

    # Print summary
    print("\n" + "=" * 70)
    print("PRE-EVENT SIGNAL STUDY - SUMMARY")
    print("=" * 70)
    print(f"\nEvents analyzed: {len(signals):,}")

    print("\n📊 KEY CORRELATIONS:")
    for key, val in stats.items():
        if key.startswith("corr_") and not key.startswith("pval_"):
            pval_key = key.replace("corr_", "pval_")
            pval = stats.get(pval_key, 1)
            sig = "✅" if pval < 0.05 else "  "
            print(f"  {sig} {key[5:]}: {val:.4f} (p={pval:.4f})")

    print(f"\n📁 Full report: {report_path}")

    return {
        "events_analyzed": len(signals),
        "statistics": stats,
        "report_path": str(report_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Pre-Event Signal Analysis")
    parser.add_argument("--symbols", nargs="+", help="Symbols to analyze")
    parser.add_argument("--years", type=int, default=5, help="Years of history")
    parser.add_argument("--output", type=str, help="Output directory")

    args = parser.parse_args()

    symbols = args.symbols if args.symbols else None
    output_dir = Path(args.output) if args.output else None

    run_pre_event_study(symbols=symbols, years_back=args.years, output_dir=output_dir)


if __name__ == "__main__":
    main()
