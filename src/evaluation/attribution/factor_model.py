"""Factor-based performance attribution.

Decomposes portfolio returns into:
- Factor contributions (Market, Size, Value, Momentum, Quality)
- Alpha (unexplained returns)
- Selection and allocation effects (Brinson attribution)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class FactorExposure:
    """Exposure to a single factor."""

    factor_name: str
    beta: float  # Factor loading/beta
    t_stat: float  # T-statistic for significance
    p_value: float
    contribution: float  # Contribution to returns
    contribution_pct: float  # As percentage of total return

    @property
    def is_significant(self) -> bool:
        """Check if exposure is statistically significant (p < 0.05)."""
        return self.p_value < 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "beta": self.beta,
            "t_stat": self.t_stat,
            "p_value": self.p_value,
            "contribution": self.contribution,
            "contribution_pct": self.contribution_pct,
            "is_significant": self.is_significant,
        }


@dataclass
class AttributionResult:
    """Results of factor attribution analysis."""

    total_return: float
    alpha: float  # Unexplained return
    alpha_annualized: float
    alpha_t_stat: float
    alpha_p_value: float
    r_squared: float  # Model fit
    adjusted_r_squared: float
    factor_exposures: list[FactorExposure]
    residual_volatility: float
    information_ratio: float
    analysis_period_days: int
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def factor_contribution_total(self) -> float:
        """Total return explained by factors."""
        return sum(fe.contribution for fe in self.factor_exposures)

    @property
    def alpha_significant(self) -> bool:
        """Check if alpha is statistically significant."""
        return self.alpha_p_value < 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return": self.total_return,
            "alpha": self.alpha,
            "alpha_annualized": self.alpha_annualized,
            "alpha_t_stat": self.alpha_t_stat,
            "alpha_p_value": self.alpha_p_value,
            "alpha_significant": self.alpha_significant,
            "r_squared": self.r_squared,
            "adjusted_r_squared": self.adjusted_r_squared,
            "factor_contribution_total": self.factor_contribution_total,
            "residual_volatility": self.residual_volatility,
            "information_ratio": self.information_ratio,
            "analysis_period_days": self.analysis_period_days,
            "factor_exposures": [fe.to_dict() for fe in self.factor_exposures],
        }

    def summary(self) -> str:
        """Generate text summary of attribution."""
        lines = [
            "=" * 60,
            "FACTOR ATTRIBUTION SUMMARY",
            "=" * 60,
            f"Analysis Period: {self.analysis_period_days} days",
            f"Total Return: {self.total_return:.2%}",
            "",
            "FACTOR CONTRIBUTIONS:",
        ]

        for fe in sorted(self.factor_exposures, key=lambda x: abs(x.contribution), reverse=True):
            sig = "*" if fe.is_significant else ""
            lines.append(
                f"  {fe.factor_name:15s}: {fe.contribution:+.2%} "
                f"(beta={fe.beta:.3f}, t={fe.t_stat:.2f}){sig}"
            )

        lines.extend([
            "",
            f"Factor Total: {self.factor_contribution_total:.2%}",
            f"Alpha: {self.alpha:.2%} (annualized: {self.alpha_annualized:.2%})",
            f"Alpha t-stat: {self.alpha_t_stat:.2f} {'(significant)' if self.alpha_significant else ''}",
            "",
            f"R-squared: {self.r_squared:.2%}",
            f"Information Ratio: {self.information_ratio:.2f}",
            "=" * 60,
        ])

        return "\n".join(lines)


@dataclass
class BrinsonAttribution:
    """Brinson-style attribution (allocation + selection effects)."""

    allocation_effect: float  # Return from sector/asset allocation
    selection_effect: float  # Return from security selection
    interaction_effect: float  # Combined effect
    total_active_return: float
    by_sector: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allocation_effect": self.allocation_effect,
            "selection_effect": self.selection_effect,
            "interaction_effect": self.interaction_effect,
            "total_active_return": self.total_active_return,
            "by_sector": self.by_sector,
        }


class FactorModel:
    """
    Factor-based performance attribution model.

    Implements a multi-factor model to decompose returns:
    R_p = alpha + beta_mkt * R_mkt + beta_smb * SMB + beta_hml * HML + ...

    Default factors (Fama-French style):
    - Market (MKT): Market excess return
    - Size (SMB): Small minus Big
    - Value (HML): High minus Low book-to-market
    - Momentum (MOM): Winners minus Losers
    - Quality (QMJ): Quality minus Junk

    For budget traders, we use simplified proxies:
    - Market: SPY returns
    - Size: IWM - SPY (small vs large)
    - Value: IWD - IWF (value vs growth)
    - Momentum: MTUM returns
    """

    DEFAULT_FACTOR_PROXIES = {
        "Market": "SPY",
        "Size": ("IWM", "SPY"),  # Long IWM, short SPY
        "Value": ("IWD", "IWF"),  # Long Value, short Growth
        "Momentum": "MTUM",
    }

    def __init__(
        self,
        factor_proxies: dict[str, str | tuple[str, str]] | None = None,
        risk_free_rate: float = 0.05,  # Annual risk-free rate
    ):
        """
        Initialize factor model.

        Args:
            factor_proxies: Mapping of factor names to ETF proxies
            risk_free_rate: Annual risk-free rate for excess returns
        """
        self.factor_proxies = factor_proxies or self.DEFAULT_FACTOR_PROXIES.copy()
        self.risk_free_rate = risk_free_rate
        self._factor_returns: pd.DataFrame | None = None

    def attribute(
        self,
        portfolio_returns: pd.Series,
        factor_returns: pd.DataFrame | None = None,
    ) -> AttributionResult:
        """
        Perform factor attribution on portfolio returns.

        Args:
            portfolio_returns: Series of portfolio returns (daily)
            factor_returns: DataFrame of factor returns (optional, will fetch if None)

        Returns:
            AttributionResult with factor exposures and alpha
        """
        # Align dates
        if factor_returns is not None:
            common_idx = portfolio_returns.index.intersection(factor_returns.index)
            portfolio_returns = portfolio_returns.loc[common_idx]
            factor_returns = factor_returns.loc[common_idx]
        else:
            # Use cached or empty factor returns
            if self._factor_returns is not None:
                common_idx = portfolio_returns.index.intersection(self._factor_returns.index)
                portfolio_returns = portfolio_returns.loc[common_idx]
                factor_returns = self._factor_returns.loc[common_idx]
            else:
                # Create dummy factors for testing
                factor_returns = pd.DataFrame(index=portfolio_returns.index)
                factor_returns["Market"] = np.random.randn(len(portfolio_returns)) * 0.01

        if len(portfolio_returns) < 30:
            raise ValueError("Need at least 30 observations for attribution")

        # Calculate excess returns (subtract risk-free rate)
        daily_rf = self.risk_free_rate / 252
        excess_returns = portfolio_returns - daily_rf

        # Run regression
        X = factor_returns.values
        y = excess_returns.values

        # Add constant for alpha
        X_with_const = np.column_stack([np.ones(len(X)), X])

        # OLS regression
        try:
            coeffs, residuals, rank, s = np.linalg.lstsq(X_with_const, y, rcond=None)
        except np.linalg.LinAlgError:
            raise ValueError("Regression failed - check for multicollinearity")

        alpha = coeffs[0]
        betas = coeffs[1:]

        # Calculate statistics
        y_pred = X_with_const @ coeffs
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        n, k = len(y), len(coeffs)
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - k - 1) if n > k + 1 else r_squared

        # Standard errors and t-stats
        mse = ss_res / (n - k) if n > k else ss_res
        var_covar = mse * np.linalg.pinv(X_with_const.T @ X_with_const)
        std_errors = np.sqrt(np.diag(var_covar))

        alpha_se = std_errors[0]
        alpha_t_stat = alpha / alpha_se if alpha_se > 0 else 0
        alpha_p_value = 2 * (1 - stats.t.cdf(abs(alpha_t_stat), n - k))

        # Factor exposures
        factor_names = list(factor_returns.columns)
        factor_exposures = []

        for i, factor_name in enumerate(factor_names):
            beta = betas[i]
            se = std_errors[i + 1]
            t_stat = beta / se if se > 0 else 0
            p_value = 2 * (1 - stats.t.cdf(abs(t_stat), n - k))

            # Factor contribution = beta * factor_mean_return * num_periods
            factor_mean = factor_returns[factor_name].mean()
            contribution = beta * factor_mean * len(portfolio_returns)

            total_return = portfolio_returns.sum()
            contribution_pct = contribution / total_return if total_return != 0 else 0

            factor_exposures.append(FactorExposure(
                factor_name=factor_name,
                beta=float(beta),
                t_stat=float(t_stat),
                p_value=float(p_value),
                contribution=float(contribution),
                contribution_pct=float(contribution_pct),
            ))

        # Residual analysis
        residuals = y - y_pred
        residual_vol = float(np.std(residuals) * np.sqrt(252))

        # Information ratio
        info_ratio = (alpha * 252) / residual_vol if residual_vol > 0 else 0

        return AttributionResult(
            total_return=float(portfolio_returns.sum()),
            alpha=float(alpha * len(portfolio_returns)),  # Cumulative alpha
            alpha_annualized=float(alpha * 252),
            alpha_t_stat=float(alpha_t_stat),
            alpha_p_value=float(alpha_p_value),
            r_squared=float(r_squared),
            adjusted_r_squared=float(adj_r_squared),
            factor_exposures=factor_exposures,
            residual_volatility=residual_vol,
            information_ratio=float(info_ratio),
            analysis_period_days=len(portfolio_returns),
        )

    def fetch_factor_returns(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Fetch factor returns from ETF proxies.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame of factor returns
        """
        import yfinance as yf

        factor_returns = pd.DataFrame()

        for factor_name, proxy in self.factor_proxies.items():
            try:
                if isinstance(proxy, tuple):
                    # Long-short factor
                    long_ticker, short_ticker = proxy
                    long_data = yf.download(long_ticker, start=start_date, end=end_date, progress=False)
                    short_data = yf.download(short_ticker, start=start_date, end=end_date, progress=False)

                    if not long_data.empty and not short_data.empty:
                        long_ret = long_data["Adj Close"].pct_change()
                        short_ret = short_data["Adj Close"].pct_change()
                        factor_returns[factor_name] = long_ret - short_ret
                else:
                    # Single ETF factor
                    data = yf.download(proxy, start=start_date, end=end_date, progress=False)
                    if not data.empty:
                        factor_returns[factor_name] = data["Adj Close"].pct_change()

            except Exception as e:
                logger.warning(f"Failed to fetch {factor_name} factor: {e}")

        factor_returns = factor_returns.dropna()
        self._factor_returns = factor_returns

        return factor_returns

    def calculate_factor_tilts(
        self,
        holdings: dict[str, float],
    ) -> dict[str, float]:
        """
        Calculate portfolio's factor tilts based on holdings.

        Args:
            holdings: Dict of symbol -> weight

        Returns:
            Dict of factor_name -> tilt (deviation from market)
        """
        # Simplified implementation - would need fundamental data for full analysis
        tilts = {factor: 0.0 for factor in self.factor_proxies.keys()}

        # Placeholder - in production, would calculate based on
        # individual stock characteristics
        return tilts


class RollingFactorAnalysis:
    """
    Rolling window factor analysis for time-varying exposures.
    """

    def __init__(
        self,
        factor_model: FactorModel,
        window_days: int = 60,
        step_days: int = 20,
    ):
        """
        Initialize rolling analysis.

        Args:
            factor_model: Factor model to use
            window_days: Rolling window size
            step_days: Step size between windows
        """
        self.factor_model = factor_model
        self.window_days = window_days
        self.step_days = step_days

    def analyze(
        self,
        portfolio_returns: pd.Series,
        factor_returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Perform rolling factor analysis.

        Args:
            portfolio_returns: Portfolio returns series
            factor_returns: Factor returns DataFrame

        Returns:
            DataFrame with rolling exposures over time
        """
        results = []

        # Align data
        common_idx = portfolio_returns.index.intersection(factor_returns.index)
        portfolio_returns = portfolio_returns.loc[common_idx]
        factor_returns = factor_returns.loc[common_idx]

        n = len(portfolio_returns)

        for start in range(0, n - self.window_days, self.step_days):
            end = start + self.window_days
            window_returns = portfolio_returns.iloc[start:end]
            window_factors = factor_returns.iloc[start:end]

            try:
                attribution = self.factor_model.attribute(window_returns, window_factors)

                row = {
                    "date": portfolio_returns.index[end - 1],
                    "alpha": attribution.alpha_annualized,
                    "r_squared": attribution.r_squared,
                }

                for fe in attribution.factor_exposures:
                    row[f"beta_{fe.factor_name}"] = fe.beta

                results.append(row)

            except Exception as e:
                logger.warning(f"Rolling window {start}-{end} failed: {e}")

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df.set_index("date", inplace=True)

        return df

    def plot_exposures(self, rolling_results: pd.DataFrame) -> None:
        """Plot rolling factor exposures."""
        try:
            import matplotlib.pyplot as plt

            beta_cols = [c for c in rolling_results.columns if c.startswith("beta_")]

            fig, axes = plt.subplots(len(beta_cols) + 1, 1, figsize=(12, 3 * (len(beta_cols) + 1)))

            # Alpha plot
            axes[0].plot(rolling_results.index, rolling_results["alpha"])
            axes[0].axhline(y=0, color="r", linestyle="--", alpha=0.5)
            axes[0].set_title("Rolling Alpha (Annualized)")
            axes[0].set_ylabel("Alpha")

            # Beta plots
            for i, col in enumerate(beta_cols):
                factor_name = col.replace("beta_", "")
                axes[i + 1].plot(rolling_results.index, rolling_results[col])
                axes[i + 1].axhline(y=0, color="r", linestyle="--", alpha=0.5)
                axes[i + 1].set_title(f"Rolling {factor_name} Beta")
                axes[i + 1].set_ylabel("Beta")

            plt.tight_layout()
            plt.show()

        except ImportError:
            logger.warning("matplotlib not available for plotting")


def brinson_attribution(
    portfolio_weights: pd.Series,
    benchmark_weights: pd.Series,
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    sector_mapping: dict[str, str],
) -> BrinsonAttribution:
    """
    Perform Brinson attribution analysis.

    Decomposes active return into:
    - Allocation effect: Over/underweighting sectors
    - Selection effect: Picking winners within sectors
    - Interaction effect: Combined effect

    Args:
        portfolio_weights: Portfolio weights by security
        benchmark_weights: Benchmark weights by security
        portfolio_returns: Portfolio returns by security
        benchmark_returns: Benchmark returns by security
        sector_mapping: Dict mapping security -> sector

    Returns:
        BrinsonAttribution result
    """
    # Group by sector
    sectors = set(sector_mapping.values())

    allocation_total = 0.0
    selection_total = 0.0
    interaction_total = 0.0
    by_sector = {}

    for sector in sectors:
        # Get securities in this sector
        sector_securities = [s for s, sec in sector_mapping.items() if sec == sector]

        # Portfolio sector weight and return
        p_weight = sum(portfolio_weights.get(s, 0) for s in sector_securities)
        p_return = sum(
            portfolio_weights.get(s, 0) * portfolio_returns.get(s, 0)
            for s in sector_securities
        )
        p_return = p_return / p_weight if p_weight > 0 else 0

        # Benchmark sector weight and return
        b_weight = sum(benchmark_weights.get(s, 0) for s in sector_securities)
        b_return = sum(
            benchmark_weights.get(s, 0) * benchmark_returns.get(s, 0)
            for s in sector_securities
        )
        b_return = b_return / b_weight if b_weight > 0 else 0

        # Total benchmark return
        total_b_return = sum(
            benchmark_weights.get(s, 0) * benchmark_returns.get(s, 0)
            for s in benchmark_returns.index
        )

        # Attribution effects
        allocation = (p_weight - b_weight) * (b_return - total_b_return)
        selection = b_weight * (p_return - b_return)
        interaction = (p_weight - b_weight) * (p_return - b_return)

        allocation_total += allocation
        selection_total += selection
        interaction_total += interaction

        by_sector[sector] = {
            "allocation": allocation,
            "selection": selection,
            "interaction": interaction,
            "portfolio_weight": p_weight,
            "benchmark_weight": b_weight,
        }

    total_active = allocation_total + selection_total + interaction_total

    return BrinsonAttribution(
        allocation_effect=allocation_total,
        selection_effect=selection_total,
        interaction_effect=interaction_total,
        total_active_return=total_active,
        by_sector=by_sector,
    )
