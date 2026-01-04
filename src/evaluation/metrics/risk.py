"""Risk metrics for portfolio evaluation."""

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def value_at_risk(
    returns: pd.Series,
    confidence: float = 0.95,
    method: str = "historical",
) -> float:
    """
    Calculate Value at Risk (VaR).

    Args:
        returns: Series of period returns
        confidence: Confidence level (e.g., 0.95 for 95%)
        method: 'historical', 'parametric', or 'cornish_fisher'

    Returns:
        VaR as positive number (potential loss)
    """
    if len(returns) == 0:
        return 0.0

    if method == "historical":
        var = -np.percentile(returns, (1 - confidence) * 100)

    elif method == "parametric":
        mean = returns.mean()
        std = returns.std()
        z_score = stats.norm.ppf(1 - confidence)
        var = -(mean + z_score * std)

    elif method == "cornish_fisher":
        # Cornish-Fisher expansion for non-normal distributions
        mean = returns.mean()
        std = returns.std()
        skew = returns.skew()
        kurt = returns.kurtosis()

        z = stats.norm.ppf(1 - confidence)
        z_cf = (
            z
            + (z**2 - 1) * skew / 6
            + (z**3 - 3 * z) * (kurt - 3) / 24
            - (2 * z**3 - 5 * z) * (skew**2) / 36
        )

        var = -(mean + z_cf * std)

    else:
        raise ValueError(f"Unknown VaR method: {method}")

    return float(max(0, var))


def conditional_var(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """
    Calculate Conditional Value at Risk (CVaR / Expected Shortfall).

    The expected loss given that the loss exceeds VaR.

    Args:
        returns: Series of period returns
        confidence: Confidence level

    Returns:
        CVaR as positive number
    """
    if len(returns) == 0:
        return 0.0

    var = value_at_risk(returns, confidence, "historical")
    tail_losses = returns[returns < -var]

    if len(tail_losses) == 0:
        return var

    return float(-tail_losses.mean())


def max_drawdown_duration(returns: pd.Series) -> int:
    """
    Calculate maximum drawdown duration in periods.

    Args:
        returns: Series of period returns

    Returns:
        Duration of longest drawdown in periods
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()

    # Track drawdown periods
    in_drawdown = cumulative < running_max
    drawdown_periods = []
    current_duration = 0

    for is_dd in in_drawdown:
        if is_dd:
            current_duration += 1
        else:
            if current_duration > 0:
                drawdown_periods.append(current_duration)
            current_duration = 0

    if current_duration > 0:
        drawdown_periods.append(current_duration)

    return max(drawdown_periods) if drawdown_periods else 0


def ulcer_index(returns: pd.Series) -> float:
    """
    Calculate Ulcer Index (measure of downside volatility).

    Based on drawdown depth and duration.

    Args:
        returns: Series of period returns

    Returns:
        Ulcer Index
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown_pct = ((cumulative - running_max) / running_max) * 100

    return float(np.sqrt((drawdown_pct**2).mean()))


def pain_index(returns: pd.Series) -> float:
    """
    Calculate Pain Index (average drawdown).

    Args:
        returns: Series of period returns

    Returns:
        Pain Index (average absolute drawdown)
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max

    return float(abs(drawdown).mean())


def pain_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Pain Ratio (excess return / pain index).

    Args:
        returns: Series of period returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year

    Returns:
        Pain Ratio
    """
    pi = pain_index(returns)
    if pi == 0:
        return 0.0

    excess_return = returns.mean() * periods_per_year - risk_free_rate
    return float(excess_return / pi)


def downside_deviation(
    returns: pd.Series,
    target: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate downside deviation (semi-deviation).

    Args:
        returns: Series of period returns
        target: Target/minimum acceptable return
        periods_per_year: Number of periods per year

    Returns:
        Annualized downside deviation
    """
    below_target = returns[returns < target]
    if len(below_target) == 0:
        return 0.0

    return float(below_target.std() * np.sqrt(periods_per_year))


def upside_potential_ratio(
    returns: pd.Series,
    target: float = 0.0,
) -> float:
    """
    Calculate Upside Potential Ratio.

    Args:
        returns: Series of period returns
        target: Target return

    Returns:
        Upside Potential Ratio
    """
    above_target = returns[returns > target] - target
    below_target = returns[returns < target] - target

    if len(below_target) == 0:
        return float("inf") if len(above_target) > 0 else 0.0

    upside = above_target.mean() if len(above_target) > 0 else 0.0
    downside = np.sqrt((below_target**2).mean())

    if downside == 0:
        return float("inf") if upside > 0 else 0.0

    return float(upside / downside)


def omega_ratio(
    returns: pd.Series,
    threshold: float = 0.0,
) -> float:
    """
    Calculate Omega Ratio.

    Probability-weighted ratio of gains vs losses.

    Args:
        returns: Series of period returns
        threshold: Threshold return

    Returns:
        Omega Ratio
    """
    gains = returns[returns > threshold] - threshold
    losses = threshold - returns[returns <= threshold]

    total_gains = gains.sum() if len(gains) > 0 else 0.0
    total_losses = losses.sum() if len(losses) > 0 else 0.0

    if total_losses == 0:
        return float("inf") if total_gains > 0 else 0.0

    return float(total_gains / total_losses)


def tail_ratio(
    returns: pd.Series,
    percentile: float = 5.0,
) -> float:
    """
    Calculate Tail Ratio (right tail / left tail).

    Args:
        returns: Series of period returns
        percentile: Percentile for tail calculation

    Returns:
        Tail Ratio
    """
    right_tail = np.percentile(returns, 100 - percentile)
    left_tail = np.percentile(returns, percentile)

    if left_tail == 0:
        return float("inf") if right_tail > 0 else 0.0

    return float(abs(right_tail / left_tail))


def skewness(returns: pd.Series) -> float:
    """
    Calculate return distribution skewness.

    Args:
        returns: Series of period returns

    Returns:
        Skewness coefficient
    """
    return float(returns.skew())


def kurtosis(returns: pd.Series, excess: bool = True) -> float:
    """
    Calculate return distribution kurtosis.

    Args:
        returns: Series of period returns
        excess: If True, return excess kurtosis (kurtosis - 3)

    Returns:
        Kurtosis coefficient
    """
    k = returns.kurtosis()
    return float(k) if excess else float(k + 3)


def stability_of_returns(returns: pd.Series) -> float:
    """
    Calculate R-squared of cumulative returns vs time.

    Higher values indicate more stable/linear growth.

    Args:
        returns: Series of period returns

    Returns:
        R-squared value (0 to 1)
    """
    if len(returns) < 2:
        return 0.0

    cumulative = (1 + returns).cumprod()
    x = np.arange(len(cumulative))

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, cumulative)

    return float(r_value**2)


def risk_summary(
    returns: pd.Series,
    confidence: float = 0.95,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """
    Calculate comprehensive risk summary.

    Args:
        returns: Series of period returns
        confidence: Confidence level for VaR/CVaR
        periods_per_year: Number of periods per year

    Returns:
        Dictionary of risk metrics
    """
    return {
        "volatility": float(returns.std() * np.sqrt(periods_per_year)),
        "downside_deviation": downside_deviation(returns, 0, periods_per_year),
        "var_95": value_at_risk(returns, 0.95, "historical"),
        "var_99": value_at_risk(returns, 0.99, "historical"),
        "cvar_95": conditional_var(returns, 0.95),
        "cvar_99": conditional_var(returns, 0.99),
        "max_drawdown": float(((1 + returns).cumprod() / (1 + returns).cumprod().cummax() - 1).min()),
        "max_drawdown_duration": max_drawdown_duration(returns),
        "ulcer_index": ulcer_index(returns),
        "pain_index": pain_index(returns),
        "skewness": skewness(returns),
        "kurtosis": kurtosis(returns),
        "tail_ratio": tail_ratio(returns),
        "stability": stability_of_returns(returns),
    }
