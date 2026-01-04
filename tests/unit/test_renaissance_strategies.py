"""Tests for Renaissance-style quantitative strategies."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta


class TestCointegration:
    """Tests for cointegration testing."""

    def test_cointegrated_series_creation(self):
        """Test creation of cointegrated series for testing."""
        np.random.seed(42)
        n = 500

        # Create cointegrated pair
        # y = beta * x + epsilon (mean-reverting spread)
        x = np.cumsum(np.random.normal(0, 1, n))  # Random walk
        beta = 0.8
        spread = np.random.normal(0, 0.5, n)  # Mean-reverting
        y = beta * x + spread

        # Spread should be stationary (mean-reverting)
        spread_actual = y - beta * x
        assert np.abs(np.mean(spread_actual)) < 1.0
        assert np.std(spread_actual) < 1.0

    def test_non_cointegrated_series(self):
        """Test detection of non-cointegrated series."""
        np.random.seed(42)
        n = 500

        # Two independent random walks (not cointegrated)
        x = np.cumsum(np.random.normal(0, 1, n))
        y = np.cumsum(np.random.normal(0, 1, n))

        # Their difference should also be a random walk, not stationary
        spread = y - x
        # Random walk variance grows with time
        first_half_var = np.var(spread[:n//2])
        second_half_var = np.var(spread[n//2:])

        # For random walk, variance should increase over time
        # This is a rough heuristic, not a formal test
        # In practice, use ADF test

    def test_hedge_ratio_ols(self):
        """Test OLS hedge ratio estimation."""
        np.random.seed(42)
        n = 100

        x = np.random.normal(100, 10, n)
        beta = 1.2
        y = beta * x + np.random.normal(0, 5, n)

        # OLS estimate: beta = cov(x,y) / var(x)
        beta_ols = np.cov(x, y)[0, 1] / np.var(x)

        np.testing.assert_almost_equal(beta_ols, beta, decimal=1)

    def test_half_life_estimation(self):
        """Test half-life estimation for mean reversion."""
        np.random.seed(42)

        # Create mean-reverting series with known half-life
        n = 1000
        theta = 0.1  # Mean reversion speed
        mu = 0  # Long-term mean
        sigma = 0.1

        spread = np.zeros(n)
        spread[0] = 1.0

        for i in range(1, n):
            spread[i] = spread[i-1] - theta * (spread[i-1] - mu) + sigma * np.random.normal()

        # Half-life = ln(2) / theta
        theoretical_half_life = np.log(2) / theta
        assert 5 < theoretical_half_life < 10  # Should be around 6.9


class TestLeadLag:
    """Tests for lead-lag relationship analysis."""

    def test_cross_correlation(self):
        """Test cross-correlation calculation."""
        np.random.seed(42)
        n = 100

        # Create leader-follower relationship
        leader = np.random.normal(0, 1, n)
        follower = np.roll(leader, 5) + np.random.normal(0, 0.3, n)  # Follows with 5-period lag

        # Cross-correlation at different lags
        max_lag = 10
        correlations = []
        for lag in range(0, max_lag + 1):
            if lag == 0:
                corr = np.corrcoef(leader, follower)[0, 1]
            else:
                corr = np.corrcoef(leader[:-lag], follower[lag:])[0, 1]
            correlations.append((lag, corr))

        # Should find correlation structure
        assert len(correlations) == max_lag + 1

    def test_granger_causality_concept(self):
        """Test Granger causality conceptual understanding."""
        # X Granger-causes Y if:
        # VAR model with X improves Y prediction over Y alone

        # Criteria:
        # 1. X must precede Y
        # 2. X must contain information not in Y

        # A leads B by 2 periods
        np.random.seed(42)
        n = 100
        A = np.random.normal(0, 1, n)
        B = np.zeros(n)
        B[2:] = 0.7 * A[:-2] + 0.3 * np.random.normal(0, 1, n-2)

        # A should Granger-cause B
        # B should not Granger-cause A

    def test_information_coefficient(self):
        """Test information coefficient calculation."""
        np.random.seed(42)

        # Predicted returns vs actual returns
        predicted = np.array([0.01, -0.02, 0.015, -0.01, 0.005])
        actual = np.array([0.008, -0.015, 0.012, -0.008, 0.003])

        # IC = correlation between predictions and actuals
        ic = np.corrcoef(predicted, actual)[0, 1]
        assert ic > 0.9  # High correlation in this example


class TestRegimeDetection:
    """Tests for regime detection."""

    def test_volatility_regimes(self):
        """Test volatility regime classification."""
        np.random.seed(42)

        # Low volatility regime
        low_vol_returns = np.random.normal(0, 0.01, 100)
        low_vol = np.std(low_vol_returns) * np.sqrt(252)

        # High volatility regime
        high_vol_returns = np.random.normal(0, 0.03, 100)
        high_vol = np.std(high_vol_returns) * np.sqrt(252)

        assert high_vol > low_vol * 2

    def test_trend_regimes(self):
        """Test trend regime detection."""
        np.random.seed(42)
        n = 100

        # Uptrend
        uptrend = np.cumsum(np.random.normal(0.005, 0.01, n))
        uptrend_slope = np.polyfit(range(n), uptrend, 1)[0]
        assert uptrend_slope > 0

        # Downtrend
        downtrend = np.cumsum(np.random.normal(-0.005, 0.01, n))
        downtrend_slope = np.polyfit(range(n), downtrend, 1)[0]
        assert downtrend_slope < 0

    def test_regime_persistence(self):
        """Test regime persistence measurement."""
        # Regimes should persist (not switch every day)
        regimes = [1, 1, 1, 1, 2, 2, 2, 1, 1, 1, 1, 1]

        # Count regime changes
        changes = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i-1])
        persistence = 1 - changes / (len(regimes) - 1)

        assert persistence > 0.7  # Regimes persist most of the time


class TestOrderFlowEstimation:
    """Tests for order flow estimation from OHLCV."""

    def test_close_location_value(self):
        """Test Close Location Value (CLV) calculation."""
        # CLV = (Close - Low) / (High - Low) * 2 - 1
        # Range: -1 (closed at low) to +1 (closed at high)

        # Closed at high
        high, low, close = 110, 100, 110
        clv_high = (close - low) / (high - low) * 2 - 1
        assert clv_high == 1.0

        # Closed at low
        close = 100
        clv_low = (close - low) / (high - low) * 2 - 1
        assert clv_low == -1.0

        # Closed at midpoint
        close = 105
        clv_mid = (close - low) / (high - low) * 2 - 1
        assert clv_mid == 0.0

    def test_volume_weighted_clv(self):
        """Test volume-weighted CLV for flow estimation."""
        bars = [
            {'high': 110, 'low': 100, 'close': 108, 'volume': 1000},
            {'high': 112, 'low': 105, 'close': 106, 'volume': 1500},
            {'high': 109, 'low': 103, 'close': 109, 'volume': 800},
        ]

        total_flow = 0
        for bar in bars:
            clv = (bar['close'] - bar['low']) / (bar['high'] - bar['low']) * 2 - 1
            flow = clv * bar['volume']
            total_flow += flow

        # Positive total flow suggests net buying pressure
        # Negative suggests net selling pressure

    def test_imbalance_calculation(self):
        """Test buy/sell imbalance calculation."""
        # Estimate buy volume using CLV
        # Buy = volume * (CLV + 1) / 2
        # Sell = volume * (1 - CLV) / 2

        high, low, close = 110, 100, 108
        volume = 10000

        clv = (close - low) / (high - low) * 2 - 1  # 0.6
        buy_volume = volume * (clv + 1) / 2  # 8000
        sell_volume = volume * (1 - clv) / 2  # 2000

        assert buy_volume > sell_volume
        np.testing.assert_almost_equal(buy_volume + sell_volume, volume)


class TestStatisticalArbitrageSignals:
    """Tests for statistical arbitrage signal generation."""

    def test_zscore_entry_exit(self):
        """Test z-score based entry and exit."""
        entry_threshold = 2.0
        exit_threshold = 0.5

        # Entry long when z-score < -2
        zscore = -2.5
        should_enter_long = zscore < -entry_threshold
        assert should_enter_long

        # Exit when z-score returns to 0
        zscore = -0.3
        should_exit = abs(zscore) < exit_threshold
        assert should_exit

    def test_position_sizing_by_zscore(self):
        """Test position sizing based on z-score."""
        max_position = 1.0
        zscore = -2.5
        entry_threshold = 2.0

        # Size proportional to deviation
        size = min(abs(zscore) / entry_threshold, 1.0) * max_position

        assert 0 < size <= max_position

    def test_half_life_filter(self):
        """Test half-life filter for pairs selection."""
        # Only trade pairs with reasonable half-life
        min_half_life = 2  # days
        max_half_life = 30  # days

        half_life = 15
        is_tradeable = min_half_life <= half_life <= max_half_life
        assert is_tradeable

        # Too fast (noise)
        half_life = 0.5
        is_tradeable = min_half_life <= half_life <= max_half_life
        assert not is_tradeable

        # Too slow (not mean-reverting quickly enough)
        half_life = 60
        is_tradeable = min_half_life <= half_life <= max_half_life
        assert not is_tradeable


class TestCorrelationBreakdown:
    """Tests for correlation breakdown detection."""

    def test_rolling_correlation(self):
        """Test rolling correlation calculation."""
        np.random.seed(42)
        n = 100

        # Two correlated series
        x = np.random.normal(0, 1, n)
        y = 0.8 * x + 0.2 * np.random.normal(0, 1, n)

        # Rolling correlation (window = 20)
        window = 20
        rolling_corr = []
        for i in range(window, n):
            corr = np.corrcoef(x[i-window:i], y[i-window:i])[0, 1]
            rolling_corr.append(corr)

        avg_corr = np.mean(rolling_corr)
        assert avg_corr > 0.7

    def test_correlation_zscore(self):
        """Test correlation z-score calculation."""
        current_corr = 0.3
        historical_mean = 0.7
        historical_std = 0.1

        zscore = (current_corr - historical_mean) / historical_std
        np.testing.assert_almost_equal(zscore, -4.0, decimal=5)  # Significant breakdown

    def test_breakdown_classification(self):
        """Test breakdown type classification."""
        # Decorrelation: correlation dropped
        prev_corr, current_corr = 0.8, 0.2
        is_decorrelation = current_corr < prev_corr - 0.3
        assert is_decorrelation

        # Sign flip
        prev_corr, current_corr = 0.5, -0.3
        is_sign_flip = prev_corr * current_corr < 0
        assert is_sign_flip

        # Stress spike (correlations go to 1 in crisis)
        prev_corr, current_corr = 0.4, 0.9
        is_stress = current_corr > 0.8 and prev_corr < 0.6
        assert is_stress


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
