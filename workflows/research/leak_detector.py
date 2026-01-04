"""
Data Leakage Detection for Backtesting

Automated detection of look-ahead bias and other forms of data leakage
that can inflate backtest performance.

Key checks:
1. Feature timing - features don't correlate with future targets
2. Walk-forward integrity - proper gap between train/test
3. Signal execution lag - signals use lagged data
4. Target computation - no future data in target at training time
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Callable, Optional
import warnings


@dataclass
class LeakageReport:
    """Report from leak detection analysis."""
    is_clean: bool
    issues: list[str]
    warnings: list[str]
    details: dict

    def __str__(self) -> str:
        status = "CLEAN" if self.is_clean else "LEAKAGE DETECTED"
        lines = [f"\n{'='*60}", f"LEAK DETECTION REPORT: {status}", "="*60]

        if self.issues:
            lines.append("\nCRITICAL ISSUES:")
            for issue in self.issues:
                lines.append(f"  - {issue}")

        if self.warnings:
            lines.append("\nWARNINGS:")
            for warn in self.warnings:
                lines.append(f"  - {warn}")

        if not self.issues and not self.warnings:
            lines.append("\nNo issues found. Backtest appears clean.")

        return "\n".join(lines)


class LeakDetector:
    """
    Automated detection of look-ahead bias and data leakage.

    Usage:
        detector = LeakDetector()
        report = detector.run_all_checks(features, target, positions, df)
        print(report)
    """

    def __init__(self, target_horizon: int = 5, significance_threshold: float = 1.5):
        """
        Initialize leak detector.

        Args:
            target_horizon: Number of days for forward return target
            significance_threshold: Correlation ratio threshold for flagging
        """
        self.target_horizon = target_horizon
        self.significance_threshold = significance_threshold

    def test_feature_timing(
        self,
        features: pd.DataFrame,
        target: pd.Series,
    ) -> dict:
        """
        Verify features don't have suspicious correlations with future targets.

        If features at time t correlate MORE with target at time t than with
        target at time t-5, this suggests look-ahead bias.

        Returns:
            Dictionary with correlation analysis per feature
        """
        results = {}
        suspicious_features = []

        for col in features.columns:
            feature = features[col].dropna()
            aligned_target = target.reindex(feature.index).dropna()
            common_idx = feature.index.intersection(aligned_target.index)

            if len(common_idx) < 50:
                continue

            feature = feature.loc[common_idx]
            current_target = aligned_target.loc[common_idx]

            # Correlation with current target (what model sees)
            corr_current = feature.corr(current_target)

            # Correlation with lagged target (what's "natural")
            past_target = aligned_target.shift(self.target_horizon).loc[common_idx].dropna()
            if len(past_target) > 50:
                corr_past = feature.loc[past_target.index].corr(past_target)
            else:
                corr_past = 0

            # Red flag: If correlation with current > past by large margin
            is_suspicious = (
                abs(corr_current) > 0.1 and
                abs(corr_current) > abs(corr_past) * self.significance_threshold
            )

            results[col] = {
                'corr_with_current_target': round(corr_current, 4),
                'corr_with_past_target': round(corr_past, 4) if corr_past else None,
                'suspicious': is_suspicious,
            }

            if is_suspicious:
                suspicious_features.append(col)

        return {
            'feature_results': results,
            'suspicious_features': suspicious_features,
            'has_issues': len(suspicious_features) > 0,
        }

    def test_walk_forward_integrity(
        self,
        train_end_idx: int,
        test_start_idx: int,
        target_horizon: int = None,
    ) -> dict:
        """
        Verify no overlap between train and test+horizon.

        The training target at train_end uses price data up to train_end + horizon.
        This must not overlap with the test period.
        """
        horizon = target_horizon or self.target_horizon
        gap = test_start_idx - train_end_idx

        is_valid = gap >= horizon

        return {
            'is_valid': is_valid,
            'gap_days': gap,
            'required_gap': horizon,
            'message': (
                f"Gap of {gap} days is {'sufficient' if is_valid else 'INSUFFICIENT'} "
                f"(need >= {horizon})"
            )
        }

    def test_signal_execution_lag(
        self,
        positions: pd.Series,
        signals: pd.Series = None,
    ) -> dict:
        """
        Verify that positions are properly lagged from signals.

        If positions at time t are based on signals at time t,
        this means we're using data that wouldn't be available for trading.
        """
        if signals is None:
            # Can't test without original signals
            return {'status': 'skipped', 'reason': 'No signal series provided'}

        # Check if positions appear to be lagged
        corr_same_day = positions.corr(signals)
        corr_lagged = positions.corr(signals.shift(1))

        # If same-day correlation is much higher, positions might not be lagged
        is_properly_lagged = corr_lagged > corr_same_day * 0.9

        return {
            'corr_same_day': round(corr_same_day, 4),
            'corr_lagged': round(corr_lagged, 4),
            'is_properly_lagged': is_properly_lagged,
            'message': (
                "Positions appear properly lagged" if is_properly_lagged
                else "WARNING: Positions may not be properly lagged from signals"
            )
        }

    def test_target_computation(
        self,
        df: pd.DataFrame,
        target: pd.Series,
        horizon: int = None,
    ) -> dict:
        """
        Verify target is computed correctly.

        Target at time t should be the return from close[t] to close[t+horizon],
        not using any data after close[t] in its computation.
        """
        horizon = horizon or self.target_horizon

        # Recompute target the correct way
        expected_target = (df['close'].shift(-horizon) / df['close'] - 1 > 0).astype(int)

        # Check alignment
        common_idx = target.dropna().index.intersection(expected_target.dropna().index)
        if len(common_idx) < 50:
            return {'status': 'skipped', 'reason': 'Insufficient data for comparison'}

        match_rate = (target.loc[common_idx] == expected_target.loc[common_idx]).mean()

        is_correct = match_rate > 0.99  # Allow tiny floating point differences

        return {
            'match_rate': round(match_rate, 4),
            'is_correct': is_correct,
            'message': (
                f"Target computation appears correct (match rate: {match_rate:.2%})"
                if is_correct else
                f"WARNING: Target may be incorrectly computed (match rate: {match_rate:.2%})"
            )
        }

    def test_returns_timing(
        self,
        positions: pd.Series,
        returns: pd.Series,
        df: pd.DataFrame,
    ) -> dict:
        """
        Check if returns are computed with proper execution timing.

        For realistic execution:
        - Signal at close[t] -> Execute at open[t+1]
        - Returns should be based on open[t+1] to open[t+2], not close-to-close
        """
        if 'open' not in df.columns:
            return {'status': 'skipped', 'reason': 'No open prices available'}

        # Compute what returns SHOULD be with proper timing
        open_returns = df['open'].pct_change()
        close_returns = df['close'].pct_change()

        # Compare correlation with actual returns
        corr_with_open = returns.corr(positions.shift(1) * open_returns)
        corr_with_close = returns.corr(positions.shift(1) * close_returns)

        # If returns correlate more with close-to-close, execution timing may be unrealistic
        uses_open_prices = corr_with_open > corr_with_close * 0.9

        return {
            'corr_with_open_based': round(corr_with_open, 4) if not pd.isna(corr_with_open) else None,
            'corr_with_close_based': round(corr_with_close, 4) if not pd.isna(corr_with_close) else None,
            'uses_realistic_timing': uses_open_prices,
            'message': (
                "Returns use realistic execution timing (open prices)"
                if uses_open_prices else
                "WARNING: Returns may use unrealistic close-to-close timing"
            )
        }

    def run_all_checks(
        self,
        features: pd.DataFrame,
        target: pd.Series,
        positions: pd.Series,
        df: pd.DataFrame,
        returns: pd.Series = None,
        signals: pd.Series = None,
    ) -> LeakageReport:
        """
        Run comprehensive leak detection suite.

        Args:
            features: Feature DataFrame
            target: Target series
            positions: Position series (after any lagging)
            df: Price DataFrame with OHLCV
            returns: Strategy returns (optional)
            signals: Original signals before lagging (optional)

        Returns:
            LeakageReport with findings
        """
        issues = []
        warnings_list = []
        details = {}

        # 1. Feature timing check
        try:
            feature_check = self.test_feature_timing(features, target)
            details['feature_timing'] = feature_check
            if feature_check['has_issues']:
                issues.append(
                    f"Suspicious feature correlations detected in: "
                    f"{', '.join(feature_check['suspicious_features'][:5])}"
                )
        except Exception as e:
            warnings_list.append(f"Feature timing check failed: {e}")

        # 2. Signal lag check
        if signals is not None:
            try:
                lag_check = self.test_signal_execution_lag(positions, signals)
                details['signal_lag'] = lag_check
                if not lag_check.get('is_properly_lagged', True):
                    issues.append("Positions may not be properly lagged from signals")
            except Exception as e:
                warnings_list.append(f"Signal lag check failed: {e}")

        # 3. Target computation check
        try:
            target_check = self.test_target_computation(df, target)
            details['target_computation'] = target_check
            if target_check.get('status') != 'skipped' and not target_check.get('is_correct', True):
                warnings_list.append("Target computation may be incorrect")
        except Exception as e:
            warnings_list.append(f"Target computation check failed: {e}")

        # 4. Returns timing check
        if returns is not None:
            try:
                timing_check = self.test_returns_timing(positions, returns, df)
                details['returns_timing'] = timing_check
                if timing_check.get('status') != 'skipped' and not timing_check.get('uses_realistic_timing', True):
                    warnings_list.append("Returns may use unrealistic execution timing")
            except Exception as e:
                warnings_list.append(f"Returns timing check failed: {e}")

        is_clean = len(issues) == 0

        return LeakageReport(
            is_clean=is_clean,
            issues=issues,
            warnings=warnings_list,
            details=details,
        )


def quick_leak_check(
    features: pd.DataFrame,
    target: pd.Series,
    target_horizon: int = 5,
) -> bool:
    """
    Quick check for obvious data leakage.

    Returns True if no obvious leaks detected, False otherwise.
    """
    detector = LeakDetector(target_horizon=target_horizon)
    check = detector.test_feature_timing(features, target)
    return not check['has_issues']


if __name__ == "__main__":
    # Example usage
    import yfinance as yf

    # Get sample data
    df = yf.download("AAPL", period="2y", progress=False)
    df.columns = [c.lower() for c in df.columns]

    # Create features (with proper shifting)
    features = pd.DataFrame(index=df.index)
    features['ret_5d'] = df['close'].pct_change(5).shift(1)
    features['ret_20d'] = df['close'].pct_change(20).shift(1)
    features['vol_20d'] = df['close'].pct_change().rolling(20).std().shift(1)

    # Create target
    target = (df['close'].shift(-5) / df['close'] - 1 > 0).astype(int)

    # Create simple positions
    momentum = df['close'].pct_change(20).shift(1)
    positions = pd.Series(0.0, index=df.index)
    positions[momentum > 0] = 1
    positions[momentum < 0] = -1
    positions = positions.shift(1).fillna(0)

    # Run leak detection
    detector = LeakDetector(target_horizon=5)
    report = detector.run_all_checks(
        features=features,
        target=target,
        positions=positions,
        df=df,
    )

    print(report)
