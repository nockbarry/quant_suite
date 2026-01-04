"""
Experiment runner for autonomous research.

Runs hypotheses through MCPT validation and records results.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd

from .data_hub import DataHub, DataBundle
from .hypothesis_engine import Hypothesis
from .knowledge_base import KnowledgeBase


@dataclass
class ExperimentResult:
    """Result from running a single experiment."""
    hypothesis: Hypothesis
    status: Literal["success", "failed", "error", "skipped"]

    # Validation metrics
    train_sharpe: float = 0.0
    train_return: float = 0.0
    val_sharpe: float = 0.0
    val_return: float = 0.0
    val_max_dd: float = 0.0

    # MCPT results
    mcpt_p_value: float = 1.0
    is_significant: bool = False
    perm_sharpe_mean: float = 0.0
    perm_sharpe_std: float = 0.0

    # Data quality
    data_coverage: float = 0.0
    missing_signals: list[str] = field(default_factory=list)

    # Insights
    insights: list[str] = field(default_factory=list)
    error_message: str = ""

    # Timing
    runtime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hypothesis": self.hypothesis.to_dict(),
            "status": self.status,
            "train_sharpe": self.train_sharpe,
            "train_return": self.train_return,
            "val_sharpe": self.val_sharpe,
            "val_return": self.val_return,
            "val_max_dd": self.val_max_dd,
            "mcpt_p_value": self.mcpt_p_value,
            "is_significant": self.is_significant,
            "perm_sharpe_mean": self.perm_sharpe_mean,
            "perm_sharpe_std": self.perm_sharpe_std,
            "data_coverage": self.data_coverage,
            "missing_signals": self.missing_signals,
            "insights": self.insights,
            "error_message": self.error_message,
            "runtime_seconds": self.runtime_seconds,
        }


class StrategyExecutor:
    """
    Executes strategy hypotheses on price data.

    Maps hypothesis types to actual trading logic.
    """

    def __init__(self):
        self._strategies = {
            "sma_crossover": self._sma_crossover,
            "momentum": self._momentum,
            "breakout": self._breakout,
            "rsi_reversal": self._rsi_reversal,
            "bollinger_reversal": self._bollinger_reversal,
            "insider_momentum": self._insider_momentum,
            "insider_value": self._insider_value,
            "sentiment_momentum": self._sentiment_momentum,
            "sentiment_reversal": self._sentiment_reversal,
            "multi_signal": self._multi_signal,
        }

    def execute(
        self,
        hypothesis: Hypothesis,
        price_data: pd.DataFrame,
        insider_signal: Any = None,
        sentiment_score: float = 0.0,
    ) -> pd.Series:
        """Execute strategy and return position series."""
        strategy_type = hypothesis.strategy_type
        params = hypothesis.strategy_params

        if strategy_type in self._strategies:
            return self._strategies[strategy_type](
                price_data, params, insider_signal, sentiment_score
            )
        else:
            # Default to simple momentum
            return self._momentum(price_data, params, insider_signal, sentiment_score)

    def _sma_crossover(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """SMA crossover strategy."""
        fast = params.get("fast_period", 10)
        slow = params.get("slow_period", 30)

        fast_ma = df["close"].rolling(fast).mean()
        slow_ma = df["close"].rolling(slow).mean()

        positions = pd.Series(0, index=df.index)
        positions[fast_ma > slow_ma] = 1
        positions[fast_ma < slow_ma] = -1

        return positions.shift(1).fillna(0)

    def _momentum(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Momentum strategy."""
        lookback = params.get("lookback", 20)
        threshold = params.get("threshold", 0.0)

        momentum = df["close"].pct_change(lookback)

        positions = pd.Series(0, index=df.index)
        positions[momentum > threshold] = 1
        positions[momentum < -threshold] = -1

        return positions.shift(1).fillna(0)

    def _breakout(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Breakout strategy."""
        lookback = params.get("lookback", 20)

        high_channel = df["high"].rolling(lookback).max()
        low_channel = df["low"].rolling(lookback).min()

        positions = pd.Series(0, index=df.index)
        positions[df["close"] >= high_channel.shift(1)] = 1
        positions[df["close"] <= low_channel.shift(1)] = -1

        return positions.ffill().shift(1).fillna(0)

    def _rsi_reversal(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """RSI mean reversion."""
        period = params.get("period", 14)
        oversold = params.get("oversold", 30)
        overbought = params.get("overbought", 70)

        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        positions = pd.Series(0, index=df.index)
        positions[rsi < oversold] = 1
        positions[rsi > overbought] = -1

        return positions.ffill().shift(1).fillna(0)

    def _bollinger_reversal(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Bollinger band mean reversion."""
        period = params.get("period", 20)
        num_std = params.get("num_std", 2.0)

        ma = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        upper = ma + num_std * std
        lower = ma - num_std * std

        positions = pd.Series(0, index=df.index)
        positions[df["close"] < lower] = 1
        positions[df["close"] > upper] = -1

        return positions.ffill().shift(1).fillna(0)

    def _insider_momentum(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Insider + momentum strategy."""
        momentum_period = params.get("momentum_period", 20)
        require_cluster = params.get("require_cluster", False)

        momentum = df["close"].pct_change(momentum_period)
        positions = pd.Series(0.0, index=df.index)  # Use float for fractional positions

        # Base momentum signal
        positions[momentum > 0] = 1.0
        positions[momentum < 0] = -1.0

        # Modify based on insider signal
        if insider:
            if insider.signal == "bullish":
                if require_cluster and not insider.cluster_buying:
                    pass  # Require cluster
                else:
                    # Boost long positions
                    positions.loc[positions == 0] = 0.5  # Slight long bias
            elif insider.signal == "bearish":
                # Suppress long positions
                positions.loc[positions == 1] = 0

        return positions.shift(1).fillna(0)

    def _insider_value(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Insider + value (below MA) strategy."""
        ma_period = params.get("ma_period", 50)

        ma = df["close"].rolling(ma_period).mean()
        below_ma = df["close"] < ma

        positions = pd.Series(0, index=df.index)

        # Only buy if insider bullish AND price below MA
        if insider and insider.signal == "bullish":
            positions[below_ma] = 1

        return positions.shift(1).fillna(0)

    def _sentiment_momentum(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Trade in direction of sentiment."""
        threshold = params.get("sentiment_threshold", 0.3)

        positions = pd.Series(0, index=df.index)

        if sentiment > threshold:
            positions[:] = 1
        elif sentiment < -threshold:
            positions[:] = -1

        return positions.shift(1).fillna(0)

    def _sentiment_reversal(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Mean revert on extreme sentiment."""
        extreme = params.get("sentiment_extreme", 0.5)
        rsi_confirm = params.get("rsi_confirm", True)

        positions = pd.Series(0, index=df.index)

        # Calculate RSI for confirmation
        if rsi_confirm:
            period = 14
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(period).mean()
            loss = (-delta.clip(upper=0)).rolling(period).mean()
            rs = gain / (loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))

            if sentiment < -extreme and (rsi < 30).any():
                positions[rsi < 30] = 1  # Buy on extreme negative + oversold
            elif sentiment > extreme and (rsi > 70).any():
                positions[rsi > 70] = -1  # Sell on extreme positive + overbought
        else:
            if sentiment < -extreme:
                positions[:] = 1
            elif sentiment > extreme:
                positions[:] = -1

        return positions.ffill().shift(1).fillna(0)

    def _multi_signal(
        self,
        df: pd.DataFrame,
        params: dict,
        insider: Any,
        sentiment: float,
    ) -> pd.Series:
        """Weighted combination of signals."""
        insider_weight = params.get("insider_weight", 0.4)
        sentiment_weight = params.get("sentiment_weight", 0.3)
        momentum_weight = params.get("momentum_weight", 0.3)

        # Momentum signal
        momentum = df["close"].pct_change(20)
        momentum_signal = np.sign(momentum)

        # Insider signal
        insider_signal = 0
        if insider:
            if insider.signal == "bullish":
                insider_signal = insider.strength
            elif insider.signal == "bearish":
                insider_signal = -insider.strength

        # Sentiment signal
        sentiment_signal = np.clip(sentiment, -1, 1)

        # Combine
        combined = (
            momentum_weight * momentum_signal +
            insider_weight * insider_signal +
            sentiment_weight * sentiment_signal
        )

        positions = pd.Series(0, index=df.index)
        positions[combined > 0.3] = 1
        positions[combined < -0.3] = -1

        return positions.shift(1).fillna(0)


def permute_returns(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Permute OHLCV data by shuffling gap and intrabar components."""
    np.random.seed(seed)
    n = len(df)
    if n < 20:
        return df.copy()

    # Decompose into components
    prev_close = df["close"].shift(1)
    gap_returns = ((df["open"] - prev_close) / prev_close).fillna(0).values
    intrabar_returns = ((df["close"] - df["open"]) / df["open"]).fillna(0).values

    # Shuffle independently
    perm_gap = np.random.permutation(n - 1)
    perm_intra = np.random.permutation(n - 1)

    shuffled_gaps = gap_returns[1:][perm_gap]
    shuffled_intra = intrabar_returns[1:][perm_intra]

    # Reconstruct prices
    prices = np.zeros(n)
    opens = np.zeros(n)
    prices[0] = df["close"].iloc[0]
    opens[0] = df["open"].iloc[0]

    for i in range(1, n):
        opens[i] = prices[i - 1] * (1 + shuffled_gaps[i - 1])
        prices[i] = opens[i] * (1 + shuffled_intra[i - 1])

    # Reconstruct high/low
    high_rel = ((df["high"] - df["open"]) / df["open"]).fillna(0).values
    low_rel = ((df["low"] - df["open"]) / df["open"]).fillna(0).values

    permuted = pd.DataFrame(index=df.index)
    permuted["open"] = opens
    permuted["close"] = prices
    permuted["high"] = opens * (1 + np.abs(high_rel))
    permuted["low"] = opens * (1 - np.abs(low_rel))
    permuted["volume"] = df["volume"].values

    # Ensure OHLC constraints
    permuted["high"] = permuted[["open", "close", "high"]].max(axis=1)
    permuted["low"] = permuted[["open", "close", "low"]].min(axis=1)

    return permuted


def backtest_strategy(
    positions: pd.Series,
    price_data: pd.DataFrame,
    cost_bps: float = 10,
) -> dict:
    """Run backtest and return metrics."""
    returns = price_data["close"].pct_change()
    strategy_returns = positions * returns

    # Transaction costs
    trades = (positions.diff().abs() > 0).sum()
    costs = positions.diff().abs() * (cost_bps / 10000)
    strategy_returns = strategy_returns - costs

    # Clean returns
    strategy_returns = strategy_returns.replace([np.inf, -np.inf], 0).fillna(0)

    # Metrics
    total_return = (1 + strategy_returns).prod() - 1
    sharpe = (
        strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
        if strategy_returns.std() > 0 else 0
    )

    cum_returns = (1 + strategy_returns).cumprod()
    rolling_max = cum_returns.expanding().max()
    drawdown = (cum_returns - rolling_max) / rolling_max
    max_dd = drawdown.min()

    return {
        "returns": strategy_returns,
        "total_return": float(total_return),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(max_dd),
        "trades": int(trades),
        "n_days": len(price_data),
    }


class ExperimentRunner:
    """
    Runs experiments (hypotheses) through MCPT validation.
    """

    def __init__(
        self,
        data_hub: DataHub,
        knowledge_base: KnowledgeBase,
    ):
        self.hub = data_hub
        self.kb = knowledge_base
        self.executor = StrategyExecutor()

    async def run_experiment(
        self,
        hypothesis: Hypothesis,
        data_bundle: DataBundle,
        validation_days: int = 90,
        n_permutations: int = 200,
    ) -> ExperimentResult:
        """Run a single experiment with MCPT validation."""
        start_time = datetime.now()

        # Check data availability
        symbol = hypothesis.symbols[0]
        if symbol not in data_bundle.price_data:
            return ExperimentResult(
                hypothesis=hypothesis,
                status="skipped",
                error_message=f"No price data for {symbol}",
                missing_signals=["price"],
            )

        price_data = data_bundle.price_data[symbol]
        if len(price_data) < 100:
            return ExperimentResult(
                hypothesis=hypothesis,
                status="skipped",
                error_message=f"Insufficient price data: {len(price_data)} days",
            )

        # Check additional data requirements
        missing = []
        for req in hypothesis.data_requirements:
            if req == "price":
                continue
            elif req == "insider":
                if symbol not in data_bundle.insider_signals:
                    missing.append("insider")
            elif req == "sentiment":
                if symbol not in data_bundle.sentiment_scores:
                    missing.append("sentiment")
            elif req == "economic":
                if data_bundle.economic_regime is None:
                    missing.append("economic")

        # Get auxiliary data
        insider_signal = data_bundle.insider_signals.get(symbol)
        sentiment_score = data_bundle.sentiment_scores.get(symbol, 0.0)

        try:
            # Split into training and validation
            val_start = len(price_data) - validation_days
            train_data = price_data.iloc[:val_start]
            val_data = price_data.iloc[val_start:]

            if len(train_data) < 100 or len(val_data) < 20:
                return ExperimentResult(
                    hypothesis=hypothesis,
                    status="skipped",
                    error_message="Insufficient data for train/val split",
                )

            # Run on training data
            train_positions = self.executor.execute(
                hypothesis, train_data, insider_signal, sentiment_score
            )
            train_result = backtest_strategy(train_positions, train_data)

            # Run on validation data
            val_positions = self.executor.execute(
                hypothesis, val_data, insider_signal, sentiment_score
            )
            val_result = backtest_strategy(val_positions, val_data)

            # MCPT on validation data
            original_sharpe = val_result["sharpe_ratio"]
            perm_sharpes = []

            for i in range(n_permutations):
                try:
                    permuted_data = permute_returns(val_data, seed=42 + i)
                    perm_positions = self.executor.execute(
                        hypothesis, permuted_data, insider_signal, sentiment_score
                    )
                    perm_result = backtest_strategy(perm_positions, permuted_data)
                    perm_sharpes.append(perm_result["sharpe_ratio"])
                except Exception:
                    continue

            if len(perm_sharpes) < 50:
                return ExperimentResult(
                    hypothesis=hypothesis,
                    status="error",
                    error_message="Insufficient permutations succeeded",
                    train_sharpe=train_result["sharpe_ratio"],
                    val_sharpe=val_result["sharpe_ratio"],
                )

            # Calculate p-value
            p_value = (
                np.sum(np.array(perm_sharpes) >= original_sharpe) + 1
            ) / (len(perm_sharpes) + 1)

            is_significant = p_value < 0.05

            # Generate insights
            insights = self._generate_insights(
                hypothesis, train_result, val_result, p_value, is_significant
            )

            # Mark as tested
            self.kb.mark_tested(
                hypothesis.strategy_type,
                symbol,
                hypothesis.strategy_params,
            )

            # Record success/failure
            if is_significant:
                self.kb.record_success(
                    strategy_name=hypothesis.strategy_type,
                    symbol=symbol,
                    params=hypothesis.strategy_params,
                    train_sharpe=train_result["sharpe_ratio"],
                    val_sharpe=val_result["sharpe_ratio"],
                    p_value=p_value,
                    session_id="experiment",
                    validation_period=f"{validation_days}d",
                )

            runtime = (datetime.now() - start_time).total_seconds()

            return ExperimentResult(
                hypothesis=hypothesis,
                status="success" if is_significant else "failed",
                train_sharpe=train_result["sharpe_ratio"],
                train_return=train_result["total_return"],
                val_sharpe=val_result["sharpe_ratio"],
                val_return=val_result["total_return"],
                val_max_dd=val_result["max_drawdown"],
                mcpt_p_value=p_value,
                is_significant=is_significant,
                perm_sharpe_mean=np.mean(perm_sharpes),
                perm_sharpe_std=np.std(perm_sharpes),
                data_coverage=1.0 - len(missing) / max(len(hypothesis.data_requirements), 1),
                missing_signals=missing,
                insights=insights,
                runtime_seconds=runtime,
            )

        except Exception as e:
            return ExperimentResult(
                hypothesis=hypothesis,
                status="error",
                error_message=str(e),
                runtime_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _generate_insights(
        self,
        hypothesis: Hypothesis,
        train_result: dict,
        val_result: dict,
        p_value: float,
        is_significant: bool,
    ) -> list[str]:
        """Generate insights from experiment results."""
        insights = []

        # Significance insight
        if is_significant:
            insights.append(
                f"SIGNIFICANT: {hypothesis.strategy_type} on {hypothesis.symbols[0]} "
                f"with p={p_value:.3f}, val_sharpe={val_result['sharpe_ratio']:.2f}"
            )
        else:
            insights.append(
                f"Not significant: p={p_value:.3f}"
            )

        # Overfitting detection
        train_sharpe = train_result["sharpe_ratio"]
        val_sharpe = val_result["sharpe_ratio"]
        if train_sharpe > 1.5 and val_sharpe < 0.5:
            insights.append("WARNING: Possible overfitting (high train, low val)")

        # Strategy behavior
        if val_result["trades"] < 5:
            insights.append("Low trade count - strategy may be too conservative")
        elif val_result["trades"] > 200:
            insights.append("High trade count - consider higher thresholds")

        return insights

    async def run_batch(
        self,
        hypotheses: list[Hypothesis],
        data_bundle: DataBundle,
        max_concurrent: int = 3,
        validation_days: int = 90,
        n_permutations: int = 200,
    ) -> list[ExperimentResult]:
        """Run multiple experiments."""
        results = []

        # Run in batches
        for i in range(0, len(hypotheses), max_concurrent):
            batch = hypotheses[i:i + max_concurrent]

            # Run batch concurrently
            tasks = [
                self.run_experiment(h, data_bundle, validation_days, n_permutations)
                for h in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

            # Progress
            print(f"  Completed {min(i + max_concurrent, len(hypotheses))}/{len(hypotheses)} experiments")

        return results
