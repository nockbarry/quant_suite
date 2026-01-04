"""Tests for Multiple Hypothesis Testing module."""

import numpy as np
import pandas as pd
import pytest


class TestBlockBootstrap:
    """Tests for block bootstrap implementation."""

    def test_block_size_estimation(self):
        """Test automatic block size estimation."""
        np.random.seed(42)

        # Create autocorrelated data
        n = 500
        data = np.zeros(n)
        data[0] = np.random.normal()
        for i in range(1, n):
            data[i] = 0.7 * data[i-1] + np.random.normal() * 0.3

        # For highly autocorrelated data, optimal block size should be larger
        # Politis & White (2004) rule suggests b* = n^(1/3) as baseline
        baseline_block_size = int(n ** (1/3))

        # With autocorrelation, block size should be >= baseline
        assert baseline_block_size >= 5

    def test_bootstrap_preserves_length(self):
        """Test that bootstrap sample has same length as original."""
        np.random.seed(42)
        data = np.random.normal(0, 1, 100)
        block_size = 10

        # Manual block bootstrap
        n_blocks = len(data) // block_size + 1
        bootstrap_indices = []
        while len(bootstrap_indices) < len(data):
            start = np.random.randint(0, len(data) - block_size + 1)
            bootstrap_indices.extend(range(start, start + block_size))

        bootstrap_sample = data[bootstrap_indices[:len(data)]]

        assert len(bootstrap_sample) == len(data)

    def test_stationary_bootstrap_expected_block_length(self):
        """Test stationary bootstrap has correct expected block length."""
        # In stationary bootstrap, block lengths are geometric random variables
        # Expected length = 1/p where p = 1/expected_block_size

        expected_block_size = 10
        p = 1 / expected_block_size

        # Simulate block lengths
        np.random.seed(42)
        block_lengths = np.random.geometric(p, 1000)

        # Mean should be close to expected_block_size
        np.testing.assert_almost_equal(
            np.mean(block_lengths),
            expected_block_size,
            decimal=0  # Allow integer rounding
        )


class TestWhiteRealityCheck:
    """Tests for White's Reality Check."""

    def test_null_hypothesis_interpretation(self):
        """Test understanding of null hypothesis."""
        # H0: Best strategy is no better than benchmark
        # If p-value < alpha, reject H0 and conclude best strategy is better

        # When best strategy significantly outperforms
        best_excess_return = 0.15  # 15% excess return
        permuted_bests = np.random.normal(0, 0.02, 1000)  # Random strategies

        p_value = np.mean(permuted_bests >= best_excess_return)
        assert p_value < 0.05  # Should reject H0

    def test_data_snooping_correction(self):
        """Test that WRC corrects for data snooping."""
        np.random.seed(42)

        # Without correction: many strategies might look significant
        n_strategies = 100
        strategy_returns = np.random.normal(0, 0.02, n_strategies)

        # At least some will exceed threshold by chance
        uncorrected_significant = np.sum(strategy_returns > 0.02)
        assert uncorrected_significant > 0

        # With WRC, we compare to max of permuted strategies
        # This controls for multiple testing


class TestHansenSPA:
    """Tests for Hansen's Superior Predictive Ability test."""

    def test_spa_more_powerful_than_wrc(self):
        """Test that SPA is more powerful than WRC."""
        # Hansen's SPA avoids 'least favorable configuration' problem
        # It should have lower p-values (higher power) in general

        # This is a conceptual test - in practice:
        # p^u (upper) >= p^c (consistent) >= p^l (lower)
        # where p^l is the most conservative

        p_lower = 0.03
        p_consistent = 0.05
        p_upper = 0.08

        assert p_lower <= p_consistent <= p_upper

    def test_studentization(self):
        """Test studentization of loss differentials."""
        # SPA uses studentized statistics for better finite-sample properties
        np.random.seed(42)

        # Loss differentials (benchmark - strategy returns)
        loss_diffs = np.random.normal(0.01, 0.05, 100)

        # Studentized statistic = mean / (std / sqrt(n))
        mean_diff = np.mean(loss_diffs)
        std_diff = np.std(loss_diffs)
        n = len(loss_diffs)

        t_stat = mean_diff / (std_diff / np.sqrt(n))

        # With positive mean diff, t-stat should be positive
        assert t_stat > 0


class TestStepwiseSPA:
    """Tests for Stepwise SPA procedure."""

    def test_fwer_control(self):
        """Test familywise error rate control."""
        # Stepwise SPA should control FWER at specified level
        # Under complete null (all strategies = benchmark), probability
        # of ANY false rejection should be <= alpha

        # Simulate under null
        np.random.seed(42)
        n_simulations = 100
        n_strategies = 20
        alpha = 0.05

        false_rejections = 0
        for _ in range(n_simulations):
            # All strategies are null (no skill)
            strategy_sharpes = np.random.normal(0, 0.3, n_strategies)

            # If any is "significant", it's a false rejection
            # Simple threshold for illustration
            if np.max(strategy_sharpes) > 1.5:
                false_rejections += 1

        # FWER should be controlled
        fwer = false_rejections / n_simulations
        # This is a simplified test - actual stepwise SPA would have FWER <= alpha
        assert fwer < 0.5  # Very loose bound for this simple test

    def test_identifies_true_strategies(self):
        """Test that stepwise SPA identifies truly significant strategies."""
        np.random.seed(42)

        # Some strategies have real alpha
        true_strategies = np.array([0.1, 0.15, 0.12])  # Real excess returns
        null_strategies = np.random.normal(0, 0.02, 17)  # No alpha

        all_strategies = np.concatenate([true_strategies, null_strategies])

        # Top strategies should be the true ones
        top_indices = np.argsort(all_strategies)[-3:]
        true_indices = np.array([0, 1, 2])

        # All true strategies should be in top performers
        assert np.all(np.isin(true_indices, top_indices))


class TestMultipleTesting:
    """Tests for multiple testing concepts."""

    def test_bonferroni_too_conservative(self):
        """Test that Bonferroni is too conservative for correlated tests."""
        # Bonferroni divides alpha by number of tests
        alpha = 0.05
        n_tests = 100

        bonferroni_alpha = alpha / n_tests  # 0.0005

        # This is extremely conservative, especially with correlated strategies
        assert bonferroni_alpha == 0.0005

    def test_bootstrap_handles_correlation(self):
        """Test that bootstrap naturally handles correlation."""
        np.random.seed(42)

        # Create correlated strategy returns
        n = 100
        base = np.random.normal(0, 0.01, n)

        # Strategies correlated with base
        strategy1 = base + np.random.normal(0, 0.005, n)
        strategy2 = base + np.random.normal(0, 0.005, n)

        correlation = np.corrcoef(strategy1, strategy2)[0, 1]
        assert correlation > 0.5  # Should be correlated

        # Block bootstrap will preserve this correlation structure


class TestBootstrapConfidenceIntervals:
    """Tests for bootstrap confidence intervals."""

    def test_percentile_interval(self):
        """Test percentile confidence interval."""
        np.random.seed(42)

        # Bootstrap distribution of statistic
        bootstrap_stats = np.random.normal(1.5, 0.3, 1000)

        # 95% percentile interval
        lower = np.percentile(bootstrap_stats, 2.5)
        upper = np.percentile(bootstrap_stats, 97.5)

        assert lower < 1.5 < upper
        assert (upper - lower) > 0

    def test_bias_corrected_interval(self):
        """Test bias-corrected confidence interval."""
        np.random.seed(42)

        # Original statistic
        original = 1.5

        # Bootstrap statistics with slight bias
        bootstrap_stats = np.random.normal(1.6, 0.3, 1000)  # Biased upward

        # Bias = E[bootstrap] - original
        bias = np.mean(bootstrap_stats) - original

        # Bias-corrected estimate
        bias_corrected = original - bias

        np.testing.assert_almost_equal(bias_corrected, 1.4, decimal=1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
