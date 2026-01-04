#!/usr/bin/env python3
"""
Walk-Forward Validation Analysis with Real Market Data

This script:
1. Loads real market data from Yahoo Finance
2. Splits into training and validation periods (3mo, 6mo holdouts)
3. Develops strategies on training data
4. Validates with MCPT against random permutations
5. Records all insights for future trading

Usage:
    python workflows/analysis/walk_forward_validation.py
"""

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# Local imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.sources.yahoo import YahooFinanceSource
from src.core import Timeframe
from workflows.runner import create_session, list_sessions


# =============================================================================
# CONFIGURATION
# =============================================================================

# Stock universe - mix of high volume tech and potential value plays
UNIVERSE = [
    # Large cap tech (high liquidity, strong trends)
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA",
    # Semiconductors
    "AMD", "INTC", "AVGO", "QCOM",
    # ETFs for broader market exposure
    "QQQ", "SPY", "IWM",
    # Some mid-cap potential budget picks
    "PLTR", "CRWD", "NET", "SNOW",
]

# Time periods
TODAY = datetime.now()
VALIDATION_3M_START = TODAY - timedelta(days=90)  # Last 3 months = validation
VALIDATION_6M_START = TODAY - timedelta(days=180) # Last 6 months = validation
TRAINING_END_3M = VALIDATION_3M_START  # Training ends where validation starts
TRAINING_END_6M = VALIDATION_6M_START
TRAINING_START = TODAY - timedelta(days=365*2)  # 2 years of training data


# =============================================================================
# STRATEGY IMPLEMENTATIONS
# =============================================================================

class Strategy:
    """Base strategy class."""
    name = "base"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def backtest(self, df: pd.DataFrame, cost_bps: float = 10) -> dict:
        """Run backtest on OHLCV data."""
        if len(df) < 50:
            return {"error": "Insufficient data"}

        signals = self.generate_signals(df)
        positions = signals.shift(1).fillna(0)

        returns = df['close'].pct_change()
        strategy_returns = positions * returns

        # Transaction costs
        trades = (positions.diff().abs() > 0).sum()
        costs = positions.diff().abs() * (cost_bps / 10000)
        strategy_returns = strategy_returns - costs

        # Clean returns
        strategy_returns = strategy_returns.replace([np.inf, -np.inf], 0).fillna(0)

        # Metrics
        total_return = (1 + strategy_returns).prod() - 1
        sharpe = (strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
                  if strategy_returns.std() > 0 else 0)

        cum_returns = (1 + strategy_returns).cumprod()
        rolling_max = cum_returns.expanding().max()
        drawdown = (cum_returns - rolling_max) / rolling_max
        max_dd = drawdown.min()

        winning = (strategy_returns > 0).sum()
        losing = (strategy_returns < 0).sum()
        win_rate = winning / (winning + losing) if (winning + losing) > 0 else 0

        return {
            "returns": strategy_returns,
            "positions": positions,
            "trades": int(trades),
            "total_return": float(total_return),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_dd),
            "win_rate": float(win_rate),
            "n_days": len(df),
        }


class SMACrossover(Strategy):
    """Simple Moving Average Crossover."""

    def __init__(self, fast: int = 10, slow: int = 30):
        self.fast = fast
        self.slow = slow
        self.name = f"SMA_{fast}_{slow}"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_ma = df['close'].rolling(self.fast).mean()
        slow_ma = df['close'].rolling(self.slow).mean()
        return pd.Series(np.where(fast_ma > slow_ma, 1, -1), index=df.index)


class MomentumStrategy(Strategy):
    """Price momentum strategy."""

    def __init__(self, lookback: int = 20, threshold: float = 0.0):
        self.lookback = lookback
        self.threshold = threshold
        self.name = f"Momentum_{lookback}"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        momentum = df['close'].pct_change(self.lookback)
        signals = pd.Series(0, index=df.index)
        signals[momentum > self.threshold] = 1
        signals[momentum < -self.threshold] = -1
        return signals


class RSIMeanReversion(Strategy):
    """RSI mean reversion strategy."""

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.name = f"RSI_{period}"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(self.period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.period).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        signals = pd.Series(0, index=df.index)
        signals[rsi < self.oversold] = 1
        signals[rsi > self.overbought] = -1
        return signals.ffill().fillna(0)


class BreakoutStrategy(Strategy):
    """Channel breakout strategy."""

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.name = f"Breakout_{lookback}"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        high_channel = df['high'].rolling(self.lookback).max()
        low_channel = df['low'].rolling(self.lookback).min()

        signals = pd.Series(0, index=df.index)
        signals[df['close'] >= high_channel.shift(1)] = 1
        signals[df['close'] <= low_channel.shift(1)] = -1
        return signals.ffill().fillna(0)


class TrendFollowing(Strategy):
    """ADX-based trend following."""

    def __init__(self, period: int = 14, threshold: float = 25):
        self.period = period
        self.threshold = threshold
        self.name = f"TrendFollow_{period}"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        high, low, close = df['high'], df['low'], df['close']

        plus_dm = high.diff().clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(self.period).mean()
        plus_di = 100 * (plus_dm.rolling(self.period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(self.period).mean() / atr)

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(self.period).mean()

        signals = pd.Series(0, index=df.index)
        trending = adx > self.threshold
        signals[trending & (plus_di > minus_di)] = 1
        signals[trending & (plus_di < minus_di)] = -1

        return signals


class BollingerReversion(Strategy):
    """Bollinger Band mean reversion."""

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std
        self.name = f"Bollinger_{period}"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma = df['close'].rolling(self.period).mean()
        std = df['close'].rolling(self.period).std()
        upper = ma + self.num_std * std
        lower = ma - self.num_std * std

        signals = pd.Series(0, index=df.index)
        signals[df['close'] < lower] = 1
        signals[df['close'] > upper] = -1
        return signals.ffill().fillna(0)


# All strategies to test
STRATEGIES = [
    SMACrossover(5, 20),
    SMACrossover(10, 30),
    SMACrossover(20, 50),
    MomentumStrategy(10),
    MomentumStrategy(20),
    MomentumStrategy(60),
    RSIMeanReversion(7, 20, 80),
    RSIMeanReversion(14, 30, 70),
    BreakoutStrategy(10),
    BreakoutStrategy(20),
    TrendFollowing(14, 25),
    BollingerReversion(10, 1.5),
    BollingerReversion(20, 2.0),
]


# =============================================================================
# MCPT IMPLEMENTATION (Simplified)
# =============================================================================

def permute_returns(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """
    Permute OHLCV data by shuffling gap and intrabar components.
    This preserves return distribution but destroys temporal patterns.
    """
    np.random.seed(seed)
    n = len(df)
    if n < 20:
        return df.copy()

    # Decompose into components
    prev_close = df['close'].shift(1)
    gap_returns = ((df['open'] - prev_close) / prev_close).fillna(0).values
    intrabar_returns = ((df['close'] - df['open']) / df['open']).fillna(0).values

    # Shuffle independently (skip first bar)
    perm_gap = np.random.permutation(n - 1)
    perm_intra = np.random.permutation(n - 1)

    shuffled_gaps = gap_returns[1:][perm_gap]
    shuffled_intra = intrabar_returns[1:][perm_intra]

    # Reconstruct prices
    prices = np.zeros(n)
    opens = np.zeros(n)
    prices[0] = df['close'].iloc[0]
    opens[0] = df['open'].iloc[0]

    for i in range(1, n):
        opens[i] = prices[i-1] * (1 + shuffled_gaps[i-1])
        prices[i] = opens[i] * (1 + shuffled_intra[i-1])

    # Reconstruct high/low maintaining structure
    high_rel = ((df['high'] - df['open']) / df['open']).fillna(0).values
    low_rel = ((df['low'] - df['open']) / df['open']).fillna(0).values

    permuted = pd.DataFrame(index=df.index)
    permuted['open'] = opens
    permuted['close'] = prices
    permuted['high'] = opens * (1 + np.abs(high_rel))
    permuted['low'] = opens * (1 - np.abs(low_rel))
    permuted['volume'] = df['volume'].values

    # Ensure OHLC constraints
    permuted['high'] = permuted[['open', 'close', 'high']].max(axis=1)
    permuted['low'] = permuted[['open', 'close', 'low']].min(axis=1)

    return permuted


def mcpt_test(
    strategy: Strategy,
    df: pd.DataFrame,
    n_permutations: int = 500,
    seed: int = 42
) -> dict:
    """
    Run Monte Carlo Permutation Test.
    Returns p-value for strategy Sharpe ratio.
    """
    # Original result
    original = strategy.backtest(df)
    if "error" in original:
        return {"error": original["error"]}

    original_sharpe = original["sharpe_ratio"]

    # Run permutations
    perm_sharpes = []
    for i in range(n_permutations):
        try:
            permuted_df = permute_returns(df, seed + i)
            perm_result = strategy.backtest(permuted_df)
            if "error" not in perm_result:
                perm_sharpes.append(perm_result["sharpe_ratio"])
        except Exception:
            continue

    if len(perm_sharpes) < 10:
        return {"error": "Insufficient permutations succeeded"}

    # Calculate p-value (proportion of permuted Sharpes >= original)
    p_value = (np.sum(np.array(perm_sharpes) >= original_sharpe) + 1) / (len(perm_sharpes) + 1)

    return {
        "original_sharpe": original_sharpe,
        "original_return": original["total_return"],
        "original_max_dd": original["max_drawdown"],
        "p_value": p_value,
        "is_significant": p_value < 0.05,
        "perm_sharpe_mean": np.mean(perm_sharpes),
        "perm_sharpe_std": np.std(perm_sharpes),
        "perm_5th": np.percentile(perm_sharpes, 5),
        "perm_95th": np.percentile(perm_sharpes, 95),
        "n_permutations": len(perm_sharpes),
    }


# =============================================================================
# DATA LOADING
# =============================================================================

async def load_market_data(
    symbols: list[str],
    start: datetime,
    end: datetime
) -> dict[str, pd.DataFrame]:
    """Load market data from Yahoo Finance."""
    print(f"Loading data for {len(symbols)} symbols...")

    source = YahooFinanceSource(rate_limit_delay=0.2)

    data = await source.fetch_multiple(
        symbols=symbols,
        start=start,
        end=end,
        timeframe=Timeframe.DAILY
    )

    print(f"Loaded data for {len(data)} symbols")
    for sym, df in data.items():
        if len(df) > 0:
            ret = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
            print(f"  {sym}: {len(df)} days, {ret:+.1f}%")

    return data


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

@dataclass
class ValidationResult:
    """Results from a single validation run."""
    strategy_name: str
    symbol: str
    period: str  # "3m" or "6m"

    # Training metrics
    train_sharpe: float
    train_return: float
    train_days: int

    # Validation metrics
    val_sharpe: float
    val_return: float
    val_max_dd: float
    val_days: int

    # MCPT results
    mcpt_p_value: float
    mcpt_significant: bool
    mcpt_perm_mean: float
    mcpt_perm_95th: float


async def run_validation_analysis() -> dict:
    """Run the full walk-forward validation analysis."""

    print("=" * 80)
    print("WALK-FORWARD VALIDATION ANALYSIS WITH REAL MARKET DATA")
    print("=" * 80)
    print(f"\nAnalysis Date: {TODAY.strftime('%Y-%m-%d')}")
    print(f"Universe: {len(UNIVERSE)} symbols")
    print(f"Validation Periods: 3-month and 6-month holdouts")
    print()

    # Create session for this analysis
    session = create_session(
        name="walk_forward_validation",
        session_type="mcpt",
        symbols=UNIVERSE,
        description="Walk-forward validation with 3m and 6m holdout periods"
    )
    print(f"Session ID: {session.session_id}")
    print(f"Output Path: {session.session_path}")

    # Load all data
    print("\n" + "=" * 80)
    print("STEP 1: LOADING MARKET DATA")
    print("=" * 80)

    all_data = await load_market_data(UNIVERSE, TRAINING_START, TODAY)

    if len(all_data) == 0:
        print("ERROR: No data loaded!")
        return {"error": "No data loaded"}

    # Split data into periods
    print("\n" + "=" * 80)
    print("STEP 2: SPLITTING DATA INTO TRAINING/VALIDATION PERIODS")
    print("=" * 80)

    data_splits = {}
    for symbol, df in all_data.items():
        df = df.sort_index()

        # 3-month validation split
        train_3m = df[df.index < pd.Timestamp(VALIDATION_3M_START)]
        val_3m = df[df.index >= pd.Timestamp(VALIDATION_3M_START)]

        # 6-month validation split
        train_6m = df[df.index < pd.Timestamp(VALIDATION_6M_START)]
        val_6m = df[df.index >= pd.Timestamp(VALIDATION_6M_START)]

        if len(train_3m) >= 100 and len(val_3m) >= 20:
            data_splits[symbol] = {
                "train_3m": train_3m,
                "val_3m": val_3m,
                "train_6m": train_6m,
                "val_6m": val_6m,
            }
            print(f"  {symbol}: Train(3m)={len(train_3m)}, Val(3m)={len(val_3m)}, "
                  f"Train(6m)={len(train_6m)}, Val(6m)={len(val_6m)}")

    if len(data_splits) == 0:
        print("ERROR: Insufficient data for any symbol!")
        return {"error": "Insufficient data"}

    # Run strategy development on training data
    print("\n" + "=" * 80)
    print("STEP 3: DEVELOPING STRATEGIES ON TRAINING DATA")
    print("=" * 80)

    training_results = []
    for symbol, splits in data_splits.items():
        train_df = splits["train_6m"]  # Use 6m training for development

        for strategy in STRATEGIES:
            result = strategy.backtest(train_df)
            if "error" not in result:
                training_results.append({
                    "strategy": strategy.name,
                    "symbol": symbol,
                    "sharpe": result["sharpe_ratio"],
                    "return": result["total_return"],
                    "max_dd": result["max_drawdown"],
                    "trades": result["trades"],
                })

    # Sort by Sharpe ratio
    training_results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\nTop 20 Strategy-Symbol combinations on training data:")
    print(f"{'Rank':<5} {'Strategy':<20} {'Symbol':<8} {'Sharpe':>8} {'Return':>10} {'MaxDD':>8}")
    print("-" * 65)
    for i, r in enumerate(training_results[:20], 1):
        print(f"{i:<5} {r['strategy']:<20} {r['symbol']:<8} {r['sharpe']:>8.2f} {r['return']:>9.1%} {r['max_dd']:>7.1%}")

    # Select top strategies for validation
    # Use top 5 unique strategies
    seen_strategies = set()
    top_strategies = []
    for r in training_results:
        if r["strategy"] not in seen_strategies and len(top_strategies) < 5:
            seen_strategies.add(r["strategy"])
            top_strategies.append(r)

    print(f"\nSelected {len(top_strategies)} strategies for validation")

    # Run MCPT validation
    print("\n" + "=" * 80)
    print("STEP 4: MCPT VALIDATION ON HOLDOUT PERIODS")
    print("=" * 80)

    validation_results = []

    for period_name, val_key, train_key in [("3m", "val_3m", "train_3m"), ("6m", "val_6m", "train_6m")]:
        print(f"\n--- {period_name.upper()} Validation Period ---")

        for strat_info in top_strategies:
            strategy_name = strat_info["strategy"]

            # Find the strategy object
            strategy = None
            for s in STRATEGIES:
                if s.name == strategy_name:
                    strategy = s
                    break

            if strategy is None:
                continue

            # Test on each symbol
            for symbol, splits in data_splits.items():
                train_df = splits[train_key]
                val_df = splits[val_key]

                if len(val_df) < 20:
                    continue

                # Training metrics
                train_result = strategy.backtest(train_df)
                if "error" in train_result:
                    continue

                # Validation metrics
                val_result = strategy.backtest(val_df)
                if "error" in val_result:
                    continue

                # MCPT on validation data
                print(f"  Testing {strategy_name} on {symbol} ({period_name})...", end=" ")
                mcpt_result = mcpt_test(strategy, val_df, n_permutations=200)

                if "error" not in mcpt_result:
                    sig_mark = "✓" if mcpt_result["is_significant"] else "✗"
                    print(f"p={mcpt_result['p_value']:.3f} {sig_mark}")

                    validation_results.append(ValidationResult(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        period=period_name,
                        train_sharpe=train_result["sharpe_ratio"],
                        train_return=train_result["total_return"],
                        train_days=train_result["n_days"],
                        val_sharpe=val_result["sharpe_ratio"],
                        val_return=val_result["total_return"],
                        val_max_dd=val_result["max_drawdown"],
                        val_days=val_result["n_days"],
                        mcpt_p_value=mcpt_result["p_value"],
                        mcpt_significant=mcpt_result["is_significant"],
                        mcpt_perm_mean=mcpt_result["perm_sharpe_mean"],
                        mcpt_perm_95th=mcpt_result["perm_95th"],
                    ))
                else:
                    print(f"Error: {mcpt_result['error']}")

    # Analyze results
    print("\n" + "=" * 80)
    print("STEP 5: ANALYSIS AND INSIGHTS")
    print("=" * 80)

    # Convert to DataFrame for analysis
    results_df = pd.DataFrame([asdict(r) for r in validation_results])

    if len(results_df) == 0:
        print("No validation results to analyze!")
        insights = {"error": "No validation results"}
    else:
        # Save raw results
        session.save_data(results_df, "validation_results", format="csv")

        # Summary statistics
        summary = {
            "total_tests": len(results_df),
            "significant_count": results_df["mcpt_significant"].sum(),
            "significance_rate": results_df["mcpt_significant"].mean(),
        }

        print(f"\nTotal strategy-symbol-period combinations tested: {summary['total_tests']}")
        print(f"Statistically significant (p < 0.05): {summary['significant_count']} ({summary['significance_rate']:.1%})")

        # Significant results
        significant = results_df[results_df["mcpt_significant"]]

        if len(significant) > 0:
            print(f"\n🎯 SIGNIFICANT RESULTS (p < 0.05):")
            print(f"{'Strategy':<20} {'Symbol':<8} {'Period':<6} {'Val Sharpe':>10} {'Val Return':>10} {'p-value':>8}")
            print("-" * 70)
            for _, row in significant.sort_values("val_sharpe", ascending=False).iterrows():
                print(f"{row['strategy_name']:<20} {row['symbol']:<8} {row['period']:<6} "
                      f"{row['val_sharpe']:>10.2f} {row['val_return']:>9.1%} {row['mcpt_p_value']:>8.3f}")
        else:
            print("\n⚠️ No statistically significant strategies found!")
            print("This is actually informative - most strategies don't beat random!")

        # Compare 3m vs 6m validation
        print("\n--- Period Comparison ---")
        for period in ["3m", "6m"]:
            period_data = results_df[results_df["period"] == period]
            if len(period_data) > 0:
                sig_rate = period_data["mcpt_significant"].mean()
                avg_p = period_data["mcpt_p_value"].mean()
                print(f"{period}: {len(period_data)} tests, {sig_rate:.1%} significant, avg p-value: {avg_p:.3f}")

        # Best strategies overall
        print("\n--- Top Strategies by Validation Sharpe (regardless of significance) ---")
        top_val = results_df.nlargest(10, "val_sharpe")
        for _, row in top_val.iterrows():
            sig = "✓" if row["mcpt_significant"] else "✗"
            print(f"  {row['strategy_name']} on {row['symbol']} ({row['period']}): "
                  f"Sharpe={row['val_sharpe']:.2f}, Return={row['val_return']:.1%}, p={row['mcpt_p_value']:.3f} {sig}")

        # Generate insights
        insights = generate_insights(results_df, training_results)

        # Save insights
        session.save_data(insights, "insights", format="json")

    # Generate HTML report
    html = generate_html_report(
        training_results[:20],
        validation_results,
        insights if "insights" in dir() else {}
    )
    session.save_html_report(html)

    # Complete session
    metrics = {
        "symbols_tested": len(data_splits),
        "strategies_tested": len(STRATEGIES),
        "total_validations": len(validation_results),
        "significant_count": len([r for r in validation_results if r.mcpt_significant]),
    }

    interpretation = generate_interpretation(insights if "insights" in dir() else {}, validation_results)
    result = session.complete(metrics, interpretation)

    print(f"\n{'=' * 80}")
    print("ANALYSIS COMPLETE")
    print(f"{'=' * 80}")
    print(f"Session ID: {result.session_id}")
    print(f"Report: {result.session_path}/report.html")
    print(f"Data: {result.session_path}/data/")

    return {
        "session_id": result.session_id,
        "session_path": str(result.session_path),
        "metrics": metrics,
        "insights": insights if "insights" in dir() else {},
    }


def generate_insights(results_df: pd.DataFrame, training_results: list) -> dict:
    """Generate actionable insights from the analysis."""

    insights = {
        "generated_at": datetime.now().isoformat(),
        "summary": {},
        "recommendations": [],
        "warnings": [],
        "next_steps": [],
    }

    # Overall significance
    sig_rate = results_df["mcpt_significant"].mean()
    insights["summary"]["significance_rate"] = sig_rate

    if sig_rate < 0.1:
        insights["warnings"].append(
            "Very few strategies show statistical significance. "
            "Most apparent alpha is likely due to random chance or overfitting."
        )

    # Best strategy-symbol combinations
    significant = results_df[results_df["mcpt_significant"]]
    if len(significant) > 0:
        best = significant.nlargest(3, "val_sharpe")
        insights["summary"]["best_combinations"] = [
            {
                "strategy": row["strategy_name"],
                "symbol": row["symbol"],
                "val_sharpe": row["val_sharpe"],
                "p_value": row["mcpt_p_value"],
            }
            for _, row in best.iterrows()
        ]

        # Strategy type analysis
        for strat in best["strategy_name"].unique():
            insights["recommendations"].append(
                f"Consider {strat} for live trading - showed significance in validation"
            )

    # Consistency check (same strategy significant in both periods)
    consistent = []
    for (strat, sym), group in results_df.groupby(["strategy_name", "symbol"]):
        if len(group) == 2 and group["mcpt_significant"].all():
            consistent.append({"strategy": strat, "symbol": sym})

    if consistent:
        insights["summary"]["consistent_performers"] = consistent
        insights["recommendations"].append(
            f"Found {len(consistent)} strategy-symbol pairs significant in BOTH 3m and 6m validation"
        )
    else:
        insights["warnings"].append(
            "No strategy-symbol combination was significant in both validation periods"
        )

    # Overfitting detection
    high_train_low_val = results_df[
        (results_df["train_sharpe"] > 1.5) &
        (results_df["val_sharpe"] < 0.5)
    ]
    if len(high_train_low_val) > len(results_df) * 0.3:
        insights["warnings"].append(
            "Significant overfitting detected: many strategies perform well in-sample but poorly out-of-sample"
        )

    # Next steps
    insights["next_steps"] = [
        "Paper trade the significant strategies for 1-2 weeks before committing capital",
        "Monitor for regime changes that could invalidate the strategies",
        "Consider position sizing based on Kelly criterion using the validation Sharpe ratios",
        "Set up stop-losses based on the observed max drawdowns",
        "Re-run this analysis monthly to check for strategy decay",
    ]

    return insights


def generate_interpretation(insights: dict, validation_results: list) -> str:
    """Generate human-readable interpretation."""

    lines = ["# Walk-Forward Validation Results\n"]

    lines.append("## Summary\n")
    if insights.get("summary", {}).get("significance_rate"):
        rate = insights["summary"]["significance_rate"]
        lines.append(f"- **Significance Rate**: {rate:.1%} of strategy-symbol combinations\n")

    lines.append(f"- **Total Validations**: {len(validation_results)}\n")
    sig_count = len([r for r in validation_results if r.mcpt_significant])
    lines.append(f"- **Significant Results**: {sig_count}\n")

    if insights.get("summary", {}).get("best_combinations"):
        lines.append("\n## Top Performers\n")
        for combo in insights["summary"]["best_combinations"]:
            lines.append(f"- {combo['strategy']} on {combo['symbol']}: "
                        f"Sharpe={combo['val_sharpe']:.2f}, p={combo['p_value']:.3f}\n")

    if insights.get("warnings"):
        lines.append("\n## Warnings\n")
        for warning in insights["warnings"]:
            lines.append(f"- ⚠️ {warning}\n")

    if insights.get("recommendations"):
        lines.append("\n## Recommendations\n")
        for rec in insights["recommendations"]:
            lines.append(f"- {rec}\n")

    if insights.get("next_steps"):
        lines.append("\n## Next Steps\n")
        for step in insights["next_steps"]:
            lines.append(f"1. {step}\n")

    return "".join(lines)


def generate_html_report(
    training_results: list,
    validation_results: list,
    insights: dict
) -> str:
    """Generate HTML report."""

    significant_results = [r for r in validation_results if r.mcpt_significant]

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Walk-Forward Validation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            background: #f9fafb;
            color: #1f2937;
        }}
        h1 {{ color: #1e40af; border-bottom: 2px solid #3b82f6; padding-bottom: 0.5rem; }}
        h2 {{ color: #374151; margin-top: 2rem; }}
        .summary-box {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin: 1rem 0;
        }}
        .metric-card {{
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #1e40af;
        }}
        .metric-label {{
            color: #6b7280;
            font-size: 0.875rem;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            margin: 1rem 0;
        }}
        th, td {{
            border: 1px solid #e5e7eb;
            padding: 0.75rem;
            text-align: left;
        }}
        th {{
            background: #f3f4f6;
            font-weight: 600;
        }}
        tr.significant {{
            background: #dcfce7;
        }}
        tr.not-significant {{
            background: #fef3c7;
        }}
        .warning {{
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 1rem;
            margin: 1rem 0;
        }}
        .success {{
            background: #dcfce7;
            border-left: 4px solid #22c55e;
            padding: 1rem;
            margin: 1rem 0;
        }}
        .recommendation {{
            background: #dbeafe;
            border-left: 4px solid #3b82f6;
            padding: 1rem;
            margin: 1rem 0;
        }}
        .footer {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
            color: #6b7280;
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <h1>Walk-Forward Validation Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

    <div class="summary-box">
        <div class="metric-card">
            <div class="metric-value">{len(validation_results)}</div>
            <div class="metric-label">Total Tests</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(significant_results)}</div>
            <div class="metric-label">Significant (p&lt;0.05)</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(significant_results)/max(len(validation_results),1)*100:.1f}%</div>
            <div class="metric-label">Significance Rate</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{len(set(r.symbol for r in validation_results))}</div>
            <div class="metric-label">Symbols Tested</div>
        </div>
    </div>

    <h2>Top Training Results</h2>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Sharpe</th>
                <th>Return</th>
                <th>Max DD</th>
            </tr>
        </thead>
        <tbody>
"""

    for i, r in enumerate(training_results[:15], 1):
        html += f"""            <tr>
                <td>{i}</td>
                <td>{r['strategy']}</td>
                <td>{r['symbol']}</td>
                <td>{r['sharpe']:.2f}</td>
                <td>{r['return']:.1%}</td>
                <td>{r['max_dd']:.1%}</td>
            </tr>
"""

    html += """        </tbody>
    </table>

    <h2>Validation Results (MCPT)</h2>
    <table>
        <thead>
            <tr>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Period</th>
                <th>Val Sharpe</th>
                <th>Val Return</th>
                <th>p-value</th>
                <th>Significant</th>
            </tr>
        </thead>
        <tbody>
"""

    sorted_results = sorted(validation_results, key=lambda x: x.val_sharpe, reverse=True)
    for r in sorted_results[:30]:
        row_class = "significant" if r.mcpt_significant else "not-significant"
        sig_text = "✓ Yes" if r.mcpt_significant else "✗ No"
        html += f"""            <tr class="{row_class}">
                <td>{r.strategy_name}</td>
                <td>{r.symbol}</td>
                <td>{r.period}</td>
                <td>{r.val_sharpe:.2f}</td>
                <td>{r.val_return:.1%}</td>
                <td>{r.mcpt_p_value:.3f}</td>
                <td>{sig_text}</td>
            </tr>
"""

    html += """        </tbody>
    </table>
"""

    # Add warnings and recommendations
    if insights.get("warnings"):
        for warning in insights["warnings"]:
            html += f'    <div class="warning"><strong>⚠️ Warning:</strong> {warning}</div>\n'

    if insights.get("recommendations"):
        for rec in insights["recommendations"]:
            html += f'    <div class="recommendation"><strong>💡 Recommendation:</strong> {rec}</div>\n'

    if significant_results:
        html += '    <div class="success"><strong>✓ Success:</strong> '
        html += f'Found {len(significant_results)} statistically significant strategy-symbol combinations!</div>\n'

    html += f"""
    <h2>Next Steps</h2>
    <ol>
"""

    for step in insights.get("next_steps", []):
        html += f"        <li>{step}</li>\n"

    html += """    </ol>

    <div class="footer">
        <p>This analysis uses Monte Carlo Permutation Testing (MCPT) to validate whether strategy performance
        is statistically significant or could have occurred by random chance.</p>
        <p>A p-value &lt; 0.05 indicates the strategy's performance is unlikely to be due to chance alone.</p>
    </div>
</body>
</html>
"""

    return html


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    result = asyncio.run(run_validation_analysis())
    print(f"\nFinal Result: {json.dumps(result, indent=2, default=str)}")
