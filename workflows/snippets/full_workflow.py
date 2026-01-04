#!/usr/bin/env python3
"""
Complete Strategy Development Workflow
Run with: python workflows/snippets/full_workflow.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from itertools import product
from scipy import stats
from enum import Enum


# =============================================================================
# DATA GENERATION
# =============================================================================

def generate_realistic_data(symbol: str, days: int = 180,
                           initial_price: float = 100,
                           volatility: float = 0.25,
                           trend: float = 0.0,
                           seed: Optional[int] = None) -> pd.DataFrame:
    """Generate realistic OHLCV data for backtesting."""
    if seed:
        np.random.seed(seed)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.4))
    dates = pd.date_range(start=start_date, end=end_date, freq='B')[:days]

    n = len(dates)
    daily_trend = trend / 252
    daily_vol = volatility / np.sqrt(252)

    returns = np.random.normal(daily_trend, daily_vol, n)
    prices = initial_price * np.exp(np.cumsum(returns))

    daily_range = daily_vol * prices
    highs = prices + np.abs(np.random.normal(0, 1, n)) * daily_range
    lows = prices - np.abs(np.random.normal(0, 1, n)) * daily_range
    opens = prices + np.random.normal(0, 0.3, n) * daily_range

    return pd.DataFrame({
        'open': opens,
        'high': np.maximum(highs, np.maximum(opens, prices)),
        'low': np.minimum(lows, np.minimum(opens, prices)),
        'close': prices,
        'volume': np.random.uniform(1e6, 1e8, n)
    }, index=dates)


def load_universe(symbols: List[str], days: int = 180, seed: int = 42) -> Dict[str, pd.DataFrame]:
    """Load data for a universe of symbols."""
    np.random.seed(seed)

    configs = {
        'QQQ': {'price': 400, 'vol': 0.22, 'trend': 0.08},
        'SPY': {'price': 480, 'vol': 0.18, 'trend': 0.10},
        'META': {'price': 350, 'vol': 0.35, 'trend': 0.20},
        'TSLA': {'price': 250, 'vol': 0.55, 'trend': 0.05},
        'NVDA': {'price': 500, 'vol': 0.45, 'trend': 0.25},
        'AAPL': {'price': 180, 'vol': 0.22, 'trend': 0.08},
        'MSFT': {'price': 400, 'vol': 0.22, 'trend': 0.12},
        'GOOGL': {'price': 140, 'vol': 0.28, 'trend': 0.05},
        'AMZN': {'price': 180, 'vol': 0.30, 'trend': 0.10},
    }

    universe = {}
    for sym in symbols:
        cfg = configs.get(sym, {'price': 100, 'vol': 0.25, 'trend': 0.0})
        universe[sym] = generate_realistic_data(
            sym, days, cfg['price'], cfg['vol'], cfg['trend']
        )
    return universe


# =============================================================================
# REGIME DETECTION
# =============================================================================

class TrendRegime(Enum):
    STRONG_UPTREND = "strong_uptrend"
    UPTREND = "uptrend"
    SIDEWAYS = "sideways"
    DOWNTREND = "downtrend"
    STRONG_DOWNTREND = "strong_downtrend"

class VolatilityRegime(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRISIS = "crisis"

@dataclass
class RegimeState:
    trend: TrendRegime
    volatility: VolatilityRegime
    trend_strength: float
    vol_percentile: float


def detect_regime(df: pd.DataFrame, lookback: int = 20) -> RegimeState:
    """Detect current market regime from OHLCV data."""
    close = df['close']
    returns = close.pct_change()

    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()

    price = close.iloc[-1]
    s20, s50 = sma_20.iloc[-1], sma_50.iloc[-1]

    trend_score = 0
    if price > s20: trend_score += 1
    if price > s50: trend_score += 1
    if s20 > s50: trend_score += 1
    trend_strength = trend_score / 3

    if trend_strength >= 0.9:
        trend = TrendRegime.STRONG_UPTREND
    elif trend_strength >= 0.6:
        trend = TrendRegime.UPTREND
    elif trend_strength <= 0.1:
        trend = TrendRegime.STRONG_DOWNTREND
    elif trend_strength <= 0.4:
        trend = TrendRegime.DOWNTREND
    else:
        trend = TrendRegime.SIDEWAYS

    current_vol = returns.rolling(lookback).std().iloc[-1] * np.sqrt(252)
    hist_vol = returns.rolling(60).std() * np.sqrt(252)
    vol_percentile = (hist_vol < current_vol).mean() * 100

    if vol_percentile >= 90:
        vol_regime = VolatilityRegime.CRISIS
    elif vol_percentile >= 70:
        vol_regime = VolatilityRegime.HIGH
    elif vol_percentile <= 30:
        vol_regime = VolatilityRegime.LOW
    else:
        vol_regime = VolatilityRegime.NORMAL

    return RegimeState(trend, vol_regime, trend_strength, vol_percentile)


def regime_summary(stocks: Dict[str, pd.DataFrame]) -> Dict:
    """Get regime summary for entire universe."""
    results = {}
    for symbol, df in stocks.items():
        if len(df) < 50:
            continue
        regime = detect_regime(df)
        total_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1)
        results[symbol] = {
            'trend': regime.trend.value,
            'volatility': regime.volatility.value,
            'trend_strength': regime.trend_strength,
            'vol_percentile': regime.vol_percentile,
            'total_return': total_return
        }
    return results


# =============================================================================
# BACKTEST RESULT
# =============================================================================

@dataclass
class BacktestResult:
    returns: pd.Series
    positions: pd.Series
    trades: int
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float


# =============================================================================
# STRATEGIES
# =============================================================================

class Strategy(ABC):
    """Base strategy class."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        pass

    def backtest(self, df: pd.DataFrame, cost_bps: float = 10) -> BacktestResult:
        """Run backtest on OHLCV data."""
        signals = self.generate_signals(df)
        positions = signals.shift(1).fillna(0)

        returns = df['close'].pct_change()
        strategy_returns = positions * returns

        trades = (positions.diff().abs() > 0).sum()
        costs = positions.diff().abs() * (cost_bps / 10000)
        strategy_returns = strategy_returns - costs

        total_return = (1 + strategy_returns).prod() - 1
        sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() > 0 else 0

        cum_returns = (1 + strategy_returns).cumprod()
        rolling_max = cum_returns.expanding().max()
        drawdown = (cum_returns - rolling_max) / rolling_max
        max_dd = drawdown.min()

        winning = (strategy_returns > 0).sum()
        losing = (strategy_returns < 0).sum()
        win_rate = winning / (winning + losing) if (winning + losing) > 0 else 0

        gross_profit = strategy_returns[strategy_returns > 0].sum()
        gross_loss = abs(strategy_returns[strategy_returns < 0].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return BacktestResult(
            returns=strategy_returns,
            positions=positions,
            trades=int(trades),
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor
        )


class SMACrossover(Strategy):
    def __init__(self, fast: int = 10, slow: int = 30):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_ma = df['close'].rolling(self.fast).mean()
        slow_ma = df['close'].rolling(self.slow).mean()
        return pd.Series(np.where(fast_ma > slow_ma, 1, -1), index=df.index)


class BreakoutStrategy(Strategy):
    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        high_channel = df['high'].rolling(self.lookback).max()
        low_channel = df['low'].rolling(self.lookback).min()

        signals = pd.Series(0, index=df.index)
        signals[df['close'] >= high_channel.shift(1)] = 1
        signals[df['close'] <= low_channel.shift(1)] = -1
        return signals.ffill().fillna(0)


class TrendFollowing(Strategy):
    def __init__(self, adx_period: int = 14, adx_threshold: float = 25):
        self.period = adx_period
        self.threshold = adx_threshold

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


class RSIMeanReversion(Strategy):
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

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


class BollingerReversion(Strategy):
    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma = df['close'].rolling(self.period).mean()
        std = df['close'].rolling(self.period).std()
        upper = ma + self.num_std * std
        lower = ma - self.num_std * std

        signals = pd.Series(0, index=df.index)
        signals[df['close'] < lower] = 1
        signals[df['close'] > upper] = -1
        return signals.ffill().fillna(0)


class MomentumStrategy(Strategy):
    def __init__(self, lookback: int = 20, threshold: float = 0.0):
        self.lookback = lookback
        self.threshold = threshold

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        momentum = df['close'].pct_change(self.lookback)
        signals = pd.Series(0, index=df.index)
        signals[momentum > self.threshold] = 1
        signals[momentum < -self.threshold] = -1
        return signals


class DualMomentum(Strategy):
    def __init__(self, lookback: int = 60):
        self.lookback = lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        returns = df['close'].pct_change(self.lookback)
        signals = pd.Series(0, index=df.index)
        signals[returns > 0] = 1
        return signals


class VolatilityBreakout(Strategy):
    def __init__(self, atr_period: int = 14, multiplier: float = 1.5):
        self.period = atr_period
        self.multiplier = multiplier

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        high, low, close = df['high'], df['low'], df['close']

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(self.period).mean()

        upper = close.shift(1) + atr * self.multiplier
        lower = close.shift(1) - atr * self.multiplier

        signals = pd.Series(0, index=df.index)
        signals[close > upper] = 1
        signals[close < lower] = -1
        return signals.ffill().fillna(0)


# =============================================================================
# COMPARISON
# =============================================================================

@dataclass
class StrategyRanking:
    name: str
    symbol: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    trades: int
    params: dict


def test_all_strategies(stocks: Dict[str, pd.DataFrame],
                        min_sharpe: float = 0.0) -> List[StrategyRanking]:
    """Test all strategy variants across all symbols."""
    results = []

    strategies = {
        'SMA_10_30': SMACrossover(10, 30),
        'SMA_20_50': SMACrossover(20, 50),
        'SMA_5_20': SMACrossover(5, 20),
        'Breakout_20': BreakoutStrategy(20),
        'Breakout_10': BreakoutStrategy(10),
        'Breakout_40': BreakoutStrategy(40),
        'TrendFollow': TrendFollowing(14, 25),
        'RSI_14': RSIMeanReversion(14, 30, 70),
        'RSI_7': RSIMeanReversion(7, 20, 80),
        'Bollinger_20': BollingerReversion(20, 2.0),
        'Bollinger_10': BollingerReversion(10, 1.5),
        'Momentum_20': MomentumStrategy(20),
        'Momentum_60': MomentumStrategy(60),
        'DualMom_60': DualMomentum(60),
        'VolBreakout': VolatilityBreakout(14, 1.5),
    }

    for symbol, df in stocks.items():
        if len(df) < 100:
            continue

        for name, strategy in strategies.items():
            try:
                result = strategy.backtest(df)

                if result.sharpe_ratio >= min_sharpe:
                    results.append(StrategyRanking(
                        name=name,
                        symbol=symbol,
                        total_return=result.total_return,
                        sharpe_ratio=result.sharpe_ratio,
                        max_drawdown=result.max_drawdown,
                        trades=result.trades,
                        params=getattr(strategy, '__dict__', {})
                    ))
            except Exception as e:
                continue

    return sorted(results, key=lambda x: x.sharpe_ratio, reverse=True)


def print_rankings(rankings: List[StrategyRanking], top_n: int = 20):
    """Print formatted rankings."""
    print(f"\n{'Rank':<5} {'Strategy':<15} {'Symbol':<6} {'Return':>10} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>7}")
    print("-" * 65)

    for i, r in enumerate(rankings[:top_n], 1):
        print(f"{i:<5} {r.name:<15} {r.symbol:<6} {r.total_return:>9.1%} {r.sharpe_ratio:>8.2f} {r.max_drawdown:>7.1%} {r.trades:>7}")


# =============================================================================
# OPTIMIZATION
# =============================================================================

@dataclass
class OptimizationResult:
    best_params: dict
    best_sharpe: float
    best_return: float
    all_results: List[dict]


def grid_search(strategy_class: type,
                param_grid: Dict[str, List[Any]],
                df: pd.DataFrame,
                metric: str = 'sharpe_ratio') -> OptimizationResult:
    """Grid search optimization for strategy parameters."""
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())

    results = []
    best_metric = -np.inf
    best_params = None

    for values in product(*param_values):
        params = dict(zip(param_names, values))

        try:
            strategy = strategy_class(**params)
            result = strategy.backtest(df)

            if metric == 'sharpe_ratio':
                score = result.sharpe_ratio
            elif metric == 'total_return':
                score = result.total_return
            elif metric == 'calmar':
                score = -result.total_return / result.max_drawdown if result.max_drawdown < 0 else 0
            else:
                score = result.sharpe_ratio

            results.append({
                'params': params,
                'sharpe': result.sharpe_ratio,
                'return': result.total_return,
                'max_dd': result.max_drawdown,
                'score': score
            })

            if score > best_metric:
                best_metric = score
                best_params = params

        except Exception:
            continue

    best_result = next((r for r in results if r['params'] == best_params), None)

    return OptimizationResult(
        best_params=best_params,
        best_sharpe=best_result['sharpe'] if best_result else 0,
        best_return=best_result['return'] if best_result else 0,
        all_results=results
    )


# =============================================================================
# VALIDATION
# =============================================================================

@dataclass
class SignificanceResult:
    p_value: float
    is_significant: bool
    confidence_level: float
    test_statistic: float
    interpretation: str


def test_sharpe_significance(returns: pd.Series,
                             benchmark_sharpe: float = 0.0,
                             alpha: float = 0.05) -> SignificanceResult:
    """Test if Sharpe ratio is significantly different from benchmark."""
    n = len(returns)
    mu = returns.mean()
    sigma = returns.std()

    sharpe = (mu / sigma) * np.sqrt(252) if sigma > 0 else 0
    se = np.sqrt((1 + 0.5 * sharpe**2) / n)
    z = (sharpe - benchmark_sharpe) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    is_sig = p_value < alpha

    return SignificanceResult(
        p_value=p_value,
        is_significant=is_sig,
        confidence_level=1 - alpha,
        test_statistic=z,
        interpretation=f"Sharpe={sharpe:.2f}, {'significant' if is_sig else 'not significant'} at {(1-alpha)*100:.0f}%"
    )


def monte_carlo_test(strategy_returns: pd.Series,
                     n_simulations: int = 1000) -> SignificanceResult:
    """Monte Carlo permutation test."""
    # Remove NaN values
    clean_returns = strategy_returns.dropna()
    if len(clean_returns) < 10:
        return SignificanceResult(1.0, False, 0.95, 0, "Insufficient data")

    actual_sharpe = (clean_returns.mean() / clean_returns.std()) * np.sqrt(252) if clean_returns.std() > 0 else 0

    random_sharpes = []
    for _ in range(n_simulations):
        shuffled = np.random.permutation(clean_returns.values)
        std = np.std(shuffled)
        if std > 0:
            random_sharpe = (np.mean(shuffled) / std) * np.sqrt(252)
            random_sharpes.append(random_sharpe)

    if len(random_sharpes) == 0:
        return SignificanceResult(1.0, False, 0.95, actual_sharpe, "Monte Carlo failed")

    p_value = np.mean([rs >= actual_sharpe for rs in random_sharpes])

    return SignificanceResult(
        p_value=p_value,
        is_significant=p_value < 0.05,
        confidence_level=0.95,
        test_statistic=actual_sharpe,
        interpretation=f"p={p_value:.3f}, beats {(1-p_value)*100:.1f}% of random"
    )


def bootstrap_ci(returns: pd.Series, n_bootstrap: int = 1000, confidence: float = 0.95) -> Dict:
    """Bootstrap confidence interval for Sharpe ratio."""
    sharpes = []
    n = len(returns)

    for _ in range(n_bootstrap):
        sample = np.random.choice(returns.values, size=n, replace=True)
        if np.std(sample) > 0:
            sharpe = (np.mean(sample) / np.std(sample)) * np.sqrt(252)
            sharpes.append(sharpe)

    alpha = 1 - confidence
    lower = np.percentile(sharpes, alpha/2 * 100)
    upper = np.percentile(sharpes, (1 - alpha/2) * 100)

    return {
        'point_estimate': np.median(sharpes),
        'lower_bound': lower,
        'upper_bound': upper,
        'confidence': confidence
    }


# =============================================================================
# MAIN WORKFLOW
# =============================================================================

def run_full_workflow(symbols: List[str] = None, days: int = 180, verbose: bool = True):
    """Run the complete strategy development workflow."""

    if symbols is None:
        symbols = ['QQQ', 'META', 'TSLA', 'NVDA', 'AAPL', 'MSFT']

    # Step 1: Load data
    if verbose:
        print("=" * 70)
        print("STEP 1: DATA ACQUISITION")
        print("=" * 70)

    stocks = load_universe(symbols, days=days)

    if verbose:
        for sym, df in stocks.items():
            ret = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
            print(f"  {sym}: {len(df)} bars, {ret:+.1f}% return")

    # Step 2: Regime detection
    if verbose:
        print("\n" + "=" * 70)
        print("STEP 2: REGIME DETECTION")
        print("=" * 70)

    regimes = regime_summary(stocks)

    if verbose:
        for sym, info in regimes.items():
            print(f"  {sym}: {info['trend']:20s} | {info['volatility']:10s} | {info['total_return']:+.1%}")

    # Step 3: Test strategies
    if verbose:
        print("\n" + "=" * 70)
        print("STEP 3: STRATEGY TESTING")
        print("=" * 70)

    rankings = test_all_strategies(stocks, min_sharpe=-10)

    if verbose:
        print_rankings(rankings, top_n=15)

    # Step 4: Optimize top performers
    if verbose:
        print("\n" + "=" * 70)
        print("STEP 4: OPTIMIZATION")
        print("=" * 70)

    # Find best SMA strategy and optimize
    sma_rankings = [r for r in rankings if 'SMA' in r.name]
    if sma_rankings:
        best_sma = sma_rankings[0]
        opt_result = grid_search(
            SMACrossover,
            {'fast': [3, 5, 7, 10, 15, 20], 'slow': [20, 30, 40, 50, 60, 80]},
            stocks[best_sma.symbol]
        )

        if verbose:
            print(f"  Optimizing SMA on {best_sma.symbol}")
            print(f"  Best params: {opt_result.best_params}")
            print(f"  Best Sharpe: {opt_result.best_sharpe:.2f}")
            print(f"  Best Return: {opt_result.best_return:.1%}")

    # Step 5: Statistical validation
    if verbose:
        print("\n" + "=" * 70)
        print("STEP 5: STATISTICAL VALIDATION")
        print("=" * 70)

    validation_results = {}
    for r in rankings[:5]:
        strategy_map = {
            'SMA_10_30': SMACrossover(10, 30),
            'SMA_20_50': SMACrossover(20, 50),
            'SMA_5_20': SMACrossover(5, 20),
            'Breakout_20': BreakoutStrategy(20),
            'Momentum_20': MomentumStrategy(20),
            'DualMom_60': DualMomentum(60),
        }

        if r.name in strategy_map:
            strategy = strategy_map[r.name]
            result = strategy.backtest(stocks[r.symbol])

            sig_test = test_sharpe_significance(result.returns)
            mc_test = monte_carlo_test(result.returns, n_simulations=500)
            ci = bootstrap_ci(result.returns)

            validation_results[f"{r.name}_{r.symbol}"] = {
                'sharpe_sig': sig_test,
                'monte_carlo': mc_test,
                'ci': ci
            }

            if verbose:
                sig_mark = "✓" if sig_test.is_significant else "✗"
                mc_mark = "✓" if mc_test.is_significant else "✗"
                print(f"  {r.name} on {r.symbol}:")
                print(f"    Sharpe test: p={sig_test.p_value:.3f} {sig_mark}")
                print(f"    Monte Carlo: p={mc_test.p_value:.3f} {mc_mark}")
                print(f"    95% CI: [{ci['lower_bound']:.2f}, {ci['upper_bound']:.2f}]")

    # Step 6: Summary
    if verbose:
        print("\n" + "=" * 70)
        print("STEP 6: RECOMMENDATIONS")
        print("=" * 70)

        significant_strategies = [
            r for r in rankings[:10]
            if f"{r.name}_{r.symbol}" in validation_results
            and validation_results[f"{r.name}_{r.symbol}"]['sharpe_sig'].is_significant
        ]

        if significant_strategies:
            print("  Statistically significant strategies:")
            for r in significant_strategies[:5]:
                print(f"    - {r.name} on {r.symbol}: Sharpe={r.sharpe_ratio:.2f}, Return={r.total_return:.1%}")
        else:
            print("  No strategies showed statistical significance at 95% level.")
            print("  Top performers (use with caution):")
            for r in rankings[:3]:
                print(f"    - {r.name} on {r.symbol}: Sharpe={r.sharpe_ratio:.2f}, Return={r.total_return:.1%}")

    return {
        'stocks': stocks,
        'regimes': regimes,
        'rankings': rankings,
        'validation': validation_results
    }


if __name__ == "__main__":
    results = run_full_workflow()
