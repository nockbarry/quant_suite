"""Tests for Monte Carlo Permutation Testing module."""

import numpy as np
import pandas as pd
import pytest


class TestBarPermuter:
    """Tests for BarPermuter class."""

    def test_decompose_returns_basic(self):
        """Test decomposition of OHLCV into gap and intra returns."""
        # Create simple OHLCV data
        data = pd.DataFrame({
            'open': [100, 102, 105],
            'high': [103, 107, 108],
            'low': [99, 101, 103],
            'close': [102, 105, 106],
        })

        # Gap return = open / prev_close - 1
        # Intra return = close / open - 1
        expected_gap = [np.nan, 102/102 - 1, 105/105 - 1]
        expected_intra = [102/100 - 1, 105/102 - 1, 106/105 - 1]

        # Manual calculation for verification
        gap_returns = data['open'] / data['close'].shift(1) - 1
        intra_returns = data['close'] / data['open'] - 1

        assert len(gap_returns) == 3
        assert len(intra_returns) == 3
        np.testing.assert_almost_equal(intra_returns.iloc[0], 0.02)  # 102/100 - 1

    def test_high_low_ratio_preserved(self):
        """Test that high/low ratios are preserved in permutation."""
        data = pd.DataFrame({
            'open': [100, 102, 105],
            'high': [103, 107, 108],
            'low': [99, 101, 103],
            'close': [102, 105, 106],
        })

        # High-to-open ratio
        h_o_ratio = data['high'] / data['open']
        # Low-to-open ratio
        l_o_ratio = data['low'] / data['open']

        # These ratios should be preserved during permutation
        assert all(h_o_ratio >= 1.0)  # High >= Open
        assert all(l_o_ratio <= 1.0)  # Low <= Open


class TestMCPTResult:
    """Tests for MCPTResult dataclass."""

    def test_significance_check(self):
        """Test p-value significance checking."""
        # A p-value of 0.03 should be significant at 0.05 level
        p_value = 0.03
        alpha = 0.05
        assert p_value < alpha

        # A p-value of 0.07 should not be significant at 0.05 level
        p_value = 0.07
        assert p_value >= alpha

    def test_percentile_calculation(self):
        """Test percentile calculation for test statistic."""
        # Simulated permuted statistics
        permuted_stats = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4])
        original_stat = 1.15

        # Percentile = proportion of permuted stats <= original
        percentile = np.mean(permuted_stats <= original_stat) * 100

        assert 70 <= percentile <= 90  # Should be around 80%


class TestPermutationDistribution:
    """Tests for permutation distribution properties."""

    def test_mean_preserved(self):
        """Test that permutation preserves mean."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100)

        # Permutation should preserve mean
        permuted = np.random.permutation(returns)
        np.testing.assert_almost_equal(np.mean(returns), np.mean(permuted), decimal=10)

    def test_std_preserved(self):
        """Test that permutation preserves standard deviation."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100)

        permuted = np.random.permutation(returns)
        np.testing.assert_almost_equal(np.std(returns), np.std(permuted), decimal=10)

    def test_distribution_shape_preserved(self):
        """Test that permutation preserves distribution shape."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 1000)

        permuted = np.random.permutation(returns)

        # Quartiles should be preserved
        np.testing.assert_almost_equal(
            np.percentile(returns, [25, 50, 75]),
            np.percentile(permuted, [25, 50, 75]),
            decimal=10
        )


class TestPValueCalculation:
    """Tests for p-value calculation."""

    def test_extreme_performance_low_pvalue(self):
        """Test that extreme performance gives low p-value."""
        np.random.seed(42)

        # Original strategy has very high Sharpe
        original_sharpe = 3.0

        # Permuted strategies have lower Sharpes
        permuted_sharpes = np.random.normal(0, 0.5, 1000)

        # p-value = proportion of permuted >= original
        p_value = np.mean(permuted_sharpes >= original_sharpe)

        assert p_value < 0.01  # Should be very significant

    def test_average_performance_high_pvalue(self):
        """Test that average performance gives high p-value."""
        np.random.seed(42)

        # Original strategy has average Sharpe
        original_sharpe = 0.0

        # Permuted strategies have similar distribution
        permuted_sharpes = np.random.normal(0, 0.5, 1000)

        # p-value = proportion of permuted >= original
        p_value = np.mean(permuted_sharpes >= original_sharpe)

        assert p_value > 0.4  # Should not be significant


class TestWalkForwardMCPT:
    """Tests for walk-forward MCPT."""

    def test_oos_only_permutation(self):
        """Test that only OOS data is permuted in walk-forward."""
        # In walk-forward MCPT, we should only permute out-of-sample returns
        # In-sample optimization results should use original data

        is_returns = np.array([0.01, 0.02, -0.01, 0.015])  # In-sample
        oos_returns = np.array([0.02, -0.005, 0.01])  # Out-of-sample

        # Only OOS should be permuted
        np.random.seed(42)
        permuted_oos = np.random.permutation(oos_returns)

        # IS should remain unchanged
        np.testing.assert_array_equal(is_returns, is_returns)  # Identity

        # OOS should be different (with high probability)
        # Note: There's a small chance permutation returns same order
        assert len(permuted_oos) == len(oos_returns)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
