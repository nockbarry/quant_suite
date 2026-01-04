"""
Universe Analysis & Strategy Classification Pipeline

Analyzes 100+ assets to determine:
1. Which asset categories work best with each strategy
2. Performance vs benchmarks (SPY, SPXL, random)
3. Robustness across different time periods
4. Asset classification by market cap, volume, sector, fundamentals
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Literal
import json
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Import execution model for realistic costs
from workflows.research.execution_model import ExecutionConfig, ExecutionSimulator


# =============================================================================
# LARGE UNIVERSE DEFINITION
# =============================================================================

STOCK_UNIVERSE = {
    # Mega Cap Tech (>500B)
    'mega_cap_tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'],

    # Large Cap Tech (50B-500B)
    'large_cap_tech': ['AMD', 'AVGO', 'QCOM', 'ADBE', 'CRM', 'ORCL', 'INTC',
                       'NOW', 'INTU', 'AMAT', 'MU', 'LRCX', 'KLAC', 'SNPS', 'CDNS'],

    # Mid Cap Tech (10B-50B)
    'mid_cap_tech': ['CRWD', 'NET', 'PLTR', 'SNOW', 'DDOG', 'ZS', 'PANW',
                     'FTNT', 'MRVL', 'ON', 'NXPI', 'MPWR', 'SWKS', 'QRVO'],

    # Financials
    'financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW',
                   'AXP', 'COF', 'USB', 'PNC', 'TFC', 'SPGI', 'ICE'],

    # Healthcare
    'healthcare': ['UNH', 'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT',
                   'DHR', 'BMY', 'AMGN', 'GILD', 'VRTX', 'REGN', 'ISRG'],

    # Consumer Discretionary
    'consumer_disc': ['HD', 'LOW', 'NKE', 'SBUX', 'TGT', 'COST', 'MCD',
                      'TJX', 'BKNG', 'MAR', 'CMG', 'ROST', 'DG', 'DLTR', 'YUM'],

    # Consumer Staples
    'consumer_staples': ['PG', 'KO', 'PEP', 'WMT', 'MDLZ', 'CL', 'KMB',
                         'GIS', 'K', 'HSY', 'KHC', 'SJM', 'CAG', 'CPB', 'MKC'],

    # Industrials
    'industrials': ['CAT', 'DE', 'UNP', 'UPS', 'RTX', 'HON', 'GE', 'LMT',
                    'BA', 'MMM', 'EMR', 'ETN', 'ITW', 'PH', 'ROK'],

    # Energy
    'energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO',
               'OXY', 'PXD', 'DVN', 'HES', 'HAL', 'BKR', 'FANG'],

    # Materials
    'materials': ['LIN', 'APD', 'ECL', 'SHW', 'DD', 'NEM', 'FCX', 'NUE',
                  'DOW', 'VMC', 'MLM', 'ALB', 'CTVA', 'PPG', 'EMN'],

    # REITs
    'reits': ['PLD', 'AMT', 'EQIX', 'CCI', 'PSA', 'SPG', 'O', 'WELL',
              'DLR', 'AVB', 'EQR', 'VTR', 'ARE', 'MAA', 'UDR'],

    # Utilities
    'utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'XEL', 'ED',
                  'EXC', 'WEC', 'ES', 'AWK', 'DTE', 'ETR', 'FE'],

    # ETFs & Benchmarks
    'etfs': ['SPY', 'QQQ', 'IWM', 'DIA', 'SPXL', 'TQQQ', 'SOXL',
             'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU', 'XLB', 'XLRE'],
}


@dataclass
class AssetProfile:
    """Profile of an asset's characteristics."""
    symbol: str
    sector: str
    market_cap: float  # in billions
    market_cap_category: str  # mega, large, mid, small
    avg_volume: float  # in millions
    volume_category: str  # high, medium, low
    volatility: float  # annualized
    volatility_category: str  # high, medium, low
    beta: float
    pe_ratio: float | None
    dividend_yield: float
    price: float

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'sector': self.sector,
            'market_cap': self.market_cap,
            'market_cap_category': self.market_cap_category,
            'avg_volume': self.avg_volume,
            'volume_category': self.volume_category,
            'volatility': self.volatility,
            'volatility_category': self.volatility_category,
            'beta': self.beta,
            'pe_ratio': self.pe_ratio,
            'dividend_yield': self.dividend_yield,
            'price': self.price,
        }


@dataclass
class StrategyResult:
    """Result of strategy backtest."""
    symbol: str
    strategy: str
    total_return: float
    sharpe: float
    max_dd: float
    win_rate: float
    n_trades: int
    vs_spy: float  # Alpha vs SPY
    vs_spxl: float  # vs 3x SPY
    vs_random: float  # vs random baseline


# =============================================================================
# DATA FETCHING
# =============================================================================

class UniverseFetcher:
    """Fetches data for large stock universe."""

    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path.home() / ".quant_cache" / "universe"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_single(self, symbol: str, start: datetime, end: datetime) -> tuple[str, pd.DataFrame | None]:
        """Fetch single symbol with error handling."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end)
            if len(df) < 100:
                return symbol, None
            df.columns = df.columns.str.lower()
            return symbol, df
        except:
            return symbol, None

    def fetch_universe(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        max_workers: int = 10,
    ) -> dict[str, pd.DataFrame]:
        """Fetch all symbols in parallel."""
        data = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.fetch_single, s, start, end): s
                for s in symbols
            }

            for future in as_completed(futures):
                symbol, df = future.result()
                if df is not None:
                    data[symbol] = df

        return data

    def get_asset_info(self, symbol: str) -> dict:
        """Get fundamental info for an asset."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                'market_cap': info.get('marketCap', 0) / 1e9,  # billions
                'pe_ratio': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'dividend_yield': info.get('dividendYield', 0) or 0,
                'beta': info.get('beta', 1.0) or 1.0,
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'avg_volume': info.get('averageVolume', 0) / 1e6,  # millions
                'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            }
        except:
            return {}


# =============================================================================
# ASSET CLASSIFICATION
# =============================================================================

class AssetClassifier:
    """Classifies assets by various characteristics."""

    def __init__(self):
        self.profiles: dict[str, AssetProfile] = {}

    def classify_market_cap(self, cap: float) -> str:
        """Classify by market cap (billions)."""
        if cap >= 200:
            return 'mega'
        elif cap >= 50:
            return 'large'
        elif cap >= 10:
            return 'mid'
        else:
            return 'small'

    def classify_volume(self, vol: float) -> str:
        """Classify by average volume (millions)."""
        if vol >= 20:
            return 'high'
        elif vol >= 5:
            return 'medium'
        else:
            return 'low'

    def classify_volatility(self, vol: float) -> str:
        """Classify by annualized volatility."""
        if vol >= 0.5:
            return 'high'
        elif vol >= 0.25:
            return 'medium'
        else:
            return 'low'

    def create_profile(
        self,
        symbol: str,
        sector: str,
        price_data: pd.DataFrame,
        fundamentals: dict,
    ) -> AssetProfile:
        """Create comprehensive asset profile."""
        # Calculate volatility from price data
        returns = price_data['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)

        market_cap = fundamentals.get('market_cap', 0)
        avg_volume = fundamentals.get('avg_volume', 0)

        profile = AssetProfile(
            symbol=symbol,
            sector=sector,
            market_cap=market_cap,
            market_cap_category=self.classify_market_cap(market_cap),
            avg_volume=avg_volume,
            volume_category=self.classify_volume(avg_volume),
            volatility=volatility,
            volatility_category=self.classify_volatility(volatility),
            beta=fundamentals.get('beta', 1.0),
            pe_ratio=fundamentals.get('pe_ratio'),
            dividend_yield=fundamentals.get('dividend_yield', 0),
            price=fundamentals.get('price', price_data['close'].iloc[-1]),
        )

        self.profiles[symbol] = profile
        return profile

    def get_symbols_by_category(
        self,
        category: str,
        value: str,
    ) -> list[str]:
        """Get symbols matching a category value."""
        symbols = []
        for symbol, profile in self.profiles.items():
            if category == 'market_cap' and profile.market_cap_category == value:
                symbols.append(symbol)
            elif category == 'volume' and profile.volume_category == value:
                symbols.append(symbol)
            elif category == 'volatility' and profile.volatility_category == value:
                symbols.append(symbol)
            elif category == 'sector' and profile.sector == value:
                symbols.append(symbol)
        return symbols


# =============================================================================
# STRATEGIES
# =============================================================================

class StrategyEngine:
    """Implements and tests multiple strategies."""

    STRATEGIES = {
        'momentum_20d': {
            'description': 'Buy when 20-day return > 0, sell when < 0',
            'type': 'momentum',
            'horizon': 20,
        },
        'momentum_60d': {
            'description': 'Buy when 60-day return > 0, sell when < 0',
            'type': 'momentum',
            'horizon': 60,
        },
        'mean_reversion_rsi': {
            'description': 'Buy when RSI < 30, sell when RSI > 70',
            'type': 'mean_reversion',
            'params': {'period': 14, 'oversold': 30, 'overbought': 70},
        },
        'mean_reversion_bb': {
            'description': 'Buy at lower Bollinger Band, sell at upper',
            'type': 'mean_reversion',
            'params': {'period': 20, 'num_std': 2.0},
        },
        'trend_sma_cross': {
            'description': 'Buy when 20 SMA > 50 SMA, sell when <',
            'type': 'trend',
            'params': {'fast': 20, 'slow': 50},
        },
        'trend_breakout': {
            'description': 'Buy on 20-day high breakout, sell on low',
            'type': 'trend',
            'params': {'lookback': 20},
        },
        'volatility_regime': {
            'description': 'Trade based on volatility regime changes',
            'type': 'volatility',
            'params': {'lookback': 20},
        },
        'ml_xgboost': {
            'description': 'XGBoost with technical features',
            'type': 'ml',
            'model': 'xgboost',
        },
        'ml_random_forest': {
            'description': 'Random Forest with cross-asset features',
            'type': 'ml',
            'model': 'rf',
        },
        'ml_ensemble': {
            'description': 'Ensemble of RF + GBM + LogReg',
            'type': 'ml',
            'model': 'ensemble',
        },
    }

    def __init__(self):
        self.scaler = StandardScaler()

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create features for ML strategies.

        IMPORTANT: All features are shifted by 1 day to ensure we only use
        data available at the time of signal generation.

        At market open on day t, we only have yesterday's (t-1) close.
        So features at index t should use data up to close[t-1].
        """
        features = pd.DataFrame(index=df.index)

        # Returns - shifted by 1 to use yesterday's values
        for p in [5, 10, 20, 60]:
            features[f'ret_{p}d'] = df['close'].pct_change(p).shift(1)

        # Volatility - shifted by 1
        daily_ret = df['close'].pct_change()
        for p in [5, 20, 60]:
            features[f'vol_{p}d'] = daily_ret.rolling(p).std().shift(1)

        # MA distances - shifted by 1
        for p in [10, 20, 50]:
            ma = df['close'].rolling(p).mean()
            features[f'ma_{p}_dist'] = ((df['close'] - ma) / ma).shift(1)

        # RSI - shifted by 1
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        features['rsi_14'] = (100 - (100 / (1 + gain / loss))).shift(1)

        # Bollinger position - shifted by 1
        ma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        features['bb_pos'] = ((df['close'] - ma20) / (2 * std20)).shift(1)

        # MACD - shifted by 1
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        features['macd'] = (ema12 - ema26).shift(1)

        return features.ffill().bfill()

    def run_strategy(
        self,
        strategy_name: str,
        df: pd.DataFrame,
        train_ratio: float = 0.7,
    ) -> dict:
        """Run a single strategy on price data."""
        strategy = self.STRATEGIES[strategy_name]

        df = df.copy()
        n = len(df)
        train_end = int(n * train_ratio)

        # Generate signals based on strategy type
        if strategy['type'] == 'momentum':
            horizon = strategy['horizon']
            momentum = df['close'].pct_change(horizon)
            positions = pd.Series(0, index=df.index)
            positions[momentum > 0] = 1
            positions[momentum < 0] = -1
            positions = positions.shift(1).fillna(0)

        elif strategy['type'] == 'mean_reversion':
            if 'rsi' in strategy_name:
                params = strategy['params']
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0).rolling(params['period']).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(params['period']).mean()
                rsi = 100 - (100 / (1 + gain / loss))

                positions = pd.Series(0, index=df.index)
                positions[rsi < params['oversold']] = 1
                positions[rsi > params['overbought']] = -1
                positions = positions.replace(0, np.nan).ffill().fillna(0)
                positions = positions.shift(1).fillna(0)

            elif 'bb' in strategy_name:
                params = strategy['params']
                ma = df['close'].rolling(params['period']).mean()
                std = df['close'].rolling(params['period']).std()
                upper = ma + params['num_std'] * std
                lower = ma - params['num_std'] * std

                positions = pd.Series(0, index=df.index)
                positions[df['close'] < lower] = 1
                positions[df['close'] > upper] = -1
                positions = positions.replace(0, np.nan).ffill().fillna(0)
                positions = positions.shift(1).fillna(0)

        elif strategy['type'] == 'trend':
            if 'sma_cross' in strategy_name:
                params = strategy['params']
                fast_ma = df['close'].rolling(params['fast']).mean()
                slow_ma = df['close'].rolling(params['slow']).mean()

                positions = pd.Series(0, index=df.index)
                positions[fast_ma > slow_ma] = 1
                positions[fast_ma < slow_ma] = -1
                positions = positions.shift(1).fillna(0)

            elif 'breakout' in strategy_name:
                params = strategy['params']
                high_channel = df['high'].rolling(params['lookback']).max()
                low_channel = df['low'].rolling(params['lookback']).min()

                positions = pd.Series(0, index=df.index)
                positions[df['close'] >= high_channel.shift(1)] = 1
                positions[df['close'] <= low_channel.shift(1)] = -1
                positions = positions.replace(0, np.nan).ffill().fillna(0)
                positions = positions.shift(1).fillna(0)

        elif strategy['type'] == 'volatility':
            params = strategy['params']
            vol = df['close'].pct_change().rolling(params['lookback']).std() * np.sqrt(252)
            vol_ma = vol.rolling(60).mean()

            # Low vol regime: momentum, High vol regime: mean reversion
            momentum = df['close'].pct_change(20)
            rsi = self._calc_rsi(df['close'], 14)

            positions = pd.Series(0, index=df.index)
            # Low vol: follow momentum
            low_vol = vol < vol_ma
            positions[low_vol & (momentum > 0)] = 1
            positions[low_vol & (momentum < 0)] = -1
            # High vol: mean revert
            high_vol = vol >= vol_ma
            positions[high_vol & (rsi < 30)] = 1
            positions[high_vol & (rsi > 70)] = -1
            positions = positions.shift(1).fillna(0)

        elif strategy['type'] == 'ml':
            # ML strategies need walk-forward
            features = self._create_features(df)

            # Target: 5-day forward return direction
            # This is computed correctly - at time t, we predict if close[t+5] > close[t]
            target = (df['close'].shift(-5) / df['close'] - 1 > 0).astype(int)

            valid_idx = features.dropna().index.intersection(target.dropna().index)
            features = features.loc[valid_idx]
            target = target.loc[valid_idx]

            positions = pd.Series(0.0, index=df.index)

            # Walk-forward with proper gap to prevent data leakage
            train_window = 252
            target_horizon = 5  # Must gap by at least this many days
            gap = target_horizon  # Gap between train end and test start

            for i in range(train_window, len(features) - gap - 21, 21):
                # Training ends at i-gap to ensure target at train end doesn't use test data
                train_end = i
                test_start = i + gap  # Start testing after gap

                X_train = features.iloc[max(0, train_end - train_window):train_end]
                y_train = target.iloc[max(0, train_end - train_window):train_end]
                X_test = features.iloc[test_start:min(test_start + 63, len(features) - 5)]

                if len(X_train) < 50 or len(X_test) == 0:
                    continue

                X_train_scaled = self.scaler.fit_transform(X_train)
                X_test_scaled = self.scaler.transform(X_test)

                if strategy['model'] == 'xgboost':
                    try:
                        from xgboost import XGBClassifier
                        model = XGBClassifier(n_estimators=50, max_depth=4, random_state=42, eval_metric='logloss')
                    except:
                        model = GradientBoostingClassifier(n_estimators=50, max_depth=4, random_state=42)
                elif strategy['model'] == 'rf':
                    model = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42)
                else:  # ensemble
                    model = GradientBoostingClassifier(n_estimators=50, max_depth=4, random_state=42)

                model.fit(X_train_scaled, y_train)
                probs = model.predict_proba(X_test_scaled)[:, 1]

                test_idx = features.index[test_start:test_start + len(probs)]
                positions.loc[test_idx] = (probs - 0.5) * 2

            positions = positions.shift(1).fillna(0)

        # Calculate returns with realistic execution model
        exec_config = ExecutionConfig(
            commission_bps=1.0,   # 1 bp commission
            slippage_bps=5.0,     # 5 bps slippage (conservative)
        )
        exec_sim = ExecutionSimulator(exec_config)

        # Use open prices for realistic execution timing
        # Signal at close[t] -> Execute at open[t+1]
        if 'open' in df.columns:
            price_ret = df['open'].pct_change()
        else:
            price_ret = df['close'].pct_change()

        # Gross returns (before costs)
        gross_ret = positions * price_ret

        # Net returns (after costs)
        strat_ret = exec_sim.compute_realistic_returns(df, positions, apply_costs=True)

        # Only evaluate on test period for fair comparison
        test_start = df.index[train_end]
        strat_ret_test = strat_ret.loc[test_start:]
        gross_ret_test = gross_ret.loc[test_start:]
        positions_test = positions.loc[test_start:]

        if len(strat_ret_test) < 20:
            return None

        # Metrics (using net returns after costs)
        total_ret = (1 + strat_ret_test.dropna()).prod() - 1
        total_ret_gross = (1 + gross_ret_test.dropna()).prod() - 1
        sharpe = strat_ret_test.mean() / strat_ret_test.std() * np.sqrt(252) if strat_ret_test.std() > 0 else 0

        cum = (1 + strat_ret_test.fillna(0)).cumprod()
        peak = cum.cummax()
        dd = (cum - peak) / peak
        max_dd = dd.min()

        win_rate = (strat_ret_test > 0).sum() / (strat_ret_test != 0).sum() if (strat_ret_test != 0).sum() > 0 else 0

        # Accurate trade counting
        trade_stats = exec_sim.count_trades(positions_test)
        n_trades = trade_stats['effective_trades']  # Includes reversals

        # Cost impact
        cost_drag = (total_ret_gross - total_ret) * 100  # Percentage points

        return {
            'total_return': total_ret * 100,
            'total_return_gross': total_ret_gross * 100,
            'cost_drag': cost_drag,
            'sharpe': sharpe,
            'max_dd': max_dd * 100,
            'win_rate': win_rate * 100,
            'n_trades': n_trades,
            'trade_stats': trade_stats,
            'positions': positions_test,
            'returns': strat_ret_test,
        }

    def _calc_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        return 100 - (100 / (1 + gain / loss))


# =============================================================================
# BENCHMARK COMPARISON
# =============================================================================

class BenchmarkComparator:
    """Compare strategies against benchmarks."""

    def __init__(self, spy_data: pd.DataFrame, spxl_data: pd.DataFrame = None):
        self.spy = spy_data
        self.spxl = spxl_data

    def get_spy_return(self, start_date, end_date) -> float:
        """Get SPY return for period."""
        spy_period = self.spy.loc[start_date:end_date]
        if len(spy_period) < 2:
            return 0
        return (spy_period['close'].iloc[-1] / spy_period['close'].iloc[0] - 1) * 100

    def get_spxl_return(self, start_date, end_date) -> float:
        """Get SPXL (3x SPY) return for period."""
        if self.spxl is None:
            return self.get_spy_return(start_date, end_date) * 3  # Approximate
        spxl_period = self.spxl.loc[start_date:end_date]
        if len(spxl_period) < 2:
            return 0
        return (spxl_period['close'].iloc[-1] / spxl_period['close'].iloc[0] - 1) * 100

    def get_random_baseline(self, df: pd.DataFrame, n_simulations: int = 100) -> float:
        """Calculate random buy/sell baseline."""
        daily_ret = df['close'].pct_change()
        random_returns = []

        for _ in range(n_simulations):
            # Random positions: -1, 0, or 1
            positions = pd.Series(
                np.random.choice([-1, 0, 1], size=len(df)),
                index=df.index
            )
            strat_ret = positions.shift(1) * daily_ret
            total_ret = (1 + strat_ret.dropna()).prod() - 1
            random_returns.append(total_ret * 100)

        return np.mean(random_returns)

    def compare(
        self,
        strategy_return: float,
        df: pd.DataFrame,
    ) -> dict:
        """Compare strategy to all benchmarks."""
        start_date = df.index[int(len(df) * 0.7)]  # Test period start
        end_date = df.index[-1]

        spy_ret = self.get_spy_return(start_date, end_date)
        spxl_ret = self.get_spxl_return(start_date, end_date)
        random_ret = self.get_random_baseline(df.loc[start_date:])

        return {
            'spy_return': spy_ret,
            'spxl_return': spxl_ret,
            'random_return': random_ret,
            'vs_spy': strategy_return - spy_ret,
            'vs_spxl': strategy_return - spxl_ret,
            'vs_random': strategy_return - random_ret,
        }


# =============================================================================
# TIME SPLIT TESTING
# =============================================================================

class TimeSplitTester:
    """Test strategies across different time periods."""

    def __init__(self):
        self.splits = [
            ('full', 0.0, 1.0),
            ('first_half', 0.0, 0.5),
            ('second_half', 0.5, 1.0),
            ('q1', 0.0, 0.25),
            ('q2', 0.25, 0.5),
            ('q3', 0.5, 0.75),
            ('q4', 0.75, 1.0),
        ]

    def test_splits(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        df: pd.DataFrame,
    ) -> dict[str, dict]:
        """Test strategy across all time splits."""
        results = {}
        n = len(df)

        for split_name, start_pct, end_pct in self.splits:
            start_idx = int(n * start_pct)
            end_idx = int(n * end_pct)

            if end_idx - start_idx < 200:  # Need minimum data
                continue

            split_df = df.iloc[start_idx:end_idx].copy()

            result = strategy_engine.run_strategy(strategy_name, split_df)
            if result:
                results[split_name] = {
                    'return': result['total_return'],
                    'sharpe': result['sharpe'],
                    'max_dd': result['max_dd'],
                }

        return results


# =============================================================================
# MAIN ANALYSIS PIPELINE
# =============================================================================

def run_universe_analysis(
    n_symbols: int = 100,
    years: int = 3,
) -> dict:
    """Run full universe analysis."""

    print("="*70)
    print("UNIVERSE ANALYSIS & STRATEGY CLASSIFICATION")
    print("="*70)

    # Flatten universe - ensure benchmarks are always included
    all_symbols = ['SPY', 'SPXL']  # Always include benchmarks first
    symbol_sectors = {'SPY': 'etfs', 'SPXL': 'etfs'}

    for sector, symbols in STOCK_UNIVERSE.items():
        for s in symbols:
            if s not in all_symbols:
                all_symbols.append(s)
                symbol_sectors[s] = sector

    all_symbols = all_symbols[:n_symbols]

    # Ensure SPY and SPXL are always present
    if 'SPY' not in all_symbols:
        all_symbols.append('SPY')
    if 'SPXL' not in all_symbols:
        all_symbols.append('SPXL')
    print(f"\nAnalyzing {len(all_symbols)} symbols...")

    # Fetch data
    print("\n[1/6] Fetching price data...")
    fetcher = UniverseFetcher()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    universe_data = fetcher.fetch_universe(all_symbols, start_date, end_date)
    print(f"  Loaded {len(universe_data)} symbols")

    # Get SPY and SPXL for benchmarks
    spy_data = universe_data.get('SPY')
    spxl_data = universe_data.get('SPXL')

    if spy_data is None:
        print("  ERROR: Could not load SPY data")
        return {}

    # Classify assets
    print("\n[2/6] Classifying assets...")
    classifier = AssetClassifier()

    for symbol, df in universe_data.items():
        if symbol in ['SPY', 'SPXL', 'TQQQ', 'SOXL']:
            continue

        fundamentals = fetcher.get_asset_info(symbol)
        sector = symbol_sectors.get(symbol, 'Unknown')

        try:
            classifier.create_profile(symbol, sector, df, fundamentals)
        except:
            pass

        time.sleep(0.1)  # Rate limiting

    print(f"  Classified {len(classifier.profiles)} assets")

    # Initialize engines
    strategy_engine = StrategyEngine()
    benchmark_comp = BenchmarkComparator(spy_data, spxl_data)
    time_tester = TimeSplitTester()

    # Run strategies
    print("\n[3/6] Running strategies...")
    all_results = []
    strategies_to_test = list(StrategyEngine.STRATEGIES.keys())

    tested = 0
    total = len(universe_data) * len(strategies_to_test)

    for symbol, df in universe_data.items():
        if symbol in ['SPY', 'SPXL', 'TQQQ', 'SOXL']:
            continue

        for strat_name in strategies_to_test:
            tested += 1
            if tested % 50 == 0:
                print(f"  Progress: {tested}/{total} ({100*tested/total:.0f}%)")

            try:
                result = strategy_engine.run_strategy(strat_name, df)
                if result is None:
                    continue

                # Compare to benchmarks
                bench = benchmark_comp.compare(result['total_return'], df)

                # Get asset profile
                profile = classifier.profiles.get(symbol)

                all_results.append({
                    'symbol': symbol,
                    'strategy': strat_name,
                    'total_return': result['total_return'],
                    'total_return_gross': result.get('total_return_gross', result['total_return']),
                    'cost_drag': result.get('cost_drag', 0.0),
                    'sharpe': result['sharpe'],
                    'max_dd': result['max_dd'],
                    'win_rate': result['win_rate'],
                    'n_trades': result['n_trades'],
                    'spy_return': bench['spy_return'],
                    'spxl_return': bench['spxl_return'],
                    'random_return': bench['random_return'],
                    'vs_spy': bench['vs_spy'],
                    'vs_spxl': bench['vs_spxl'],
                    'vs_random': bench['vs_random'],
                    'sector': profile.sector if profile else 'Unknown',
                    'market_cap_cat': profile.market_cap_category if profile else 'Unknown',
                    'volume_cat': profile.volume_category if profile else 'Unknown',
                    'volatility_cat': profile.volatility_category if profile else 'Unknown',
                })
            except Exception as e:
                continue

    results_df = pd.DataFrame(all_results)

    # Analyze by category
    print("\n[4/6] Analyzing by asset category...")
    category_analysis = analyze_by_category(results_df)

    # Time split analysis
    print("\n[5/6] Testing time stability...")
    time_stability = test_time_stability(strategy_engine, time_tester, universe_data)

    # Save results
    print("\n[6/6] Saving results...")
    output_dir = Path.home() / "quant_results" / "universe_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    results_df.to_csv(output_dir / "all_results.csv", index=False)

    # Save profiles
    profiles_data = [p.to_dict() for p in classifier.profiles.values()]
    with open(output_dir / "asset_profiles.json", 'w') as f:
        json.dump(profiles_data, f, indent=2)

    # Save category analysis
    with open(output_dir / "category_analysis.json", 'w') as f:
        json.dump(category_analysis, f, indent=2, default=str)

    # Print summary
    print_summary(results_df, category_analysis)

    return {
        'results': results_df,
        'profiles': classifier.profiles,
        'category_analysis': category_analysis,
        'time_stability': time_stability,
    }


def analyze_by_category(results_df: pd.DataFrame) -> dict:
    """Analyze which categories work best for each strategy."""
    analysis = {}

    for strategy in results_df['strategy'].unique():
        strat_results = results_df[results_df['strategy'] == strategy]

        analysis[strategy] = {
            'overall': {
                'avg_return': strat_results['total_return'].mean(),
                'avg_sharpe': strat_results['sharpe'].mean(),
                'avg_vs_spy': strat_results['vs_spy'].mean(),
                'pct_beat_spy': (strat_results['vs_spy'] > 0).mean() * 100,
                'pct_beat_random': (strat_results['vs_random'] > 0).mean() * 100,
            },
            'by_market_cap': {},
            'by_volume': {},
            'by_volatility': {},
            'by_sector': {},
        }

        # By market cap
        for cat in ['mega', 'large', 'mid', 'small']:
            cat_results = strat_results[strat_results['market_cap_cat'] == cat]
            if len(cat_results) > 0:
                analysis[strategy]['by_market_cap'][cat] = {
                    'n': len(cat_results),
                    'avg_return': cat_results['total_return'].mean(),
                    'avg_sharpe': cat_results['sharpe'].mean(),
                    'pct_beat_spy': (cat_results['vs_spy'] > 0).mean() * 100,
                }

        # By volume
        for cat in ['high', 'medium', 'low']:
            cat_results = strat_results[strat_results['volume_cat'] == cat]
            if len(cat_results) > 0:
                analysis[strategy]['by_volume'][cat] = {
                    'n': len(cat_results),
                    'avg_return': cat_results['total_return'].mean(),
                    'avg_sharpe': cat_results['sharpe'].mean(),
                    'pct_beat_spy': (cat_results['vs_spy'] > 0).mean() * 100,
                }

        # By volatility
        for cat in ['high', 'medium', 'low']:
            cat_results = strat_results[strat_results['volatility_cat'] == cat]
            if len(cat_results) > 0:
                analysis[strategy]['by_volatility'][cat] = {
                    'n': len(cat_results),
                    'avg_return': cat_results['total_return'].mean(),
                    'avg_sharpe': cat_results['sharpe'].mean(),
                    'pct_beat_spy': (cat_results['vs_spy'] > 0).mean() * 100,
                }

        # By sector (top sectors)
        sector_stats = strat_results.groupby('sector').agg({
            'total_return': 'mean',
            'sharpe': 'mean',
            'vs_spy': lambda x: (x > 0).mean() * 100,
        }).reset_index()
        sector_stats.columns = ['sector', 'avg_return', 'avg_sharpe', 'pct_beat_spy']
        sector_stats = sector_stats.sort_values('avg_sharpe', ascending=False)

        for _, row in sector_stats.head(5).iterrows():
            analysis[strategy]['by_sector'][row['sector']] = {
                'avg_return': row['avg_return'],
                'avg_sharpe': row['avg_sharpe'],
                'pct_beat_spy': row['pct_beat_spy'],
            }

    return analysis


def test_time_stability(
    strategy_engine: StrategyEngine,
    time_tester: TimeSplitTester,
    universe_data: dict,
) -> dict:
    """Test strategy stability across time periods."""
    stability = {}

    # Test on a subset of symbols
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'JPM', 'XOM', 'UNH']

    for strat_name in ['momentum_20d', 'mean_reversion_rsi', 'ml_xgboost']:
        stability[strat_name] = {}

        for symbol in test_symbols:
            if symbol not in universe_data:
                continue

            splits = time_tester.test_splits(
                strategy_engine,
                strat_name,
                universe_data[symbol]
            )

            if splits:
                stability[strat_name][symbol] = splits

    return stability


def print_summary(results_df: pd.DataFrame, category_analysis: dict):
    """Print comprehensive summary."""
    print("\n" + "="*70)
    print("ANALYSIS SUMMARY")
    print("="*70)

    # Overall stats
    print(f"\nTotal tests: {len(results_df)}")
    print(f"Symbols tested: {results_df['symbol'].nunique()}")
    print(f"Strategies tested: {results_df['strategy'].nunique()}")

    # Best performing strategies overall
    print("\n" + "-"*50)
    print("BEST STRATEGIES (by avg Sharpe)")
    print("-"*50)

    strat_summary = results_df.groupby('strategy').agg({
        'sharpe': 'mean',
        'total_return': 'mean',
        'vs_spy': 'mean',
        'vs_random': lambda x: (x > 0).mean() * 100,
    }).sort_values('sharpe', ascending=False)

    print(f"\n{'Strategy':<25} {'Sharpe':>8} {'Return':>10} {'vs SPY':>10} {'Beat Rnd%':>10}")
    print("-" * 65)
    for strat, row in strat_summary.iterrows():
        print(f"{strat:<25} {row['sharpe']:>8.2f} {row['total_return']:>+9.1f}% {row['vs_spy']:>+9.1f}% {row['vs_random']:>9.0f}%")

    # Best category combinations
    print("\n" + "-"*50)
    print("BEST CATEGORY COMBINATIONS")
    print("-"*50)

    best_combos = []
    for strat, analysis in category_analysis.items():
        for cap, stats in analysis['by_market_cap'].items():
            if stats['n'] >= 3:
                best_combos.append({
                    'strategy': strat,
                    'category': f'market_cap={cap}',
                    'sharpe': stats['avg_sharpe'],
                    'beat_spy': stats['pct_beat_spy'],
                })
        for vol, stats in analysis['by_volatility'].items():
            if stats['n'] >= 3:
                best_combos.append({
                    'strategy': strat,
                    'category': f'volatility={vol}',
                    'sharpe': stats['avg_sharpe'],
                    'beat_spy': stats['pct_beat_spy'],
                })

    best_combos = sorted(best_combos, key=lambda x: x['sharpe'], reverse=True)[:15]

    print(f"\n{'Strategy':<25} {'Category':<20} {'Sharpe':>8} {'Beat SPY%':>10}")
    print("-" * 65)
    for combo in best_combos:
        print(f"{combo['strategy']:<25} {combo['category']:<20} {combo['sharpe']:>8.2f} {combo['beat_spy']:>9.0f}%")

    # Top individual results
    print("\n" + "-"*50)
    print("TOP 20 INDIVIDUAL RESULTS")
    print("-"*50)

    top_results = results_df.nlargest(20, 'sharpe')

    print(f"\n{'Symbol':<8} {'Strategy':<25} {'Sharpe':>8} {'Return':>10} {'vs SPY':>10}")
    print("-" * 65)
    for _, row in top_results.iterrows():
        print(f"{row['symbol']:<8} {row['strategy']:<25} {row['sharpe']:>8.2f} {row['total_return']:>+9.1f}% {row['vs_spy']:>+9.1f}%")


if __name__ == "__main__":
    results = run_universe_analysis(n_symbols=100, years=3)
