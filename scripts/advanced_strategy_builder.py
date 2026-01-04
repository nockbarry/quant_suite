#!/usr/bin/env python3
"""
Advanced Strategy Builder - Sentiment and Insider Data Integration.

Builds and evaluates strategies incorporating experimental data sources:
1. Sentiment-Momentum Hybrid: News sentiment + price momentum
2. Insider-Technical Confluence: Insider buying + technical indicators
3. Multi-Signal Alpha: Combines all available signals

Based on knowledge base learnings:
- RSI Reversal works well on IWM (p=0.04)
- Volatility Breakout works well on AMD (p=0.02)
- Multi-signal strategies on NVDA showed promise (Sharpe 0.52)
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

# Setup path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Simple MCPT Implementation
# =============================================================================

def simple_mcpt(
    strategy,
    data: pd.DataFrame,
    n_permutations: int = 200,
) -> dict:
    """
    Simple Monte Carlo Permutation Test.

    Tests if strategy Sharpe ratio is statistically significant.
    """
    # Get actual strategy returns
    signals = strategy.generate_signals(data)
    positions = signals["signal"].shift(1).fillna(0)
    returns = data["close"].pct_change()
    strategy_returns = positions * returns

    # Actual Sharpe ratio
    actual_sharpe = (
        strategy_returns.mean() / (strategy_returns.std() + 1e-10)
    ) * np.sqrt(252)

    # Permutation test
    permuted_sharpes = []
    for _ in range(n_permutations):
        # Shuffle returns
        permuted_returns = returns.sample(frac=1, replace=False)
        permuted_returns.index = returns.index

        # Reconstruct price series
        permuted_prices = (1 + permuted_returns).cumprod() * data["close"].iloc[0]
        permuted_data = data.copy()
        permuted_data["close"] = permuted_prices
        permuted_data["open"] = permuted_prices.shift(1).fillna(permuted_prices.iloc[0])
        permuted_data["high"] = permuted_data[["open", "close"]].max(axis=1) * 1.005
        permuted_data["low"] = permuted_data[["open", "close"]].min(axis=1) * 0.995

        # Get permuted strategy returns
        perm_signals = strategy.generate_signals(permuted_data)
        perm_positions = perm_signals["signal"].shift(1).fillna(0)
        perm_returns = permuted_data["close"].pct_change()
        perm_strategy_returns = perm_positions * perm_returns

        perm_sharpe = (
            perm_strategy_returns.mean() / (perm_strategy_returns.std() + 1e-10)
        ) * np.sqrt(252)
        permuted_sharpes.append(perm_sharpe)

    permuted_sharpes = np.array(permuted_sharpes)
    p_value = float((permuted_sharpes >= actual_sharpe).sum() / n_permutations)

    return {
        "actual_sharpe": float(actual_sharpe),
        "mean_permuted_sharpe": float(np.mean(permuted_sharpes)),
        "std_permuted_sharpe": float(np.std(permuted_sharpes)),
        "p_value": p_value,
        "significant_5pct": p_value < 0.05,
        "significant_10pct": p_value < 0.10,
        "n_permutations": n_permutations,
    }


# =============================================================================
# Data Classes for Alternative Data
# =============================================================================

@dataclass
class SentimentSignal:
    """Aggregated sentiment signal."""
    symbol: str
    date: datetime
    sentiment_score: float  # -1 to 1
    sentiment_momentum: float  # Change in sentiment
    news_volume: int
    confidence: float


@dataclass
class InsiderSignal:
    """Aggregated insider trading signal."""
    symbol: str
    date: datetime
    net_buying_ratio: float  # -1 (all selling) to 1 (all buying)
    cluster_buying: bool
    c_suite_activity: bool
    value_bought: float
    value_sold: float
    signal_strength: float


# =============================================================================
# Sentiment-Momentum Hybrid Strategy
# =============================================================================

class SentimentMomentumHybridStrategy:
    """
    Combines news sentiment signals with price momentum.

    Hypothesis: Positive sentiment + positive momentum = strong continuation
    Negative sentiment + negative momentum = strong continuation
    Divergence = potential reversal opportunity

    Based on knowledge base insight: Multi-signal strategies showed
    improved consistency across different market conditions.
    """

    name = "sentiment_momentum_hybrid"

    def __init__(
        self,
        sentiment_threshold: float = 0.3,
        momentum_window: int = 20,
        sentiment_weight: float = 0.4,
        momentum_weight: float = 0.6,
        require_alignment: bool = False,
    ):
        self.sentiment_threshold = sentiment_threshold
        self.momentum_window = momentum_window
        self.sentiment_weight = sentiment_weight
        self.momentum_weight = momentum_weight
        self.require_alignment = require_alignment

    def _simulate_sentiment(self, data: pd.DataFrame) -> pd.Series:
        """
        Simulate sentiment using price-based proxy.

        In production, this would use actual news sentiment from FinBERT.
        For backtesting, we use returns + volatility as proxy:
        - High returns + low volatility = positive sentiment
        - Low returns + high volatility = negative sentiment
        """
        returns = data["close"].pct_change()
        volatility = returns.rolling(10).std()

        # Normalize returns to sentiment-like scale
        norm_returns = returns.rolling(20).mean() / (volatility + 1e-6)
        sentiment = np.tanh(norm_returns * 2)  # Scale to [-1, 1]

        # Add some mean reversion (sentiment tends to normalize)
        sentiment_ma = sentiment.rolling(5).mean()
        return sentiment_ma.fillna(0)

    def _calculate_momentum(self, data: pd.DataFrame) -> pd.Series:
        """Calculate price momentum."""
        returns = data["close"].pct_change(self.momentum_window)
        # Normalize momentum
        momentum_std = returns.rolling(50).std()
        normalized_momentum = returns / (momentum_std + 1e-6)
        return np.tanh(normalized_momentum).fillna(0)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals from sentiment + momentum."""
        signals = pd.DataFrame(index=data.index)
        signals["signal"] = 0.0

        if len(data) < self.momentum_window + 20:
            return signals

        sentiment = self._simulate_sentiment(data)
        momentum = self._calculate_momentum(data)

        # Combined signal
        combined = (
            self.sentiment_weight * sentiment +
            self.momentum_weight * momentum
        )

        if self.require_alignment:
            # Only trade when sentiment and momentum agree
            aligned = (sentiment > 0) == (momentum > 0)
            combined = combined.where(aligned, 0)

        # Generate signals
        signals.loc[combined > self.sentiment_threshold, "signal"] = 1.0
        signals.loc[combined < -self.sentiment_threshold, "signal"] = -1.0

        return signals


# =============================================================================
# Insider-Technical Confluence Strategy
# =============================================================================

class InsiderTechnicalConfluenceStrategy:
    """
    Combines insider buying signals with technical indicators.

    Hypothesis: Insider buying at technical support levels provides
    high-conviction entry points. Insiders have information edge;
    technical levels provide timing edge.

    Based on knowledge base insight: Insider cluster buying with
    RSI oversold conditions showed strong predictive value.
    """

    name = "insider_technical_confluence"

    def __init__(
        self,
        insider_lookback: int = 60,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        min_insider_ratio: float = 0.2,
    ):
        self.insider_lookback = insider_lookback
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.min_insider_ratio = min_insider_ratio

    def _simulate_insider_signal(self, data: pd.DataFrame) -> pd.Series:
        """
        Simulate insider buying signal.

        In production, this would use actual SEC Form 4 data.
        For backtesting, we use accumulation patterns as proxy:
        - High volume + small price change = potential accumulation
        - Volume increasing while price stable = institutional buying
        """
        volume = data["volume"]
        close = data["close"]

        # Volume relative to average
        avg_volume = volume.rolling(20).mean()
        volume_ratio = volume / (avg_volume + 1)

        # Price change
        returns = close.pct_change()
        abs_returns = returns.abs()

        # Accumulation score: high volume, low price change
        accum_score = (volume_ratio - 1) / (abs_returns * 100 + 1)
        accum_score = accum_score.rolling(self.insider_lookback).mean()

        # Normalize to [-1, 1]
        normalized = np.tanh(accum_score / 10)
        return normalized.fillna(0)

    def _calculate_rsi(self, data: pd.DataFrame) -> pd.Series:
        """Calculate RSI indicator."""
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def _calculate_bollinger_position(self, data: pd.DataFrame) -> pd.Series:
        """Calculate position within Bollinger Bands (-1 to 1)."""
        close = data["close"]
        ma = close.rolling(self.bb_period).mean()
        std = close.rolling(self.bb_period).std()

        upper = ma + self.bb_std * std
        lower = ma - self.bb_std * std

        # Position: -1 at lower band, 0 at middle, 1 at upper band
        position = (close - ma) / (self.bb_std * std + 1e-10)
        return position.clip(-1, 1).fillna(0)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate signals from insider + technical confluence."""
        signals = pd.DataFrame(index=data.index)
        signals["signal"] = 0.0

        if len(data) < max(self.insider_lookback, self.bb_period) + 20:
            return signals

        insider = self._simulate_insider_signal(data)
        rsi = self._calculate_rsi(data)
        bb_position = self._calculate_bollinger_position(data)

        # Long signal: Insider buying + technical oversold
        long_insider = insider > self.min_insider_ratio
        long_rsi = rsi < self.rsi_oversold
        long_bb = bb_position < -0.8

        # Short signal: Insider selling + technical overbought
        short_insider = insider < -self.min_insider_ratio
        short_rsi = rsi > self.rsi_overbought
        short_bb = bb_position > 0.8

        # Confluence scoring
        long_score = (
            long_insider.astype(float) * 0.5 +
            long_rsi.astype(float) * 0.25 +
            long_bb.astype(float) * 0.25
        )

        short_score = (
            short_insider.astype(float) * 0.5 +
            short_rsi.astype(float) * 0.25 +
            short_bb.astype(float) * 0.25
        )

        # Require at least 2 conditions (score >= 0.5)
        signals.loc[long_score >= 0.5, "signal"] = 1.0
        signals.loc[short_score >= 0.5, "signal"] = -1.0

        return signals


# =============================================================================
# Multi-Alpha Ensemble Strategy
# =============================================================================

class MultiAlphaEnsembleStrategy:
    """
    Ensemble of multiple alpha sources with dynamic weighting.

    Combines:
    1. Sentiment momentum (news-based)
    2. Insider confluence (information edge)
    3. Technical momentum (price-based)
    4. Volatility regime (risk-adjusted)

    Based on knowledge base: Combining multiple uncorrelated signals
    improves consistency and reduces max drawdown.
    """

    name = "multi_alpha_ensemble"

    def __init__(
        self,
        sentiment_weight: float = 0.25,
        insider_weight: float = 0.25,
        momentum_weight: float = 0.30,
        volatility_weight: float = 0.20,
        signal_threshold: float = 0.3,
        regime_adaptive: bool = True,
    ):
        self.sentiment_weight = sentiment_weight
        self.insider_weight = insider_weight
        self.momentum_weight = momentum_weight
        self.volatility_weight = volatility_weight
        self.signal_threshold = signal_threshold
        self.regime_adaptive = regime_adaptive

        # Component strategies
        self._sentiment_strategy = SentimentMomentumHybridStrategy()
        self._insider_strategy = InsiderTechnicalConfluenceStrategy()

    def _calculate_momentum_signal(self, data: pd.DataFrame) -> pd.Series:
        """Pure price momentum signal."""
        returns = data["close"].pct_change()

        # Multiple timeframe momentum
        mom_5 = returns.rolling(5).mean()
        mom_20 = returns.rolling(20).mean()
        mom_60 = returns.rolling(60).mean()

        # Combine with decay
        combined = 0.5 * mom_5 + 0.3 * mom_20 + 0.2 * mom_60

        # Normalize
        std = combined.rolling(60).std()
        normalized = combined / (std + 1e-6)
        return np.tanh(normalized * 2).fillna(0)

    def _calculate_volatility_regime(self, data: pd.DataFrame) -> pd.Series:
        """Volatility regime indicator."""
        returns = data["close"].pct_change()
        vol_short = returns.rolling(10).std() * np.sqrt(252)
        vol_long = returns.rolling(60).std() * np.sqrt(252)

        # Vol regime: high vol = -1, low vol = 1
        vol_ratio = vol_short / (vol_long + 1e-6)
        regime = 2 - vol_ratio.clip(0.5, 2)  # Invert: low vol = positive

        return (regime - 1).fillna(0)  # Center at 0

    def _adaptive_weights(self, volatility_regime: pd.Series) -> tuple:
        """Adjust weights based on volatility regime."""
        if not self.regime_adaptive:
            return (
                self.sentiment_weight,
                self.insider_weight,
                self.momentum_weight,
                self.volatility_weight
            )

        # In high vol: reduce momentum, increase insider/volatility
        # In low vol: increase momentum, reduce volatility
        vol_adjustment = volatility_regime.iloc[-1] if len(volatility_regime) > 0 else 0

        # Adjust weights (keep sum = 1)
        momentum_adj = self.momentum_weight * (1 + 0.3 * vol_adjustment)
        volatility_adj = self.volatility_weight * (1 - 0.3 * vol_adjustment)

        total = self.sentiment_weight + self.insider_weight + momentum_adj + volatility_adj

        return (
            self.sentiment_weight / total,
            self.insider_weight / total,
            momentum_adj / total,
            volatility_adj / total
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate ensemble signals."""
        signals = pd.DataFrame(index=data.index)
        signals["signal"] = 0.0

        if len(data) < 100:
            return signals

        # Get component signals
        sentiment_signals = self._sentiment_strategy._simulate_sentiment(data)
        insider_signals = self._insider_strategy._simulate_insider_signal(data)
        momentum_signals = self._calculate_momentum_signal(data)
        vol_regime = self._calculate_volatility_regime(data)

        # Get adaptive weights
        w_sent, w_ins, w_mom, w_vol = self._adaptive_weights(vol_regime)

        # Combine signals
        combined = (
            w_sent * sentiment_signals +
            w_ins * insider_signals +
            w_mom * momentum_signals +
            w_vol * vol_regime
        )

        # Generate final signals
        signals.loc[combined > self.signal_threshold, "signal"] = 1.0
        signals.loc[combined < -self.signal_threshold, "signal"] = -1.0

        return signals


# =============================================================================
# Evaluation Runner
# =============================================================================

def run_strategy_evaluation(
    symbols: list[str],
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
    n_permutations: int = 200,
) -> dict[str, Any]:
    """
    Run comprehensive evaluation of advanced strategies.
    """
    logger.info("=" * 60)
    logger.info("Advanced Strategy Evaluation")
    logger.info("=" * 60)

    strategies = {
        "sentiment_momentum": SentimentMomentumHybridStrategy(),
        "sentiment_momentum_aligned": SentimentMomentumHybridStrategy(require_alignment=True),
        "insider_technical": InsiderTechnicalConfluenceStrategy(),
        "insider_technical_strict": InsiderTechnicalConfluenceStrategy(min_insider_ratio=0.4),
        "multi_alpha": MultiAlphaEnsembleStrategy(),
        "multi_alpha_adaptive": MultiAlphaEnsembleStrategy(regime_adaptive=True),
    }

    results = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "symbols": symbols,
        "strategies": list(strategies.keys()),
        "backtest_results": [],
        "walk_forward_results": [],
        "mcpt_results": [],
        "summary": {},
    }

    # Fetch data
    logger.info(f"Fetching data for {len(symbols)} symbols...")
    data_cache = {}

    for symbol in symbols:
        try:
            data = yf.download(
                symbol,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=True,
            )
            if data is not None and len(data) > 200:
                # Handle multi-index columns from yfinance
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                # Normalize column names
                data.columns = [c.lower() for c in data.columns]
                data_cache[symbol] = data
                logger.info(f"  {symbol}: {len(data)} bars")
        except Exception as e:
            logger.warning(f"  {symbol}: Failed to fetch - {e}")

    # Run backtests
    logger.info("\nRunning backtests...")
    best_results = []

    for strategy_name, strategy in strategies.items():
        for symbol, data in data_cache.items():
            try:
                signals = strategy.generate_signals(data)

                # Convert signals to positions
                positions = signals["signal"].shift(1).fillna(0)

                # Calculate returns
                returns = data["close"].pct_change()
                strategy_returns = positions * returns

                # Calculate metrics
                sharpe = (
                    strategy_returns.mean() / (strategy_returns.std() + 1e-10)
                ) * np.sqrt(252)

                total_return = (1 + strategy_returns).prod() - 1
                max_dd = (
                    (1 + strategy_returns).cumprod() /
                    (1 + strategy_returns).cumprod().cummax() - 1
                ).min()

                n_trades = (positions.diff().abs() > 0).sum()

                result = {
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "sharpe_ratio": float(sharpe),
                    "total_return": float(total_return),
                    "max_drawdown": float(max_dd),
                    "n_trades": int(n_trades),
                }

                results["backtest_results"].append(result)

                if sharpe > 0.4:
                    best_results.append((strategy_name, symbol, sharpe, result))
                    logger.info(
                        f"  {strategy_name} on {symbol}: "
                        f"Sharpe={sharpe:.2f}, Return={total_return:.1%}"
                    )

            except Exception as e:
                logger.warning(f"  {strategy_name} on {symbol}: Error - {e}")

    # Run MCPT on best results
    logger.info(f"\nRunning MCPT validation on {len(best_results)} promising strategies...")

    for strategy_name, symbol, sharpe, result in best_results:
        try:
            data = data_cache[symbol]
            strategy = strategies[strategy_name]

            # Run simple MCPT
            mcpt_result = simple_mcpt(strategy, data, n_permutations)

            mcpt_entry = {
                "strategy": strategy_name,
                "symbol": symbol,
                "actual_sharpe": mcpt_result["actual_sharpe"],
                "mean_permuted_sharpe": mcpt_result["mean_permuted_sharpe"],
                "p_value": mcpt_result["p_value"],
                "significant_5pct": mcpt_result["significant_5pct"],
                "significant_10pct": mcpt_result["significant_10pct"],
            }

            results["mcpt_results"].append(mcpt_entry)

            sig_marker = "**" if mcpt_result["p_value"] < 0.05 else "*" if mcpt_result["p_value"] < 0.10 else ""
            logger.info(
                f"  {strategy_name} on {symbol}: "
                f"p={mcpt_result['p_value']:.3f} {sig_marker}"
            )

        except Exception as e:
            logger.warning(f"  MCPT {strategy_name} on {symbol}: Error - {e}")

    # Generate summary
    backtest_df = pd.DataFrame(results["backtest_results"])

    if len(backtest_df) > 0:
        summary = {
            "total_combinations": len(backtest_df),
            "positive_sharpe_count": int((backtest_df["sharpe_ratio"] > 0).sum()),
            "sharpe_gt_05_count": int((backtest_df["sharpe_ratio"] > 0.5).sum()),
        }

        # Best by strategy
        summary["by_strategy"] = {}
        for strat in strategies.keys():
            strat_df = backtest_df[backtest_df["strategy"] == strat]
            if len(strat_df) > 0:
                best_idx = strat_df["sharpe_ratio"].idxmax()
                summary["by_strategy"][strat] = {
                    "avg_sharpe": float(strat_df["sharpe_ratio"].mean()),
                    "best_symbol": strat_df.loc[best_idx, "symbol"],
                    "best_sharpe": float(strat_df.loc[best_idx, "sharpe_ratio"]),
                }

        # Significant results
        mcpt_df = pd.DataFrame(results["mcpt_results"])
        if len(mcpt_df) > 0:
            sig_results = mcpt_df[mcpt_df["p_value"] < 0.05]
            summary["significant_at_5pct"] = len(sig_results)
            if len(sig_results) > 0:
                summary["best_significant"] = sig_results.loc[
                    sig_results["actual_sharpe"].idxmax()
                ].to_dict()

        results["summary"] = summary

    return results


def main():
    """Main entry point."""
    # Universe based on knowledge base learnings
    symbols = [
        # Best performers from previous evaluation
        "AMD", "IWM", "META", "NVDA", "MRVL",
        # Large cap tech (more data, liquid)
        "AAPL", "MSFT", "GOOGL", "AMZN",
        # ETFs (regime testing)
        "QQQ", "SPY", "XLV", "XLK",
        # Mid-cap (potential alpha)
        "QCOM", "AMAT", "MU",
    ]

    results = run_strategy_evaluation(
        symbols=symbols,
        start_date="2020-01-01",
        end_date="2025-12-31",
        n_permutations=200,
    )

    # Save results
    output_dir = Path("/home/nock/quant_results/strategy_evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"advanced_evaluation_{results['timestamp']}.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"\nResults saved to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    if results["summary"]:
        summary = results["summary"]
        print(f"\nTotal strategy/symbol combinations: {summary['total_combinations']}")
        print(f"Positive Sharpe: {summary['positive_sharpe_count']}")
        print(f"Sharpe > 0.5: {summary['sharpe_gt_05_count']}")

        if "significant_at_5pct" in summary:
            print(f"\nStatistically significant (p < 0.05): {summary['significant_at_5pct']}")

            if "best_significant" in summary:
                best = summary["best_significant"]
                print(f"  Best: {best['strategy']} on {best['symbol']}")
                print(f"        Sharpe={best['actual_sharpe']:.3f}, p={best['p_value']:.3f}")

        print("\nBy Strategy:")
        for strat, stats in summary.get("by_strategy", {}).items():
            print(f"  {strat}:")
            print(f"    Avg Sharpe: {stats['avg_sharpe']:.3f}")
            print(f"    Best: {stats['best_symbol']} ({stats['best_sharpe']:.3f})")

    return results


if __name__ == "__main__":
    main()
