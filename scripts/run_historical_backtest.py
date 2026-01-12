#!/usr/bin/env python3
"""
Historical Data Backtest

Runs backtests using the 6-month historical data we collected.
Tests multiple strategies:
1. VIX Mean Reversion - Buy SPY when VIX is elevated
2. Breadth Momentum - Buy when market breadth is strong
3. Volatility Regime - Reduce exposure in high volatility
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths
from src.core import Direction, Signal, SignalType, Symbol, Timeframe
from src.strategies.base import RuleBasedStrategy
from src.evaluation.backtest.engine import VectorizedBacktest, BacktestConfig, BacktestResult


# ==============================================================================
# Load Historical Data
# ==============================================================================

def load_historical_data() -> dict:
    """Load all historical data from JSON files."""
    history_dir = paths.live / "historical_data"

    data = {}

    # Load VIX history
    vix_file = history_dir / "vix_history_6mo.json"
    if vix_file.exists():
        with open(vix_file) as f:
            data["vix"] = json.load(f)["vix"]
        print(f"Loaded VIX: {len(data['vix'])} days")

    # Load ETF history
    etf_file = history_dir / "etf_history_6mo.json"
    if etf_file.exists():
        with open(etf_file) as f:
            data["etfs"] = json.load(f)["etfs"]
        print(f"Loaded ETFs: {len(data['etfs'])} symbols")

    # Load breadth history
    breadth_file = history_dir / "breadth_history_6mo.json"
    if breadth_file.exists():
        with open(breadth_file) as f:
            data["breadth"] = json.load(f)["breadth"]
        print(f"Loaded Breadth: {len(data['breadth'])} days")

    # Load put/call history
    pc_file = history_dir / "put_call_history_6mo.json"
    if pc_file.exists():
        with open(pc_file) as f:
            data["put_call"] = json.load(f)["put_call"]
        print(f"Loaded Put/Call: {len(data['put_call'])} days")

    # Load volatility history
    vol_file = history_dir / "volatility_history_6mo.json"
    if vol_file.exists():
        with open(vol_file) as f:
            data["volatility"] = json.load(f)["volatility"]
        print(f"Loaded Volatility: {len(data['volatility'])} symbols")

    return data


def create_ohlcv_dataframe(etf_records: list) -> pd.DataFrame:
    """Convert ETF records to OHLCV DataFrame."""
    df = pd.DataFrame(etf_records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.sort_index()

    # Rename columns to standard OHLCV
    df.columns = [c.lower() for c in df.columns]

    return df


def create_signal_dataframe(vix_records: list, breadth_records: list) -> pd.DataFrame:
    """Create a combined signal DataFrame from VIX and breadth data."""
    vix_df = pd.DataFrame(vix_records)
    vix_df["date"] = pd.to_datetime(vix_df["date"])
    vix_df = vix_df.set_index("date")

    breadth_df = pd.DataFrame(breadth_records)
    breadth_df["date"] = pd.to_datetime(breadth_df["date"])
    breadth_df = breadth_df.set_index("date")

    # Merge
    combined = vix_df.join(breadth_df, how="outer", rsuffix="_breadth")

    return combined


# ==============================================================================
# Strategy Implementations
# ==============================================================================

class VIXMeanReversionStrategy(RuleBasedStrategy):
    """
    VIX Mean Reversion Strategy

    - When VIX is elevated (>20), buy SPY expecting mean reversion
    - When VIX is low (<15), reduce exposure (complacency)
    - Uses VIX term structure for confirmation
    """

    name = "vix_mean_reversion"
    description = "Buy SPY when VIX elevated, expecting mean reversion"

    def __init__(
        self,
        universe: list[Symbol],
        vix_data: pd.DataFrame,
        high_vix_threshold: float = 20,
        low_vix_threshold: float = 15,
        **params,
    ):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.vix_data = vix_data
        self.high_vix = high_vix_threshold
        self.low_vix = low_vix_threshold

    def get_required_history(self) -> int:
        return 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        signals = []

        if timestamp is None:
            return signals

        # Get VIX data for this date
        try:
            # Try to find VIX data for this date
            date_str = timestamp.strftime("%Y-%m-%d")
            if date_str in self.vix_data.index:
                vix_row = self.vix_data.loc[date_str]
            else:
                # Find nearest date
                idx = self.vix_data.index.get_indexer([date_str], method="ffill")[0]
                if idx >= 0:
                    vix_row = self.vix_data.iloc[idx]
                else:
                    return signals

            vix_spot = vix_row.get("vix_spot", 15)
            vix_signal = vix_row.get("signal", 0)

        except Exception:
            return signals

        # Generate signals based on VIX level
        for symbol in self.universe:
            if vix_spot > self.high_vix:
                # High VIX = Fear = Contrarian Buy
                strength = min((vix_spot - self.high_vix) / 10, 1.0) * 0.8
                signals.append(self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=strength,
                    confidence=0.6,
                    timestamp=timestamp,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={"vix": vix_spot, "reason": "high_vix_reversal"},
                ))
            elif vix_spot < self.low_vix:
                # Low VIX = Complacency = Reduce exposure
                strength = -0.3  # Small short or exit signal
                signals.append(self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=strength,
                    confidence=0.4,
                    timestamp=timestamp,
                    signal_type=SignalType.EXIT_LONG,
                    metadata={"vix": vix_spot, "reason": "low_vix_complacency"},
                ))

        return signals


class BreadthMomentumStrategy(RuleBasedStrategy):
    """
    Breadth Momentum Strategy

    - Buy when market breadth is strong (>60% sectors advancing)
    - Sell when breadth is weak (<40% sectors advancing)
    """

    name = "breadth_momentum"
    description = "Follow market breadth for momentum signals"

    def __init__(
        self,
        universe: list[Symbol],
        breadth_data: pd.DataFrame,
        strong_threshold: float = 0.6,
        weak_threshold: float = 0.4,
        **params,
    ):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.breadth_data = breadth_data
        self.strong = strong_threshold
        self.weak = weak_threshold

    def get_required_history(self) -> int:
        return 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        signals = []

        if timestamp is None:
            return signals

        try:
            date_str = timestamp.strftime("%Y-%m-%d")
            if date_str in self.breadth_data.index:
                breadth_row = self.breadth_data.loc[date_str]
            else:
                idx = self.breadth_data.index.get_indexer([date_str], method="ffill")[0]
                if idx >= 0:
                    breadth_row = self.breadth_data.iloc[idx]
                else:
                    return signals

            pct_advancing = breadth_row.get("pct_advancing", 0.5)
            breadth_signal = breadth_row.get("breadth_signal", 0)

        except Exception:
            return signals

        for symbol in self.universe:
            if pct_advancing > self.strong:
                # Strong breadth = bullish momentum
                strength = (pct_advancing - self.strong) / 0.4 * 0.6
                signals.append(self.create_signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=min(strength, 0.8),
                    confidence=0.55,
                    timestamp=timestamp,
                    signal_type=SignalType.ENTRY_LONG,
                    metadata={"breadth": pct_advancing, "reason": "strong_breadth"},
                ))
            elif pct_advancing < self.weak:
                # Weak breadth = bearish
                strength = -((self.weak - pct_advancing) / 0.4 * 0.6)
                signals.append(self.create_signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=max(strength, -0.8),
                    confidence=0.5,
                    timestamp=timestamp,
                    signal_type=SignalType.EXIT_LONG,
                    metadata={"breadth": pct_advancing, "reason": "weak_breadth"},
                ))

        return signals


class CombinedRegimeStrategy(RuleBasedStrategy):
    """
    Combined Regime Strategy

    Uses VIX, breadth, and volatility together:
    - High VIX + weak breadth = stay cautious
    - High VIX + strong breadth = buy the dip
    - Low VIX + strong breadth = full long
    - Low VIX + weak breadth = reduce exposure
    """

    name = "combined_regime"
    description = "Multi-factor regime-based strategy"

    def __init__(
        self,
        universe: list[Symbol],
        signal_data: pd.DataFrame,
        **params,
    ):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.signal_data = signal_data

    def get_required_history(self) -> int:
        return 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        signals = []

        if timestamp is None:
            return signals

        try:
            date_str = timestamp.strftime("%Y-%m-%d")
            if date_str in self.signal_data.index:
                row = self.signal_data.loc[date_str]
            else:
                idx = self.signal_data.index.get_indexer([date_str], method="ffill")[0]
                if idx >= 0:
                    row = self.signal_data.iloc[idx]
                else:
                    return signals

            vix_spot = row.get("vix_spot", 15)
            vix_signal = row.get("signal", 0)
            pct_advancing = row.get("pct_advancing", 0.5)
            breadth_signal = row.get("breadth_signal", 0)

        except Exception:
            return signals

        # Combine signals
        combined_score = 0

        # VIX component (contrarian)
        if vix_spot > 25:
            combined_score += 0.4  # Buy fear
        elif vix_spot > 20:
            combined_score += 0.2
        elif vix_spot < 12:
            combined_score -= 0.3  # Reduce on complacency

        # Breadth component
        if pct_advancing > 0.7:
            combined_score += 0.3
        elif pct_advancing > 0.5:
            combined_score += 0.1
        elif pct_advancing < 0.3:
            combined_score -= 0.4

        # Use pre-computed signals
        combined_score += vix_signal * 0.2
        combined_score += breadth_signal * 0.2

        # Clamp
        combined_score = max(-1, min(1, combined_score))

        for symbol in self.universe:
            if abs(combined_score) > 0.1:
                direction = Direction.LONG if combined_score > 0 else Direction.SHORT
                signal_type = SignalType.ENTRY_LONG if combined_score > 0 else SignalType.EXIT_LONG

                signals.append(self.create_signal(
                    symbol=symbol,
                    direction=direction,
                    strength=abs(combined_score),
                    confidence=0.55,
                    timestamp=timestamp,
                    signal_type=signal_type,
                    metadata={
                        "vix": vix_spot,
                        "breadth": pct_advancing,
                        "combined_score": combined_score,
                    },
                ))

        return signals


# ==============================================================================
# Backtest Runner
# ==============================================================================

def print_results(name: str, result: BacktestResult):
    """Print backtest results."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print('='*60)

    m = result.metrics
    print(f"Total Return: {m.get('total_return', 0)*100:.2f}%")
    print(f"CAGR: {m.get('cagr', 0)*100:.2f}%")
    print(f"Sharpe Ratio: {m.get('sharpe_ratio', 0):.2f}")
    print(f"Max Drawdown: {m.get('max_drawdown', 0)*100:.2f}%")
    print(f"Volatility: {m.get('volatility', 0)*100:.2f}%")
    print(f"Number of Trades: {m.get('num_trades', 0)}")
    print(f"Final Value: ${m.get('final_value', 100000):,.2f}")

    return m


def main():
    print("="*60)
    print("  HISTORICAL DATA BACKTEST")
    print("  Using 6 months of collected data")
    print("="*60)

    # Load data
    print("\nLoading historical data...")
    data = load_historical_data()

    if not data.get("vix") or not data.get("etfs"):
        print("Error: Historical data not found. Run collect_historical_data.py first.")
        return 1

    # Create DataFrames
    print("\nPreparing data...")

    # ETF prices
    spy_df = create_ohlcv_dataframe(data["etfs"]["SPY"]["records"])
    qqq_df = create_ohlcv_dataframe(data["etfs"]["QQQ"]["records"])

    print(f"SPY: {len(spy_df)} days from {spy_df.index[0]} to {spy_df.index[-1]}")
    print(f"QQQ: {len(qqq_df)} days from {qqq_df.index[0]} to {qqq_df.index[-1]}")

    # VIX signal data
    vix_df = pd.DataFrame(data["vix"])
    vix_df["date"] = pd.to_datetime(vix_df["date"])
    vix_df = vix_df.set_index("date")

    # Breadth data
    breadth_df = pd.DataFrame(data["breadth"])
    breadth_df["date"] = pd.to_datetime(breadth_df["date"])
    breadth_df = breadth_df.set_index("date")

    # Combined signal data
    signal_df = create_signal_dataframe(data["vix"], data["breadth"])

    # Backtest configuration
    config = BacktestConfig(
        initial_capital=100_000,
        position_size=0.20,  # 20% per position
        max_positions=5,
        allow_short=False,  # Long only
        signal_delay=1,  # Execute next day
        use_open_price=True,  # Execute at open
    )

    engine = VectorizedBacktest(config)

    results = {}

    # Strategy 1: VIX Mean Reversion on SPY
    print("\n" + "-"*60)
    print("Running VIX Mean Reversion Strategy...")
    vix_strategy = VIXMeanReversionStrategy(
        universe=["SPY"],
        vix_data=vix_df,
        high_vix_threshold=18,  # Lower threshold for more signals
        low_vix_threshold=14,
    )
    vix_result = engine.run(vix_strategy, {"SPY": spy_df})
    results["VIX Mean Reversion (SPY)"] = print_results("VIX Mean Reversion (SPY)", vix_result)

    # Strategy 2: Breadth Momentum on QQQ
    print("\n" + "-"*60)
    print("Running Breadth Momentum Strategy...")
    breadth_strategy = BreadthMomentumStrategy(
        universe=["QQQ"],
        breadth_data=breadth_df,
        strong_threshold=0.55,
        weak_threshold=0.45,
    )
    breadth_result = engine.run(breadth_strategy, {"QQQ": qqq_df})
    results["Breadth Momentum (QQQ)"] = print_results("Breadth Momentum (QQQ)", breadth_result)

    # Strategy 3: Combined Regime on SPY
    print("\n" + "-"*60)
    print("Running Combined Regime Strategy...")
    combined_strategy = CombinedRegimeStrategy(
        universe=["SPY"],
        signal_data=signal_df,
    )
    combined_result = engine.run(combined_strategy, {"SPY": spy_df})
    results["Combined Regime (SPY)"] = print_results("Combined Regime (SPY)", combined_result)

    # Buy and Hold benchmark
    print("\n" + "-"*60)
    print("Calculating Buy & Hold Benchmark...")
    spy_return = (spy_df["close"].iloc[-1] / spy_df["close"].iloc[0] - 1) * 100
    print(f"SPY Buy & Hold Return: {spy_return:.2f}%")

    qqq_return = (qqq_df["close"].iloc[-1] / qqq_df["close"].iloc[0] - 1) * 100
    print(f"QQQ Buy & Hold Return: {qqq_return:.2f}%")

    # Summary
    print("\n" + "="*60)
    print("  BACKTEST SUMMARY")
    print("="*60)
    print(f"\n{'Strategy':<30} {'Return':>10} {'Sharpe':>10} {'MaxDD':>10}")
    print("-"*60)
    for name, metrics in results.items():
        ret = metrics.get('total_return', 0) * 100
        sharpe = metrics.get('sharpe_ratio', 0)
        mdd = metrics.get('max_drawdown', 0) * 100
        print(f"{name:<30} {ret:>9.2f}% {sharpe:>10.2f} {mdd:>9.2f}%")

    print(f"{'SPY Buy & Hold':<30} {spy_return:>9.2f}% {'N/A':>10} {'N/A':>10}")
    print(f"{'QQQ Buy & Hold':<30} {qqq_return:>9.2f}% {'N/A':>10} {'N/A':>10}")

    # Save results
    results_file = paths.live / "backtest_results" / f"historical_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)

    save_data = {
        "timestamp": datetime.now().isoformat(),
        "data_period": {
            "start": str(spy_df.index[0]),
            "end": str(spy_df.index[-1]),
            "days": len(spy_df),
        },
        "strategies": {
            name: {
                "total_return": m.get("total_return", 0),
                "sharpe_ratio": m.get("sharpe_ratio", 0),
                "max_drawdown": m.get("max_drawdown", 0),
                "num_trades": m.get("num_trades", 0),
            }
            for name, m in results.items()
        },
        "benchmarks": {
            "SPY": spy_return / 100,
            "QQQ": qqq_return / 100,
        }
    }

    with open(results_file, "w") as f:
        json.dump(save_data, f, indent=2)

    print(f"\nResults saved to: {results_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
