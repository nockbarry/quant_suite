#!/usr/bin/env python3
"""
Evaluate Alternative Strategies

Runs backtests and walk-forward validation on the new alternative strategies:
1. SEC Filing Alpha
2. Narrative Momentum
3. Composite Alternative

Two evaluation modes:
1. Historical backtest using technical proxies
2. Current signal evaluation for forward-looking analysis
"""

import asyncio
import json
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths
from src.core import Direction, Signal, SignalType, Symbol, Timeframe
from src.strategies.base import Strategy
from src.evaluation.backtest.engine import VectorizedBacktest, BacktestConfig, BacktestResult

# Import Renaissance-style strategies (Kalman, HMM)
try:
    from src.strategies.alternative.renaissance import (
        StatisticalArbitrageStrategy,
        RegimeConditionalStrategy,
        OrderFlowStrategy,
        FILTERPY_AVAILABLE,
        HMMLEARN_AVAILABLE,
    )
    RENAISSANCE_AVAILABLE = True
except ImportError:
    RENAISSANCE_AVAILABLE = False
    FILTERPY_AVAILABLE = False
    HMMLEARN_AVAILABLE = False

# Output directory
OUTPUT_DIR = paths.base / "strategy_evaluation"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# STRATEGY IMPLEMENTATIONS
# =============================================================================

class TechnicalMomentumStrategy(Strategy):
    """Simple technical momentum strategy as baseline."""

    name = "technical_momentum"
    description = "Price momentum with RSI confirmation"

    def __init__(self, universe: list[Symbol], lookback: int = 20, **params):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.lookback = lookback
        self._is_trained = True

    def get_required_history(self) -> int:
        return max(self.lookback + 14, 40)

    def generate_signals(self, data: dict[Symbol, pd.DataFrame], timestamp: datetime = None) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            df = df.copy()
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            if "close" not in df.columns:
                continue

            try:
                returns = df["close"].pct_change()
                momentum = returns.tail(self.lookback).sum()

                delta = df["close"].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1]

                if momentum > 0.05 and current_rsi < 70:
                    strength = min(1.0, momentum * 5)
                    signals.append(self.create_signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=strength,
                        confidence=0.6,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_LONG,
                    ))
                elif momentum < -0.05 and current_rsi > 30:
                    strength = min(1.0, abs(momentum) * 5)
                    signals.append(self.create_signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=strength,
                        confidence=0.6,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_SHORT,
                    ))
            except Exception:
                continue

        return signals


class MeanReversionStrategy(Strategy):
    """Mean reversion strategy using Bollinger Bands."""

    name = "mean_reversion"
    description = "Bollinger Band mean reversion"

    def __init__(self, universe: list[Symbol], lookback: int = 20, num_std: float = 2.0, **params):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.lookback = lookback
        self.num_std = num_std
        self._is_trained = True

    def get_required_history(self) -> int:
        return self.lookback + 5

    def generate_signals(self, data: dict[Symbol, pd.DataFrame], timestamp: datetime = None) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            df = df.copy()
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            if "close" not in df.columns:
                continue

            try:
                close = df["close"]
                sma = close.rolling(self.lookback).mean()
                std = close.rolling(self.lookback).std()

                upper = sma + self.num_std * std
                lower = sma - self.num_std * std

                current = close.iloc[-1]
                current_upper = upper.iloc[-1]
                current_lower = lower.iloc[-1]
                current_sma = sma.iloc[-1]

                if current < current_lower:
                    distance = (current_sma - current) / (current_sma - current_lower)
                    strength = min(1.0, distance * 0.5)
                    signals.append(self.create_signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=strength,
                        confidence=0.55,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_LONG,
                    ))
                elif current > current_upper:
                    distance = (current - current_sma) / (current_upper - current_sma)
                    strength = min(1.0, distance * 0.5)
                    signals.append(self.create_signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=strength,
                        confidence=0.55,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_SHORT,
                    ))
            except Exception:
                continue

        return signals


class SentimentProxyStrategy(Strategy):
    """
    Proxy for sentiment/alternative strategies using volume and price patterns.

    This simulates what sentiment-based strategies might do by looking at
    volume spikes and price gaps as proxies for news-driven moves.
    """

    name = "sentiment_proxy"
    description = "Volume and gap-based sentiment proxy"

    def __init__(self, universe: list[Symbol], volume_threshold: float = 2.0, **params):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.volume_threshold = volume_threshold
        self._is_trained = True

    def get_required_history(self) -> int:
        return 30

    def generate_signals(self, data: dict[Symbol, pd.DataFrame], timestamp: datetime = None) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            df = df.copy()
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            try:
                # Volume spike detection
                avg_volume = df["volume"].rolling(20).mean().iloc[-1]
                current_volume = df["volume"].iloc[-1]
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

                # Price gap detection
                gap = (df["open"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]

                # Recent return
                recent_return = (df["close"].iloc[-1] / df["close"].iloc[-5]) - 1

                # Generate signal based on volume spike + direction
                if volume_ratio > self.volume_threshold:
                    if recent_return > 0.02:
                        # High volume up move - positive sentiment
                        strength = min(1.0, volume_ratio / 4)
                        signals.append(self.create_signal(
                            symbol=symbol,
                            direction=Direction.LONG,
                            strength=strength,
                            confidence=0.55,
                            timestamp=timestamp,
                            signal_type=SignalType.ENTRY_LONG,
                        ))
                    elif recent_return < -0.02:
                        # High volume down move - negative sentiment
                        strength = min(1.0, volume_ratio / 4)
                        signals.append(self.create_signal(
                            symbol=symbol,
                            direction=Direction.SHORT,
                            strength=strength,
                            confidence=0.55,
                            timestamp=timestamp,
                            signal_type=SignalType.ENTRY_SHORT,
                        ))
            except Exception:
                continue

        return signals


class RSIExtremeStrategy(Strategy):
    """
    RSI extreme strategy as proxy for mean reversion on sentiment extremes.
    """

    name = "rsi_extreme"
    description = "RSI extreme mean reversion"

    def __init__(self, universe: list[Symbol], oversold: float = 25, overbought: float = 75, **params):
        super().__init__(universe, Timeframe.DAILY, **params)
        self.oversold = oversold
        self.overbought = overbought
        self._is_trained = True

    def get_required_history(self) -> int:
        return 20

    def generate_signals(self, data: dict[Symbol, pd.DataFrame], timestamp: datetime = None) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.get_required_history():
                continue

            df = df.copy()
            df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

            try:
                delta = df["close"].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1]

                if current_rsi < self.oversold:
                    strength = (self.oversold - current_rsi) / self.oversold
                    signals.append(self.create_signal(
                        symbol=symbol,
                        direction=Direction.LONG,
                        strength=min(1.0, strength),
                        confidence=0.6,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_LONG,
                    ))
                elif current_rsi > self.overbought:
                    strength = (current_rsi - self.overbought) / (100 - self.overbought)
                    signals.append(self.create_signal(
                        symbol=symbol,
                        direction=Direction.SHORT,
                        strength=min(1.0, strength),
                        confidence=0.6,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_SHORT,
                    ))
            except Exception:
                continue

        return signals


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_price_data(symbols: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Fetch price data for backtesting."""
    import yfinance as yf

    print(f"\nFetching price data for {len(symbols)} symbols...")

    data = {}
    for symbol in symbols:
        try:
            df = yf.download(symbol, period=period, progress=False)
            if not df.empty:
                df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
                data[symbol] = df
                print(f"  {symbol}: {len(df)} rows")
        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    return data


# =============================================================================
# CURRENT SIGNAL EVALUATION
# =============================================================================

async def evaluate_current_signals(symbols: list[str]) -> dict:
    """
    Evaluate current signals from alternative strategies.

    This provides real-time signal analysis rather than historical backtest.
    """
    from src.strategies.alternative.composite_alternative import CompositeAlternative
    from src.strategies.alternative.narrative_momentum import NarrativeMomentum
    from src.strategies.alternative.sec_alpha import SECFilingAlpha

    print("\n" + "=" * 60)
    print("CURRENT ALTERNATIVE SIGNALS")
    print("=" * 60)

    results = {
        "timestamp": datetime.now().isoformat(),
        "signals": {},
        "summary": {},
    }

    composite = CompositeAlternative()
    narrative = NarrativeMomentum()
    sec_alpha = SECFilingAlpha()

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0

    for symbol in symbols:
        results["signals"][symbol] = {}

        try:
            # Composite signal
            comp = await composite.generate_signal(symbol)
            if comp:
                results["signals"][symbol]["composite"] = {
                    "signal": comp.signal.name,
                    "value": comp.signal.value,
                    "confidence": comp.confidence,
                    "score": comp.weighted_score,
                }

                if comp.signal.value > 0:
                    bullish_count += 1
                elif comp.signal.value < 0:
                    bearish_count += 1
                else:
                    neutral_count += 1

            # Narrative signal
            narr = await narrative.generate_signal(symbol)
            if narr:
                results["signals"][symbol]["narrative"] = {
                    "signal": narr.signal.name,
                    "value": narr.signal.value,
                    "confidence": narr.confidence,
                }

            # SEC Alpha signal
            sec = await sec_alpha.generate_signal(symbol)
            if sec:
                results["signals"][symbol]["sec_alpha"] = {
                    "signal": sec.signal.name,
                    "value": sec.signal.value,
                    "confidence": sec.confidence,
                }

            # Print status
            comp_str = f"{comp.signal.name}({comp.confidence:.0%})" if comp else "N/A"
            narr_str = f"{narr.signal.name}({narr.confidence:.0%})" if narr else "N/A"
            sec_str = f"{sec.signal.name}({sec.confidence:.0%})" if sec else "N/A"

            print(f"  {symbol}: Composite={comp_str}, Narrative={narr_str}, SEC={sec_str}")

        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    await sec_alpha.close()

    results["summary"] = {
        "bullish": bullish_count,
        "bearish": bearish_count,
        "neutral": neutral_count,
        "total": len(symbols),
    }

    print(f"\nSummary: {bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral")

    return results


# =============================================================================
# BACKTEST RUNNER
# =============================================================================

def run_strategy_backtest(
    strategy: Strategy,
    data: dict[str, pd.DataFrame],
    config: BacktestConfig = None,
) -> BacktestResult:
    """Run backtest for a strategy."""
    config = config or BacktestConfig(
        initial_capital=100_000,
        position_size=0.1,
        max_positions=10,
    )

    engine = VectorizedBacktest(config)
    return engine.run(strategy, data)


def format_metrics(metrics: dict) -> str:
    """Format metrics for display."""
    lines = []
    for key, value in metrics.items():
        if isinstance(value, float):
            if "return" in key or "drawdown" in key:
                lines.append(f"  {key}: {value:.2%}")
            elif "ratio" in key:
                lines.append(f"  {key}: {value:.3f}")
            else:
                lines.append(f"  {key}: {value:.4f}")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


# =============================================================================
# EVALUATION FRAMEWORK
# =============================================================================

class StrategyEvaluator:
    """Comprehensive strategy evaluation framework."""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or OUTPUT_DIR
        self.results = {}

    def evaluate_strategy(
        self,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
        name: str = None,
    ) -> dict:
        """Evaluate a single strategy."""
        name = name or strategy.name
        print(f"\n{'='*60}")
        print(f"Evaluating: {name}")
        print(f"{'='*60}")

        config = BacktestConfig(
            initial_capital=100_000,
            position_size=0.1,
            max_positions=10,
            allow_short=True,
        )

        try:
            result = run_strategy_backtest(strategy, data, config)

            print(f"\nResults for {name}:")
            print(format_metrics(result.metrics))

            self.results[name] = {
                "metrics": result.metrics,
                "num_trades": len(result.trades),
                "final_value": result.metrics.get("final_value", 0),
            }

            return self.results[name]

        except Exception as e:
            print(f"Error evaluating {name}: {e}")
            import traceback
            traceback.print_exc()
            self.results[name] = {"error": str(e)}
            return self.results[name]

    def compare_strategies(self) -> pd.DataFrame:
        """Compare all evaluated strategies."""
        comparison = []

        for name, result in self.results.items():
            if "error" in result:
                continue

            metrics = result.get("metrics", {})
            comparison.append({
                "strategy": name,
                "total_return": metrics.get("total_return", 0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                "max_drawdown": metrics.get("max_drawdown", 0),
                "volatility": metrics.get("volatility", 0),
                "num_trades": result.get("num_trades", 0),
                "final_value": metrics.get("final_value", 0),
            })

        if not comparison:
            return pd.DataFrame()

        df = pd.DataFrame(comparison)
        df = df.sort_values("sharpe_ratio", ascending=False)
        return df

    def generate_report(self, current_signals: dict = None) -> str:
        """Generate evaluation report."""
        lines = [
            "# Strategy Evaluation Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Historical Backtest Results",
            "",
        ]

        comparison = self.compare_strategies()
        if len(comparison) > 0:
            lines.append("### Strategy Comparison")
            lines.append("")
            lines.append("| Strategy | Return | Sharpe | Max DD | Volatility | Trades |")
            lines.append("|----------|--------|--------|--------|------------|--------|")

            for _, row in comparison.iterrows():
                lines.append(
                    f"| {row['strategy']} | {row['total_return']:.2%} | "
                    f"{row['sharpe_ratio']:.3f} | {row['max_drawdown']:.2%} | "
                    f"{row['volatility']:.2%} | {int(row['num_trades'])} |"
                )

            lines.append("")

            # Best performers
            lines.append("### Best Performers")
            lines.append("")

            if len(comparison) > 0:
                best_sharpe = comparison.iloc[0]
                lines.append(f"- **Best Sharpe Ratio**: {best_sharpe['strategy']} ({best_sharpe['sharpe_ratio']:.3f})")

                best_return = comparison.loc[comparison['total_return'].idxmax()]
                lines.append(f"- **Best Return**: {best_return['strategy']} ({best_return['total_return']:.2%})")

                lowest_dd = comparison.loc[comparison['max_drawdown'].idxmax()]
                lines.append(f"- **Lowest Drawdown**: {lowest_dd['strategy']} ({lowest_dd['max_drawdown']:.2%})")

        # Current signals section
        if current_signals:
            lines.append("")
            lines.append("## Current Alternative Signals")
            lines.append("")
            lines.append(f"**Generated**: {current_signals.get('timestamp', 'N/A')}")
            lines.append("")

            summary = current_signals.get("summary", {})
            lines.append(f"- Bullish: {summary.get('bullish', 0)}")
            lines.append(f"- Bearish: {summary.get('bearish', 0)}")
            lines.append(f"- Neutral: {summary.get('neutral', 0)}")
            lines.append("")

            lines.append("### Signal Details")
            lines.append("")
            lines.append("| Symbol | Composite | Narrative | SEC Alpha |")
            lines.append("|--------|-----------|-----------|-----------|")

            for symbol, signals in current_signals.get("signals", {}).items():
                comp = signals.get("composite", {})
                narr = signals.get("narrative", {})
                sec = signals.get("sec_alpha", {})

                comp_str = f"{comp.get('signal', 'N/A')} ({comp.get('confidence', 0):.0%})" if comp else "N/A"
                narr_str = f"{narr.get('signal', 'N/A')} ({narr.get('confidence', 0):.0%})" if narr else "N/A"
                sec_str = f"{sec.get('signal', 'N/A')} ({sec.get('confidence', 0):.0%})" if sec else "N/A"

                lines.append(f"| {symbol} | {comp_str} | {narr_str} | {sec_str} |")

        lines.append("")
        lines.append("## Detailed Results")
        lines.append("")

        for name, result in self.results.items():
            lines.append(f"### {name}")
            lines.append("")

            if "error" in result:
                lines.append(f"Error: {result['error']}")
            else:
                metrics = result.get("metrics", {})
                for key, value in metrics.items():
                    if isinstance(value, float):
                        if "return" in key or "drawdown" in key:
                            lines.append(f"- {key}: {value:.2%}")
                        elif "ratio" in key:
                            lines.append(f"- {key}: {value:.3f}")
                        else:
                            lines.append(f"- {key}: {value:.4f}")
                    else:
                        lines.append(f"- {key}: {value}")

            lines.append("")

        lines.append("---")
        lines.append("*Report generated by Quant Suite Strategy Evaluator*")

        return "\n".join(lines)

    def save_results(self, filename: str = "evaluation_results.json"):
        """Save results to JSON."""
        output_path = self.output_dir / filename

        def convert_types(obj):
            if isinstance(obj, (np.integer, np.floating)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, (pd.Timestamp, datetime)):
                return obj.isoformat() if hasattr(obj, 'isoformat') else str(obj)
            elif isinstance(obj, dict):
                return {str(k): convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(v) for v in obj]
            return obj

        with open(output_path, "w") as f:
            json.dump(convert_types(self.results), f, indent=2, default=str)

        print(f"\nResults saved to: {output_path}")


# =============================================================================
# MAIN EVALUATION
# =============================================================================

async def main():
    """Run comprehensive strategy evaluation."""
    print("\n" + "=" * 70)
    print("STRATEGY EVALUATION SUITE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Define universe
    universe = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "JPM", "V", "JNJ", "WMT", "PG",
    ]

    # Fetch price data
    price_data = fetch_price_data(universe, period="2y")

    if not price_data:
        print("No price data available!")
        return

    # Initialize evaluator
    evaluator = StrategyEvaluator(OUTPUT_DIR)

    # Evaluate baseline strategies
    print("\n" + "-" * 60)
    print("BASELINE STRATEGIES")
    print("-" * 60)

    strategies = [
        ("Technical Momentum", TechnicalMomentumStrategy(list(price_data.keys()))),
        ("Mean Reversion", MeanReversionStrategy(list(price_data.keys()))),
        ("RSI Extreme", RSIExtremeStrategy(list(price_data.keys()))),
        ("Sentiment Proxy", SentimentProxyStrategy(list(price_data.keys()))),
    ]

    for name, strategy in strategies:
        evaluator.evaluate_strategy(strategy, price_data, name)

    # Evaluate Renaissance-style strategies (Kalman, HMM)
    if RENAISSANCE_AVAILABLE:
        print("\n" + "-" * 60)
        print("RENAISSANCE STRATEGIES (Kalman Filter, HMM)")
        print("-" * 60)

        # Order Flow Strategy (CLV-based)
        order_flow = OrderFlowStrategy(
            universe=list(price_data.keys()),
            imbalance_threshold=0.25,
            lookback=10,
        )
        evaluator.evaluate_strategy(order_flow, price_data, "Order Flow (CLV)")

        # Statistical Arbitrage with Kalman hedge ratio
        if FILTERPY_AVAILABLE and len(price_data) >= 2:
            stat_arb = StatisticalArbitrageStrategy(
                universe=list(price_data.keys()),
                use_kalman=True,
                entry_zscore=2.0,
                exit_zscore=0.5,
                max_pairs=3,
            )
            evaluator.evaluate_strategy(stat_arb, price_data, "Stat Arb (Kalman)")
        else:
            print("  Skipping Stat Arb - filterpy not available or insufficient symbols")

        # HMM Regime-Conditional Strategy
        if HMMLEARN_AVAILABLE:
            regime_strategy = RegimeConditionalStrategy(
                universe=list(price_data.keys()),
                n_regimes=3,
                lookback=252,
            )
            evaluator.evaluate_strategy(regime_strategy, price_data, "Regime HMM")
        else:
            print("  Skipping Regime HMM - hmmlearn not available")
    else:
        print("\n  Renaissance strategies not available (import error)")

    # Evaluate current alternative signals
    current_signals = await evaluate_current_signals(universe)

    # Compare strategies
    print("\n" + "=" * 70)
    print("STRATEGY COMPARISON")
    print("=" * 70)

    comparison = evaluator.compare_strategies()
    if len(comparison) > 0:
        print("\n")
        print(comparison.to_string(index=False))

    # Generate and save report
    report = evaluator.generate_report(current_signals)
    report_path = OUTPUT_DIR / "evaluation_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    # Save results
    evaluator.save_results()

    # Save current signals
    signals_path = OUTPUT_DIR / "current_signals.json"
    with open(signals_path, "w") as f:
        json.dump(current_signals, f, indent=2, default=str)
    print(f"Current signals saved to: {signals_path}")

    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)

    return evaluator.results


if __name__ == "__main__":
    results = asyncio.run(main())
