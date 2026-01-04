# LLM Strategy Development Workflow

This document serves as a reference for Claude (or other LLM agents) when developing, testing, and monitoring trading strategies.

## Workflow Overview

1. **Data Acquisition** - Fetch recent market data
2. **Regime Detection** - Understand current market conditions
3. **Strategy Testing** - Backtest multiple strategy types
4. **Performance Comparison** - Rank strategies by metrics
5. **Optimization** - Fine-tune winning strategies
6. **Statistical Validation** - Ensure results aren't due to luck
7. **Deployment Recommendations** - Provide actionable output

---

## Step 1: Data Acquisition

### Code Snippet: Generate/Load Market Data

```python
# File: workflows/snippets/data_acquisition.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_realistic_data(symbol: str, days: int = 180,
                           initial_price: float = 100,
                           volatility: float = 0.25,
                           trend: float = 0.0) -> pd.DataFrame:
    """
    Generate realistic OHLCV data for backtesting.

    Args:
        symbol: Stock symbol (used for regime characteristics)
        days: Number of trading days
        initial_price: Starting price
        volatility: Annualized volatility
        trend: Annualized trend (e.g., 0.10 = 10% annual growth)

    Returns:
        DataFrame with OHLCV columns and datetime index
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days * 1.4))  # Account for weekends
    dates = pd.date_range(start=start_date, end=end_date, freq='B')[:days]

    n = len(dates)
    daily_trend = trend / 252
    daily_vol = volatility / np.sqrt(252)

    returns = np.random.normal(daily_trend, daily_vol, n)
    prices = initial_price * np.exp(np.cumsum(returns))

    # Generate OHLC from close prices
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


def load_universe(symbols: list[str], days: int = 180) -> dict[str, pd.DataFrame]:
    """Load data for a universe of symbols."""
    # Default characteristics by symbol type
    configs = {
        'QQQ': {'price': 400, 'vol': 0.22, 'trend': 0.08},
        'SPY': {'price': 480, 'vol': 0.18, 'trend': 0.10},
        'META': {'price': 350, 'vol': 0.35, 'trend': 0.15},
        'TSLA': {'price': 250, 'vol': 0.55, 'trend': 0.0},
        'NVDA': {'price': 500, 'vol': 0.45, 'trend': 0.20},
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
```

---

## Step 2: Regime Detection

### Code Snippet: Detect Market Regime

```python
# File: workflows/snippets/regime_detection.py
import pandas as pd
import numpy as np
from enum import Enum
from dataclasses import dataclass

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
    trend_strength: float  # 0-1
    vol_percentile: float  # 0-100


def detect_regime(df: pd.DataFrame, lookback: int = 20) -> RegimeState:
    """
    Detect current market regime from OHLCV data.

    Returns RegimeState with trend and volatility classification.
    """
    close = df['close']
    returns = close.pct_change()

    # Trend indicators
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean() if len(close) >= 200 else sma_50

    # Current values
    price = close.iloc[-1]
    s20, s50 = sma_20.iloc[-1], sma_50.iloc[-1]

    # Trend strength: distance from SMAs
    trend_score = 0
    if price > s20: trend_score += 1
    if price > s50: trend_score += 1
    if s20 > s50: trend_score += 1
    trend_strength = trend_score / 3

    # Classify trend
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

    # Volatility
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


def regime_summary(stocks: dict[str, pd.DataFrame]) -> dict:
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
```

---

## Step 3: Strategy Testing

### Code Snippet: Strategy Implementations

```python
# File: workflows/snippets/strategies.py
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

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


class Strategy(ABC):
    """Base strategy class."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals: 1=long, -1=short, 0=flat."""
        pass

    def backtest(self, df: pd.DataFrame, cost_bps: float = 10) -> BacktestResult:
        """Run backtest on OHLCV data."""
        signals = self.generate_signals(df)
        positions = signals.shift(1).fillna(0)  # Execute next bar

        returns = df['close'].pct_change()
        strategy_returns = positions * returns

        # Transaction costs
        trades = (positions.diff().abs() > 0).sum()
        costs = positions.diff().abs() * (cost_bps / 10000)
        strategy_returns = strategy_returns - costs

        # Metrics
        total_return = (1 + strategy_returns).prod() - 1
        sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() > 0 else 0

        # Drawdown
        cum_returns = (1 + strategy_returns).cumprod()
        rolling_max = cum_returns.expanding().max()
        drawdown = (cum_returns - rolling_max) / rolling_max
        max_dd = drawdown.min()

        # Win rate
        winning = (strategy_returns > 0).sum()
        losing = (strategy_returns < 0).sum()
        win_rate = winning / (winning + losing) if (winning + losing) > 0 else 0

        # Profit factor
        gross_profit = strategy_returns[strategy_returns > 0].sum()
        gross_loss = abs(strategy_returns[strategy_returns < 0].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return BacktestResult(
            returns=strategy_returns,
            positions=positions,
            trades=trades,
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor
        )


# === TREND FOLLOWING STRATEGIES ===

class SMACrossover(Strategy):
    """Simple moving average crossover."""

    def __init__(self, fast: int = 10, slow: int = 30):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_ma = df['close'].rolling(self.fast).mean()
        slow_ma = df['close'].rolling(self.slow).mean()
        return pd.Series(np.where(fast_ma > slow_ma, 1, -1), index=df.index)


class BreakoutStrategy(Strategy):
    """Donchian channel breakout."""

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
    """ADX-based trend following."""

    def __init__(self, adx_period: int = 14, adx_threshold: float = 25):
        self.period = adx_period
        self.threshold = adx_threshold

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        # Simplified ADX calculation
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

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.rolling(self.period).mean()

        signals = pd.Series(0, index=df.index)
        trending = adx > self.threshold
        signals[trending & (plus_di > minus_di)] = 1
        signals[trending & (plus_di < minus_di)] = -1

        return signals


# === MEAN REVERSION STRATEGIES ===

class RSIMeanReversion(Strategy):
    """RSI-based mean reversion."""

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(self.period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        signals = pd.Series(0, index=df.index)
        signals[rsi < self.oversold] = 1   # Buy oversold
        signals[rsi > self.overbought] = -1  # Sell overbought
        return signals.ffill().fillna(0)


class BollingerReversion(Strategy):
    """Bollinger Band mean reversion."""

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma = df['close'].rolling(self.period).mean()
        std = df['close'].rolling(self.period).std()
        upper = ma + self.num_std * std
        lower = ma - self.num_std * std

        signals = pd.Series(0, index=df.index)
        signals[df['close'] < lower] = 1   # Buy at lower band
        signals[df['close'] > upper] = -1  # Sell at upper band
        return signals.ffill().fillna(0)


# === MOMENTUM STRATEGIES ===

class MomentumStrategy(Strategy):
    """Price momentum strategy."""

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
    """Absolute + relative momentum."""

    def __init__(self, lookback: int = 60):
        self.lookback = lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        returns = df['close'].pct_change(self.lookback)

        # Absolute momentum: positive = long, negative = cash
        signals = pd.Series(0, index=df.index)
        signals[returns > 0] = 1
        signals[returns < 0] = 0  # Go to cash, not short
        return signals


# === VOLATILITY STRATEGIES ===

class VolatilityBreakout(Strategy):
    """Volatility expansion breakout."""

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
```

---

## Step 4: Performance Comparison

### Code Snippet: Compare Strategies

```python
# File: workflows/snippets/comparison.py
import pandas as pd
from typing import Dict, List
from dataclasses import dataclass

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
                        min_sharpe: float = 0.5) -> List[StrategyRanking]:
    """
    Test all strategy variants across all symbols.
    Returns sorted list of successful strategies.
    """
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

                if result.sharpe_ratio >= min_sharpe and result.total_return > 0:
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

    # Sort by Sharpe ratio
    return sorted(results, key=lambda x: x.sharpe_ratio, reverse=True)


def print_rankings(rankings: List[StrategyRanking], top_n: int = 20):
    """Print formatted rankings."""
    print(f"\n{'Rank':<5} {'Strategy':<15} {'Symbol':<6} {'Return':>10} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>7}")
    print("-" * 65)

    for i, r in enumerate(rankings[:top_n], 1):
        print(f"{i:<5} {r.name:<15} {r.symbol:<6} {r.total_return:>9.1%} {r.sharpe_ratio:>8.2f} {r.max_drawdown:>7.1%} {r.trades:>7}")
```

---

## Step 5: Optimization

### Code Snippet: Parameter Optimization

```python
# File: workflows/snippets/optimization.py
import numpy as np
from itertools import product
from typing import Callable, Dict, Any, List
from dataclasses import dataclass

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
    """
    Grid search optimization for strategy parameters.

    Args:
        strategy_class: Strategy class to optimize
        param_grid: Dict of param_name -> list of values
        df: OHLCV DataFrame
        metric: Metric to optimize ('sharpe_ratio', 'total_return', 'calmar')

    Returns:
        OptimizationResult with best parameters
    """
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

    return OptimizationResult(
        best_params=best_params,
        best_sharpe=best_metric if metric == 'sharpe_ratio' else
                    max(r['sharpe'] for r in results if r['params'] == best_params),
        best_return=max(r['return'] for r in results if r['params'] == best_params),
        all_results=results
    )


def walk_forward_optimize(strategy_class: type,
                          param_grid: Dict[str, List[Any]],
                          df: pd.DataFrame,
                          n_splits: int = 5,
                          train_ratio: float = 0.7) -> Dict:
    """
    Walk-forward optimization to avoid overfitting.

    Splits data into n_splits, optimizes on train portion,
    tests on remaining portion.
    """
    n = len(df)
    split_size = n // n_splits

    oos_returns = []

    for i in range(n_splits):
        start = i * split_size
        end = start + split_size

        train_end = start + int(split_size * train_ratio)

        train_df = df.iloc[start:train_end]
        test_df = df.iloc[train_end:end]

        if len(train_df) < 50 or len(test_df) < 10:
            continue

        # Optimize on train
        opt_result = grid_search(strategy_class, param_grid, train_df)

        # Test on OOS
        strategy = strategy_class(**opt_result.best_params)
        test_result = strategy.backtest(test_df)

        oos_returns.append({
            'fold': i,
            'params': opt_result.best_params,
            'is_sharpe': opt_result.best_sharpe,
            'oos_sharpe': test_result.sharpe_ratio,
            'oos_return': test_result.total_return
        })

    return {
        'folds': oos_returns,
        'avg_oos_sharpe': np.mean([r['oos_sharpe'] for r in oos_returns]),
        'avg_oos_return': np.mean([r['oos_return'] for r in oos_returns]),
        'consistency': sum(1 for r in oos_returns if r['oos_sharpe'] > 0) / len(oos_returns)
    }
```

---

## Step 6: Statistical Validation

### Code Snippet: Significance Testing

```python
# File: workflows/snippets/validation.py
import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import List

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
    """
    Test if Sharpe ratio is significantly different from benchmark.
    Uses Jobson-Korkie test statistic.
    """
    n = len(returns)
    mu = returns.mean()
    sigma = returns.std()

    sharpe = (mu / sigma) * np.sqrt(252) if sigma > 0 else 0

    # Standard error of Sharpe ratio
    se = np.sqrt((1 + 0.5 * sharpe**2) / n)

    # Test statistic
    z = (sharpe - benchmark_sharpe) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    is_sig = p_value < alpha

    return SignificanceResult(
        p_value=p_value,
        is_significant=is_sig,
        confidence_level=1 - alpha,
        test_statistic=z,
        interpretation=f"Sharpe={sharpe:.2f}, {'statistically significant' if is_sig else 'not significant'} at {(1-alpha)*100:.0f}% level"
    )


def monte_carlo_test(strategy_returns: pd.Series,
                     n_simulations: int = 1000) -> SignificanceResult:
    """
    Monte Carlo permutation test.
    Tests if returns are better than random.
    """
    actual_sharpe = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)

    # Generate random permutations
    random_sharpes = []
    for _ in range(n_simulations):
        shuffled = np.random.permutation(strategy_returns.values)
        if np.std(shuffled) > 0:
            random_sharpe = (np.mean(shuffled) / np.std(shuffled)) * np.sqrt(252)
            random_sharpes.append(random_sharpe)

    # P-value: proportion of random sharpes >= actual
    p_value = np.mean([rs >= actual_sharpe for rs in random_sharpes])

    return SignificanceResult(
        p_value=p_value,
        is_significant=p_value < 0.05,
        confidence_level=0.95,
        test_statistic=actual_sharpe,
        interpretation=f"p={p_value:.3f}, strategy beats {(1-p_value)*100:.1f}% of random"
    )


def bootstrap_confidence_interval(returns: pd.Series,
                                  n_bootstrap: int = 1000,
                                  confidence: float = 0.95) -> Dict:
    """
    Bootstrap confidence interval for Sharpe ratio.
    """
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
        'confidence': confidence,
        'interpretation': f"95% CI: [{lower:.2f}, {upper:.2f}]"
    }
```

---

## Step 7: Summary Report

### Code Snippet: Generate Report

```python
# File: workflows/snippets/reporting.py

def generate_strategy_report(rankings: List[StrategyRanking],
                            validation_results: Dict,
                            regime_info: Dict) -> str:
    """Generate markdown summary report."""

    report = []
    report.append("# Strategy Development Report\n")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Market Regime
    report.append("## Market Regime\n")
    for symbol, info in regime_info.items():
        report.append(f"- **{symbol}**: {info['trend']} | Vol: {info['volatility']} | Return: {info['total_return']:.1%}\n")

    # Top Strategies
    report.append("\n## Top Performing Strategies\n")
    report.append("| Rank | Strategy | Symbol | Return | Sharpe | MaxDD |\n")
    report.append("|------|----------|--------|--------|--------|-------|\n")

    for i, r in enumerate(rankings[:10], 1):
        report.append(f"| {i} | {r.name} | {r.symbol} | {r.total_return:.1%} | {r.sharpe_ratio:.2f} | {r.max_drawdown:.1%} |\n")

    # Validation
    report.append("\n## Statistical Validation\n")
    for name, result in validation_results.items():
        sig = "✓" if result.is_significant else "✗"
        report.append(f"- **{name}**: p={result.p_value:.3f} {sig}\n")

    # Recommendations
    report.append("\n## Recommendations\n")
    significant = [r for r in rankings if r.name in validation_results
                   and validation_results[r.name].is_significant]

    if significant:
        report.append("The following strategies showed statistically significant performance:\n")
        for r in significant[:5]:
            report.append(f"- {r.name} on {r.symbol}: Sharpe={r.sharpe_ratio:.2f}\n")
    else:
        report.append("No strategies showed statistically significant outperformance.\n")

    return "".join(report)
```

---

## Quick Reference

### Common Workflow Commands

```python
# 1. Load data
stocks = load_universe(['QQQ', 'META', 'TSLA', 'NVDA', 'AAPL'], days=180)

# 2. Check regime
regime = regime_summary(stocks)

# 3. Test strategies
rankings = test_all_strategies(stocks, min_sharpe=0.5)
print_rankings(rankings)

# 4. Optimize best performer
best = rankings[0]
opt = grid_search(
    SMACrossover,
    {'fast': [5, 10, 15, 20], 'slow': [20, 30, 40, 50, 60]},
    stocks[best.symbol]
)

# 5. Validate
sig = test_sharpe_significance(result.returns)
mc = monte_carlo_test(result.returns)
ci = bootstrap_confidence_interval(result.returns)

# 6. Report
print(generate_strategy_report(rankings, {'best': sig}, regime))
```

### Strategy Selection by Regime

| Regime | Recommended Strategies |
|--------|----------------------|
| Strong Uptrend | Momentum, Breakout, SMA Crossover |
| Sideways | Mean Reversion (RSI, Bollinger) |
| Downtrend | Inverse strategies, Cash |
| High Volatility | Volatility Breakout, Wider stops |
| Low Volatility | Mean Reversion, Tighter bands |

---

## Notes for Future Sessions

1. Always start by detecting the current market regime
2. Match strategy type to regime conditions
3. Use walk-forward optimization to avoid overfitting
4. Require statistical significance before recommending
5. Consider transaction costs (default 10 bps)
6. Maximum drawdown is as important as returns
