#!/usr/bin/env python3
"""Portfolio Optimizer - Risk parity, mean-variance, and Kelly criterion optimization.

Provides optimal position sizing and rebalancing recommendations.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of portfolio optimization."""
    method: str
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    max_drawdown_estimate: float
    rebalance_trades: list[dict]
    constraints_applied: list[str]

    def to_dict(self):
        return {
            "method": self.method,
            "weights": self.weights,
            "expected_return": self.expected_return,
            "expected_volatility": self.expected_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_estimate": self.max_drawdown_estimate,
            "rebalance_trades": self.rebalance_trades,
            "constraints_applied": self.constraints_applied,
        }


@dataclass
class PortfolioStats:
    """Portfolio statistics."""
    symbols: list[str]
    returns: pd.DataFrame
    covariance: pd.DataFrame
    correlation: pd.DataFrame
    volatilities: dict[str, float]
    expected_returns: dict[str, float]


class PortfolioOptimizer:
    """Optimize portfolio allocation using various methods."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.base / "optimization"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Constraints
        self.max_position_weight = 0.20  # 20% max per position
        self.min_position_weight = 0.02  # 2% min if included
        self.max_sector_weight = 0.40   # 40% max per sector
        self.risk_free_rate = 0.05      # 5% risk-free rate

    async def fetch_price_data(self, symbols: list[str], days: int = 252) -> pd.DataFrame:
        """Fetch historical price data."""
        prices = {}

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=f"{days}d")
                if not df.empty:
                    prices[symbol] = df["Close"]
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")

        if not prices:
            return pd.DataFrame()

        return pd.DataFrame(prices)

    def calculate_stats(self, prices: pd.DataFrame) -> PortfolioStats:
        """Calculate portfolio statistics from price data."""
        returns = prices.pct_change().dropna()

        # Annualized covariance (252 trading days)
        covariance = returns.cov() * 252
        correlation = returns.corr()

        # Individual volatilities and expected returns
        volatilities = {}
        expected_returns = {}

        for symbol in returns.columns:
            vol = returns[symbol].std() * np.sqrt(252)
            ret = returns[symbol].mean() * 252
            volatilities[symbol] = vol
            expected_returns[symbol] = ret

        return PortfolioStats(
            symbols=list(returns.columns),
            returns=returns,
            covariance=covariance,
            correlation=correlation,
            volatilities=volatilities,
            expected_returns=expected_returns,
        )

    def risk_parity_weights(self, stats: PortfolioStats) -> dict[str, float]:
        """Calculate risk parity weights (equal risk contribution)."""
        n = len(stats.symbols)
        cov_matrix = stats.covariance.values

        # Start with equal weights
        weights = np.ones(n) / n

        # Iterative optimization for risk parity
        for _ in range(100):
            # Calculate marginal risk contributions
            portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
            marginal_risk = cov_matrix @ weights / portfolio_vol
            risk_contributions = weights * marginal_risk

            # Target equal risk contribution
            target_risk = portfolio_vol / n

            # Adjust weights
            adjustments = target_risk / (risk_contributions + 1e-10)
            weights = weights * adjustments
            weights = weights / weights.sum()  # Normalize

        return dict(zip(stats.symbols, weights))

    def mean_variance_weights(self, stats: PortfolioStats,
                             target_return: Optional[float] = None) -> dict[str, float]:
        """Calculate mean-variance optimal weights (Markowitz)."""
        n = len(stats.symbols)
        returns = np.array([stats.expected_returns[s] for s in stats.symbols])
        cov_matrix = stats.covariance.values

        # If no target return, maximize Sharpe ratio
        if target_return is None:
            # Grid search for max Sharpe
            best_sharpe = -np.inf
            best_weights = np.ones(n) / n

            for target in np.linspace(returns.min(), returns.max(), 50):
                try:
                    weights = self._solve_mv(returns, cov_matrix, target)
                    port_return = weights @ returns
                    port_vol = np.sqrt(weights @ cov_matrix @ weights)
                    sharpe = (port_return - self.risk_free_rate) / port_vol

                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_weights = weights
                except:
                    continue

            weights = best_weights
        else:
            weights = self._solve_mv(returns, cov_matrix, target_return)

        # Apply constraints
        weights = self._apply_constraints(weights)

        return dict(zip(stats.symbols, weights))

    def _solve_mv(self, returns: np.ndarray, cov: np.ndarray,
                  target_return: float) -> np.ndarray:
        """Solve mean-variance optimization for target return."""
        n = len(returns)

        # Simple quadratic programming solution
        # Minimize: w'Σw subject to w'μ = r, w'1 = 1, w >= 0

        # Use iterative approach
        weights = np.ones(n) / n

        for _ in range(100):
            # Gradient descent on variance with return constraint
            grad = 2 * cov @ weights

            # Project to maintain constraints
            weights = weights - 0.01 * grad
            weights = np.maximum(weights, 0)
            weights = weights / weights.sum()

            # Check return constraint
            current_return = weights @ returns
            if abs(current_return - target_return) < 0.001:
                break

        return weights

    def _apply_constraints(self, weights: np.ndarray) -> np.ndarray:
        """Apply position size constraints."""
        # Cap maximum weight
        weights = np.minimum(weights, self.max_position_weight)

        # Remove very small positions
        weights[weights < self.min_position_weight] = 0

        # Renormalize
        if weights.sum() > 0:
            weights = weights / weights.sum()

        return weights

    def kelly_weights(self, stats: PortfolioStats,
                     fraction: float = 0.5) -> dict[str, float]:
        """Calculate Kelly criterion weights (fractional Kelly for safety)."""
        weights = {}

        for symbol in stats.symbols:
            ret = stats.expected_returns[symbol]
            vol = stats.volatilities[symbol]

            if vol > 0:
                # Kelly fraction = (expected_return - risk_free) / variance
                kelly = (ret - self.risk_free_rate) / (vol ** 2)
                # Apply fractional Kelly (half Kelly is common)
                kelly = kelly * fraction
                # Cap at max position
                kelly = min(max(kelly, 0), self.max_position_weight)
                weights[symbol] = kelly
            else:
                weights[symbol] = 0

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def equal_weight(self, symbols: list[str]) -> dict[str, float]:
        """Simple equal weighting."""
        n = len(symbols)
        return {s: 1.0 / n for s in symbols}

    def calculate_rebalance_trades(self, current_weights: dict[str, float],
                                   target_weights: dict[str, float],
                                   portfolio_value: float,
                                   prices: dict[str, float]) -> list[dict]:
        """Calculate trades needed to rebalance."""
        trades = []

        all_symbols = set(current_weights.keys()) | set(target_weights.keys())

        for symbol in all_symbols:
            current = current_weights.get(symbol, 0)
            target = target_weights.get(symbol, 0)
            diff = target - current

            if abs(diff) < 0.01:  # Less than 1% difference, skip
                continue

            value_change = diff * portfolio_value
            price = prices.get(symbol, 0)

            if price > 0:
                shares = int(value_change / price)
                if shares != 0:
                    trades.append({
                        "symbol": symbol,
                        "action": "BUY" if shares > 0 else "SELL",
                        "shares": abs(shares),
                        "value": abs(value_change),
                        "current_weight": current,
                        "target_weight": target,
                    })

        # Sort by absolute value change
        trades.sort(key=lambda x: x["value"], reverse=True)

        return trades

    async def optimize(self, symbols: list[str], current_holdings: dict[str, float],
                      portfolio_value: float, method: str = "risk_parity") -> OptimizationResult:
        """Run portfolio optimization."""
        # Fetch data
        prices_df = await self.fetch_price_data(symbols)
        if prices_df.empty:
            raise ValueError("Could not fetch price data")

        # Calculate statistics
        stats = self.calculate_stats(prices_df)

        # Get current prices
        current_prices = {s: prices_df[s].iloc[-1] for s in prices_df.columns}

        # Calculate current weights
        current_weights = {}
        for symbol, shares in current_holdings.items():
            if symbol in current_prices:
                value = shares * current_prices[symbol]
                current_weights[symbol] = value / portfolio_value

        # Optimize based on method
        if method == "risk_parity":
            target_weights = self.risk_parity_weights(stats)
        elif method == "mean_variance":
            target_weights = self.mean_variance_weights(stats)
        elif method == "kelly":
            target_weights = self.kelly_weights(stats)
        elif method == "equal":
            target_weights = self.equal_weight(stats.symbols)
        else:
            raise ValueError(f"Unknown method: {method}")

        # Calculate expected portfolio metrics
        w = np.array([target_weights.get(s, 0) for s in stats.symbols])
        r = np.array([stats.expected_returns[s] for s in stats.symbols])
        cov = stats.covariance.values

        expected_return = w @ r
        expected_vol = np.sqrt(w @ cov @ w)
        sharpe = (expected_return - self.risk_free_rate) / expected_vol if expected_vol > 0 else 0
        max_dd_estimate = expected_vol * 2.5  # Rule of thumb

        # Calculate rebalance trades
        rebalance_trades = self.calculate_rebalance_trades(
            current_weights, target_weights, portfolio_value, current_prices
        )

        result = OptimizationResult(
            method=method,
            weights=target_weights,
            expected_return=expected_return,
            expected_volatility=expected_vol,
            sharpe_ratio=sharpe,
            max_drawdown_estimate=max_dd_estimate,
            rebalance_trades=rebalance_trades,
            constraints_applied=[
                f"Max position: {self.max_position_weight:.0%}",
                f"Min position: {self.min_position_weight:.0%}",
            ],
        )

        # Save result
        output_file = self.cache_dir / f"optimization_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(output_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        return result

    def get_optimization_summary(self, result: OptimizationResult) -> str:
        """Get human-readable optimization summary."""
        lines = [
            f"Portfolio Optimization ({result.method})",
            "=" * 50,
            f"Expected Return: {result.expected_return:.1%}",
            f"Expected Volatility: {result.expected_volatility:.1%}",
            f"Sharpe Ratio: {result.sharpe_ratio:.2f}",
            f"Max Drawdown Est: {result.max_drawdown_estimate:.1%}",
            "",
            "Target Weights:",
        ]

        for symbol, weight in sorted(result.weights.items(), key=lambda x: x[1], reverse=True):
            if weight > 0.01:
                lines.append(f"  {symbol:6s}: {weight:6.1%}")

        if result.rebalance_trades:
            lines.extend(["", "Rebalance Trades:"])
            for trade in result.rebalance_trades[:10]:
                lines.append(
                    f"  {trade['action']:4s} {trade['shares']:4d} {trade['symbol']:6s} "
                    f"(${trade['value']:,.0f})"
                )

        return "\n".join(lines)


async def main():
    """Test portfolio optimizer."""
    optimizer = PortfolioOptimizer()

    # Test with sample portfolio
    symbols = ["SPY", "QQQ", "GLD", "TLT", "XLE"]
    current_holdings = {
        "SPY": 50,
        "QQQ": 30,
        "GLD": 20,
        "TLT": 40,
        "XLE": 60,
    }

    print("Optimizing portfolio...")

    for method in ["risk_parity", "mean_variance", "kelly", "equal"]:
        print(f"\n{'='*60}")
        result = await optimizer.optimize(
            symbols=symbols,
            current_holdings=current_holdings,
            portfolio_value=100000,
            method=method,
        )
        print(optimizer.get_optimization_summary(result))


if __name__ == "__main__":
    asyncio.run(main())
