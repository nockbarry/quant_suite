#!/usr/bin/env python3
"""
Commodity Mean-Reversion Strategy Validation Pipeline

Validates mean-reversion strategies on commodity ETFs with:
1. Data acquisition (via yfinance)
2. Z-score analysis
3. Full backtest with transaction costs
4. MCPT statistical validation
5. Walk-forward out-of-sample testing
6. Bootstrap confidence intervals
7. Regime analysis

Usage:
    # Full validation on all commodities
    PYTHONPATH=. python scripts/validate_commodity_mean_rev.py

    # Specific commodities
    PYTHONPATH=. python scripts/validate_commodity_mean_rev.py --symbols SLV PPLT

    # Quick test mode
    PYTHONPATH=. python scripts/validate_commodity_mean_rev.py --quick

    # Custom parameters
    PYTHONPATH=. python scripts/validate_commodity_mean_rev.py \
        --symbols SLV PPLT CPER \
        --lookback 20 \
        --threshold 2.0 \
        --days 730

Author: Claude Code
Created: 2026-01-05
"""

import argparse
import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Results from validating a single commodity strategy."""

    symbol: str
    lookback_window: int
    entry_threshold: float

    # Z-score analysis
    current_zscore: float
    zscore_percentile: float
    zscore_state: str

    # Backtest results
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    avg_holding_days: float

    # MCPT validation
    mcpt_p_value: float
    mcpt_significant: bool

    # Walk-forward results
    oos_sharpe: float
    oos_degradation: float
    walk_forward_stable: bool

    # Bootstrap CI
    sharpe_ci_lower: float
    sharpe_ci_upper: float

    # Overall
    production_ready: bool
    notes: str = ""


class CommodityValidator:
    """Validates commodity mean-reversion strategies."""

    COMMODITY_INFO = {
        "SLV": {"name": "Silver", "type": "precious_metal"},
        "PPLT": {"name": "Platinum", "type": "precious_metal"},
        "CPER": {"name": "Copper", "type": "industrial_metal"},
        "GLD": {"name": "Gold", "type": "precious_metal"},
        "USO": {"name": "Oil", "type": "energy"},
        "UNG": {"name": "Natural Gas", "type": "energy"},
        "DBA": {"name": "Agriculture", "type": "agriculture"},
    }

    def __init__(
        self,
        lookback_window: int = 20,
        entry_threshold: float = 2.0,
        transaction_cost_bps: float = 10,
    ):
        self.lookback_window = lookback_window
        self.entry_threshold = entry_threshold
        self.transaction_cost_bps = transaction_cost_bps

    def fetch_data(self, symbol: str, days: int = 730) -> pd.DataFrame:
        """Fetch historical data for a commodity ETF."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)  # Extra buffer

        logger.info(f"Fetching {symbol} data from {start_date.date()} to {end_date.date()}")

        data = yf.download(symbol, start=start_date, end=end_date, progress=False)

        if len(data) < 100:
            raise ValueError(f"Insufficient data for {symbol}: only {len(data)} rows")

        # Handle multi-level columns from yfinance
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        logger.info(f"Fetched {len(data)} rows for {symbol}")
        return data

    def compute_zscore(self, data: pd.DataFrame) -> pd.Series:
        """Compute z-score series."""
        close = data["Close"]
        rolling_mean = close.rolling(self.lookback_window).mean()
        rolling_std = close.rolling(self.lookback_window).std()
        return (close - rolling_mean) / rolling_std

    def analyze_current_state(self, data: pd.DataFrame) -> dict:
        """Analyze current z-score state."""
        zscore = self.compute_zscore(data)
        current = zscore.iloc[-1]
        percentile = (zscore.dropna() < current).mean() * 100

        if current < -self.entry_threshold:
            state = "oversold"
        elif current > self.entry_threshold:
            state = "overbought"
        elif current < -1.0:
            state = "slightly_oversold"
        elif current > 1.0:
            state = "slightly_overbought"
        else:
            state = "neutral"

        return {
            "current_zscore": current,
            "percentile": percentile,
            "state": state,
        }

    def backtest(
        self,
        data: pd.DataFrame,
        min_holding_days: int = 2,
    ) -> dict:
        """
        Run vectorized backtest with mean-reversion signals.

        Strategy:
        - Long when z-score < -threshold (oversold)
        - Short when z-score > +threshold (overbought)
        - Exit when z-score crosses 0 or after max_holding_days
        """
        close = data["Close"].copy()
        zscore = self.compute_zscore(data)
        returns = close.pct_change()

        # Generate raw signals
        signals = pd.Series(0, index=data.index)
        signals[zscore < -self.entry_threshold] = 1  # Long oversold
        signals[zscore > self.entry_threshold] = -1  # Short overbought

        # Apply minimum holding period
        position = pd.Series(0, index=data.index)
        entry_price = pd.Series(np.nan, index=data.index)
        holding_days_series = pd.Series(0, index=data.index)

        current_position = 0
        current_entry = np.nan
        days_held = 0

        for i in range(len(data)):
            idx = data.index[i]

            if current_position == 0:
                # Check for entry
                if signals.iloc[i] != 0:
                    current_position = signals.iloc[i]
                    current_entry = close.iloc[i]
                    days_held = 0
            else:
                days_held += 1

                # Check for exit (z-score crosses 0 OR max holding)
                z = zscore.iloc[i]
                should_exit = False

                if days_held >= min_holding_days:
                    # Mean reversion achieved (z-score back to 0)
                    if current_position == 1 and z >= 0:
                        should_exit = True
                    elif current_position == -1 and z <= 0:
                        should_exit = True
                    # Max holding period
                    elif days_held >= 15:
                        should_exit = True

                if should_exit:
                    current_position = 0
                    current_entry = np.nan
                    days_held = 0

            position.iloc[i] = current_position
            entry_price.iloc[i] = current_entry
            holding_days_series.iloc[i] = days_held

        # Calculate strategy returns
        strategy_returns = position.shift(1) * returns

        # Apply transaction costs
        position_changes = position.diff().abs()
        costs = position_changes * (self.transaction_cost_bps / 10000)
        strategy_returns = strategy_returns - costs

        # Drop NaN
        strategy_returns = strategy_returns.dropna()

        # Calculate metrics
        if len(strategy_returns) == 0 or strategy_returns.std() == 0:
            return {
                "total_return": 0,
                "sharpe_ratio": 0,
                "sortino_ratio": 0,
                "max_drawdown": 0,
                "win_rate": 0,
                "n_trades": 0,
                "avg_holding_days": 0,
                "returns": pd.Series(dtype=float),
            }

        total_return = (1 + strategy_returns).prod() - 1
        sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)

        # Sortino (downside deviation)
        downside = strategy_returns[strategy_returns < 0]
        if len(downside) > 0 and downside.std() > 0:
            sortino = strategy_returns.mean() / downside.std() * np.sqrt(252)
        else:
            sortino = sharpe

        # Max drawdown
        cumulative = (1 + strategy_returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_dd = drawdown.min()

        # Win rate
        trades = strategy_returns[strategy_returns != 0]
        win_rate = (trades > 0).mean() if len(trades) > 0 else 0

        # Trade count
        entries = (position.diff().abs() > 0) & (position != 0)
        n_trades = entries.sum()

        # Average holding days
        holding_periods = holding_days_series[position != 0]
        avg_holding = holding_periods.mean() if len(holding_periods) > 0 else 0

        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "n_trades": int(n_trades),
            "avg_holding_days": avg_holding,
            "returns": strategy_returns,
        }

    def run_mcpt(
        self,
        strategy_returns: pd.Series,
        n_permutations: int = 1000,
    ) -> dict:
        """
        Run Monte Carlo Permutation Test.

        Tests if the strategy Sharpe ratio is significantly better than random.
        """
        if len(strategy_returns) == 0 or strategy_returns.std() == 0:
            return {"p_value": 1.0, "significant": False, "original_sharpe": 0}

        original_sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)

        # Generate permuted Sharpes
        returns_array = strategy_returns.values
        permuted_sharpes = []

        for _ in range(n_permutations):
            # Random sign flipping (preserves return distribution)
            signs = np.random.choice([-1, 1], size=len(returns_array))
            permuted = returns_array * signs

            if permuted.std() > 0:
                perm_sharpe = permuted.mean() / permuted.std() * np.sqrt(252)
                permuted_sharpes.append(perm_sharpe)

        # P-value: fraction of permutations with Sharpe >= original
        p_value = (np.array(permuted_sharpes) >= original_sharpe).mean()

        return {
            "p_value": p_value,
            "significant": p_value < 0.05,
            "original_sharpe": original_sharpe,
            "permuted_sharpes": permuted_sharpes,
        }

    def run_walk_forward(
        self,
        data: pd.DataFrame,
        n_splits: int = 3,
        train_pct: float = 0.7,
    ) -> list[dict]:
        """
        Run walk-forward validation with expanding window.
        """
        results = []
        n = len(data)

        for split in range(n_splits):
            # Expanding window: train on more data each split
            train_end_pct = 0.5 + (split * 0.15)  # 50%, 65%, 80%
            test_end_pct = train_end_pct + 0.2  # 70%, 85%, 100%

            train_end = int(n * train_end_pct)
            test_end = min(int(n * test_end_pct), n)

            if train_end >= test_end - 20:
                continue

            train_data = data.iloc[:train_end]
            test_data = data.iloc[train_end:test_end]

            # Backtest on train
            train_result = self.backtest(train_data)
            test_result = self.backtest(test_data)

            # Calculate OOS degradation
            train_sharpe = train_result["sharpe_ratio"]
            test_sharpe = test_result["sharpe_ratio"]

            if train_sharpe != 0:
                degradation = 1 - (test_sharpe / train_sharpe)
            else:
                degradation = 1.0

            results.append(
                {
                    "split": split + 1,
                    "train_start": str(train_data.index[0].date()),
                    "train_end": str(train_data.index[-1].date()),
                    "test_start": str(test_data.index[0].date()),
                    "test_end": str(test_data.index[-1].date()),
                    "train_sharpe": train_sharpe,
                    "test_sharpe": test_sharpe,
                    "train_return": train_result["total_return"],
                    "test_return": test_result["total_return"],
                    "oos_degradation": degradation,
                }
            )

        return results

    def run_bootstrap_ci(
        self,
        returns: pd.Series,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
    ) -> dict:
        """Calculate bootstrap confidence interval for Sharpe ratio."""
        if len(returns) == 0 or returns.std() == 0:
            return {"lower": 0, "upper": 0, "mean": 0}

        bootstrap_sharpes = []
        returns_array = returns.values

        for _ in range(n_bootstrap):
            # Resample with replacement
            sample = np.random.choice(returns_array, size=len(returns_array), replace=True)
            if sample.std() > 0:
                sharpe = sample.mean() / sample.std() * np.sqrt(252)
                bootstrap_sharpes.append(sharpe)

        if len(bootstrap_sharpes) == 0:
            return {"lower": 0, "upper": 0, "mean": 0}

        alpha = (1 - confidence) / 2
        lower = np.percentile(bootstrap_sharpes, alpha * 100)
        upper = np.percentile(bootstrap_sharpes, (1 - alpha) * 100)
        mean = np.mean(bootstrap_sharpes)

        return {"lower": lower, "upper": upper, "mean": mean}

    def validate_symbol(
        self,
        symbol: str,
        days: int = 730,
        n_permutations: int = 1000,
        quick: bool = False,
    ) -> ValidationResult:
        """
        Run full validation on a single commodity.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Validating {symbol} ({self.COMMODITY_INFO.get(symbol, {}).get('name', 'Unknown')})")
        logger.info(f"{'='*60}")

        # Fetch data
        data = self.fetch_data(symbol, days)

        # Analyze current state
        state = self.analyze_current_state(data)
        logger.info(f"Current z-score: {state['current_zscore']:.2f} ({state['state']})")

        # Run backtest
        logger.info("Running backtest...")
        backtest = self.backtest(data)
        logger.info(
            f"Backtest: Sharpe={backtest['sharpe_ratio']:.2f}, "
            f"Return={backtest['total_return']:.1%}, "
            f"Trades={backtest['n_trades']}"
        )

        # MCPT
        logger.info("Running MCPT...")
        n_perm = 100 if quick else n_permutations
        mcpt = self.run_mcpt(backtest["returns"], n_permutations=n_perm)
        logger.info(f"MCPT: p={mcpt['p_value']:.4f}, Significant={mcpt['significant']}")

        # Walk-forward
        logger.info("Running walk-forward validation...")
        wf_results = self.run_walk_forward(data, n_splits=3)

        if wf_results:
            avg_oos_sharpe = np.mean([r["test_sharpe"] for r in wf_results])
            avg_degradation = np.mean([r["oos_degradation"] for r in wf_results])
            all_positive = all(r["test_sharpe"] > 0 for r in wf_results)
        else:
            avg_oos_sharpe = 0
            avg_degradation = 1.0
            all_positive = False

        logger.info(f"Walk-forward: OOS Sharpe={avg_oos_sharpe:.2f}, Stable={all_positive}")

        # Bootstrap CI
        logger.info("Running bootstrap CI...")
        n_boot = 100 if quick else 1000
        bootstrap = self.run_bootstrap_ci(backtest["returns"], n_bootstrap=n_boot)
        logger.info(f"Bootstrap 95% CI: [{bootstrap['lower']:.2f}, {bootstrap['upper']:.2f}]")

        # Determine production readiness
        production_ready = (
            mcpt["significant"]
            and avg_oos_sharpe > 0.5
            and backtest["sharpe_ratio"] > 0.5
            and backtest["n_trades"] >= 10
        )

        notes = []
        if not mcpt["significant"]:
            notes.append("MCPT not significant")
        if avg_oos_sharpe <= 0.5:
            notes.append("OOS Sharpe too low")
        if backtest["n_trades"] < 10:
            notes.append("Too few trades")
        if production_ready:
            notes.append("PRODUCTION READY")

        return ValidationResult(
            symbol=symbol,
            lookback_window=self.lookback_window,
            entry_threshold=self.entry_threshold,
            current_zscore=state["current_zscore"],
            zscore_percentile=state["percentile"],
            zscore_state=state["state"],
            total_return=backtest["total_return"],
            sharpe_ratio=backtest["sharpe_ratio"],
            sortino_ratio=backtest["sortino_ratio"],
            max_drawdown=backtest["max_drawdown"],
            win_rate=backtest["win_rate"],
            n_trades=backtest["n_trades"],
            avg_holding_days=backtest["avg_holding_days"],
            mcpt_p_value=mcpt["p_value"],
            mcpt_significant=mcpt["significant"],
            oos_sharpe=avg_oos_sharpe,
            oos_degradation=avg_degradation,
            walk_forward_stable=all_positive,
            sharpe_ci_lower=bootstrap["lower"],
            sharpe_ci_upper=bootstrap["upper"],
            production_ready=production_ready,
            notes="; ".join(notes),
        )


async def run_full_validation(
    symbols: list[str] | None = None,
    lookback_window: int = 20,
    entry_threshold: float = 2.0,
    days: int = 730,
    quick: bool = False,
) -> dict:
    """
    Run full validation on commodity mean-reversion strategies.
    """
    if symbols is None:
        symbols = ["SLV", "PPLT", "CPER"]

    validator = CommodityValidator(
        lookback_window=lookback_window,
        entry_threshold=entry_threshold,
    )

    results = {}
    production_ready = []

    for symbol in symbols:
        try:
            result = validator.validate_symbol(
                symbol,
                days=days,
                quick=quick,
            )
            results[symbol] = result

            if result.production_ready:
                production_ready.append(symbol)

        except Exception as e:
            logger.error(f"Error validating {symbol}: {e}")
            results[symbol] = {"error": str(e)}

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)

    for symbol, result in results.items():
        if isinstance(result, ValidationResult):
            status = "READY" if result.production_ready else "NOT READY"
            logger.info(
                f"{symbol}: Sharpe={result.sharpe_ratio:.2f}, "
                f"p={result.mcpt_p_value:.4f}, "
                f"OOS={result.oos_sharpe:.2f} [{status}]"
            )
        else:
            logger.info(f"{symbol}: ERROR - {result.get('error', 'Unknown')}")

    logger.info(f"\nProduction Ready: {production_ready}")

    # Save results
    output_dir = Path("/home/nock/quant_results/commodity_validation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"validation_{timestamp}.json"

    output_data = {
        "timestamp": timestamp,
        "config": {
            "symbols": symbols,
            "lookback_window": lookback_window,
            "entry_threshold": entry_threshold,
            "days": days,
        },
        "results": {
            symbol: asdict(result) if isinstance(result, ValidationResult) else result
            for symbol, result in results.items()
        },
        "production_ready": production_ready,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    logger.info(f"\nResults saved to: {output_file}")

    return output_data


def main():
    parser = argparse.ArgumentParser(
        description="Validate commodity mean-reversion strategies"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SLV", "PPLT", "CPER"],
        help="Commodity ETF symbols to validate",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=20,
        help="Lookback window for z-score (default: 20)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.0,
        help="Z-score entry threshold (default: 2.0)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=730,
        help="Days of historical data (default: 730)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick validation mode (fewer permutations)",
    )

    args = parser.parse_args()

    asyncio.run(
        run_full_validation(
            symbols=args.symbols,
            lookback_window=args.lookback,
            entry_threshold=args.threshold,
            days=args.days,
            quick=args.quick,
        )
    )


if __name__ == "__main__":
    main()
