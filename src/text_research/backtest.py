"""
TextBacktester: Backtesting with Proper Text-to-Signal Temporal Alignment.

Ensures point-in-time safe backtesting for text-based strategies:
- signal_delay=1: Same-day text generates next-day trading signals
- Walk-forward validation with proper text temporal splits
- Feature information coefficient computation
- Lookahead bias detection and prevention

Key Methodology:
- Text available on day T can only inform signals for day T+1
- Train/test splits respect document availability dates
- Rolling window updates for embeddings/features
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Callable
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .corpus import TextCorpus
from .embedding_engine import EmbeddingEngine
from .feature_extractor import TextFeatureExtractor

logger = logging.getLogger(__name__)


@dataclass
class TextBacktestResult:
    """Results from text-based backtesting."""
    sharpe_ratio: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    avg_holding_days: float
    feature_ic: dict[str, float]  # Information coefficient per feature
    daily_returns: pd.Series = field(default_factory=pd.Series)
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)
    passed_lookahead_check: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""
    train_sharpe: float
    test_sharpe: float
    train_return: float
    test_return: float
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    feature_importance: dict[str, float]
    is_overfit: bool  # True if train >> test


class TextBacktester:
    """
    Backtesting engine with proper text-to-signal temporal alignment.

    Ensures that:
    1. Text available on day T only informs trades starting day T+1
    2. Walk-forward validation properly separates train/test text
    3. No future information leaks into signals

    Example Usage:
        backtester = TextBacktester(corpus, embedding_engine, feature_extractor)

        # Run walk-forward validation
        result = backtester.run_walk_forward(
            signal_generator=my_signal_fn,
            symbols=["AAPL", "GOOGL"],
            start_date=date(2024, 1, 1),
            end_date=date(2025, 12, 31),
            train_window=252,
            test_window=63
        )

        # Check for lookahead bias
        is_clean = backtester.validate_no_lookahead()
    """

    def __init__(
        self,
        corpus: TextCorpus,
        embedding_engine: EmbeddingEngine,
        feature_extractor: TextFeatureExtractor,
        signal_delay_days: int = 1,
        transaction_cost_bps: float = 10.0,
    ):
        """
        Initialize TextBacktester.

        Args:
            corpus: TextCorpus for document retrieval
            embedding_engine: EmbeddingEngine for embeddings
            feature_extractor: TextFeatureExtractor for features
            signal_delay_days: Days between text and signal (default 1)
            transaction_cost_bps: Transaction costs in basis points
        """
        self.corpus = corpus
        self.embeddings = embedding_engine
        self.features = feature_extractor
        self.signal_delay = signal_delay_days
        self.transaction_cost_bps = transaction_cost_bps

        # Logging for lookahead detection
        self._access_log: list[dict] = []

    def run_backtest(
        self,
        signal_generator: Callable[[dict[str, float], str, date], float],
        symbols: list[str],
        start_date: date,
        end_date: date,
        price_data: pd.DataFrame | None = None,
    ) -> TextBacktestResult:
        """
        Run a simple backtest on text-based signals.

        Args:
            signal_generator: Function(features, symbol, date) -> signal [-1, 1]
            symbols: List of symbols to trade
            start_date: Backtest start date
            end_date: Backtest end date
            price_data: Optional price DataFrame (fetched if not provided)

        Returns:
            TextBacktestResult with performance metrics
        """
        # Fetch price data if not provided
        if price_data is None:
            price_data = self._fetch_prices(symbols, start_date, end_date)

        if price_data.empty:
            return self._empty_result("No price data available")

        # Generate signals for each day
        all_signals = []
        all_returns = []

        # Create business day date range
        trading_dates = pd.bdate_range(start_date, end_date)

        for i, trade_date in enumerate(trading_dates[:-1]):
            signal_date = trade_date.date()

            # Text analysis date is signal_delay days before trade
            text_date = signal_date - timedelta(days=self.signal_delay)

            for symbol in symbols:
                # Get features as of text_date (point-in-time safe)
                features = self.features.compute_features(
                    symbol=symbol,
                    as_of_date=text_date,
                )

                # Log access for lookahead checking
                self._access_log.append({
                    "text_date": text_date,
                    "signal_date": signal_date,
                    "symbol": symbol,
                })

                # Generate signal
                try:
                    signal = signal_generator(features, symbol, signal_date)
                except Exception as e:
                    logger.debug(f"Signal generation failed for {symbol} on {signal_date}: {e}")
                    signal = 0.0

                if signal != 0 and not np.isnan(signal):
                    all_signals.append({
                        "date": signal_date,
                        "symbol": symbol,
                        "signal": signal,
                        "features": features,
                    })

                    # Compute return for this signal
                    next_date = trading_dates[i + 1].date()
                    if symbol in price_data.columns:
                        price_col = symbol
                    elif f"{symbol}_close" in price_data.columns:
                        price_col = f"{symbol}_close"
                    else:
                        continue

                    try:
                        entry_price = price_data.loc[str(signal_date), price_col]
                        exit_price = price_data.loc[str(next_date), price_col]

                        if pd.notna(entry_price) and pd.notna(exit_price):
                            raw_return = (exit_price - entry_price) / entry_price
                            signal_return = signal * raw_return

                            # Apply transaction costs
                            cost = self.transaction_cost_bps / 10000 * 2 * abs(signal)
                            net_return = signal_return - cost

                            all_returns.append({
                                "date": signal_date,
                                "symbol": symbol,
                                "return": net_return,
                                "raw_return": raw_return,
                                "signal": signal,
                            })
                    except (KeyError, IndexError):
                        continue

        # Compute metrics
        if not all_returns:
            return self._empty_result("No trades generated")

        returns_df = pd.DataFrame(all_returns)
        daily_returns = returns_df.groupby("date")["return"].sum()

        # Compute information coefficient for each feature
        feature_ic = self._compute_feature_ic(all_signals, all_returns)

        return TextBacktestResult(
            sharpe_ratio=self._compute_sharpe(daily_returns),
            total_return=float(daily_returns.sum()),
            annualized_return=float(daily_returns.mean() * 252),
            max_drawdown=self._compute_max_drawdown(daily_returns),
            win_rate=float((returns_df["return"] > 0).mean()),
            n_trades=len(returns_df),
            avg_holding_days=1.0,  # Single-day holds by design
            feature_ic=feature_ic,
            daily_returns=daily_returns,
            signals=pd.DataFrame(all_signals),
            passed_lookahead_check=self.validate_no_lookahead(),
        )

    def run_walk_forward(
        self,
        signal_generator: Callable[[dict[str, float], str, date], float],
        symbols: list[str],
        start_date: date,
        end_date: date,
        train_window: int = 252,
        test_window: int = 63,
        price_data: pd.DataFrame | None = None,
    ) -> list[WalkForwardResult]:
        """
        Run walk-forward validation with proper text temporal splits.

        Args:
            signal_generator: Function(features, symbol, date) -> signal
            symbols: List of symbols to trade
            start_date: Start date for validation
            end_date: End date for validation
            train_window: Training window in trading days
            test_window: Testing window in trading days
            price_data: Optional price DataFrame

        Returns:
            List of WalkForwardResult for each fold
        """
        results = []

        # Create date ranges
        trading_dates = pd.bdate_range(start_date, end_date)

        if len(trading_dates) < train_window + test_window:
            logger.warning("Insufficient data for walk-forward validation")
            return results

        # Fetch price data if not provided
        if price_data is None:
            price_data = self._fetch_prices(symbols, start_date, end_date)

        # Walk forward through time
        current_idx = train_window

        while current_idx + test_window <= len(trading_dates):
            # Define train/test periods
            train_start = trading_dates[current_idx - train_window].date()
            train_end = trading_dates[current_idx - 1].date()
            test_start = trading_dates[current_idx].date()
            test_end = trading_dates[min(current_idx + test_window - 1, len(trading_dates) - 1)].date()

            logger.info(f"Walk-forward fold: train {train_start} to {train_end}, test {test_start} to {test_end}")

            # Run backtest on train period
            train_result = self.run_backtest(
                signal_generator=signal_generator,
                symbols=symbols,
                start_date=train_start,
                end_date=train_end,
                price_data=price_data,
            )

            # Run backtest on test period
            test_result = self.run_backtest(
                signal_generator=signal_generator,
                symbols=symbols,
                start_date=test_start,
                end_date=test_end,
                price_data=price_data,
            )

            # Detect overfitting
            is_overfit = (
                train_result.sharpe_ratio > 0
                and test_result.sharpe_ratio < train_result.sharpe_ratio * 0.5
            )

            results.append(WalkForwardResult(
                train_sharpe=train_result.sharpe_ratio,
                test_sharpe=test_result.sharpe_ratio,
                train_return=train_result.total_return,
                test_return=test_result.total_return,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                feature_importance=train_result.feature_ic,
                is_overfit=is_overfit,
            ))

            # Advance by test_window
            current_idx += test_window

        return results

    def compute_information_coefficient(
        self,
        feature_name: str,
        symbols: list[str],
        start_date: date,
        end_date: date,
        price_data: pd.DataFrame | None = None,
    ) -> float:
        """
        Compute information coefficient for a single text feature.

        IC measures the correlation between feature values and forward returns.

        Args:
            feature_name: Name of feature to test
            symbols: List of symbols
            start_date: Start date
            end_date: End date
            price_data: Optional price DataFrame

        Returns:
            Information coefficient (correlation)
        """
        if price_data is None:
            price_data = self._fetch_prices(symbols, start_date, end_date)

        if price_data.empty:
            return np.nan

        feature_values = []
        forward_returns = []

        trading_dates = pd.bdate_range(start_date, end_date)

        for i, signal_date in enumerate(trading_dates[:-1]):
            text_date = signal_date.date() - timedelta(days=self.signal_delay)

            for symbol in symbols:
                # Get feature value
                features = self.features.compute_features(
                    symbol=symbol,
                    as_of_date=text_date,
                    features=[feature_name],
                )

                feature_value = features.get(feature_name)
                if feature_value is None or np.isnan(feature_value):
                    continue

                # Get forward return
                try:
                    if symbol in price_data.columns:
                        price_col = symbol
                    elif f"{symbol}_close" in price_data.columns:
                        price_col = f"{symbol}_close"
                    else:
                        continue

                    current_price = price_data.loc[str(signal_date.date()), price_col]
                    next_price = price_data.loc[str(trading_dates[i + 1].date()), price_col]

                    if pd.notna(current_price) and pd.notna(next_price):
                        forward_return = (next_price - current_price) / current_price
                        feature_values.append(feature_value)
                        forward_returns.append(forward_return)
                except (KeyError, IndexError):
                    continue

        if len(feature_values) < 10:
            return np.nan

        # Compute correlation
        return float(np.corrcoef(feature_values, forward_returns)[0, 1])

    def validate_no_lookahead(self) -> bool:
        """
        Verify no future information leakage in the backtest.

        Checks that:
        1. All text access dates are before signal dates
        2. Signal delay is properly applied

        Returns:
            True if no lookahead bias detected
        """
        for access in self._access_log:
            text_date = access["text_date"]
            signal_date = access["signal_date"]

            # Text date must be before signal date
            if text_date >= signal_date:
                logger.error(
                    f"Lookahead bias detected: text_date {text_date} >= signal_date {signal_date}"
                )
                return False

            # Check signal delay
            expected_signal_date = text_date + timedelta(days=self.signal_delay)
            if signal_date < expected_signal_date:
                logger.error(
                    f"Signal delay violation: signal_date {signal_date} < expected {expected_signal_date}"
                )
                return False

        return True

    def analyze_feature_decay(
        self,
        feature_name: str,
        symbols: list[str],
        start_date: date,
        end_date: date,
        max_horizon: int = 10,
    ) -> dict[int, float]:
        """
        Analyze how feature IC decays over different prediction horizons.

        Useful for understanding signal persistence.

        Args:
            feature_name: Feature to analyze
            symbols: List of symbols
            start_date: Start date
            end_date: End date
            max_horizon: Maximum prediction horizon in days

        Returns:
            Dictionary mapping horizon to IC
        """
        price_data = self._fetch_prices(symbols, start_date, end_date)
        ic_by_horizon = {}

        for horizon in range(1, max_horizon + 1):
            # Temporarily change signal delay
            original_delay = self.signal_delay
            self.signal_delay = horizon

            ic = self.compute_information_coefficient(
                feature_name=feature_name,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                price_data=price_data,
            )

            ic_by_horizon[horizon] = ic

            # Restore original delay
            self.signal_delay = original_delay

        return ic_by_horizon

    def generate_backtest_report(
        self,
        result: TextBacktestResult,
        output_path: str | Path | None = None,
    ) -> str:
        """
        Generate a markdown report from backtest results.

        Args:
            result: TextBacktestResult to report on
            output_path: Optional path to save report

        Returns:
            Report as markdown string
        """
        lines = [
            "# Text Research Backtest Report",
            "",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Performance Summary",
            "",
            f"- **Sharpe Ratio**: {result.sharpe_ratio:.2f}",
            f"- **Total Return**: {result.total_return:.2%}",
            f"- **Annualized Return**: {result.annualized_return:.2%}",
            f"- **Max Drawdown**: {result.max_drawdown:.2%}",
            f"- **Win Rate**: {result.win_rate:.2%}",
            f"- **Number of Trades**: {result.n_trades}",
            "",
            "## Lookahead Check",
            "",
            f"- **Passed**: {'Yes' if result.passed_lookahead_check else 'NO - BIAS DETECTED'}",
            "",
        ]

        if result.feature_ic:
            lines.extend([
                "## Feature Information Coefficients",
                "",
                "| Feature | IC |",
                "|---------|-----|",
            ])
            for feature, ic in sorted(result.feature_ic.items(), key=lambda x: abs(x[1]), reverse=True):
                lines.append(f"| {feature} | {ic:.4f} |")
            lines.append("")

        if result.warnings:
            lines.extend([
                "## Warnings",
                "",
            ])
            for warning in result.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        report = "\n".join(lines)

        if output_path:
            Path(output_path).write_text(report)

        return report

    # ==================== Helper Methods ====================

    def _empty_result(self, reason: str) -> TextBacktestResult:
        """Create empty result with warning."""
        return TextBacktestResult(
            sharpe_ratio=0.0,
            total_return=0.0,
            annualized_return=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            n_trades=0,
            avg_holding_days=0.0,
            feature_ic={},
            warnings=[reason],
        )

    def _fetch_prices(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch price data for symbols."""
        try:
            import yfinance as yf

            # Add buffer for computing returns
            buffer_start = start_date - timedelta(days=10)

            data = yf.download(
                symbols,
                start=buffer_start.strftime("%Y-%m-%d"),
                end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                progress=False,
            )

            if data.empty:
                return pd.DataFrame()

            # Extract close prices
            if len(symbols) == 1:
                prices = data["Close"].to_frame(name=symbols[0])
            else:
                prices = data["Close"]

            prices.index = pd.to_datetime(prices.index).strftime("%Y-%m-%d")
            return prices

        except Exception as e:
            logger.warning(f"Failed to fetch prices: {e}")
            return pd.DataFrame()

    def _compute_sharpe(self, returns: pd.Series) -> float:
        """Compute annualized Sharpe ratio."""
        if returns.empty or returns.std() == 0:
            return 0.0
        return float(returns.mean() / returns.std() * np.sqrt(252))

    def _compute_max_drawdown(self, returns: pd.Series) -> float:
        """Compute maximum drawdown."""
        if returns.empty:
            return 0.0

        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max

        return float(drawdown.min())

    def _compute_feature_ic(
        self,
        signals: list[dict],
        returns: list[dict],
    ) -> dict[str, float]:
        """Compute IC for each feature from signal/return pairs."""
        if not signals or not returns:
            return {}

        # Create lookup for returns
        return_lookup = {
            (r["date"], r["symbol"]): r["raw_return"]
            for r in returns
        }

        # Collect feature values and corresponding returns
        feature_data: dict[str, tuple[list, list]] = {}

        for sig in signals:
            key = (sig["date"], sig["symbol"])
            if key not in return_lookup:
                continue

            fwd_return = return_lookup[key]

            for feature_name, feature_value in sig.get("features", {}).items():
                if feature_value is None or np.isnan(feature_value):
                    continue

                if feature_name not in feature_data:
                    feature_data[feature_name] = ([], [])

                feature_data[feature_name][0].append(feature_value)
                feature_data[feature_name][1].append(fwd_return)

        # Compute IC for each feature
        feature_ic = {}
        for feature_name, (values, rets) in feature_data.items():
            if len(values) >= 10:
                try:
                    ic = np.corrcoef(values, rets)[0, 1]
                    feature_ic[feature_name] = float(ic) if not np.isnan(ic) else 0.0
                except Exception:
                    feature_ic[feature_name] = 0.0

        return feature_ic

    def clear_access_log(self) -> None:
        """Clear the access log for lookahead checking."""
        self._access_log = []

    def __repr__(self) -> str:
        """String representation."""
        return f"TextBacktester(signal_delay={self.signal_delay}d, cost={self.transaction_cost_bps}bps)"
