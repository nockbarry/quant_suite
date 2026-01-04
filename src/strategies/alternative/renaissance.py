"""Renaissance-style quantitative trading techniques.

Implements statistical arbitrage, pattern detection, and regime-adaptive
strategies inspired by Renaissance Technologies' approach, adapted for
retail-scale trading.

Key techniques:
- Statistical arbitrage with cointegration
- Lead-lag relationship exploitation
- Hidden Markov Model regime detection
- Multi-timeframe signal aggregation
- Order flow estimation from OHLCV
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy import stats

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ..base import Strategy

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from filterpy.kalman import KalmanFilter

    FILTERPY_AVAILABLE = True
except ImportError:
    FILTERPY_AVAILABLE = False
    logger.warning("filterpy not available, Kalman filtering disabled")

try:
    from hmmlearn.hmm import GaussianHMM

    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False
    logger.warning("hmmlearn not available, HMM regime detection disabled")

try:
    from statsmodels.tsa.stattools import adfuller, coint, grangercausalitytests
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant

    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available, cointegration tests disabled")


# =============================================================================
# Statistical Arbitrage
# =============================================================================


@dataclass
class CointegrationResult:
    """Result of cointegration test between two series."""

    symbol1: Symbol
    symbol2: Symbol
    is_cointegrated: bool
    test_statistic: float
    p_value: float
    critical_values: dict[str, float]
    hedge_ratio: float
    half_life: float  # Mean reversion half-life in periods
    correlation: float
    spread_mean: float
    spread_std: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol1": self.symbol1,
            "symbol2": self.symbol2,
            "is_cointegrated": self.is_cointegrated,
            "test_statistic": self.test_statistic,
            "p_value": self.p_value,
            "critical_values": self.critical_values,
            "hedge_ratio": self.hedge_ratio,
            "half_life": self.half_life,
            "correlation": self.correlation,
            "spread_mean": self.spread_mean,
            "spread_std": self.spread_std,
        }


class CointegrationTester:
    """
    Test for cointegration between price series.

    Uses Engle-Granger two-step method:
    1. Regress Y on X to get hedge ratio
    2. Test residuals for stationarity (ADF test)

    Cointegrated pairs mean-revert, making them suitable for pairs trading.
    """

    def __init__(self, significance_level: float = 0.05):
        """
        Initialize cointegration tester.

        Args:
            significance_level: P-value threshold for cointegration
        """
        self.significance_level = significance_level

    def test_pair(
        self,
        series1: pd.Series,
        series2: pd.Series,
        symbol1: Symbol = "ASSET1",
        symbol2: Symbol = "ASSET2",
    ) -> CointegrationResult:
        """
        Test if two series are cointegrated.

        Args:
            series1: First price series
            series2: Second price series
            symbol1: Name of first asset
            symbol2: Name of second asset

        Returns:
            CointegrationResult with test statistics
        """
        if not STATSMODELS_AVAILABLE:
            # Return dummy result
            return CointegrationResult(
                symbol1=symbol1,
                symbol2=symbol2,
                is_cointegrated=False,
                test_statistic=0.0,
                p_value=1.0,
                critical_values={},
                hedge_ratio=1.0,
                half_life=float("inf"),
                correlation=0.0,
                spread_mean=0.0,
                spread_std=1.0,
            )

        # Align series
        df = pd.DataFrame({"s1": series1, "s2": series2}).dropna()
        if len(df) < 30:
            return CointegrationResult(
                symbol1=symbol1,
                symbol2=symbol2,
                is_cointegrated=False,
                test_statistic=0.0,
                p_value=1.0,
                critical_values={},
                hedge_ratio=1.0,
                half_life=float("inf"),
                correlation=0.0,
                spread_mean=0.0,
                spread_std=1.0,
            )

        s1, s2 = df["s1"].values, df["s2"].values

        # Engle-Granger cointegration test
        try:
            score, pvalue, _ = coint(s1, s2)
        except Exception:
            score, pvalue = 0.0, 1.0

        # Calculate hedge ratio via OLS regression
        hedge_ratio = self._calculate_hedge_ratio(s1, s2)

        # Calculate spread
        spread = s1 - hedge_ratio * s2

        # Calculate half-life of mean reversion
        half_life = self._estimate_half_life(spread)

        # Calculate correlation
        correlation = np.corrcoef(s1, s2)[0, 1]

        # ADF test on spread for critical values
        try:
            adf_result = adfuller(spread, autolag="AIC")
            critical_values = {
                "1%": adf_result[4]["1%"],
                "5%": adf_result[4]["5%"],
                "10%": adf_result[4]["10%"],
            }
        except Exception:
            critical_values = {"1%": -3.5, "5%": -2.9, "10%": -2.6}

        is_cointegrated = pvalue < self.significance_level

        return CointegrationResult(
            symbol1=symbol1,
            symbol2=symbol2,
            is_cointegrated=is_cointegrated,
            test_statistic=float(score),
            p_value=float(pvalue),
            critical_values=critical_values,
            hedge_ratio=float(hedge_ratio),
            half_life=float(half_life),
            correlation=float(correlation),
            spread_mean=float(np.mean(spread)),
            spread_std=float(np.std(spread)),
        )

    def _calculate_hedge_ratio(self, y: np.ndarray, x: np.ndarray) -> float:
        """Calculate hedge ratio using OLS."""
        try:
            X = add_constant(x)
            model = OLS(y, X).fit()
            return model.params[1]
        except Exception:
            # Fallback to simple ratio
            return np.std(y) / np.std(x) if np.std(x) > 0 else 1.0

    def _estimate_half_life(self, spread: np.ndarray) -> float:
        """
        Estimate mean reversion half-life using Ornstein-Uhlenbeck process.

        Uses the relationship: half_life = -log(2) / theta
        where theta is the mean reversion speed.
        """
        try:
            # Regress spread changes on lagged spread
            spread_lag = spread[:-1]
            spread_diff = np.diff(spread)

            X = add_constant(spread_lag)
            model = OLS(spread_diff, X).fit()

            # theta is negative of the slope coefficient
            theta = -model.params[1]

            if theta <= 0:
                return float("inf")

            half_life = np.log(2) / theta
            return max(1.0, min(half_life, 1000.0))  # Bound between 1 and 1000

        except Exception:
            return float("inf")

    def find_cointegrated_pairs(
        self,
        data: dict[Symbol, pd.DataFrame],
        price_col: str = "close",
        min_correlation: float = 0.5,
        max_half_life: float = 30.0,
        min_half_life: float = 1.0,
    ) -> list[CointegrationResult]:
        """
        Find all cointegrated pairs from a universe.

        Args:
            data: Dict mapping symbols to OHLCV DataFrames
            price_col: Column to use for prices
            min_correlation: Minimum correlation to consider
            max_half_life: Maximum acceptable half-life
            min_half_life: Minimum acceptable half-life

        Returns:
            List of CointegrationResult for valid pairs
        """
        symbols = list(data.keys())
        results = []

        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i + 1:]:
                # Get aligned price series
                s1 = data[sym1][price_col]
                s2 = data[sym2][price_col]

                # Quick correlation check
                df = pd.DataFrame({"s1": s1, "s2": s2}).dropna()
                if len(df) < 60:
                    continue

                corr = df["s1"].corr(df["s2"])
                if abs(corr) < min_correlation:
                    continue

                # Full cointegration test
                result = self.test_pair(df["s1"], df["s2"], sym1, sym2)

                if (
                    result.is_cointegrated
                    and min_half_life <= result.half_life <= max_half_life
                ):
                    results.append(result)

        # Sort by p-value
        results.sort(key=lambda x: x.p_value)
        return results


class KalmanHedgeRatioEstimator:
    """
    Estimate dynamic hedge ratio using Kalman filter.

    The hedge ratio can drift over time, so using a static OLS estimate
    can lead to spread blow-ups. Kalman filtering allows the hedge ratio
    to evolve.
    """

    def __init__(
        self,
        process_variance: float = 1e-4,
        observation_variance: float = 1e-2,
    ):
        """
        Initialize Kalman estimator.

        Args:
            process_variance: Variance of state transition (lower = more stable)
            observation_variance: Variance of observations (lower = more trust in data)
        """
        self.process_variance = process_variance
        self.observation_variance = observation_variance
        self._kf = None
        self._initialized = False

    def _initialize_filter(self, initial_hedge_ratio: float) -> None:
        """Initialize the Kalman filter."""
        if not FILTERPY_AVAILABLE:
            return

        self._kf = KalmanFilter(dim_x=2, dim_z=1)

        # State: [hedge_ratio, intercept]
        self._kf.x = np.array([[initial_hedge_ratio], [0.0]])

        # State transition (random walk)
        self._kf.F = np.eye(2)

        # Measurement function (will be set dynamically)
        self._kf.H = np.array([[1.0, 1.0]])

        # Covariance matrices
        self._kf.P *= 1.0
        self._kf.Q = np.eye(2) * self.process_variance
        self._kf.R = np.array([[self.observation_variance]])

        self._initialized = True

    def update(self, y: float, x: float) -> tuple[float, float]:
        """
        Update hedge ratio estimate with new observation.

        Args:
            y: Dependent variable (asset 1 price)
            x: Independent variable (asset 2 price)

        Returns:
            (hedge_ratio, intercept)
        """
        if not FILTERPY_AVAILABLE:
            return 1.0, 0.0

        if not self._initialized:
            initial_ratio = y / x if x != 0 else 1.0
            self._initialize_filter(initial_ratio)

        # Set measurement function for this observation
        self._kf.H = np.array([[x, 1.0]])

        # Predict and update
        self._kf.predict()
        self._kf.update(np.array([[y]]))

        return float(self._kf.x[0, 0]), float(self._kf.x[1, 0])

    def get_hedge_ratio(self) -> float:
        """Get current hedge ratio estimate."""
        if not self._initialized or self._kf is None:
            return 1.0
        return float(self._kf.x[0, 0])


class StatisticalArbitrageStrategy(Strategy):
    """
    Statistical arbitrage using cointegrated pairs.

    Enhancements over basic pairs trading:
    - Dynamic hedge ratio estimation (optional Kalman filter)
    - Half-life aware position sizing
    - Multi-pair portfolio management
    - Spread z-score based entry/exit
    """

    name = "stat_arb"
    description = "Statistical arbitrage with cointegration"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        lookback: int = 60,
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.5,
        max_half_life: float = 30.0,
        min_half_life: float = 2.0,
        use_kalman: bool = True,
        rebalance_frequency: int = 5,  # Re-estimate hedge ratio every N bars
        max_pairs: int = 5,
        **params: Any,
    ):
        """
        Initialize statistical arbitrage strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            lookback: Bars for cointegration test
            entry_zscore: Z-score threshold for entry
            exit_zscore: Z-score threshold for exit
            max_half_life: Skip pairs with slow mean reversion
            min_half_life: Skip pairs that revert too fast (noise)
            use_kalman: Use Kalman filter for hedge ratio
            rebalance_frequency: How often to re-estimate hedge ratio
            max_pairs: Maximum concurrent pairs to trade
        """
        super().__init__(universe, timeframe, **params)

        self.lookback = lookback
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.max_half_life = max_half_life
        self.min_half_life = min_half_life
        self.use_kalman = use_kalman and FILTERPY_AVAILABLE
        self.rebalance_frequency = rebalance_frequency
        self.max_pairs = max_pairs

        self._tester = CointegrationTester()
        self._kalman_estimators: dict[tuple[Symbol, Symbol], KalmanHedgeRatioEstimator] = {}
        self._active_pairs: dict[tuple[Symbol, Symbol], dict] = {}
        self._bars_since_rebalance = 0

    def get_required_history(self) -> int:
        return self.lookback + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate statistical arbitrage signals.

        Args:
            data: Price data for universe
            timestamp: Current timestamp

        Returns:
            List of signals for pair entries/exits
        """
        signals = []
        timestamp = timestamp or datetime.now()

        # Need multi-asset data
        if isinstance(data, pd.DataFrame):
            return signals

        # Find cointegrated pairs periodically
        self._bars_since_rebalance += 1
        if (
            self._bars_since_rebalance >= self.rebalance_frequency
            or not self._active_pairs
        ):
            self._update_pairs(data)
            self._bars_since_rebalance = 0

        # Generate signals for each pair
        for (sym1, sym2), pair_info in list(self._active_pairs.items()):
            if sym1 not in data or sym2 not in data:
                continue

            pair_signals = self._generate_pair_signals(
                sym1, sym2, data[sym1], data[sym2], pair_info, timestamp
            )
            signals.extend(pair_signals)

        return signals

    def _update_pairs(self, data: dict[Symbol, pd.DataFrame]) -> None:
        """Update the set of tradeable pairs."""
        # Find cointegrated pairs
        results = self._tester.find_cointegrated_pairs(
            data,
            min_correlation=0.5,
            max_half_life=self.max_half_life,
            min_half_life=self.min_half_life,
        )

        # Keep top pairs
        new_pairs = {}
        for result in results[: self.max_pairs]:
            key = (result.symbol1, result.symbol2)
            new_pairs[key] = {
                "hedge_ratio": result.hedge_ratio,
                "half_life": result.half_life,
                "spread_mean": result.spread_mean,
                "spread_std": result.spread_std,
                "position": None,  # None, "long_spread", "short_spread"
            }

            # Initialize Kalman estimator if using
            if self.use_kalman and key not in self._kalman_estimators:
                self._kalman_estimators[key] = KalmanHedgeRatioEstimator()

        self._active_pairs = new_pairs

    def _generate_pair_signals(
        self,
        sym1: Symbol,
        sym2: Symbol,
        df1: pd.DataFrame,
        df2: pd.DataFrame,
        pair_info: dict,
        timestamp: datetime,
    ) -> list[Signal]:
        """Generate signals for a single pair."""
        signals = []

        # Get current prices
        price1 = df1["close"].iloc[-1]
        price2 = df2["close"].iloc[-1]

        # Update hedge ratio if using Kalman
        if self.use_kalman:
            key = (sym1, sym2)
            if key in self._kalman_estimators:
                hedge_ratio, _ = self._kalman_estimators[key].update(price1, price2)
            else:
                hedge_ratio = pair_info["hedge_ratio"]
        else:
            hedge_ratio = pair_info["hedge_ratio"]

        # Calculate spread and z-score
        spread = price1 - hedge_ratio * price2
        spread_mean = pair_info["spread_mean"]
        spread_std = pair_info["spread_std"]

        if spread_std == 0:
            return signals

        zscore = (spread - spread_mean) / spread_std
        current_position = pair_info["position"]

        # Entry signals
        if current_position is None:
            if zscore > self.entry_zscore:
                # Spread too high -> short spread (short sym1, long sym2)
                signals.append(
                    self.create_signal(
                        symbol=sym1,
                        direction=Direction.SHORT,
                        strength=-abs(zscore) / 3,
                        confidence=min(abs(zscore) / self.entry_zscore, 1.0) * 0.7,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_SHORT,
                        metadata={
                            "strategy_type": "stat_arb",
                            "pair": f"{sym1}/{sym2}",
                            "zscore": zscore,
                            "hedge_ratio": hedge_ratio,
                            "position_type": "short_spread",
                        },
                    )
                )
                signals.append(
                    self.create_signal(
                        symbol=sym2,
                        direction=Direction.LONG,
                        strength=abs(zscore) / 3,
                        confidence=min(abs(zscore) / self.entry_zscore, 1.0) * 0.7,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_LONG,
                        metadata={
                            "strategy_type": "stat_arb",
                            "pair": f"{sym1}/{sym2}",
                            "zscore": zscore,
                            "hedge_ratio": hedge_ratio,
                            "position_type": "short_spread",
                        },
                    )
                )
                pair_info["position"] = "short_spread"

            elif zscore < -self.entry_zscore:
                # Spread too low -> long spread (long sym1, short sym2)
                signals.append(
                    self.create_signal(
                        symbol=sym1,
                        direction=Direction.LONG,
                        strength=abs(zscore) / 3,
                        confidence=min(abs(zscore) / self.entry_zscore, 1.0) * 0.7,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_LONG,
                        metadata={
                            "strategy_type": "stat_arb",
                            "pair": f"{sym1}/{sym2}",
                            "zscore": zscore,
                            "hedge_ratio": hedge_ratio,
                            "position_type": "long_spread",
                        },
                    )
                )
                signals.append(
                    self.create_signal(
                        symbol=sym2,
                        direction=Direction.SHORT,
                        strength=-abs(zscore) / 3,
                        confidence=min(abs(zscore) / self.entry_zscore, 1.0) * 0.7,
                        timestamp=timestamp,
                        signal_type=SignalType.ENTRY_SHORT,
                        metadata={
                            "strategy_type": "stat_arb",
                            "pair": f"{sym1}/{sym2}",
                            "zscore": zscore,
                            "hedge_ratio": hedge_ratio,
                            "position_type": "long_spread",
                        },
                    )
                )
                pair_info["position"] = "long_spread"

        # Exit signals
        elif current_position == "short_spread" and zscore < self.exit_zscore:
            # Close short spread
            signals.append(
                self.create_signal(
                    symbol=sym1,
                    direction=Direction.FLAT,
                    strength=0.0,
                    confidence=0.8,
                    timestamp=timestamp,
                    signal_type=SignalType.EXIT_SHORT,
                    metadata={"strategy_type": "stat_arb", "action": "exit"},
                )
            )
            signals.append(
                self.create_signal(
                    symbol=sym2,
                    direction=Direction.FLAT,
                    strength=0.0,
                    confidence=0.8,
                    timestamp=timestamp,
                    signal_type=SignalType.EXIT_LONG,
                    metadata={"strategy_type": "stat_arb", "action": "exit"},
                )
            )
            pair_info["position"] = None

        elif current_position == "long_spread" and zscore > -self.exit_zscore:
            # Close long spread
            signals.append(
                self.create_signal(
                    symbol=sym1,
                    direction=Direction.FLAT,
                    strength=0.0,
                    confidence=0.8,
                    timestamp=timestamp,
                    signal_type=SignalType.EXIT_LONG,
                    metadata={"strategy_type": "stat_arb", "action": "exit"},
                )
            )
            signals.append(
                self.create_signal(
                    symbol=sym2,
                    direction=Direction.FLAT,
                    strength=0.0,
                    confidence=0.8,
                    timestamp=timestamp,
                    signal_type=SignalType.EXIT_SHORT,
                    metadata={"strategy_type": "stat_arb", "action": "exit"},
                )
            )
            pair_info["position"] = None

        return signals


# =============================================================================
# Lead-Lag Analysis
# =============================================================================


@dataclass
class LeadLagResult:
    """Result of lead-lag analysis between two assets."""

    leader: Symbol
    follower: Symbol
    optimal_lag: int
    correlation_at_lag: float
    granger_pvalue: float | None
    is_significant: bool


class LeadLagAnalyzer:
    """
    Detect lead-lag relationships between assets.

    Some assets lead others due to:
    - Liquidity differences (large caps lead small caps)
    - Information asymmetry
    - Sector dynamics (commodities lead commodity stocks)
    """

    def __init__(self, max_lag: int = 10, significance_level: float = 0.05):
        """
        Initialize lead-lag analyzer.

        Args:
            max_lag: Maximum lag to consider
            significance_level: P-value threshold for Granger causality
        """
        self.max_lag = max_lag
        self.significance_level = significance_level

    def cross_correlation(
        self,
        leader: pd.Series,
        follower: pd.Series,
    ) -> pd.Series:
        """
        Calculate cross-correlation at different lags.

        Positive lag means leader leads follower.

        Args:
            leader: Potential leader series
            follower: Potential follower series

        Returns:
            Series of correlations indexed by lag
        """
        # Align series
        df = pd.DataFrame({"leader": leader, "follower": follower}).dropna()

        correlations = {}
        for lag in range(-self.max_lag, self.max_lag + 1):
            if lag > 0:
                # Leader leads: correlate leader[:-lag] with follower[lag:]
                corr = df["leader"].iloc[:-lag].corr(df["follower"].iloc[lag:])
            elif lag < 0:
                # Follower leads: correlate leader[-lag:] with follower[:lag]
                corr = df["leader"].iloc[-lag:].corr(df["follower"].iloc[:lag])
            else:
                corr = df["leader"].corr(df["follower"])

            correlations[lag] = corr

        return pd.Series(correlations)

    def granger_causality(
        self,
        series1: pd.Series,
        series2: pd.Series,
    ) -> dict[str, Any]:
        """
        Test Granger causality between two series.

        Tests if series1 helps predict series2 and vice versa.

        Args:
            series1: First return series
            series2: Second return series

        Returns:
            Dict with causality results
        """
        if not STATSMODELS_AVAILABLE:
            return {
                "series1_causes_series2": False,
                "series2_causes_series1": False,
                "optimal_lag": 1,
                "pvalues_1to2": {},
                "pvalues_2to1": {},
            }

        # Align series
        df = pd.DataFrame({"s1": series1, "s2": series2}).dropna()

        if len(df) < self.max_lag * 3:
            return {
                "series1_causes_series2": False,
                "series2_causes_series1": False,
                "optimal_lag": 1,
                "pvalues_1to2": {},
                "pvalues_2to1": {},
            }

        # Test s1 -> s2
        try:
            result_1to2 = grangercausalitytests(
                df[["s2", "s1"]], maxlag=self.max_lag, verbose=False
            )
            pvalues_1to2 = {
                lag: result_1to2[lag][0]["ssr_ftest"][1]
                for lag in range(1, self.max_lag + 1)
            }
            causes_1to2 = min(pvalues_1to2.values()) < self.significance_level
        except Exception:
            pvalues_1to2 = {}
            causes_1to2 = False

        # Test s2 -> s1
        try:
            result_2to1 = grangercausalitytests(
                df[["s1", "s2"]], maxlag=self.max_lag, verbose=False
            )
            pvalues_2to1 = {
                lag: result_2to1[lag][0]["ssr_ftest"][1]
                for lag in range(1, self.max_lag + 1)
            }
            causes_2to1 = min(pvalues_2to1.values()) < self.significance_level
        except Exception:
            pvalues_2to1 = {}
            causes_2to1 = False

        # Find optimal lag
        if pvalues_1to2:
            optimal_lag = min(pvalues_1to2, key=pvalues_1to2.get)
        else:
            optimal_lag = 1

        return {
            "series1_causes_series2": causes_1to2,
            "series2_causes_series1": causes_2to1,
            "optimal_lag": optimal_lag,
            "pvalues_1to2": pvalues_1to2,
            "pvalues_2to1": pvalues_2to1,
        }

    def find_leaders(
        self,
        returns: dict[Symbol, pd.Series],
        min_correlation: float = 0.3,
    ) -> list[LeadLagResult]:
        """
        Find all significant lead-lag relationships.

        Args:
            returns: Dict mapping symbols to return series
            min_correlation: Minimum correlation at optimal lag

        Returns:
            List of LeadLagResult for significant relationships
        """
        symbols = list(returns.keys())
        results = []

        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i + 1:]:
                # Calculate cross-correlation
                xcorr = self.cross_correlation(returns[sym1], returns[sym2])

                # Find maximum absolute correlation
                max_idx = xcorr.abs().idxmax()
                max_corr = xcorr[max_idx]

                if abs(max_corr) < min_correlation:
                    continue

                # Determine leader/follower
                if max_idx > 0:
                    leader, follower = sym1, sym2
                    lag = max_idx
                else:
                    leader, follower = sym2, sym1
                    lag = -max_idx

                # Granger causality test
                gc_result = self.granger_causality(returns[leader], returns[follower])
                granger_pvalue = (
                    min(gc_result["pvalues_1to2"].values())
                    if gc_result["pvalues_1to2"]
                    else None
                )

                is_significant = (
                    gc_result["series1_causes_series2"]
                    if leader == sym1
                    else gc_result["series2_causes_series1"]
                )

                results.append(
                    LeadLagResult(
                        leader=leader,
                        follower=follower,
                        optimal_lag=lag,
                        correlation_at_lag=float(max_corr),
                        granger_pvalue=granger_pvalue,
                        is_significant=is_significant,
                    )
                )

        # Sort by correlation strength
        results.sort(key=lambda x: abs(x.correlation_at_lag), reverse=True)
        return results


class LeadLagStrategy(Strategy):
    """
    Trade based on lead-lag relationships.

    When the leader moves significantly, anticipate the follower's move.
    """

    name = "lead_lag"
    description = "Trade lead-lag relationships"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        min_lead_correlation: float = 0.3,
        max_lag: int = 3,
        signal_threshold: float = 1.5,  # Leader move in std devs
        lookback: int = 60,
        **params: Any,
    ):
        """
        Initialize lead-lag strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            min_lead_correlation: Minimum correlation for relationship
            max_lag: Maximum lag to consider
            signal_threshold: Leader move threshold in std devs
            lookback: Lookback for relationship detection
        """
        super().__init__(universe, timeframe, **params)

        self.min_lead_correlation = min_lead_correlation
        self.max_lag = max_lag
        self.signal_threshold = signal_threshold
        self.lookback = lookback

        self._analyzer = LeadLagAnalyzer(max_lag)
        self._relationships: list[LeadLagResult] = []
        self._last_update = 0

    def get_required_history(self) -> int:
        return self.lookback + self.max_lag + 5

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate lead-lag signals.

        Args:
            data: Price data
            timestamp: Current timestamp

        Returns:
            List of signals based on leader movements
        """
        signals = []
        timestamp = timestamp or datetime.now()

        if isinstance(data, pd.DataFrame):
            return signals

        # Update relationships periodically
        self._last_update += 1
        if self._last_update >= 20 or not self._relationships:
            self._update_relationships(data)
            self._last_update = 0

        # Generate signals based on leader movements
        for rel in self._relationships:
            if rel.leader not in data or rel.follower not in data:
                continue

            leader_df = data[rel.leader]
            follower_df = data[rel.follower]

            # Calculate leader's recent move
            leader_returns = leader_df["close"].pct_change()
            leader_std = leader_returns.rolling(20).std().iloc[-1]
            leader_move = leader_returns.iloc[-1]

            if leader_std == 0 or np.isnan(leader_std):
                continue

            leader_zscore = leader_move / leader_std

            # Check if leader move is significant
            if abs(leader_zscore) < self.signal_threshold:
                continue

            # Generate signal for follower
            if leader_zscore > self.signal_threshold:
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
            else:
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT

            strength = min(abs(leader_zscore) / 3, 1.0)
            confidence = abs(rel.correlation_at_lag) * 0.8

            signal = self.create_signal(
                symbol=rel.follower,
                direction=direction,
                strength=strength if direction == Direction.LONG else -strength,
                confidence=confidence,
                timestamp=timestamp,
                signal_type=signal_type,
                metadata={
                    "strategy_type": "lead_lag",
                    "leader": rel.leader,
                    "follower": rel.follower,
                    "leader_zscore": leader_zscore,
                    "lag": rel.optimal_lag,
                    "correlation": rel.correlation_at_lag,
                },
            )
            signals.append(signal)

        return signals

    def _update_relationships(self, data: dict[Symbol, pd.DataFrame]) -> None:
        """Update lead-lag relationships."""
        # Calculate returns
        returns = {}
        for sym, df in data.items():
            returns[sym] = df["close"].pct_change().dropna()

        # Find relationships
        self._relationships = self._analyzer.find_leaders(
            returns, self.min_lead_correlation
        )[:5]  # Keep top 5


# =============================================================================
# Regime Detection
# =============================================================================


@dataclass
class RegimeState:
    """Current regime state and probabilities."""

    current_regime: int
    regime_probabilities: dict[int, float]
    regime_characteristics: dict[int, dict[str, float]]
    transition_matrix: np.ndarray | None


class RegimeDetector:
    """
    Detect market regimes using Hidden Markov Models.

    Regimes capture different market conditions:
    - Bull (trending up, low vol)
    - Bear (trending down, high vol)
    - Sideways (range-bound)
    - Crisis (high vol, large moves)
    """

    def __init__(
        self,
        n_regimes: int = 3,
        features: list[str] | None = None,
        lookback: int = 252,
    ):
        """
        Initialize regime detector.

        Args:
            n_regimes: Number of regimes to detect
            features: Features to use (default: returns, volatility)
            lookback: Lookback for fitting
        """
        self.n_regimes = n_regimes
        self.features = features or ["returns", "volatility"]
        self.lookback = lookback
        self._model = None
        self._fitted = False
        self._regime_stats: dict[int, dict[str, float]] = {}

    def fit(self, data: pd.DataFrame) -> None:
        """
        Fit HMM to historical data.

        Args:
            data: OHLCV DataFrame
        """
        if not HMMLEARN_AVAILABLE:
            logger.warning("hmmlearn not available, regime detection disabled")
            return

        # Prepare features
        features_df = self._prepare_features(data)
        if len(features_df) < 50:
            return

        X = features_df.values

        # Fit HMM
        try:
            self._model = GaussianHMM(
                n_components=self.n_regimes,
                covariance_type="full",
                n_iter=100,
                random_state=42,
            )
            self._model.fit(X)
            self._fitted = True

            # Calculate regime statistics
            regimes = self._model.predict(X)
            returns = data["close"].pct_change().dropna()

            for regime in range(self.n_regimes):
                mask = regimes[: len(returns)] == regime
                if mask.sum() > 0:
                    regime_returns = returns.iloc[mask]
                    self._regime_stats[regime] = {
                        "mean_return": float(regime_returns.mean()),
                        "volatility": float(regime_returns.std()),
                        "frequency": float(mask.mean()),
                    }

            logger.info(f"Fitted HMM with {self.n_regimes} regimes")

        except Exception as e:
            logger.warning(f"Failed to fit HMM: {e}")
            self._fitted = False

    def _prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for HMM."""
        features = pd.DataFrame(index=data.index)

        if "returns" in self.features:
            features["returns"] = data["close"].pct_change()

        if "volatility" in self.features:
            features["volatility"] = data["close"].pct_change().rolling(20).std()

        if "volume_change" in self.features and "volume" in data.columns:
            features["volume_change"] = data["volume"].pct_change()

        return features.dropna()

    def predict_regime(self, data: pd.DataFrame) -> int | None:
        """
        Predict current regime.

        Args:
            data: Recent OHLCV data

        Returns:
            Regime index (0 to n_regimes-1) or None
        """
        if not self._fitted or self._model is None:
            return None

        features_df = self._prepare_features(data)
        if len(features_df) == 0:
            return None

        X = features_df.values[-1:].reshape(1, -1)

        try:
            regime = self._model.predict(X)[0]
            return int(regime)
        except Exception:
            return None

    def regime_probabilities(self, data: pd.DataFrame) -> dict[int, float] | None:
        """
        Get probability distribution over regimes.

        Args:
            data: Recent OHLCV data

        Returns:
            Dict mapping regime index to probability
        """
        if not self._fitted or self._model is None:
            return None

        features_df = self._prepare_features(data)
        if len(features_df) == 0:
            return None

        X = features_df.values[-1:].reshape(1, -1)

        try:
            probs = self._model.predict_proba(X)[0]
            return {i: float(p) for i, p in enumerate(probs)}
        except Exception:
            return None

    def get_regime_state(self, data: pd.DataFrame) -> RegimeState | None:
        """
        Get full regime state information.

        Args:
            data: Recent OHLCV data

        Returns:
            RegimeState with current regime and probabilities
        """
        regime = self.predict_regime(data)
        if regime is None:
            return None

        probs = self.regime_probabilities(data) or {}

        return RegimeState(
            current_regime=regime,
            regime_probabilities=probs,
            regime_characteristics=self._regime_stats,
            transition_matrix=self._model.transmat_ if self._model else None,
        )


class RegimeConditionalStrategy(Strategy):
    """
    Apply different parameters or strategies per regime.

    Different market regimes require different trading approaches:
    - Bull: Trend following, momentum
    - Bear: Mean reversion, defensive
    - Sideways: Range trading, options
    """

    name = "regime_conditional"
    description = "Regime-adaptive strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        n_regimes: int = 3,
        regime_strategies: dict[int, dict[str, Any]] | None = None,
        lookback: int = 252,
        **params: Any,
    ):
        """
        Initialize regime-conditional strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            n_regimes: Number of regimes to detect
            regime_strategies: Dict mapping regime -> strategy parameters
            lookback: Lookback for regime detection
        """
        super().__init__(universe, timeframe, **params)

        self.n_regimes = n_regimes
        self.lookback = lookback

        # Default regime-specific parameters
        self.regime_strategies = regime_strategies or {
            0: {"strategy": "momentum", "threshold": 0.5},
            1: {"strategy": "mean_reversion", "threshold": 2.0},
            2: {"strategy": "momentum", "threshold": 1.0},
        }

        self._detector = RegimeDetector(n_regimes, lookback=lookback)
        self._fitted = False

    def get_required_history(self) -> int:
        return self.lookback + 50

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate regime-conditional signals.

        Args:
            data: Price data
            timestamp: Current timestamp

        Returns:
            List of signals based on current regime
        """
        signals = []
        timestamp = timestamp or datetime.now()

        # Normalize data
        if isinstance(data, pd.DataFrame):
            price_data = data
            symbol = self.universe[0] if self.universe else "ASSET"
        else:
            # Use first symbol for regime detection
            symbol = list(data.keys())[0]
            price_data = data[symbol]

        # Fit detector if not fitted
        if not self._fitted:
            self._detector.fit(price_data)
            self._fitted = True

        # Get current regime
        regime_state = self._detector.get_regime_state(price_data)
        if regime_state is None:
            return signals

        current_regime = regime_state.current_regime
        regime_params = self.regime_strategies.get(current_regime, {})
        strategy_type = regime_params.get("strategy", "momentum")
        threshold = regime_params.get("threshold", 1.0)

        # Generate signals based on regime
        if isinstance(data, dict):
            for sym, df in data.items():
                signal = self._generate_regime_signal(
                    sym, df, strategy_type, threshold, current_regime, timestamp
                )
                if signal:
                    signals.append(signal)
        else:
            signal = self._generate_regime_signal(
                symbol, price_data, strategy_type, threshold, current_regime, timestamp
            )
            if signal:
                signals.append(signal)

        return signals

    def _generate_regime_signal(
        self,
        symbol: Symbol,
        df: pd.DataFrame,
        strategy_type: str,
        threshold: float,
        regime: int,
        timestamp: datetime,
    ) -> Signal | None:
        """Generate signal based on regime strategy."""
        returns = df["close"].pct_change()
        volatility = returns.rolling(20).std().iloc[-1]

        if volatility == 0 or np.isnan(volatility):
            return None

        if strategy_type == "momentum":
            # Momentum: follow recent trend
            recent_return = returns.tail(5).sum()
            zscore = recent_return / (volatility * np.sqrt(5))

            if abs(zscore) < threshold:
                return None

            direction = Direction.LONG if zscore > 0 else Direction.SHORT
            signal_type = (
                SignalType.ENTRY_LONG if zscore > 0 else SignalType.ENTRY_SHORT
            )
            strength = min(abs(zscore) / 3, 1.0)

        elif strategy_type == "mean_reversion":
            # Mean reversion: fade extremes
            ma = df["close"].rolling(20).mean().iloc[-1]
            current = df["close"].iloc[-1]
            deviation = (current - ma) / volatility

            if abs(deviation) < threshold:
                return None

            direction = Direction.SHORT if deviation > 0 else Direction.LONG
            signal_type = (
                SignalType.ENTRY_SHORT if deviation > 0 else SignalType.ENTRY_LONG
            )
            strength = min(abs(deviation) / 3, 1.0)

        else:
            return None

        return self.create_signal(
            symbol=symbol,
            direction=direction,
            strength=strength if direction == Direction.LONG else -strength,
            confidence=0.6,
            timestamp=timestamp,
            signal_type=signal_type,
            metadata={
                "strategy_type": "regime_conditional",
                "regime": regime,
                "sub_strategy": strategy_type,
                "threshold": threshold,
            },
        )


# =============================================================================
# Order Flow Analysis
# =============================================================================


class OrderFlowEstimator:
    """
    Estimate order flow from OHLCV data.

    Uses Close Location Value (CLV) method to estimate buy/sell volume:
    - CLV = (Close - Low - (High - Close)) / (High - Low)
    - Buy volume = Volume * (CLV + 1) / 2
    - Sell volume = Volume * (1 - CLV) / 2
    """

    @staticmethod
    def calculate_clv(df: pd.DataFrame) -> pd.Series:
        """
        Calculate Close Location Value.

        CLV ranges from -1 (close at low) to +1 (close at high).
        """
        high_low = df["high"] - df["low"]
        clv = (2 * df["close"] - df["low"] - df["high"]) / high_low.replace(0, np.nan)
        return clv.fillna(0)

    @staticmethod
    def estimate_buy_sell_volume(df: pd.DataFrame) -> pd.DataFrame:
        """
        Estimate buy and sell volume from OHLCV.

        Returns DataFrame with buy_volume, sell_volume, imbalance columns.
        """
        clv = OrderFlowEstimator.calculate_clv(df)

        result = pd.DataFrame(index=df.index)
        result["buy_volume"] = df["volume"] * (clv + 1) / 2
        result["sell_volume"] = df["volume"] * (1 - clv) / 2
        result["imbalance"] = result["buy_volume"] - result["sell_volume"]
        result["imbalance_ratio"] = clv  # Same as CLV normalized

        return result

    @staticmethod
    def volume_weighted_imbalance(df: pd.DataFrame, window: int = 10) -> pd.Series:
        """
        Calculate rolling volume-weighted imbalance.

        Positive = buying pressure, Negative = selling pressure.
        """
        flow = OrderFlowEstimator.estimate_buy_sell_volume(df)

        buy_sum = flow["buy_volume"].rolling(window).sum()
        sell_sum = flow["sell_volume"].rolling(window).sum()
        total = buy_sum + sell_sum

        return ((buy_sum - sell_sum) / total.replace(0, np.nan)).fillna(0)


class OrderFlowStrategy(Strategy):
    """
    Trade based on order flow imbalance.

    Buy when there's sustained buying pressure, sell when selling pressure.
    """

    name = "order_flow"
    description = "Order flow imbalance strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        imbalance_threshold: float = 0.3,
        lookback: int = 10,
        confirmation_bars: int = 2,
        **params: Any,
    ):
        """
        Initialize order flow strategy.

        Args:
            universe: Symbols to trade
            timeframe: Trading timeframe
            imbalance_threshold: Imbalance threshold for signal
            lookback: Bars for imbalance calculation
            confirmation_bars: Bars of confirmation needed
        """
        super().__init__(universe, timeframe, **params)

        self.imbalance_threshold = imbalance_threshold
        self.lookback = lookback
        self.confirmation_bars = confirmation_bars

    def get_required_history(self) -> int:
        return self.lookback + 10

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
        **kwargs: Any,
    ) -> list[Signal]:
        """
        Generate order flow signals.

        Args:
            data: Price data with volume
            timestamp: Current timestamp

        Returns:
            List of signals based on order flow
        """
        signals = []
        timestamp = timestamp or datetime.now()

        # Normalize data
        if isinstance(data, pd.DataFrame):
            data = {self.universe[0] if self.universe else "ASSET": data}

        for symbol, df in data.items():
            if symbol not in self.universe:
                continue

            if "volume" not in df.columns:
                continue

            # Calculate imbalance
            imbalance = OrderFlowEstimator.volume_weighted_imbalance(df, self.lookback)

            if len(imbalance) < self.confirmation_bars:
                continue

            # Check for confirmed imbalance
            recent_imbalance = imbalance.tail(self.confirmation_bars)
            avg_imbalance = recent_imbalance.mean()

            if abs(avg_imbalance) < self.imbalance_threshold:
                continue

            # Check if all bars confirm direction
            if avg_imbalance > 0:
                if not all(recent_imbalance > 0):
                    continue
                direction = Direction.LONG
                signal_type = SignalType.ENTRY_LONG
            else:
                if not all(recent_imbalance < 0):
                    continue
                direction = Direction.SHORT
                signal_type = SignalType.ENTRY_SHORT

            strength = min(abs(avg_imbalance) / 0.5, 1.0)
            confidence = min(abs(avg_imbalance) / self.imbalance_threshold, 1.0) * 0.7

            signal = self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength if direction == Direction.LONG else -strength,
                confidence=confidence,
                timestamp=timestamp,
                signal_type=signal_type,
                metadata={
                    "strategy_type": "order_flow",
                    "imbalance": avg_imbalance,
                    "confirmation_bars": self.confirmation_bars,
                },
            )
            signals.append(signal)

        return signals


# =============================================================================
# Autocorrelation Analysis
# =============================================================================


class AutocorrelationAnalyzer:
    """
    Analyze autocorrelation structure for hidden patterns.

    Markets are not perfectly efficient - autocorrelation can reveal
    exploitable patterns.
    """

    @staticmethod
    def partial_autocorrelation(
        series: pd.Series,
        max_lag: int = 20,
    ) -> pd.Series:
        """
        Calculate partial autocorrelation function.

        PACF shows the correlation at lag k after removing effects
        of shorter lags.
        """
        from statsmodels.tsa.stattools import pacf

        try:
            pacf_values = pacf(series.dropna(), nlags=max_lag)
            return pd.Series(pacf_values, index=range(max_lag + 1))
        except Exception:
            return pd.Series(dtype=float)

    @staticmethod
    def significant_lags(
        series: pd.Series,
        max_lag: int = 20,
        significance: float = 0.05,
    ) -> list[int]:
        """
        Find statistically significant autocorrelation lags.

        Uses Bartlett's confidence band.
        """
        n = len(series)
        threshold = stats.norm.ppf(1 - significance / 2) / np.sqrt(n)

        pacf = AutocorrelationAnalyzer.partial_autocorrelation(series, max_lag)

        significant = []
        for lag in range(1, len(pacf)):
            if abs(pacf[lag]) > threshold:
                significant.append(lag)

        return significant

    @staticmethod
    def spectral_analysis(
        series: pd.Series,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Spectral analysis to find periodic patterns.

        Returns:
            (frequencies, power_spectrum)
        """
        from scipy.fft import fft, fftfreq

        values = series.dropna().values
        n = len(values)

        # Remove trend
        detrended = values - np.polyval(np.polyfit(range(n), values, 1), range(n))

        # FFT
        yf = fft(detrended)
        xf = fftfreq(n, 1)

        # Power spectrum (positive frequencies only)
        pos_mask = xf > 0
        frequencies = xf[pos_mask]
        power = np.abs(yf[pos_mask]) ** 2

        return frequencies, power

    @staticmethod
    def dominant_cycles(
        series: pd.Series,
        top_n: int = 3,
    ) -> list[tuple[float, float]]:
        """
        Find dominant cycles in the series.

        Returns:
            List of (period, power) tuples for top cycles
        """
        frequencies, power = AutocorrelationAnalyzer.spectral_analysis(series)

        if len(frequencies) == 0:
            return []

        # Find peaks
        top_indices = np.argsort(power)[-top_n:][::-1]

        cycles = []
        for idx in top_indices:
            if frequencies[idx] > 0:
                period = 1 / frequencies[idx]
                cycles.append((period, power[idx]))

        return cycles
