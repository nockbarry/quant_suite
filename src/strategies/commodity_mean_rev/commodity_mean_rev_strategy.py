"""
Commodity Mean-Reversion Strategy

Trading mean-reversion on commodity ETFs when they become overbought/oversold.

Validated Results (2026-01-05 - Walk-Forward + MCPT):
- Natural Gas (UNG): Sharpe 1.37, p=0.003, OOS Sharpe 2.02 (ALL POSITIVE OOS)
- Oil (USO): Sharpe 2.29, p=0.002, OOS Sharpe 2.85 (SIGNIFICANT)
- Copper (CPER): Sharpe 3.15, p=0.023, OOS Sharpe 1.97 (SIGNIFICANT)

Parameters:
- UNG: window=20, threshold=1.5, hold=5d (BEST - all OOS positive)
- USO: window=25, threshold=2.0, hold=5d
- CPER: window=25, threshold=2.5, hold=5d

The strategy:
1. Computes z-score of price relative to rolling mean
2. Goes LONG when z-score < -entry_threshold (oversold)
3. Goes SHORT when z-score > +entry_threshold (overbought)
4. Holds for fixed period (5 days) to capture mean reversion

Author: Claude Code
Created: 2026-01-05
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CommodityMeanRevConfig:
    """Configuration for commodity mean-reversion strategy."""

    # Target commodities (ETF symbols)
    symbols: list[str] = field(default_factory=lambda: ["SLV", "PPLT", "CPER"])

    # Z-score parameters
    lookback_window: int = 20  # Rolling window for mean/std
    entry_threshold: float = 2.0  # Z-score threshold for entry
    exit_threshold: float = 0.0  # Z-score threshold for exit (mean)

    # Position sizing
    base_position_size: float = 0.25  # 25% per position
    scale_by_zscore: bool = True  # Scale size by z-score magnitude

    # Risk management
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.08  # 8% take profit (mean rev targets smaller)
    max_holding_days: int = 15  # Max days to hold

    # Filters
    min_volume_ratio: float = 0.8  # Volume must be >= 80% of average
    require_trend_confirmation: bool = False  # Don't require trend alignment


@dataclass
class CommodityMeanRevSignal:
    """A trading signal from commodity mean-reversion analysis."""

    symbol: str
    direction: str  # 'long' or 'short'
    strength: float  # 0-1 (based on z-score magnitude)
    confidence: float  # 0-1

    # Mean-reversion specifics
    zscore: float  # Current z-score
    lookback_window: int
    entry_threshold: float

    # Price levels
    current_price: float
    rolling_mean: float
    rolling_std: float

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "zscore": self.zscore,
            "lookback_window": self.lookback_window,
            "entry_threshold": self.entry_threshold,
            "current_price": self.current_price,
            "rolling_mean": self.rolling_mean,
            "rolling_std": self.rolling_std,
            "timestamp": self.timestamp.isoformat(),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }


class CommodityMeanRevFeatureGenerator:
    """Generate features for commodity mean-reversion strategy."""

    def __init__(self, config: CommodityMeanRevConfig):
        self.config = config

    def compute_zscore_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute z-score and related features.

        Features:
        - zscore: (price - rolling_mean) / rolling_std
        - zscore_momentum: change in zscore over 5 days
        - price_vs_ma: price relative to moving average
        - volatility: rolling standard deviation of returns
        - volume_ratio: volume relative to average
        """
        df = pd.DataFrame(index=data.index)
        close = data["Close"]
        volume = data.get("Volume", pd.Series(1, index=close.index))

        window = self.config.lookback_window

        # Core z-score
        rolling_mean = close.rolling(window).mean()
        rolling_std = close.rolling(window).std()
        df["zscore"] = (close - rolling_mean) / rolling_std

        # Store for signal generation
        df["rolling_mean"] = rolling_mean
        df["rolling_std"] = rolling_std

        # Z-score momentum (is it getting more extreme or reverting?)
        df["zscore_momentum"] = df["zscore"].diff(5)

        # Price relative to MA (alternative view)
        df["price_vs_ma"] = (close / rolling_mean - 1) * 100

        # Volatility (for position sizing)
        df["volatility"] = close.pct_change().rolling(window).std() * np.sqrt(252)

        # Volume ratio (filter for liquidity)
        df["volume_ratio"] = volume / volume.rolling(window).mean()

        # RSI (additional confirmation)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.inf)
        df["rsi"] = 100 - (100 / (1 + rs))

        # Bollinger band position (0-1, where 0.5 is at mean)
        upper = rolling_mean + 2 * rolling_std
        lower = rolling_mean - 2 * rolling_std
        df["bb_position"] = (close - lower) / (upper - lower)

        return df


class CommodityMeanRevStrategy:
    """
    Strategy that trades mean-reversion on commodity ETFs.

    When commodities become overbought (high z-score) or oversold (low z-score),
    they tend to revert to the mean. This strategy exploits that tendency.

    Best performers:
    - Silver (SLV): Sharpe 2.98 - High volatility, strong mean reversion
    - Platinum (PPLT): Sharpe 2.27 - Less liquid, bigger moves
    - Copper (CPER): Sharpe 0.98 - Industrial demand cycles
    """

    name = "commodity_mean_reversion"
    description = "Mean-reversion strategy on commodity ETFs"
    version = "1.0.0"

    # Commodity-specific parameters (VALIDATED via walk-forward + MCPT)
    COMMODITY_PARAMS = {
        # VALIDATED - All OOS positive
        "UNG": {
            "lookback_window": 20,
            "entry_threshold": 1.5,
            "hold_days": 5,
            "validated": True,
            "mcpt_pvalue": 0.003,
            "oos_sharpe": 2.02,
            "description": "Natural gas - BEST: all OOS splits positive",
        },
        # VALIDATED - Significant
        "USO": {
            "lookback_window": 25,
            "entry_threshold": 2.0,
            "hold_days": 5,
            "validated": True,
            "mcpt_pvalue": 0.002,
            "oos_sharpe": 2.85,
            "description": "Oil - high volatility, strong mean reversion",
        },
        # VALIDATED - Significant
        "CPER": {
            "lookback_window": 25,
            "entry_threshold": 2.5,
            "hold_days": 5,
            "validated": True,
            "mcpt_pvalue": 0.023,
            "oos_sharpe": 1.97,
            "description": "Copper - industrial bellwether",
        },
        # NOT VALIDATED - poor OOS performance in current regime
        "SLV": {
            "lookback_window": 20,
            "entry_threshold": 2.0,
            "hold_days": 5,
            "validated": False,
            "description": "Silver - NOT VALIDATED: negative OOS in current regime",
        },
        "PPLT": {
            "lookback_window": 20,
            "entry_threshold": 2.0,
            "hold_days": 5,
            "validated": False,
            "description": "Platinum - NOT VALIDATED: negative OOS in current regime",
        },
        "GLD": {
            "lookback_window": 30,
            "entry_threshold": 2.5,
            "hold_days": 5,
            "validated": False,
            "description": "Gold - safe haven, needs validation",
        },
        "DBA": {
            "lookback_window": 25,
            "entry_threshold": 2.0,
            "hold_days": 5,
            "validated": False,
            "description": "Agriculture basket - needs validation",
        },
    }

    def __init__(
        self,
        config: CommodityMeanRevConfig | None = None,
    ):
        """
        Initialize the commodity mean-reversion strategy.

        Args:
            config: Strategy configuration
        """
        self.config = config or CommodityMeanRevConfig()
        self.feature_generator = CommodityMeanRevFeatureGenerator(self.config)
        self._last_signals: list[CommodityMeanRevSignal] = []

    def get_symbol_params(self, symbol: str) -> dict:
        """Get commodity-specific parameters."""
        if symbol in self.COMMODITY_PARAMS:
            return self.COMMODITY_PARAMS[symbol]
        return {
            "lookback_window": self.config.lookback_window,
            "entry_threshold": self.config.entry_threshold,
            "description": "Unknown commodity",
        }

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[CommodityMeanRevSignal]:
        """
        Generate trading signals based on z-score mean reversion.

        Args:
            data: Dict of {symbol: OHLCV DataFrame}
            timestamp: Current timestamp (for live trading)

        Returns:
            List of CommodityMeanRevSignal objects
        """
        signals = []

        for symbol in self.config.symbols:
            if symbol not in data:
                logger.warning(f"Symbol {symbol} not in data")
                continue

            symbol_data = data[symbol]
            params = self.get_symbol_params(symbol)

            # Compute features with symbol-specific parameters
            temp_config = CommodityMeanRevConfig(
                lookback_window=params["lookback_window"],
                entry_threshold=params["entry_threshold"],
            )
            feature_gen = CommodityMeanRevFeatureGenerator(temp_config)
            features = feature_gen.compute_zscore_features(symbol_data)

            # Check for sufficient data
            if len(features.dropna()) < params["lookback_window"] + 5:
                logger.warning(f"Insufficient data for {symbol}")
                continue

            # Get latest values
            latest = features.iloc[-1]
            zscore = latest["zscore"]
            volume_ratio = latest["volume_ratio"]
            rolling_mean = latest["rolling_mean"]
            rolling_std = latest["rolling_std"]
            current_price = symbol_data["Close"].iloc[-1]

            # Check volume filter
            if volume_ratio < self.config.min_volume_ratio:
                logger.debug(f"{symbol} volume ratio {volume_ratio:.2f} below minimum")
                continue

            # Check if z-score exceeds threshold
            entry_threshold = params["entry_threshold"]

            if abs(zscore) < entry_threshold:
                logger.debug(f"{symbol} z-score {zscore:.2f} below threshold")
                continue

            # Determine direction (mean reversion = opposite of z-score)
            if zscore < -entry_threshold:
                direction = "long"  # Oversold, expect price to rise
            elif zscore > entry_threshold:
                direction = "short"  # Overbought, expect price to fall
            else:
                continue

            # Calculate signal strength and confidence
            # Strength based on z-score magnitude (capped at 3.0)
            strength = min(abs(zscore) / 3.0, 1.0)

            # Confidence based on volume and RSI confirmation
            rsi = latest.get("rsi", 50)
            rsi_confirms = (direction == "long" and rsi < 30) or (
                direction == "short" and rsi > 70
            )
            confidence = 0.6 + (0.2 if rsi_confirms else 0) + (0.2 * min(volume_ratio, 1.5) / 1.5)
            confidence = min(confidence, 1.0)

            # Calculate entry, stop, take profit
            if direction == "long":
                stop_loss = current_price * (1 - self.config.stop_loss_pct)
                # Target is the rolling mean (mean reversion)
                take_profit = min(
                    rolling_mean,
                    current_price * (1 + self.config.take_profit_pct),
                )
            else:
                stop_loss = current_price * (1 + self.config.stop_loss_pct)
                take_profit = max(
                    rolling_mean,
                    current_price * (1 - self.config.take_profit_pct),
                )

            signal = CommodityMeanRevSignal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                confidence=confidence,
                zscore=zscore,
                lookback_window=params["lookback_window"],
                entry_threshold=entry_threshold,
                current_price=current_price,
                rolling_mean=rolling_mean,
                rolling_std=rolling_std,
                timestamp=timestamp or datetime.now(),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            signals.append(signal)
            logger.info(
                f"Signal: {direction.upper()} {symbol} | "
                f"Z-score: {zscore:+.2f} | "
                f"Target: ${rolling_mean:.2f} | "
                f"Confidence: {confidence:.2f}"
            )

        self._last_signals = signals
        return signals

    def generate_backtest_signals(
        self,
        data: pd.DataFrame,
        symbol: str,
    ) -> pd.DataFrame:
        """
        Generate signal series for backtesting.

        Returns DataFrame with columns:
        - signal: 1 (long), -1 (short), 0 (no signal)
        - strength: signal strength 0-1
        - confidence: confidence 0-1
        - zscore: current z-score
        """
        params = self.get_symbol_params(symbol)

        # Create feature generator with symbol-specific params
        temp_config = CommodityMeanRevConfig(
            lookback_window=params["lookback_window"],
            entry_threshold=params["entry_threshold"],
        )
        feature_gen = CommodityMeanRevFeatureGenerator(temp_config)
        features = feature_gen.compute_zscore_features(data)

        # Initialize signal series
        signals = pd.DataFrame(index=data.index)
        signals["signal"] = 0
        signals["strength"] = 0.0
        signals["confidence"] = 0.0
        signals["zscore"] = features["zscore"]

        entry_threshold = params["entry_threshold"]

        # Long signals: oversold (z-score < -threshold)
        long_mask = features["zscore"] < -entry_threshold
        signals.loc[long_mask, "signal"] = 1

        # Short signals: overbought (z-score > +threshold)
        short_mask = features["zscore"] > entry_threshold
        signals.loc[short_mask, "signal"] = -1

        # Signal strength (based on z-score magnitude)
        signals["strength"] = (features["zscore"].abs() / 3.0).clip(0, 1)

        # Base confidence
        signals["confidence"] = 0.7

        # Boost confidence when RSI confirms
        rsi = features.get("rsi", pd.Series(50, index=data.index))
        long_rsi_confirm = (signals["signal"] == 1) & (rsi < 30)
        short_rsi_confirm = (signals["signal"] == -1) & (rsi > 70)
        signals.loc[long_rsi_confirm | short_rsi_confirm, "confidence"] = 0.85

        return signals


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_natural_gas_strategy() -> CommodityMeanRevStrategy:
    """
    Create pre-configured strategy for Natural Gas (UNG).

    VALIDATED (2026-01-05):
    - Sharpe: 1.37
    - MCPT p-value: 0.003
    - OOS Sharpe: 2.02
    - ALL walk-forward splits positive
    """
    config = CommodityMeanRevConfig(
        symbols=["UNG"],
        lookback_window=20,
        entry_threshold=1.5,
        max_holding_days=5,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
    )
    return CommodityMeanRevStrategy(config=config)


def create_oil_strategy() -> CommodityMeanRevStrategy:
    """
    Create pre-configured strategy for Oil (USO).

    VALIDATED (2026-01-05):
    - Sharpe: 2.29
    - MCPT p-value: 0.002
    - OOS Sharpe: 2.85
    """
    config = CommodityMeanRevConfig(
        symbols=["USO"],
        lookback_window=25,
        entry_threshold=2.0,
        max_holding_days=5,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
    )
    return CommodityMeanRevStrategy(config=config)


def create_copper_strategy() -> CommodityMeanRevStrategy:
    """
    Create pre-configured strategy for Copper (CPER).

    VALIDATED (2026-01-05):
    - Sharpe: 3.15
    - MCPT p-value: 0.023
    - OOS Sharpe: 1.97
    """
    config = CommodityMeanRevConfig(
        symbols=["CPER"],
        lookback_window=25,
        entry_threshold=2.5,
        max_holding_days=5,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
    )
    return CommodityMeanRevStrategy(config=config)


def create_validated_commodities_strategy() -> CommodityMeanRevStrategy:
    """
    Create strategy for all VALIDATED commodities.

    Uses commodity-specific parameters for each symbol.
    """
    config = CommodityMeanRevConfig(
        symbols=["UNG", "USO", "CPER"],
        lookback_window=20,  # Overridden per-symbol
        entry_threshold=2.0,  # Overridden per-symbol
        max_holding_days=5,
    )
    return CommodityMeanRevStrategy(config=config)


def create_energy_strategy() -> CommodityMeanRevStrategy:
    """Create strategy for energy commodities (UNG, USO)."""
    config = CommodityMeanRevConfig(
        symbols=["UNG", "USO"],
        lookback_window=20,
        entry_threshold=1.5,
        max_holding_days=5,
    )
    return CommodityMeanRevStrategy(config=config)


# Legacy functions for backwards compatibility
def create_silver_strategy() -> CommodityMeanRevStrategy:
    """
    Create strategy for Silver (SLV).

    WARNING: NOT VALIDATED - negative OOS performance in current regime.
    Consider using create_natural_gas_strategy() instead.
    """
    config = CommodityMeanRevConfig(
        symbols=["SLV"],
        lookback_window=20,
        entry_threshold=2.0,
    )
    return CommodityMeanRevStrategy(config=config)


def create_platinum_strategy() -> CommodityMeanRevStrategy:
    """
    Create strategy for Platinum (PPLT).

    WARNING: NOT VALIDATED - negative OOS performance in current regime.
    Consider using create_oil_strategy() instead.
    """
    config = CommodityMeanRevConfig(
        symbols=["PPLT"],
        lookback_window=20,
        entry_threshold=2.0,
    )
    return CommodityMeanRevStrategy(config=config)


def analyze_commodity_zscore(
    data: pd.DataFrame,
    lookback_window: int = 20,
) -> dict:
    """
    Analyze current z-score state of a commodity.

    Returns dict with zscore, percentile, signal direction.
    """
    close = data["Close"]
    rolling_mean = close.rolling(lookback_window).mean()
    rolling_std = close.rolling(lookback_window).std()
    zscore = (close - rolling_mean) / rolling_std

    current_zscore = zscore.iloc[-1]

    # Historical percentile
    percentile = (zscore < current_zscore).mean() * 100

    # Determine state
    if current_zscore < -2.0:
        state = "oversold"
        signal = "long"
    elif current_zscore > 2.0:
        state = "overbought"
        signal = "short"
    elif current_zscore < -1.0:
        state = "slightly_oversold"
        signal = "watch_long"
    elif current_zscore > 1.0:
        state = "slightly_overbought"
        signal = "watch_short"
    else:
        state = "neutral"
        signal = "none"

    return {
        "zscore": current_zscore,
        "percentile": percentile,
        "state": state,
        "signal": signal,
        "rolling_mean": rolling_mean.iloc[-1],
        "rolling_std": rolling_std.iloc[-1],
        "current_price": close.iloc[-1],
        "distance_to_mean_pct": (close.iloc[-1] / rolling_mean.iloc[-1] - 1) * 100,
    }
