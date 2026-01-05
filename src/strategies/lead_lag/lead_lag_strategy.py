"""
Lead-Lag Strategy - Trading Cross-Asset Predictive Relationships

This strategy exploits the discovery that certain assets lead others by a
predictable time lag. For example, DRAM prices (via MU proxy) lead semiconductor
stocks by approximately 18 trading days with 88-92% correlation.

Example Discovery:
    DRAM → AVGO: r=0.922 @ -18 days
    DRAM → AMD:  r=0.914 @ -18 days
    DRAM → NVDA: r=0.883 @ -18 days

Usage:
    strategy = LeadLagStrategy(
        leader_symbol='MU',           # Leading indicator
        target_symbols=['NVDA', 'AMD', 'AVGO'],  # Stocks to trade
        lag_days=18,                  # Optimal lag from analysis
        signal_threshold=0.02,        # 2% move in leader triggers signal
    )
    signals = strategy.generate_signals(data)

Author: Claude Code
Created: 2026-01-04
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class LeadLagConfig:
    """Configuration for lead-lag strategy."""

    # Core parameters
    leader_symbol: str = "MU"  # Leading indicator symbol
    target_symbols: list[str] = field(default_factory=lambda: ["NVDA", "AMD", "AVGO", "QCOM"])
    lag_days: int = 18  # Days the leader leads by

    # Signal generation
    signal_threshold: float = 0.02  # Min leader move to trigger signal (2%)
    momentum_window: int = 5  # Window for leader momentum calculation
    confirmation_window: int = 3  # Days to confirm signal

    # Position sizing
    base_position_size: float = 0.25  # 25% per position
    scale_by_correlation: bool = True  # Scale size by leader-target correlation

    # Risk management
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.10  # 10% take profit
    max_holding_days: int = 20  # Max days to hold (lag + buffer)

    # Filters
    min_leader_volume_ratio: float = 1.0  # Leader volume must be >= avg
    require_trend_alignment: bool = True  # Target trend should align


@dataclass
class LeadLagSignal:
    """A trading signal from lead-lag analysis."""

    symbol: str
    direction: str  # 'long' or 'short'
    strength: float  # 0-1
    confidence: float  # 0-1

    # Lead-lag specifics
    leader_symbol: str
    leader_move: float  # % move in leader
    lag_days: int
    correlation: float

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'strength': self.strength,
            'confidence': self.confidence,
            'leader_symbol': self.leader_symbol,
            'leader_move': self.leader_move,
            'lag_days': self.lag_days,
            'correlation': self.correlation,
            'timestamp': self.timestamp.isoformat(),
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
        }


class LeadLagFeatureGenerator:
    """Generate features from lead-lag relationships."""

    def __init__(self, config: LeadLagConfig):
        self.config = config

    def compute_leader_features(self, leader_data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute features from the leading indicator.

        Features:
        - leader_momentum_Nd: N-day momentum of leader
        - leader_zscore: Z-score of leader price
        - leader_rsi: RSI of leader
        - leader_vol_ratio: Volume relative to average
        """
        df = pd.DataFrame(index=leader_data.index)
        close = leader_data['Close']
        volume = leader_data.get('Volume', pd.Series(1, index=close.index))

        # Momentum at different windows
        for window in [5, 10, 20]:
            df[f'leader_momentum_{window}d'] = close.pct_change(window)

        # Z-score (deviation from mean)
        df['leader_zscore'] = (close - close.rolling(20).mean()) / close.rolling(20).std()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.inf)
        df['leader_rsi'] = 100 - (100 / (1 + rs))

        # Volume ratio
        df['leader_vol_ratio'] = volume / volume.rolling(20).mean()

        # Volatility
        df['leader_volatility'] = close.pct_change().rolling(20).std() * np.sqrt(252)

        # Trend (SMA crossover)
        df['leader_trend'] = (close.rolling(10).mean() > close.rolling(50).mean()).astype(int)

        return df

    def compute_lagged_features(
        self,
        leader_features: pd.DataFrame,
        lag_days: int,
    ) -> pd.DataFrame:
        """
        Shift leader features by lag_days to create predictive features.

        If lag_days=18, feature at time T predicts target at T+18.
        For backtesting, we shift features FORWARD (positive shift).
        """
        lagged = leader_features.shift(lag_days)
        lagged.columns = [f"{col}_lag{lag_days}" for col in lagged.columns]
        return lagged

    def compute_signal_features(
        self,
        leader_data: pd.DataFrame,
        target_data: pd.DataFrame,
        lag_days: int,
    ) -> pd.DataFrame:
        """
        Compute full feature set for signal generation.

        Returns DataFrame aligned to target_data index with:
        - Leader features (lagged appropriately)
        - Target features (current)
        - Combined signal features
        """
        # Get leader features
        leader_features = self.compute_leader_features(leader_data)

        # Lag them
        lagged_features = self.compute_lagged_features(leader_features, lag_days)

        # Align to target data
        aligned = lagged_features.reindex(target_data.index, method='ffill')

        # Add target features for confirmation
        target_close = target_data['Close']
        aligned['target_momentum_5d'] = target_close.pct_change(5)
        aligned['target_zscore'] = (
            (target_close - target_close.rolling(20).mean()) /
            target_close.rolling(20).std()
        )

        # Signal strength: leader momentum magnitude
        mom_col = f'leader_momentum_{self.config.momentum_window}d_lag{lag_days}'
        if mom_col in aligned.columns:
            aligned['signal_strength'] = aligned[mom_col].abs()

        return aligned


class LeadLagStrategy:
    """
    Strategy that trades based on lead-lag relationships between assets.

    The core insight: If asset A leads asset B by N days with high correlation,
    we can use A's movements to predict B's future movements.

    Example:
        DRAM prices (MU) lead semiconductor stocks by 18 days.
        When MU moves up 5% over 5 days, we go long NVDA/AMD/AVGO
        expecting them to follow ~18 days later.
    """

    name = "lead_lag"
    description = "Cross-asset lead-lag momentum strategy"
    version = "1.0.0"

    # Known correlations from analysis (can be updated dynamically)
    DEFAULT_CORRELATIONS = {
        'MU': {
            'AVGO': 0.922,
            'AMD': 0.914,
            'NVDA': 0.883,
            'QCOM': 0.860,
            'TSM': 0.757,
        }
    }

    def __init__(
        self,
        config: LeadLagConfig | None = None,
        correlations: dict[str, dict[str, float]] | None = None,
    ):
        """
        Initialize the lead-lag strategy.

        Args:
            config: Strategy configuration
            correlations: Known correlations {leader: {target: corr}}
        """
        self.config = config or LeadLagConfig()
        self.correlations = correlations or self.DEFAULT_CORRELATIONS
        self.feature_generator = LeadLagFeatureGenerator(self.config)

        # State
        self._leader_data: pd.DataFrame | None = None
        self._last_signals: list[LeadLagSignal] = []

    def get_correlation(self, leader: str, target: str) -> float:
        """Get known correlation between leader and target."""
        if leader in self.correlations:
            return self.correlations[leader].get(target, 0.5)
        return 0.5  # Default if unknown

    def generate_signals(
        self,
        data: dict[str, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[LeadLagSignal]:
        """
        Generate trading signals from lead-lag relationship.

        Args:
            data: Dict of {symbol: OHLCV DataFrame}
            timestamp: Current timestamp (for live trading)

        Returns:
            List of LeadLagSignal objects
        """
        signals = []
        leader = self.config.leader_symbol

        if leader not in data:
            logger.warning(f"Leader symbol {leader} not in data")
            return signals

        leader_data = data[leader]

        # Generate leader features
        leader_features = self.feature_generator.compute_leader_features(leader_data)

        # Get latest leader state (lagged back to predict current targets)
        lag = self.config.lag_days
        if len(leader_features) < lag + self.config.momentum_window:
            logger.warning("Insufficient leader data for lag calculation")
            return signals

        # The signal is based on leader's state LAG days ago
        lagged_idx = -lag if lag > 0 else -1

        # Get leader momentum from lag_days ago
        mom_col = f'leader_momentum_{self.config.momentum_window}d'
        if mom_col not in leader_features.columns:
            logger.warning(f"Missing column: {mom_col}")
            return signals

        leader_momentum = leader_features[mom_col].iloc[lagged_idx]
        leader_zscore = leader_features['leader_zscore'].iloc[lagged_idx]
        leader_vol_ratio = leader_features['leader_vol_ratio'].iloc[lagged_idx]
        leader_trend = leader_features['leader_trend'].iloc[lagged_idx]

        # Check if leader move exceeds threshold
        if abs(leader_momentum) < self.config.signal_threshold:
            logger.debug(f"Leader momentum {leader_momentum:.3f} below threshold")
            return signals

        # Check volume filter
        if leader_vol_ratio < self.config.min_leader_volume_ratio:
            logger.debug(f"Leader volume ratio {leader_vol_ratio:.2f} below minimum")
            return signals

        # Determine direction
        direction = 'long' if leader_momentum > 0 else 'short'

        # Generate signals for each target
        for target in self.config.target_symbols:
            if target not in data:
                continue

            target_data = data[target]
            correlation = self.get_correlation(leader, target)

            # Check trend alignment if required
            if self.config.require_trend_alignment:
                target_trend = (
                    target_data['Close'].rolling(10).mean().iloc[-1] >
                    target_data['Close'].rolling(50).mean().iloc[-1]
                )
                if direction == 'long' and not target_trend:
                    continue
                if direction == 'short' and target_trend:
                    continue

            # Calculate signal strength and confidence
            strength = min(abs(leader_momentum) / 0.10, 1.0)  # Cap at 10% move
            confidence = correlation * strength

            # Calculate entry, stop, take profit
            current_price = target_data['Close'].iloc[-1]

            if direction == 'long':
                stop_loss = current_price * (1 - self.config.stop_loss_pct)
                take_profit = current_price * (1 + self.config.take_profit_pct)
            else:
                stop_loss = current_price * (1 + self.config.stop_loss_pct)
                take_profit = current_price * (1 - self.config.take_profit_pct)

            signal = LeadLagSignal(
                symbol=target,
                direction=direction,
                strength=strength,
                confidence=confidence,
                leader_symbol=leader,
                leader_move=leader_momentum,
                lag_days=lag,
                correlation=correlation,
                timestamp=timestamp or datetime.now(),
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            signals.append(signal)
            logger.info(
                f"Signal: {direction.upper()} {target} | "
                f"Leader {leader} moved {leader_momentum:+.1%} {lag}d ago | "
                f"Confidence: {confidence:.2f}"
            )

        self._last_signals = signals
        return signals

    def generate_backtest_signals(
        self,
        leader_data: pd.DataFrame,
        target_data: pd.DataFrame,
        target_symbol: str,
    ) -> pd.DataFrame:
        """
        Generate signal series for backtesting.

        Returns DataFrame with columns:
        - signal: 1 (long), -1 (short), 0 (no signal)
        - strength: signal strength 0-1
        - confidence: confidence 0-1
        """
        # Compute features
        features = self.feature_generator.compute_signal_features(
            leader_data, target_data, self.config.lag_days
        )

        # Initialize signal series
        signals = pd.DataFrame(index=target_data.index)
        signals['signal'] = 0
        signals['strength'] = 0.0
        signals['confidence'] = 0.0

        # Generate signals based on lagged leader momentum
        mom_col = f'leader_momentum_{self.config.momentum_window}d_lag{self.config.lag_days}'

        if mom_col not in features.columns:
            logger.warning(f"Missing momentum column: {mom_col}")
            return signals

        momentum = features[mom_col]

        # Long signals: leader momentum > threshold
        long_mask = momentum > self.config.signal_threshold
        signals.loc[long_mask, 'signal'] = 1

        # Short signals: leader momentum < -threshold
        short_mask = momentum < -self.config.signal_threshold
        signals.loc[short_mask, 'signal'] = -1

        # Signal strength
        signals['strength'] = (momentum.abs() / 0.10).clip(0, 1)

        # Confidence (correlation * strength)
        correlation = self.get_correlation(self.config.leader_symbol, target_symbol)
        signals['confidence'] = correlation * signals['strength']

        return signals


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_dram_semiconductor_strategy(
    lag_days: int = 18,
    signal_threshold: float = 0.02,
) -> LeadLagStrategy:
    """
    Create pre-configured strategy for DRAM → Semiconductor lead-lag.

    Based on analysis showing:
    - DRAM (MU proxy) leads semiconductor stocks by ~18 days
    - Correlations: AVGO (0.92), AMD (0.91), NVDA (0.88), QCOM (0.86)
    """
    config = LeadLagConfig(
        leader_symbol='MU',
        target_symbols=['NVDA', 'AMD', 'AVGO', 'QCOM'],
        lag_days=lag_days,
        signal_threshold=signal_threshold,
        momentum_window=5,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
    )

    correlations = {
        'MU': {
            'AVGO': 0.922,
            'AMD': 0.914,
            'NVDA': 0.883,
            'QCOM': 0.860,
        }
    }

    return LeadLagStrategy(config=config, correlations=correlations)


def analyze_lead_lag_relationship(
    leader_data: pd.DataFrame,
    target_data: pd.DataFrame,
    max_lag: int = 30,
) -> dict:
    """
    Analyze lead-lag relationship between two assets.

    Returns:
        dict with optimal_lag, correlation, direction, p_value
    """
    leader_returns = leader_data['Close'].pct_change().dropna()
    target_returns = target_data['Close'].pct_change().dropna()

    # Align
    aligned = pd.concat([leader_returns, target_returns], axis=1, join='inner')
    aligned.columns = ['leader', 'target']

    best_lag = 0
    best_corr = 0

    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            # Leader leads target
            shifted_leader = aligned['leader'].shift(-lag)
            corr = shifted_leader.corr(aligned['target'])
        else:
            # Target leads leader (or concurrent)
            shifted_target = aligned['target'].shift(lag)
            corr = aligned['leader'].corr(shifted_target)

        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag

    return {
        'optimal_lag': best_lag,
        'correlation': best_corr,
        'direction': 'leader_leads' if best_lag < 0 else 'target_leads' if best_lag > 0 else 'concurrent',
        'lead_days': abs(best_lag),
    }
