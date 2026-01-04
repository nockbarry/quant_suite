"""Correlation breakdown detection and trading strategies.

Monitors correlation between assets and generates signals when
correlations break down or revert to historical norms.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ...core import Signal, SignalType, Symbol
from ..base import Strategy

logger = logging.getLogger(__name__)


class CorrelationRegime(str, Enum):
    """Correlation regime classification."""

    HIGH_POSITIVE = "high_positive"  # > 0.7
    MODERATE_POSITIVE = "moderate_positive"  # 0.3 to 0.7
    LOW = "low"  # -0.3 to 0.3
    MODERATE_NEGATIVE = "moderate_negative"  # -0.7 to -0.3
    HIGH_NEGATIVE = "high_negative"  # < -0.7


class BreakdownType(str, Enum):
    """Type of correlation breakdown."""

    DECORRELATION = "decorrelation"  # Correlation dropped significantly
    RECORRELATION = "recorrelation"  # Correlation returned
    SIGN_FLIP = "sign_flip"  # Correlation changed sign
    STRESS_SPIKE = "stress_spike"  # Sudden jump to high correlation (crisis)


@dataclass
class CorrelationPair:
    """Correlation data for an asset pair."""

    asset1: str
    asset2: str
    current_correlation: float
    rolling_correlation: float
    historical_correlation: float
    correlation_zscore: float
    regime: CorrelationRegime
    is_breakdown: bool
    breakdown_type: BreakdownType | None = None
    days_in_regime: int = 0

    @property
    def pair_name(self) -> str:
        """Get pair name."""
        return f"{self.asset1}_{self.asset2}"

    @property
    def deviation_from_historical(self) -> float:
        """Deviation from historical correlation."""
        return self.current_correlation - self.historical_correlation

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "asset1": self.asset1,
            "asset2": self.asset2,
            "current_correlation": self.current_correlation,
            "rolling_correlation": self.rolling_correlation,
            "historical_correlation": self.historical_correlation,
            "correlation_zscore": self.correlation_zscore,
            "regime": self.regime.value,
            "is_breakdown": self.is_breakdown,
            "breakdown_type": self.breakdown_type.value if self.breakdown_type else None,
            "deviation": self.deviation_from_historical,
        }


@dataclass
class CorrelationMatrix:
    """Full correlation matrix with breakdown detection."""

    timestamp: datetime
    assets: list[str]
    current_matrix: np.ndarray
    historical_matrix: np.ndarray
    zscore_matrix: np.ndarray
    breakdown_pairs: list[CorrelationPair] = field(default_factory=list)

    @property
    def num_breakdowns(self) -> int:
        """Number of pair breakdowns detected."""
        return len(self.breakdown_pairs)

    @property
    def avg_correlation(self) -> float:
        """Average pairwise correlation."""
        n = len(self.assets)
        if n < 2:
            return 0
        # Extract upper triangle (excluding diagonal)
        upper = self.current_matrix[np.triu_indices(n, k=1)]
        return float(np.mean(upper))

    @property
    def is_stress_regime(self) -> bool:
        """Check if market is in stress regime (high correlations)."""
        return self.avg_correlation > 0.7

    def get_pair_correlation(self, asset1: str, asset2: str) -> float | None:
        """Get correlation for specific pair."""
        if asset1 not in self.assets or asset2 not in self.assets:
            return None
        i = self.assets.index(asset1)
        j = self.assets.index(asset2)
        return self.current_matrix[i, j]

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to DataFrame."""
        return pd.DataFrame(
            self.current_matrix,
            index=self.assets,
            columns=self.assets,
        )


class CorrelationBreakdownDetector:
    """
    Detects significant changes in asset correlations.

    Useful for:
    - Identifying regime changes
    - Detecting stress events (correlation spikes)
    - Finding diversification opportunities
    - Pairs trading signal generation
    """

    def __init__(
        self,
        lookback_short: int = 20,
        lookback_long: int = 252,
        breakdown_threshold: float = 2.0,
        regime_threshold: float = 0.3,
    ):
        """
        Initialize detector.

        Args:
            lookback_short: Short-term correlation window (days)
            lookback_long: Long-term historical correlation window
            breakdown_threshold: Z-score threshold for breakdown
            regime_threshold: Correlation change for regime shift
        """
        self.lookback_short = lookback_short
        self.lookback_long = lookback_long
        self.breakdown_threshold = breakdown_threshold
        self.regime_threshold = regime_threshold

        self._correlation_history: dict[str, list[float]] = {}

    def calculate_rolling_correlation(
        self,
        returns1: pd.Series,
        returns2: pd.Series,
        window: int,
    ) -> pd.Series:
        """
        Calculate rolling correlation between two return series.

        Args:
            returns1: First return series
            returns2: Second return series
            window: Rolling window size

        Returns:
            Rolling correlation series
        """
        return returns1.rolling(window=window).corr(returns2)

    def calculate_correlation_zscore(
        self,
        current_corr: float,
        historical_corrs: list[float],
    ) -> float:
        """
        Calculate z-score of current correlation vs historical.

        Args:
            current_corr: Current correlation
            historical_corrs: Historical correlation values

        Returns:
            Z-score
        """
        if len(historical_corrs) < 10:
            return 0

        mean_corr = np.mean(historical_corrs)
        std_corr = np.std(historical_corrs)

        if std_corr < 0.01:
            return 0

        return (current_corr - mean_corr) / std_corr

    def classify_regime(self, correlation: float) -> CorrelationRegime:
        """Classify correlation into regime."""
        if correlation > 0.7:
            return CorrelationRegime.HIGH_POSITIVE
        elif correlation > 0.3:
            return CorrelationRegime.MODERATE_POSITIVE
        elif correlation > -0.3:
            return CorrelationRegime.LOW
        elif correlation > -0.7:
            return CorrelationRegime.MODERATE_NEGATIVE
        else:
            return CorrelationRegime.HIGH_NEGATIVE

    def detect_breakdown_type(
        self,
        current_corr: float,
        previous_corr: float,
        historical_corr: float,
    ) -> BreakdownType | None:
        """
        Determine the type of correlation breakdown.

        Args:
            current_corr: Current correlation
            previous_corr: Previous period correlation
            historical_corr: Long-term historical correlation

        Returns:
            BreakdownType or None
        """
        # Sign flip
        if current_corr * previous_corr < 0 and abs(current_corr - previous_corr) > 0.3:
            return BreakdownType.SIGN_FLIP

        # Stress spike (sudden jump to high correlation)
        if current_corr > 0.8 and previous_corr < 0.5:
            return BreakdownType.STRESS_SPIKE

        # Decorrelation
        if abs(current_corr) < abs(historical_corr) - self.regime_threshold:
            return BreakdownType.DECORRELATION

        # Recorrelation
        if abs(current_corr - historical_corr) < 0.1 and abs(previous_corr - historical_corr) > 0.3:
            return BreakdownType.RECORRELATION

        return None

    def analyze_pair(
        self,
        returns1: pd.Series,
        returns2: pd.Series,
        asset1: str,
        asset2: str,
    ) -> CorrelationPair:
        """
        Analyze correlation for a single pair.

        Args:
            returns1: First asset returns
            returns2: Second asset returns
            asset1: First asset symbol
            asset2: Second asset symbol

        Returns:
            CorrelationPair analysis
        """
        # Align series
        aligned = pd.concat([returns1, returns2], axis=1).dropna()
        if len(aligned) < self.lookback_short:
            return CorrelationPair(
                asset1=asset1,
                asset2=asset2,
                current_correlation=0,
                rolling_correlation=0,
                historical_correlation=0,
                correlation_zscore=0,
                regime=CorrelationRegime.LOW,
                is_breakdown=False,
            )

        r1 = aligned.iloc[:, 0]
        r2 = aligned.iloc[:, 1]

        # Calculate correlations
        rolling_corr = self.calculate_rolling_correlation(r1, r2, self.lookback_short)
        current_corr = rolling_corr.iloc[-1] if not rolling_corr.empty else 0

        # Historical correlation
        if len(aligned) >= self.lookback_long:
            historical_corr = r1.iloc[-self.lookback_long:].corr(r2.iloc[-self.lookback_long:])
        else:
            historical_corr = r1.corr(r2)

        # Get rolling correlation history for z-score
        pair_key = f"{asset1}_{asset2}"
        if pair_key not in self._correlation_history:
            self._correlation_history[pair_key] = []

        self._correlation_history[pair_key].append(current_corr)
        # Keep limited history
        if len(self._correlation_history[pair_key]) > 252:
            self._correlation_history[pair_key] = self._correlation_history[pair_key][-252:]

        # Calculate z-score
        zscore = self.calculate_correlation_zscore(
            current_corr,
            self._correlation_history[pair_key][:-1],
        )

        # Determine regime
        regime = self.classify_regime(current_corr)

        # Check for breakdown
        is_breakdown = abs(zscore) > self.breakdown_threshold
        breakdown_type = None

        if is_breakdown and len(rolling_corr) > 1:
            previous_corr = rolling_corr.iloc[-2]
            breakdown_type = self.detect_breakdown_type(
                current_corr,
                previous_corr,
                historical_corr,
            )

        return CorrelationPair(
            asset1=asset1,
            asset2=asset2,
            current_correlation=current_corr,
            rolling_correlation=float(rolling_corr.mean()),
            historical_correlation=historical_corr,
            correlation_zscore=zscore,
            regime=regime,
            is_breakdown=is_breakdown,
            breakdown_type=breakdown_type,
        )

    def analyze_universe(
        self,
        returns_df: pd.DataFrame,
    ) -> CorrelationMatrix:
        """
        Analyze correlations for entire universe.

        Args:
            returns_df: DataFrame with returns for each asset

        Returns:
            CorrelationMatrix with breakdown detection
        """
        assets = list(returns_df.columns)
        n = len(assets)

        # Current correlation matrix
        current_matrix = returns_df.iloc[-self.lookback_short:].corr().values

        # Historical correlation matrix
        if len(returns_df) >= self.lookback_long:
            historical_matrix = returns_df.iloc[-self.lookback_long:].corr().values
        else:
            historical_matrix = returns_df.corr().values

        # Calculate z-score matrix
        zscore_matrix = np.zeros((n, n))
        breakdown_pairs = []

        for i in range(n):
            for j in range(i + 1, n):
                pair = self.analyze_pair(
                    returns_df.iloc[:, i],
                    returns_df.iloc[:, j],
                    assets[i],
                    assets[j],
                )

                zscore_matrix[i, j] = pair.correlation_zscore
                zscore_matrix[j, i] = pair.correlation_zscore

                if pair.is_breakdown:
                    breakdown_pairs.append(pair)

        return CorrelationMatrix(
            timestamp=datetime.now(),
            assets=assets,
            current_matrix=current_matrix,
            historical_matrix=historical_matrix,
            zscore_matrix=zscore_matrix,
            breakdown_pairs=breakdown_pairs,
        )


class CorrelationBreakdownStrategy(Strategy):
    """
    Strategy that trades correlation breakdowns.

    Two main signals:
    1. Mean reversion: When correlation deviates significantly from historical,
       bet on reversion
    2. Momentum: When correlation breakdown continues, trade the divergence
    """

    name = "correlation_breakdown"

    def __init__(
        self,
        universe: list[Symbol],
        lookback_short: int = 20,
        lookback_long: int = 252,
        breakdown_threshold: float = 2.0,
        mode: str = "mean_reversion",  # or "momentum"
    ):
        """
        Initialize strategy.

        Args:
            universe: Asset universe
            lookback_short: Short correlation window
            lookback_long: Long correlation window
            breakdown_threshold: Z-score threshold
            mode: Trading mode (mean_reversion or momentum)
        """
        self.universe = universe
        self.lookback_short = lookback_short
        self.lookback_long = lookback_long
        self.breakdown_threshold = breakdown_threshold
        self.mode = mode

        self._detector = CorrelationBreakdownDetector(
            lookback_short=lookback_short,
            lookback_long=lookback_long,
            breakdown_threshold=breakdown_threshold,
        )

    def generate_signals(
        self,
        data: pd.DataFrame,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate trading signals from correlation breakdowns.

        Args:
            data: Price data DataFrame with columns for each asset
            timestamp: Signal timestamp

        Returns:
            List of Signal objects
        """
        timestamp = timestamp or datetime.now()
        signals = []

        # Calculate returns
        returns = data.pct_change().dropna()

        if len(returns) < self.lookback_short:
            return signals

        # Analyze correlations
        corr_matrix = self._detector.analyze_universe(returns)

        for pair in corr_matrix.breakdown_pairs:
            # Generate signals based on breakdown type and mode
            signal = self._generate_pair_signal(pair, timestamp)
            if signal:
                signals.append(signal)

        return signals

    def _generate_pair_signal(
        self,
        pair: CorrelationPair,
        timestamp: datetime,
    ) -> Signal | None:
        """Generate signal for a breakdown pair."""
        if not pair.breakdown_type:
            return None

        # Mean reversion mode
        if self.mode == "mean_reversion":
            return self._mean_reversion_signal(pair, timestamp)
        # Momentum mode
        else:
            return self._momentum_signal(pair, timestamp)

    def _mean_reversion_signal(
        self,
        pair: CorrelationPair,
        timestamp: datetime,
    ) -> Signal | None:
        """
        Generate mean reversion signal.

        If correlation dropped significantly, expect it to revert.
        Trade the asset that moved relatively more.
        """
        # Decorrelation: expect correlation to return
        if pair.breakdown_type == BreakdownType.DECORRELATION:
            # This is more of a pairs signal - we'd need spread data
            # For now, just flag the opportunity
            return Signal(
                symbol=pair.asset1,
                signal_type=SignalType.HOLD,
                strength=abs(pair.correlation_zscore) / 5,
                timestamp=timestamp,
                metadata={
                    "strategy": self.name,
                    "pair": pair.pair_name,
                    "breakdown_type": pair.breakdown_type.value,
                    "zscore": pair.correlation_zscore,
                    "action": "monitor_for_recorrelation",
                },
            )

        # Recorrelation: correlation returning to normal
        if pair.breakdown_type == BreakdownType.RECORRELATION:
            return Signal(
                symbol=pair.asset1,
                signal_type=SignalType.HOLD,
                strength=0.3,
                timestamp=timestamp,
                metadata={
                    "strategy": self.name,
                    "pair": pair.pair_name,
                    "breakdown_type": pair.breakdown_type.value,
                    "action": "correlation_normalized",
                },
            )

        # Stress spike: high correlation means diversification lost
        if pair.breakdown_type == BreakdownType.STRESS_SPIKE:
            return Signal(
                symbol=pair.asset1,
                signal_type=SignalType.SHORT,
                strength=0.7,
                timestamp=timestamp,
                metadata={
                    "strategy": self.name,
                    "pair": pair.pair_name,
                    "breakdown_type": pair.breakdown_type.value,
                    "action": "reduce_risk_correlation_spike",
                },
            )

        return None

    def _momentum_signal(
        self,
        pair: CorrelationPair,
        timestamp: datetime,
    ) -> Signal | None:
        """
        Generate momentum signal.

        If correlation is breaking down, trade in direction of breakdown.
        """
        if pair.breakdown_type == BreakdownType.SIGN_FLIP:
            # Significant regime change - reduce positions
            return Signal(
                symbol=pair.asset1,
                signal_type=SignalType.SHORT,
                strength=0.5,
                timestamp=timestamp,
                metadata={
                    "strategy": self.name,
                    "pair": pair.pair_name,
                    "breakdown_type": pair.breakdown_type.value,
                    "action": "correlation_sign_flipped",
                },
            )

        return None


class DispersionStrategy(Strategy):
    """
    Index dispersion trading strategy.

    Trades the difference between index implied volatility and
    weighted average of component implied vols (dispersion).
    """

    name = "dispersion"

    def __init__(
        self,
        index_symbol: str = "SPY",
        component_symbols: list[str] | None = None,
        lookback: int = 20,
        dispersion_threshold: float = 1.5,
    ):
        """
        Initialize dispersion strategy.

        Args:
            index_symbol: Index ETF symbol
            component_symbols: Component stocks
            lookback: Lookback period
            dispersion_threshold: Z-score threshold
        """
        self.index_symbol = index_symbol
        self.component_symbols = component_symbols or [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "NVDA", "TSLA", "BRK.B", "UNH", "JNJ",
        ]
        self.lookback = lookback
        self.dispersion_threshold = dispersion_threshold

        self._dispersion_history: list[float] = []

    def calculate_realized_dispersion(
        self,
        index_returns: pd.Series,
        component_returns: pd.DataFrame,
    ) -> float:
        """
        Calculate realized dispersion.

        Dispersion = avg(component vols) - index vol

        Args:
            index_returns: Index return series
            component_returns: Component returns DataFrame

        Returns:
            Dispersion measure
        """
        index_vol = index_returns.std() * np.sqrt(252)
        component_vols = component_returns.std() * np.sqrt(252)
        avg_component_vol = component_vols.mean()

        return avg_component_vol - index_vol

    def calculate_correlation_dispersion(
        self,
        component_returns: pd.DataFrame,
    ) -> float:
        """
        Calculate correlation-based dispersion.

        Low avg correlation = high dispersion potential.

        Args:
            component_returns: Component returns

        Returns:
            Dispersion from correlations
        """
        corr_matrix = component_returns.corr()
        n = len(corr_matrix)

        # Average pairwise correlation
        upper_triangle = corr_matrix.values[np.triu_indices(n, k=1)]
        avg_corr = np.mean(upper_triangle)

        # Dispersion inversely related to correlation
        return 1 - avg_corr

    def generate_signals(
        self,
        data: pd.DataFrame,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate dispersion signals.

        Args:
            data: Price data with index and components
            timestamp: Signal timestamp

        Returns:
            List of signals
        """
        timestamp = timestamp or datetime.now()
        signals = []

        # Need index column
        if self.index_symbol not in data.columns:
            return signals

        # Calculate returns
        returns = data.pct_change().dropna()

        if len(returns) < self.lookback:
            return signals

        # Get index and component returns
        index_returns = returns[self.index_symbol].iloc[-self.lookback:]
        available_components = [c for c in self.component_symbols if c in returns.columns]

        if len(available_components) < 5:
            return signals

        component_returns = returns[available_components].iloc[-self.lookback:]

        # Calculate dispersion
        realized_disp = self.calculate_realized_dispersion(index_returns, component_returns)
        corr_disp = self.calculate_correlation_dispersion(component_returns)

        # Combined dispersion measure
        dispersion = (realized_disp + corr_disp) / 2

        # Track history for z-score
        self._dispersion_history.append(dispersion)
        if len(self._dispersion_history) > 252:
            self._dispersion_history = self._dispersion_history[-252:]

        # Calculate z-score
        if len(self._dispersion_history) >= 20:
            mean_disp = np.mean(self._dispersion_history)
            std_disp = np.std(self._dispersion_history)
            zscore = (dispersion - mean_disp) / std_disp if std_disp > 0.001 else 0
        else:
            zscore = 0

        # Generate signal
        if abs(zscore) > self.dispersion_threshold:
            if zscore > 0:
                # High dispersion - components moving independently
                # Could sell index vol, buy component vol
                signal_type = SignalType.LONG
                action = "high_dispersion_components_decorrelating"
            else:
                # Low dispersion - components moving together
                # Could buy index vol, sell component vol
                signal_type = SignalType.SHORT
                action = "low_dispersion_components_correlating"

            signals.append(Signal(
                symbol=self.index_symbol,
                signal_type=signal_type,
                strength=min(1.0, abs(zscore) / 3),
                timestamp=timestamp,
                metadata={
                    "strategy": self.name,
                    "dispersion": dispersion,
                    "zscore": zscore,
                    "realized_dispersion": realized_disp,
                    "correlation_dispersion": corr_disp,
                    "action": action,
                },
            ))

        return signals


def calculate_dynamic_correlation(
    returns1: pd.Series,
    returns2: pd.Series,
    halflife: int = 20,
) -> pd.Series:
    """
    Calculate exponentially weighted dynamic correlation.

    Args:
        returns1: First return series
        returns2: Second return series
        halflife: EWMA halflife

    Returns:
        Dynamic correlation series
    """
    # EWMA covariance
    ewma_cov = returns1.ewm(halflife=halflife).cov(returns2)

    # EWMA variances
    ewma_var1 = returns1.ewm(halflife=halflife).var()
    ewma_var2 = returns2.ewm(halflife=halflife).var()

    # Dynamic correlation
    dyn_corr = ewma_cov / np.sqrt(ewma_var1 * ewma_var2)

    return dyn_corr


def test_correlation_stability(
    returns1: pd.Series,
    returns2: pd.Series,
    window: int = 60,
    n_subperiods: int = 4,
) -> dict[str, float]:
    """
    Test if correlation is stable across subperiods.

    Uses Jennrich test for equality of correlation matrices.

    Args:
        returns1: First return series
        returns2: Second return series
        window: Analysis window
        n_subperiods: Number of subperiods to compare

    Returns:
        Dict with test statistics and p-value
    """
    # Split into subperiods
    subperiod_len = window // n_subperiods
    correlations = []

    for i in range(n_subperiods):
        start = i * subperiod_len
        end = start + subperiod_len
        sub_corr = returns1.iloc[start:end].corr(returns2.iloc[start:end])
        correlations.append(sub_corr)

    # Fisher z-transform
    z_values = [np.arctanh(c) if abs(c) < 0.999 else np.sign(c) * 3 for c in correlations]

    # Test for equality (simplified - chi-square test)
    mean_z = np.mean(z_values)
    chi_sq = sum((z - mean_z) ** 2 for z in z_values) * (subperiod_len - 3)

    p_value = 1 - stats.chi2.cdf(chi_sq, df=n_subperiods - 1)

    return {
        "chi_square": chi_sq,
        "p_value": p_value,
        "is_stable": p_value > 0.05,
        "subperiod_correlations": correlations,
    }
