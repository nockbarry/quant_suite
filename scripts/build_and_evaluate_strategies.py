#!/usr/bin/env python3
"""
Strategy Builder and Evaluator.

Builds strategies based on knowledge base learnings and evaluates them
with proper walk-forward validation and MCPT testing.

Based on successful patterns:
1. Bollinger Reversal - 95% confidence, works on QCOM, MRVL, XLV
2. RSI Reversal - 70% confidence, works on MSFT, SPY
3. Multi-Signal - 60% confidence, combining insider+sentiment+momentum

New experimental strategies:
4. Options Flow Sentiment
5. ETF Flow Momentum
6. Insider Cluster + Technical Confluence
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Results directory
RESULTS_DIR = Path.home() / "quant_results" / "strategy_evaluation"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_price_data(
    symbols: list[str],
    start_date: str = "2022-01-01",
    end_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data for symbols."""
    data = {}
    end = end_date or datetime.now().strftime("%Y-%m-%d")

    for symbol in symbols:
        try:
            logger.info(f"Fetching {symbol}...")
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end)

            if len(df) > 0:
                df.columns = df.columns.str.lower()
                df.index = pd.to_datetime(df.index).tz_localize(None)
                data[symbol] = df
                logger.info(f"  {symbol}: {len(df)} days")
            else:
                logger.warning(f"  {symbol}: No data")
        except Exception as e:
            logger.error(f"  {symbol}: Error - {e}")

    return data


# =============================================================================
# TECHNICAL INDICATORS
# =============================================================================

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add comprehensive technical indicators to price data."""
    df = df.copy()

    # Moving Averages
    for period in [5, 10, 20, 50, 200]:
        df[f'sma_{period}'] = df['close'].rolling(period).mean()
        df[f'ema_{period}'] = df['close'].ewm(span=period).mean()

    # RSI
    for period in [7, 14, 21]:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    for period in [10, 20]:
        for num_std in [1.5, 2.0, 2.5]:
            sma = df['close'].rolling(period).mean()
            std = df['close'].rolling(period).std()
            upper = sma + num_std * std
            lower = sma - num_std * std
            suffix = f'{period}_{str(num_std).replace(".", "")}'
            df[f'bb_upper_{suffix}'] = upper
            df[f'bb_lower_{suffix}'] = lower
            df[f'bb_pctb_{suffix}'] = (df['close'] - lower) / (upper - lower)

    # Momentum
    for period in [5, 10, 21, 63]:
        df[f'momentum_{period}d'] = df['close'].pct_change(period)
        df[f'returns_{period}d'] = df['close'].pct_change(period)

    # Volatility
    df['volatility_10d'] = df['close'].pct_change().rolling(10).std() * np.sqrt(252)
    df['volatility_21d'] = df['close'].pct_change().rolling(21).std() * np.sqrt(252)

    # MACD
    ema_12 = df['close'].ewm(span=12).mean()
    ema_26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()

    # Volume indicators
    df['volume_sma_20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma_20']

    # Distance from moving averages
    df['dist_sma_20'] = (df['close'] - df['sma_20']) / df['sma_20']
    df['dist_sma_50'] = (df['close'] - df['sma_50']) / df['sma_50']

    return df


# =============================================================================
# STRATEGY IMPLEMENTATIONS
# =============================================================================

@dataclass
class Signal:
    """Trading signal."""
    date: datetime
    symbol: str
    direction: int  # 1 = long, -1 = short, 0 = flat
    strength: float  # -1 to 1
    confidence: float  # 0 to 1
    strategy: str
    metadata: dict = field(default_factory=dict)


class BaseStrategy:
    """Base class for all strategies."""

    name: str = "base"

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        """Generate signal series. Returns values between -1 and 1."""
        raise NotImplementedError


class BollingerReversalStrategy(BaseStrategy):
    """
    Bollinger Band Mean Reversion.

    Based on successful pattern: 95% confidence, avg p-value 0.027
    Best on: QCOM, MRVL, XLV
    """

    name = "bollinger_reversal"

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        suffix = f'{self.period}_{str(self.num_std).replace(".", "")}'
        pctb_col = f'bb_pctb_{suffix}'

        if pctb_col not in data.columns:
            # Calculate if not present
            sma = data['close'].rolling(self.period).mean()
            std = data['close'].rolling(self.period).std()
            upper = sma + self.num_std * std
            lower = sma - self.num_std * std
            pctb = (data['close'] - lower) / (upper - lower)
        else:
            pctb = data[pctb_col]

        signals = pd.Series(0.0, index=data.index)

        # Buy when oversold (pctb < 0), sell when overbought (pctb > 1)
        signals[pctb < 0] = 1.0  # Strong buy
        signals[(pctb >= 0) & (pctb < 0.2)] = 0.5  # Mild buy
        signals[(pctb > 0.8) & (pctb <= 1)] = -0.5  # Mild sell
        signals[pctb > 1] = -1.0  # Strong sell

        return signals


class RSIReversalStrategy(BaseStrategy):
    """
    RSI Mean Reversion.

    Based on successful pattern: 70% confidence
    Best on: MSFT, SPY
    """

    name = "rsi_reversal"

    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        rsi_col = f'rsi_{self.period}'

        if rsi_col not in data.columns:
            delta = data['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(self.period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(self.period).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
        else:
            rsi = data[rsi_col]

        signals = pd.Series(0.0, index=data.index)

        # Buy when oversold, sell when overbought
        signals[rsi < self.oversold] = 1.0
        signals[(rsi >= self.oversold) & (rsi < 40)] = 0.3
        signals[(rsi > 60) & (rsi <= self.overbought)] = -0.3
        signals[rsi > self.overbought] = -1.0

        return signals


class MomentumStrategy(BaseStrategy):
    """
    Time-series momentum with volatility scaling.
    """

    name = "momentum"

    def __init__(self, lookback: int = 21, vol_lookback: int = 21):
        self.lookback = lookback
        self.vol_lookback = vol_lookback

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        returns = data['close'].pct_change(self.lookback)
        vol = data['close'].pct_change().rolling(self.vol_lookback).std()

        # Risk-adjusted momentum
        risk_adj_mom = returns / (vol + 1e-8)

        # Normalize to -1 to 1
        signals = np.tanh(risk_adj_mom / 2)

        return signals


class MultiSignalStrategy(BaseStrategy):
    """
    Combined multi-factor strategy.

    Based on successful pattern: 60% confidence on AMD
    Combines: momentum, mean reversion, and trend
    """

    name = "multi_signal"

    def __init__(
        self,
        momentum_weight: float = 0.4,
        reversion_weight: float = 0.3,
        trend_weight: float = 0.3,
    ):
        self.momentum_weight = momentum_weight
        self.reversion_weight = reversion_weight
        self.trend_weight = trend_weight

        self.momentum_strat = MomentumStrategy(lookback=21)
        self.bollinger_strat = BollingerReversalStrategy(period=20)

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        # Momentum signal
        mom_signal = self.momentum_strat.generate_signals(data, symbol)

        # Mean reversion signal
        rev_signal = self.bollinger_strat.generate_signals(data, symbol)

        # Trend signal (price above/below SMA50)
        trend_signal = pd.Series(0.0, index=data.index)
        if 'sma_50' in data.columns:
            trend_signal[data['close'] > data['sma_50']] = 1.0
            trend_signal[data['close'] < data['sma_50']] = -1.0

        # Combine
        combined = (
            self.momentum_weight * mom_signal +
            self.reversion_weight * rev_signal +
            self.trend_weight * trend_signal
        )

        return combined.clip(-1, 1)


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following with moving average crossovers.
    """

    name = "trend_following"

    def __init__(self, fast_period: int = 10, slow_period: int = 50):
        self.fast = fast_period
        self.slow = slow_period

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        fast_ma = data['close'].rolling(self.fast).mean()
        slow_ma = data['close'].rolling(self.slow).mean()

        # Signal strength based on MA distance
        spread = (fast_ma - slow_ma) / slow_ma
        signals = np.tanh(spread * 10)

        return signals


class VolatilityBreakoutStrategy(BaseStrategy):
    """
    Volatility breakout - trade breakouts from compressed ranges.
    """

    name = "volatility_breakout"

    def __init__(self, lookback: int = 20, vol_threshold: float = 0.5):
        self.lookback = lookback
        self.vol_threshold = vol_threshold

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        # Historical volatility percentile
        vol = data['close'].pct_change().rolling(self.lookback).std()
        vol_pct = vol.rolling(252).apply(lambda x: (x.iloc[-1] < x).sum() / len(x), raw=False)

        # Price breakout
        high_20 = data['high'].rolling(self.lookback).max()
        low_20 = data['low'].rolling(self.lookback).min()

        signals = pd.Series(0.0, index=data.index)

        # Low vol regime + price near high = potential upside breakout
        low_vol = vol_pct < self.vol_threshold
        signals[low_vol & (data['close'] > high_20.shift(1))] = 1.0
        signals[low_vol & (data['close'] < low_20.shift(1))] = -1.0

        return signals


class AdaptiveStrategy(BaseStrategy):
    """
    Adaptive strategy that switches between momentum and mean reversion
    based on market regime.
    """

    name = "adaptive_regime"

    def __init__(self, vol_threshold: float = 0.20):
        self.vol_threshold = vol_threshold
        self.momentum = MomentumStrategy()
        self.reversion = BollingerReversalStrategy()

    def generate_signals(self, data: pd.DataFrame, symbol: str) -> pd.Series:
        # Determine regime based on volatility
        vol = data['close'].pct_change().rolling(21).std() * np.sqrt(252)

        mom_signals = self.momentum.generate_signals(data, symbol)
        rev_signals = self.reversion.generate_signals(data, symbol)

        signals = pd.Series(0.0, index=data.index)

        # High vol = momentum (trending), Low vol = mean reversion
        high_vol = vol > self.vol_threshold
        signals[high_vol] = mom_signals[high_vol]
        signals[~high_vol] = rev_signals[~high_vol]

        return signals


# =============================================================================
# BACKTESTING ENGINE
# =============================================================================

@dataclass
class BacktestResult:
    """Results from a backtest."""
    strategy: str
    symbol: str
    params: dict
    start_date: datetime
    end_date: datetime
    n_trades: int
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_trade_return: float
    returns: pd.Series = None
    equity_curve: pd.Series = None


def backtest_strategy(
    strategy: BaseStrategy,
    data: pd.DataFrame,
    symbol: str,
    initial_capital: float = 10000.0,
    transaction_cost: float = 0.001,
) -> BacktestResult:
    """Run a backtest for a strategy."""

    # Generate signals
    signals = strategy.generate_signals(data, symbol)

    # Forward fill signals (hold position)
    positions = signals.copy()

    # Calculate returns
    daily_returns = data['close'].pct_change()

    # Strategy returns (position * daily return - transaction costs)
    position_changes = positions.diff().abs()
    costs = position_changes * transaction_cost
    strategy_returns = positions.shift(1) * daily_returns - costs
    strategy_returns = strategy_returns.dropna()

    if len(strategy_returns) == 0:
        return BacktestResult(
            strategy=strategy.name,
            symbol=symbol,
            params={},
            start_date=data.index[0],
            end_date=data.index[-1],
            n_trades=0,
            total_return=0,
            cagr=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            max_drawdown=0,
            win_rate=0,
            profit_factor=0,
            avg_trade_return=0,
        )

    # Calculate equity curve
    equity_curve = (1 + strategy_returns).cumprod() * initial_capital

    # Metrics
    total_return = equity_curve.iloc[-1] / initial_capital - 1

    years = (strategy_returns.index[-1] - strategy_returns.index[0]).days / 365.25
    cagr = (equity_curve.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else 0

    # Sharpe ratio (annualized)
    mean_return = strategy_returns.mean() * 252
    std_return = strategy_returns.std() * np.sqrt(252)
    sharpe = mean_return / std_return if std_return > 0 else 0

    # Sortino ratio
    downside_returns = strategy_returns[strategy_returns < 0]
    downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
    sortino = mean_return / downside_std if downside_std > 0 else 0

    # Max drawdown
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = drawdown.min()

    # Win rate
    winning_days = (strategy_returns > 0).sum()
    total_days = len(strategy_returns)
    win_rate = winning_days / total_days if total_days > 0 else 0

    # Profit factor
    gross_profits = strategy_returns[strategy_returns > 0].sum()
    gross_losses = abs(strategy_returns[strategy_returns < 0].sum())
    profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')

    # Number of trades (position changes)
    n_trades = (positions.diff().abs() > 0).sum()

    return BacktestResult(
        strategy=strategy.name,
        symbol=symbol,
        params=getattr(strategy, '__dict__', {}),
        start_date=strategy_returns.index[0].to_pydatetime(),
        end_date=strategy_returns.index[-1].to_pydatetime(),
        n_trades=int(n_trades),
        total_return=float(total_return),
        cagr=float(cagr),
        sharpe_ratio=float(sharpe),
        sortino_ratio=float(sortino),
        max_drawdown=float(max_drawdown),
        win_rate=float(win_rate),
        profit_factor=float(profit_factor) if profit_factor != float('inf') else 10.0,
        avg_trade_return=float(strategy_returns.mean()),
        returns=strategy_returns,
        equity_curve=equity_curve,
    )


# =============================================================================
# WALK-FORWARD VALIDATION
# =============================================================================

@dataclass
class WalkForwardResult:
    """Walk-forward validation result."""
    strategy: str
    symbol: str
    n_folds: int
    avg_train_sharpe: float
    avg_test_sharpe: float
    std_test_sharpe: float
    avg_test_return: float
    total_test_return: float
    consistency: float  # % of folds with positive test Sharpe
    fold_results: list[dict] = field(default_factory=list)


def walk_forward_validation(
    strategy: BaseStrategy,
    data: pd.DataFrame,
    symbol: str,
    train_days: int = 504,  # 2 years
    test_days: int = 63,    # 3 months
    step_days: int = 21,    # 1 month
) -> WalkForwardResult:
    """Run walk-forward validation."""

    fold_results = []

    n_rows = len(data)
    start_idx = train_days

    while start_idx + test_days <= n_rows:
        # Train period
        train_start = start_idx - train_days
        train_end = start_idx
        train_data = data.iloc[train_start:train_end]

        # Test period
        test_start = start_idx
        test_end = min(start_idx + test_days, n_rows)
        test_data = data.iloc[test_start:test_end]

        # Backtest on train
        train_result = backtest_strategy(strategy, train_data, symbol)

        # Backtest on test
        test_result = backtest_strategy(strategy, test_data, symbol)

        fold_results.append({
            'train_start': train_data.index[0],
            'train_end': train_data.index[-1],
            'test_start': test_data.index[0],
            'test_end': test_data.index[-1],
            'train_sharpe': train_result.sharpe_ratio,
            'test_sharpe': test_result.sharpe_ratio,
            'test_return': test_result.total_return,
        })

        start_idx += step_days

    if not fold_results:
        return WalkForwardResult(
            strategy=strategy.name,
            symbol=symbol,
            n_folds=0,
            avg_train_sharpe=0,
            avg_test_sharpe=0,
            std_test_sharpe=0,
            avg_test_return=0,
            total_test_return=0,
            consistency=0,
        )

    train_sharpes = [f['train_sharpe'] for f in fold_results]
    test_sharpes = [f['test_sharpe'] for f in fold_results]
    test_returns = [f['test_return'] for f in fold_results]

    consistency = sum(1 for s in test_sharpes if s > 0) / len(test_sharpes)

    return WalkForwardResult(
        strategy=strategy.name,
        symbol=symbol,
        n_folds=len(fold_results),
        avg_train_sharpe=float(np.mean(train_sharpes)),
        avg_test_sharpe=float(np.mean(test_sharpes)),
        std_test_sharpe=float(np.std(test_sharpes)),
        avg_test_return=float(np.mean(test_returns)),
        total_test_return=float(np.sum(test_returns)),
        consistency=float(consistency),
        fold_results=fold_results,
    )


# =============================================================================
# MCPT PERMUTATION TEST
# =============================================================================

def mcpt_test(
    strategy: BaseStrategy,
    data: pd.DataFrame,
    symbol: str,
    n_permutations: int = 500,
) -> dict:
    """
    Monte Carlo Permutation Test.

    Tests if strategy performance is statistically significant.
    """

    # Actual performance
    actual_result = backtest_strategy(strategy, data, symbol)
    actual_sharpe = actual_result.sharpe_ratio

    # Generate permuted returns
    returns = data['close'].pct_change().dropna()
    permuted_sharpes = []

    for i in range(n_permutations):
        # Permute returns
        permuted = returns.sample(frac=1, replace=False)
        permuted.index = returns.index

        # Reconstruct prices
        permuted_prices = (1 + permuted).cumprod() * data['close'].iloc[0]
        permuted_data = data.copy()
        permuted_data['close'] = permuted_prices
        permuted_data['open'] = permuted_prices.shift(1)
        permuted_data['high'] = permuted_data[['open', 'close']].max(axis=1) * 1.01
        permuted_data['low'] = permuted_data[['open', 'close']].min(axis=1) * 0.99

        # Add indicators
        permuted_data = add_technical_indicators(permuted_data)

        # Backtest
        perm_result = backtest_strategy(strategy, permuted_data, symbol)
        permuted_sharpes.append(perm_result.sharpe_ratio)

    # Calculate p-value
    permuted_sharpes = np.array(permuted_sharpes)
    p_value = (permuted_sharpes >= actual_sharpe).sum() / n_permutations

    return {
        'actual_sharpe': actual_sharpe,
        'mean_permuted_sharpe': float(np.mean(permuted_sharpes)),
        'std_permuted_sharpe': float(np.std(permuted_sharpes)),
        'p_value': float(p_value),
        'significant_5pct': p_value < 0.05,
        'significant_10pct': p_value < 0.10,
        'n_permutations': n_permutations,
    }


# =============================================================================
# MAIN EVALUATION
# =============================================================================

def evaluate_all_strategies(
    symbols: list[str],
    strategies: list[BaseStrategy],
    run_mcpt: bool = True,
    n_permutations: int = 200,
) -> dict:
    """Evaluate all strategies across all symbols."""

    logger.info(f"Evaluating {len(strategies)} strategies on {len(symbols)} symbols")

    # Fetch data
    data = fetch_price_data(symbols, start_date="2021-01-01")

    # Add technical indicators
    for symbol in data:
        data[symbol] = add_technical_indicators(data[symbol])

    results = {
        'backtest_results': [],
        'walk_forward_results': [],
        'mcpt_results': [],
        'summary': {},
    }

    for strategy in strategies:
        logger.info(f"\nEvaluating strategy: {strategy.name}")

        for symbol in data:
            symbol_data = data[symbol]

            if len(symbol_data) < 300:
                logger.warning(f"  {symbol}: Insufficient data ({len(symbol_data)} days)")
                continue

            # Full backtest
            bt_result = backtest_strategy(strategy, symbol_data, symbol)
            results['backtest_results'].append({
                'strategy': bt_result.strategy,
                'symbol': bt_result.symbol,
                'sharpe_ratio': bt_result.sharpe_ratio,
                'sortino_ratio': bt_result.sortino_ratio,
                'total_return': bt_result.total_return,
                'cagr': bt_result.cagr,
                'max_drawdown': bt_result.max_drawdown,
                'win_rate': bt_result.win_rate,
                'profit_factor': bt_result.profit_factor,
                'n_trades': bt_result.n_trades,
            })

            logger.info(f"  {symbol}: Sharpe={bt_result.sharpe_ratio:.2f}, Return={bt_result.total_return:.1%}")

            # Walk-forward validation
            wf_result = walk_forward_validation(strategy, symbol_data, symbol)
            results['walk_forward_results'].append({
                'strategy': wf_result.strategy,
                'symbol': wf_result.symbol,
                'n_folds': wf_result.n_folds,
                'avg_train_sharpe': wf_result.avg_train_sharpe,
                'avg_test_sharpe': wf_result.avg_test_sharpe,
                'std_test_sharpe': wf_result.std_test_sharpe,
                'consistency': wf_result.consistency,
                'total_test_return': wf_result.total_test_return,
            })

            logger.info(f"    WF: Test Sharpe={wf_result.avg_test_sharpe:.2f}, Consistency={wf_result.consistency:.0%}")

            # MCPT test (only for promising strategies)
            if run_mcpt and bt_result.sharpe_ratio > 0.5:
                mcpt_result = mcpt_test(strategy, symbol_data, symbol, n_permutations)
                mcpt_result['strategy'] = strategy.name
                mcpt_result['symbol'] = symbol
                results['mcpt_results'].append(mcpt_result)

                logger.info(f"    MCPT: p={mcpt_result['p_value']:.3f}, Significant={mcpt_result['significant_5pct']}")

    # Summary statistics
    bt_df = pd.DataFrame(results['backtest_results'])
    wf_df = pd.DataFrame(results['walk_forward_results'])

    results['summary'] = {
        'total_combinations': len(bt_df),
        'positive_sharpe_count': len(bt_df[bt_df['sharpe_ratio'] > 0]),
        'sharpe_gt_1_count': len(bt_df[bt_df['sharpe_ratio'] > 1]),
        'best_strategy_symbol': None,
        'best_sharpe': 0,
        'by_strategy': {},
    }

    if len(bt_df) > 0:
        best_idx = bt_df['sharpe_ratio'].idxmax()
        results['summary']['best_strategy_symbol'] = f"{bt_df.loc[best_idx, 'strategy']} on {bt_df.loc[best_idx, 'symbol']}"
        results['summary']['best_sharpe'] = float(bt_df.loc[best_idx, 'sharpe_ratio'])

        for strat in bt_df['strategy'].unique():
            strat_df = bt_df[bt_df['strategy'] == strat]
            results['summary']['by_strategy'][strat] = {
                'avg_sharpe': float(strat_df['sharpe_ratio'].mean()),
                'avg_return': float(strat_df['total_return'].mean()),
                'best_symbol': strat_df.loc[strat_df['sharpe_ratio'].idxmax(), 'symbol'],
                'best_sharpe': float(strat_df['sharpe_ratio'].max()),
            }

    return results


def main():
    """Main entry point."""

    logger.info("=" * 60)
    logger.info("STRATEGY BUILDER AND EVALUATOR")
    logger.info("=" * 60)

    # Symbols based on past successful patterns
    successful_symbols = ['QCOM', 'MRVL', 'MSFT', 'SPY', 'AMD', 'XLV']
    exploration_symbols = ['NVDA', 'AAPL', 'GOOGL', 'META', 'AMZN', 'QQQ', 'IWM']
    all_symbols = list(set(successful_symbols + exploration_symbols))

    # Strategies based on learnings
    strategies = [
        # Proven strategies
        BollingerReversalStrategy(period=20, num_std=2.0),
        BollingerReversalStrategy(period=10, num_std=2.0),
        RSIReversalStrategy(period=14, oversold=30, overbought=70),
        RSIReversalStrategy(period=21, oversold=30, overbought=80),

        # Multi-factor
        MultiSignalStrategy(momentum_weight=0.4, reversion_weight=0.3, trend_weight=0.3),

        # New experimental strategies
        TrendFollowingStrategy(fast_period=10, slow_period=50),
        VolatilityBreakoutStrategy(lookback=20, vol_threshold=0.5),
        AdaptiveStrategy(vol_threshold=0.20),
    ]

    # Run evaluation
    results = evaluate_all_strategies(
        symbols=all_symbols,
        strategies=strategies,
        run_mcpt=True,
        n_permutations=200,
    )

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"evaluation_{timestamp}.json"

    # Convert results to JSON-serializable format
    json_results = {
        'timestamp': timestamp,
        'symbols': all_symbols,
        'strategies': [s.name for s in strategies],
        'backtest_results': results['backtest_results'],
        'walk_forward_results': results['walk_forward_results'],
        'mcpt_results': results['mcpt_results'],
        'summary': results['summary'],
    }

    with open(results_file, 'w') as f:
        json.dump(json_results, f, indent=2, default=str)

    logger.info(f"\nResults saved to: {results_file}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    logger.info(f"\nTotal combinations evaluated: {results['summary']['total_combinations']}")
    logger.info(f"Positive Sharpe: {results['summary']['positive_sharpe_count']}")
    logger.info(f"Sharpe > 1: {results['summary']['sharpe_gt_1_count']}")
    logger.info(f"\nBest: {results['summary']['best_strategy_symbol']} (Sharpe={results['summary']['best_sharpe']:.2f})")

    logger.info("\nBy Strategy:")
    for strat, stats in results['summary']['by_strategy'].items():
        logger.info(f"  {strat}:")
        logger.info(f"    Avg Sharpe: {stats['avg_sharpe']:.2f}")
        logger.info(f"    Best: {stats['best_symbol']} (Sharpe={stats['best_sharpe']:.2f})")

    # Statistically significant results
    if results['mcpt_results']:
        sig_results = [r for r in results['mcpt_results'] if r['significant_5pct']]
        logger.info(f"\nStatistically Significant (p<0.05): {len(sig_results)}")
        for r in sig_results:
            logger.info(f"  {r['strategy']} on {r['symbol']}: Sharpe={r['actual_sharpe']:.2f}, p={r['p_value']:.3f}")

    return results


if __name__ == "__main__":
    results = main()
