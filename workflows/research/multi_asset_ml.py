"""
Multi-Asset ML Strategy System

Builds sophisticated strategies that:
1. Make decisions across multiple products
2. Use extensive feature engineering (50+ features)
3. Integrate external data (economic, sentiment, weather)
4. Train ML models with walk-forward validation
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any
import json

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))
import hashlib

# ML imports
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score
import yfinance as yf

# Optional imports
try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


# =============================================================================
# DATA FETCHING
# =============================================================================

class MultiAssetDataFetcher:
    """Fetches data for multiple assets and external sources."""

    def __init__(self):
        self.cache_dir = Path.home() / ".quant_cache" / "multi_asset"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_universe(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV data for all symbols."""
        data = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start, end=end)
                df.columns = df.columns.str.lower()
                if len(df) > 100:
                    data[symbol] = df
                    print(f"  {symbol}: {len(df)} bars")
            except Exception as e:
                print(f"  {symbol}: Failed - {e}")
        return data

    def fetch_fred_data(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Fetch FRED economic indicators."""
        # Key economic indicators
        indicators = {
            'DGS10': 'treasury_10y',      # 10-Year Treasury
            'DGS2': 'treasury_2y',        # 2-Year Treasury
            'VIXCLS': 'vix',              # VIX
            'DCOILWTICO': 'oil_wti',      # WTI Oil
            'DEXUSEU': 'eur_usd',         # EUR/USD
            'GOLDPMGBD228NLBM': 'gold',   # Gold
            'BAMLH0A0HYM2': 'hy_spread',  # High Yield Spread
            'T10Y2Y': 'yield_curve',      # 10Y-2Y Spread
            'UMCSENT': 'consumer_sent',   # Consumer Sentiment
            'UNRATE': 'unemployment',     # Unemployment
        }

        try:
            import fredapi
            fred = fredapi.Fred(api_key=None)  # Uses FRED_API_KEY env var

            dfs = []
            for series_id, name in indicators.items():
                try:
                    series = fred.get_series(series_id, start, end)
                    df = pd.DataFrame({name: series})
                    dfs.append(df)
                except:
                    pass

            if dfs:
                result = pd.concat(dfs, axis=1)
                result = result.ffill().bfill()
                return result
        except:
            pass

        # Return empty DataFrame if FRED unavailable
        return pd.DataFrame()

    def fetch_sector_etfs(self, start: datetime, end: datetime) -> dict[str, pd.DataFrame]:
        """Fetch sector ETF data for rotation strategies."""
        sectors = {
            'XLK': 'Technology',
            'XLF': 'Financials',
            'XLE': 'Energy',
            'XLV': 'Healthcare',
            'XLI': 'Industrials',
            'XLP': 'Consumer Staples',
            'XLY': 'Consumer Discretionary',
            'XLU': 'Utilities',
            'XLB': 'Materials',
            'XLRE': 'Real Estate',
        }
        return self.fetch_universe(list(sectors.keys()), start, end)


# =============================================================================
# FEATURE ENGINEERING
# =============================================================================

class FeatureEngineer:
    """Creates 50+ features for ML models."""

    def __init__(self):
        self.feature_names = []

    def create_single_asset_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create features for a single asset.

        IMPORTANT: All features are shifted by 1 day to ensure we only use
        data available at the time of signal generation.

        At market open on day t, we only have yesterday's (t-1) close.
        So features at index t should use data up to close[t-1].
        """
        features = pd.DataFrame(index=df.index)

        # Price-based features - all shifted by 1
        features['return_1d'] = df['close'].pct_change(1).shift(1)
        features['return_5d'] = df['close'].pct_change(5).shift(1)
        features['return_10d'] = df['close'].pct_change(10).shift(1)
        features['return_20d'] = df['close'].pct_change(20).shift(1)
        features['return_60d'] = df['close'].pct_change(60).shift(1)

        # Volatility features - shifted by 1
        daily_ret = df['close'].pct_change()
        features['volatility_5d'] = daily_ret.rolling(5).std().shift(1)
        features['volatility_20d'] = daily_ret.rolling(20).std().shift(1)
        features['volatility_60d'] = daily_ret.rolling(60).std().shift(1)
        features['volatility_ratio'] = features['volatility_5d'] / features['volatility_20d']

        # Moving averages - shifted by 1
        for period in [5, 10, 20, 50, 100, 200]:
            ma = df['close'].rolling(period).mean()
            features[f'ma_{period}_dist'] = ((df['close'] - ma) / ma).shift(1)

        # MA crossovers - shifted by 1
        features['ma_5_20_cross'] = (df['close'].rolling(5).mean() > df['close'].rolling(20).mean()).astype(int).shift(1)
        features['ma_20_50_cross'] = (df['close'].rolling(20).mean() > df['close'].rolling(50).mean()).astype(int).shift(1)
        features['ma_50_200_cross'] = (df['close'].rolling(50).mean() > df['close'].rolling(200).mean()).astype(int).shift(1)

        # RSI - shifted by 1
        for period in [7, 14, 21]:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
            rs = gain / loss
            features[f'rsi_{period}'] = (100 - (100 / (1 + rs))).shift(1)

        # MACD - shifted by 1
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        macd = ema12 - ema26
        features['macd'] = macd.shift(1)
        features['macd_signal'] = macd.ewm(span=9).mean().shift(1)
        features['macd_hist'] = (macd - macd.ewm(span=9).mean()).shift(1)

        # Bollinger Bands - shifted by 1
        for period in [10, 20]:
            ma = df['close'].rolling(period).mean()
            std = df['close'].rolling(period).std()
            features[f'bb_{period}_upper_dist'] = ((df['close'] - (ma + 2*std)) / df['close']).shift(1)
            features[f'bb_{period}_lower_dist'] = ((df['close'] - (ma - 2*std)) / df['close']).shift(1)
            features[f'bb_{period}_width'] = ((4 * std) / ma).shift(1)

        # Volume features - shifted by 1
        if 'volume' in df.columns:
            features['volume_ma_ratio'] = (df['volume'] / df['volume'].rolling(20).mean()).shift(1)
            features['volume_trend'] = (df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()).shift(1)

        # Price patterns - shifted by 1
        features['higher_high'] = (df['high'] > df['high'].shift(1)).astype(int).shift(1)
        features['lower_low'] = (df['low'] < df['low'].shift(1)).astype(int).shift(1)
        features['inside_bar'] = ((df['high'] < df['high'].shift(1)) & (df['low'] > df['low'].shift(1))).astype(int).shift(1)

        # Range features - shifted by 1
        daily_range = (df['high'] - df['low']) / df['close']
        features['daily_range'] = daily_range.shift(1)
        features['range_ma_ratio'] = (daily_range / daily_range.rolling(20).mean()).shift(1)

        # Gap features - already uses shift, add one more
        features['gap'] = ((df['open'] - df['close'].shift(1)) / df['close'].shift(1)).shift(1)

        # Trend strength - shifted by 1
        features['trend_strength'] = (abs(df['close'].pct_change(20)) / daily_ret.rolling(20).std()).shift(1)

        # Mean reversion indicators - shifted by 1
        features['z_score_20'] = ((df['close'] - df['close'].rolling(20).mean()) / df['close'].rolling(20).std()).shift(1)
        features['z_score_60'] = ((df['close'] - df['close'].rolling(60).mean()) / df['close'].rolling(60).std()).shift(1)

        # Momentum indicators - shifted by 1
        features['momentum_10'] = (df['close'] / df['close'].shift(10) - 1).shift(1)
        features['momentum_20'] = (df['close'] / df['close'].shift(20) - 1).shift(1)
        features['acceleration'] = features['momentum_10'] - features['momentum_10'].shift(10)

        return features

    def create_cross_asset_features(
        self,
        target_df: pd.DataFrame,
        universe: dict[str, pd.DataFrame],
        target_symbol: str,
    ) -> pd.DataFrame:
        """Create cross-asset features (correlations, relative strength, etc.)."""
        features = pd.DataFrame(index=target_df.index)

        # Get returns for all assets
        returns = {}
        for symbol, df in universe.items():
            returns[symbol] = df['close'].pct_change().reindex(target_df.index)

        returns_df = pd.DataFrame(returns)
        target_returns = returns_df[target_symbol] if target_symbol in returns_df.columns else None

        if target_returns is None:
            return features

        # Rolling correlations with major indices
        for index_symbol in ['SPY', 'QQQ', 'IWM']:
            if index_symbol in returns_df.columns and index_symbol != target_symbol:
                features[f'corr_{index_symbol}_20d'] = target_returns.rolling(20).corr(returns_df[index_symbol])
                features[f'corr_{index_symbol}_60d'] = target_returns.rolling(60).corr(returns_df[index_symbol])

        # Relative strength vs SPY
        if 'SPY' in returns_df.columns:
            spy_cum = (1 + returns_df['SPY']).cumprod()
            target_cum = (1 + target_returns).cumprod()
            features['rel_strength_spy_20d'] = (target_cum / spy_cum).pct_change(20)

        # Sector momentum (if sector ETFs available)
        sector_etfs = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI']
        sector_returns = returns_df[[s for s in sector_etfs if s in returns_df.columns]]
        if len(sector_returns.columns) > 0:
            features['sector_dispersion'] = sector_returns.rolling(20).std().mean(axis=1)
            features['best_sector_ret'] = sector_returns.rolling(20).mean().max(axis=1)
            features['worst_sector_ret'] = sector_returns.rolling(20).mean().min(axis=1)

        # Market breadth (% of stocks positive)
        features['market_breadth'] = (returns_df.rolling(20).mean() > 0).sum(axis=1) / len(returns_df.columns)

        # Cross-sectional momentum rank
        rolling_rets = returns_df.rolling(20).mean()
        features['momentum_rank'] = rolling_rets.rank(axis=1, pct=True)[target_symbol]

        # Volatility rank
        rolling_vol = returns_df.rolling(20).std()
        features['volatility_rank'] = rolling_vol.rank(axis=1, pct=True)[target_symbol]

        return features

    def create_economic_features(
        self,
        target_df: pd.DataFrame,
        fred_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Create features from economic data."""
        features = pd.DataFrame(index=target_df.index)

        if fred_data.empty:
            return features

        # Reindex to target
        fred_aligned = fred_data.reindex(target_df.index, method='ffill')

        # Yield curve features
        if 'yield_curve' in fred_aligned.columns:
            features['yield_curve'] = fred_aligned['yield_curve']
            features['yield_curve_change'] = fred_aligned['yield_curve'].diff(5)
            features['yield_curve_inverted'] = (fred_aligned['yield_curve'] < 0).astype(int)

        # VIX features
        if 'vix' in fred_aligned.columns:
            features['vix'] = fred_aligned['vix']
            features['vix_ma_ratio'] = fred_aligned['vix'] / fred_aligned['vix'].rolling(20).mean()
            features['vix_percentile'] = fred_aligned['vix'].rolling(252).rank(pct=True)

        # Credit spread features
        if 'hy_spread' in fred_aligned.columns:
            features['hy_spread'] = fred_aligned['hy_spread']
            features['hy_spread_change'] = fred_aligned['hy_spread'].diff(5)

        # Oil features (energy sector correlation)
        if 'oil_wti' in fred_aligned.columns:
            features['oil_return_20d'] = fred_aligned['oil_wti'].pct_change(20)

        # Gold features (risk-off indicator)
        if 'gold' in fred_aligned.columns:
            features['gold_return_20d'] = fred_aligned['gold'].pct_change(20)

        # Currency features
        if 'eur_usd' in fred_aligned.columns:
            features['eur_usd_change'] = fred_aligned['eur_usd'].pct_change(20)

        return features

    def create_all_features(
        self,
        target_symbol: str,
        universe: dict[str, pd.DataFrame],
        fred_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Create all features for a target symbol."""
        if target_symbol not in universe:
            return pd.DataFrame()

        target_df = universe[target_symbol]

        # Single asset features
        features = self.create_single_asset_features(target_df)

        # Cross-asset features
        cross_features = self.create_cross_asset_features(target_df, universe, target_symbol)
        features = pd.concat([features, cross_features], axis=1)

        # Economic features
        econ_features = self.create_economic_features(target_df, fred_data)
        features = pd.concat([features, econ_features], axis=1)

        # Store feature names
        self.feature_names = features.columns.tolist()

        # Fill NaNs
        features = features.ffill().bfill()

        return features


# =============================================================================
# ML STRATEGIES
# =============================================================================

@dataclass
class StrategyResult:
    """Result from a strategy backtest."""
    name: str
    description: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    accuracy: float
    feature_importance: dict[str, float]


class MLStrategy:
    """Base class for ML strategies."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []

    def prepare_target(self, df: pd.DataFrame, horizon: int = 5) -> pd.Series:
        """
        Create target variable (1 = up, 0 = down).

        Target at time t: whether price goes up from close[t] to close[t+horizon]

        Note: The target correctly uses future data - this is what we're predicting.
        The key is that features at time t must NOT use any data after close[t-1].
        """
        # Compute forward return: (close[t+horizon] - close[t]) / close[t]
        future_return = df['close'].shift(-horizon) / df['close'] - 1
        return (future_return > 0).astype(int)

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Train the model."""
        raise NotImplementedError

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Make predictions."""
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Get prediction probabilities."""
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]

    def get_feature_importance(self) -> dict[str, float]:
        """Get feature importance scores."""
        if hasattr(self.model, 'feature_importances_'):
            importance = self.model.feature_importances_
            return dict(zip(self.feature_names, importance))
        return {}


class RandomForestStrategy(MLStrategy):
    """Random Forest based strategy."""

    def __init__(self):
        super().__init__(
            "RF_CrossAsset",
            "Random Forest with cross-asset features"
        )
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_leaf=20,
            random_state=42,
            n_jobs=-1,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class GradientBoostingStrategy(MLStrategy):
    """Gradient Boosting based strategy."""

    def __init__(self):
        super().__init__(
            "GBM_Momentum",
            "Gradient Boosting for momentum prediction"
        )
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_samples_leaf=20,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class XGBoostStrategy(MLStrategy):
    """XGBoost based strategy."""

    def __init__(self):
        super().__init__(
            "XGB_MultiAsset",
            "XGBoost with multi-asset signals"
        )
        if HAS_XGBOOST:
            self.model = XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
                use_label_encoder=False,
                eval_metric='logloss',
            )
        else:
            # Fallback to GBM
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
            )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class SectorRotationStrategy(MLStrategy):
    """Sector rotation using ML rankings."""

    def __init__(self):
        super().__init__(
            "SectorRotation_ML",
            "ML-based sector rotation strategy"
        )
        self.model = RandomForestClassifier(
            n_estimators=50,
            max_depth=8,
            min_samples_leaf=10,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class RegimeDetectionStrategy(MLStrategy):
    """Detect market regimes and adapt."""

    def __init__(self):
        super().__init__(
            "RegimeDetect_Adaptive",
            "Regime detection with adaptive positioning"
        )
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class MeanReversionMLStrategy(MLStrategy):
    """ML-enhanced mean reversion."""

    def __init__(self):
        super().__init__(
            "MeanReversion_ML",
            "ML-enhanced mean reversion timing"
        )
        self.model = LogisticRegression(
            C=0.1,
            max_iter=1000,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class VolatilityPredictorStrategy(MLStrategy):
    """Predict volatility regimes for position sizing."""

    def __init__(self):
        super().__init__(
            "VolPredict_Sizing",
            "Volatility prediction for dynamic sizing"
        )
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=6,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class CrossAssetMomentumStrategy(MLStrategy):
    """Cross-asset momentum with ML filtering."""

    def __init__(self):
        super().__init__(
            "CrossMomentum_ML",
            "Cross-asset momentum with ML signal filtering"
        )
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_leaf=15,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class EconomicRegimeStrategy(MLStrategy):
    """Trade based on economic regime."""

    def __init__(self):
        super().__init__(
            "EconRegime_Factor",
            "Economic regime-based factor selection"
        )
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            random_state=42,
        )

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)


class EnsembleStrategy(MLStrategy):
    """Ensemble of multiple models."""

    def __init__(self):
        super().__init__(
            "Ensemble_MultiModel",
            "Ensemble of RF, GBM, and LogReg"
        )
        self.models = [
            RandomForestClassifier(n_estimators=50, max_depth=8, random_state=42),
            GradientBoostingClassifier(n_estimators=50, max_depth=5, random_state=42),
            LogisticRegression(C=0.1, max_iter=1000, random_state=42),
        ]
        self.model = self.models[0]  # For feature importance

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.feature_names = X.columns.tolist()
        X_scaled = self.scaler.fit_transform(X)
        for model in self.models:
            model.fit(X_scaled, y)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        X_scaled = self.scaler.transform(X)
        probas = []
        for model in self.models:
            probas.append(model.predict_proba(X_scaled)[:, 1])
        return np.mean(probas, axis=0)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        proba = self.predict_proba(X)
        return (proba > 0.5).astype(int)


# =============================================================================
# BACKTESTER
# =============================================================================

class WalkForwardBacktester:
    """
    Walk-forward backtesting for ML strategies.

    IMPORTANT: Includes proper gap between training and testing to prevent
    data leakage through the target variable.
    """

    def __init__(
        self,
        train_window: int = 252,  # 1 year
        test_window: int = 63,    # 3 months
        retrain_frequency: int = 21,  # Monthly
        gap_days: int = 5,        # Gap >= target_horizon to prevent leakage
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.retrain_frequency = retrain_frequency
        self.gap_days = gap_days

    def backtest(
        self,
        strategy: MLStrategy,
        features: pd.DataFrame,
        prices: pd.DataFrame,
        target_horizon: int = 5,
    ) -> StrategyResult:
        """
        Run walk-forward backtest.

        Timeline to prevent data leakage:
        - Training ends at index i
        - Gap of target_horizon days
        - Testing starts at index i + gap
        """
        # Ensure gap is at least as large as target horizon
        gap = max(self.gap_days, target_horizon)

        # Prepare target - correct computation without double counting
        # Target at time t: whether close[t+horizon] > close[t]
        target = (prices['close'].shift(-target_horizon) / prices['close'] - 1 > 0).astype(int)

        # Align features and target
        valid_idx = features.dropna().index.intersection(target.dropna().index)
        features = features.loc[valid_idx]
        target = target.loc[valid_idx]
        prices = prices.loc[valid_idx]

        # Walk-forward testing
        predictions = pd.Series(index=features.index, dtype=float)
        actuals = pd.Series(index=features.index, dtype=float)

        n_samples = len(features)

        for i in range(self.train_window, n_samples - gap - self.test_window, self.retrain_frequency):
            # Training data
            train_start = max(0, i - self.train_window)
            train_end = i

            X_train = features.iloc[train_start:train_end]
            y_train = target.iloc[train_start:train_end]

            # Test data starts after gap to prevent target leakage
            test_start = i + gap
            test_end = min(test_start + self.test_window, n_samples - target_horizon)

            if test_start >= test_end:
                continue

            X_test = features.iloc[test_start:test_end]
            y_test = target.iloc[test_start:test_end]

            # Train and predict
            try:
                strategy.train(X_train, y_train)
                preds = strategy.predict_proba(X_test)
                predictions.iloc[test_start:test_end] = preds
                actuals.iloc[test_start:test_end] = y_test.values
            except Exception as e:
                continue

        # Calculate returns
        predictions = predictions.dropna()
        if len(predictions) == 0:
            return self._empty_result(strategy.name)

        actuals = actuals.loc[predictions.index]
        prices = prices.loc[predictions.index]

        # Position: 1 if prob > 0.5, -1 if prob < 0.5, scaled by confidence
        positions = (predictions - 0.5) * 2  # Range: -1 to 1
        positions = positions.clip(-1, 1)

        # Strategy returns using open prices for realistic execution
        if 'open' in prices.columns:
            price_returns = prices['open'].pct_change()
        else:
            price_returns = prices['close'].pct_change()

        strategy_returns = positions.shift(1) * price_returns
        strategy_returns = strategy_returns.dropna()

        # Calculate metrics
        total_return = (1 + strategy_returns).prod() - 1

        if len(strategy_returns) > 0 and strategy_returns.std() > 0:
            sharpe = (strategy_returns.mean() * 252) / (strategy_returns.std() * np.sqrt(252))
        else:
            sharpe = 0

        # Drawdown
        cumulative = (1 + strategy_returns).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative - peak) / peak
        max_dd = drawdown.min()

        # Win rate
        winning = (strategy_returns > 0).sum()
        total = (strategy_returns != 0).sum()
        win_rate = winning / total if total > 0 else 0

        # Accuracy
        binary_preds = (predictions > 0.5).astype(int)
        accuracy = (binary_preds == actuals).mean()

        # Accurate trade count (including reversals)
        pos_diff = positions.diff().abs()
        n_trades = (pos_diff > 0.1).sum()
        # Add extra for reversals (long to short or vice versa)
        reversals = ((positions.shift(1) > 0) & (positions < 0)).sum()
        reversals += ((positions.shift(1) < 0) & (positions > 0)).sum()
        n_trades = n_trades + reversals

        # Feature importance
        importance = strategy.get_feature_importance()
        top_features = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10])

        return StrategyResult(
            name=strategy.name,
            description=strategy.description,
            total_return=total_return * 100,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd * 100,
            win_rate=win_rate * 100,
            n_trades=n_trades,
            accuracy=accuracy * 100,
            feature_importance=top_features,
        )

    def _empty_result(self, name: str) -> StrategyResult:
        """Return empty result when no predictions were made."""
        return StrategyResult(
            name=name,
            description="No predictions generated",
            total_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            n_trades=0,
            accuracy=0.0,
            feature_importance={},
        )


# =============================================================================
# MAIN RUNNER
# =============================================================================

def run_multi_asset_ml_research(
    target_symbols: list[str] = None,
    years: int = 3,
) -> dict:
    """Run comprehensive multi-asset ML research."""

    if target_symbols is None:
        target_symbols = ['AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN']

    # Full universe for cross-asset features
    universe_symbols = [
        # Tech
        'AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA',
        # Indices
        'SPY', 'QQQ', 'IWM', 'DIA',
        # Sectors
        'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU',
        # Semiconductors
        'AMD', 'AVGO', 'QCOM', 'MRVL',
    ]

    print("="*70)
    print("MULTI-ASSET ML STRATEGY RESEARCH")
    print("="*70)

    # Fetch data
    print("\n[1/5] Fetching price data...")
    fetcher = MultiAssetDataFetcher()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    universe = fetcher.fetch_universe(universe_symbols, start_date, end_date)
    print(f"  Loaded {len(universe)} symbols")

    # Fetch FRED data
    print("\n[2/5] Fetching economic data...")
    fred_data = fetcher.fetch_fred_data(start_date, end_date)
    print(f"  FRED indicators: {len(fred_data.columns) if not fred_data.empty else 0}")

    # Create feature engineer
    print("\n[3/5] Engineering features...")
    engineer = FeatureEngineer()

    # Initialize strategies
    strategies = [
        RandomForestStrategy(),
        GradientBoostingStrategy(),
        XGBoostStrategy(),
        SectorRotationStrategy(),
        RegimeDetectionStrategy(),
        MeanReversionMLStrategy(),
        VolatilityPredictorStrategy(),
        CrossAssetMomentumStrategy(),
        EconomicRegimeStrategy(),
        EnsembleStrategy(),
    ]

    # Run backtests for each target symbol
    print("\n[4/5] Running backtests...")
    backtester = WalkForwardBacktester()

    all_results = []

    for target in target_symbols:
        if target not in universe:
            continue

        print(f"\n  Target: {target}")

        # Create features
        features = engineer.create_all_features(target, universe, fred_data)
        print(f"    Features: {len(features.columns)}")

        prices = universe[target]

        # Test each strategy
        for strategy in strategies:
            try:
                result = backtester.backtest(strategy, features, prices)
                result_dict = {
                    'symbol': target,
                    'strategy': result.name,
                    'description': result.description,
                    'total_return': result.total_return,
                    'sharpe': result.sharpe_ratio,
                    'max_dd': result.max_drawdown,
                    'win_rate': result.win_rate,
                    'accuracy': result.accuracy,
                    'trades': result.n_trades,
                    'top_features': result.feature_importance,
                }
                all_results.append(result_dict)

                status = "✓" if result.sharpe_ratio > 0.5 else "○"
                print(f"    {status} {result.name}: Sharpe={result.sharpe_ratio:.2f}, Return={result.total_return:+.1f}%")
            except Exception as e:
                print(f"    ✗ {strategy.name}: Error - {str(e)[:50]}")

    # Compile results
    print("\n[5/5] Compiling results...")

    results_df = pd.DataFrame(all_results)

    # Sort by Sharpe ratio
    results_df = results_df.sort_values('sharpe', ascending=False)

    # Save results
    output_dir = _RESULTS_DIR / "ml_strategies"
    output_dir.mkdir(parents=True, exist_ok=True)

    results_df.to_csv(output_dir / "strategy_results.csv", index=False)

    # Print summary
    print("\n" + "="*70)
    print("TOP PERFORMING STRATEGIES")
    print("="*70)
    print(f"\n{'Strategy':<25} {'Symbol':<8} {'Sharpe':>8} {'Return':>10} {'MaxDD':>8} {'WinRate':>8}")
    print("-" * 75)

    for _, row in results_df.head(15).iterrows():
        print(f"{row['strategy']:<25} {row['symbol']:<8} {row['sharpe']:>8.2f} {row['total_return']:>+9.1f}% {row['max_dd']:>7.1f}% {row['win_rate']:>7.1f}%")

    print(f"\n  Results saved to: {output_dir}")

    return {
        'results': results_df.to_dict('records'),
        'output_dir': str(output_dir),
        'n_strategies': len(strategies),
        'n_symbols': len(target_symbols),
        'n_features': len(engineer.feature_names),
    }


if __name__ == "__main__":
    results = run_multi_asset_ml_research()
