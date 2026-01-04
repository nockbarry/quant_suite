"""Return-based performance metrics."""

from typing import Any

import numpy as np
import pandas as pd


def total_return(returns: pd.Series) -> float:
    """
    Calculate total cumulative return.

    Args:
        returns: Series of period returns

    Returns:
        Total return as decimal (e.g., 0.15 for 15%)
    """
    return float((1 + returns).prod() - 1)


def cagr(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Calculate Compound Annual Growth Rate.

    Args:
        returns: Series of period returns
        periods_per_year: Number of periods per year (252 for daily)

    Returns:
        CAGR as decimal
    """
    total = total_return(returns)
    n_periods = len(returns)
    years = n_periods / periods_per_year

    if years <= 0:
        return 0.0

    return float((1 + total) ** (1 / years) - 1)


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Calculate annualized return (arithmetic).

    Args:
        returns: Series of period returns
        periods_per_year: Number of periods per year

    Returns:
        Annualized return
    """
    return float(returns.mean() * periods_per_year)


def annualized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Calculate annualized volatility (standard deviation).

    Args:
        returns: Series of period returns
        periods_per_year: Number of periods per year

    Returns:
        Annualized volatility
    """
    return float(returns.std() * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Sharpe Ratio.

    Args:
        returns: Series of period returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year

    Returns:
        Sharpe Ratio
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    vol = annualized_volatility(returns, periods_per_year)

    if vol == 0:
        return 0.0

    return float(excess_returns.mean() * periods_per_year / vol)


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Sortino Ratio (uses downside deviation).

    Args:
        returns: Series of period returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year

    Returns:
        Sortino Ratio
    """
    excess_returns = returns - risk_free_rate / periods_per_year
    downside_returns = excess_returns[excess_returns < 0]

    if len(downside_returns) == 0:
        return float("inf")

    downside_std = downside_returns.std() * np.sqrt(periods_per_year)

    if downside_std == 0:
        return float("inf")

    return float(excess_returns.mean() * periods_per_year / downside_std)


def calmar_ratio(
    returns: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Calmar Ratio (CAGR / Max Drawdown).

    Args:
        returns: Series of period returns
        periods_per_year: Number of periods per year

    Returns:
        Calmar Ratio
    """
    annual_return = cagr(returns, periods_per_year)
    max_dd = max_drawdown(returns)

    if max_dd == 0:
        return float("inf")

    return float(annual_return / abs(max_dd))


def information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Information Ratio.

    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        periods_per_year: Number of periods per year

    Returns:
        Information Ratio
    """
    # Align indices
    common_idx = returns.index.intersection(benchmark_returns.index)
    returns = returns.loc[common_idx]
    benchmark_returns = benchmark_returns.loc[common_idx]

    excess = returns - benchmark_returns
    tracking_error = excess.std() * np.sqrt(periods_per_year)

    if tracking_error == 0:
        return 0.0

    return float(excess.mean() * periods_per_year / tracking_error)


def max_drawdown(returns: pd.Series) -> float:
    """
    Calculate maximum drawdown.

    Args:
        returns: Series of period returns

    Returns:
        Maximum drawdown as negative decimal (e.g., -0.20 for 20% drawdown)
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max

    return float(drawdown.min())


def drawdown_series(returns: pd.Series) -> pd.Series:
    """
    Calculate drawdown time series.

    Args:
        returns: Series of period returns

    Returns:
        Series of drawdowns
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    return (cumulative - running_max) / running_max


def recovery_time(returns: pd.Series) -> int | None:
    """
    Calculate longest recovery time from drawdown (in periods).

    Args:
        returns: Series of period returns

    Returns:
        Longest recovery time in periods, or None if still in drawdown
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()

    # Find recovery points
    at_high = cumulative >= running_max * 0.999  # Small tolerance

    max_recovery = 0
    current_recovery = 0

    for is_high in at_high:
        if is_high:
            max_recovery = max(max_recovery, current_recovery)
            current_recovery = 0
        else:
            current_recovery += 1

    # Still in drawdown
    if current_recovery > 0:
        return None

    return max_recovery


def win_rate(returns: pd.Series) -> float:
    """
    Calculate win rate (percentage of positive returns).

    Args:
        returns: Series of period returns

    Returns:
        Win rate as decimal
    """
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def profit_factor(returns: pd.Series) -> float:
    """
    Calculate profit factor (gross profits / gross losses).

    Args:
        returns: Series of period returns

    Returns:
        Profit factor
    """
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())

    if losses == 0:
        return float("inf") if gains > 0 else 0.0

    return float(gains / losses)


def avg_win_loss_ratio(returns: pd.Series) -> float:
    """
    Calculate average win to average loss ratio.

    Args:
        returns: Series of period returns

    Returns:
        Win/loss ratio
    """
    wins = returns[returns > 0]
    losses = returns[returns < 0]

    if len(losses) == 0:
        return float("inf") if len(wins) > 0 else 0.0
    if len(wins) == 0:
        return 0.0

    avg_win = wins.mean()
    avg_loss = abs(losses.mean())

    return float(avg_win / avg_loss) if avg_loss > 0 else float("inf")


def expectancy(returns: pd.Series) -> float:
    """
    Calculate expectancy (expected return per trade).

    Args:
        returns: Series of trade returns

    Returns:
        Expectancy
    """
    if len(returns) == 0:
        return 0.0

    wr = win_rate(returns)
    wins = returns[returns > 0]
    losses = returns[returns < 0]

    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0

    return float(wr * avg_win - (1 - wr) * avg_loss)


def rolling_sharpe(
    returns: pd.Series,
    window: int = 252,
    risk_free_rate: float = 0.0,
) -> pd.Series:
    """
    Calculate rolling Sharpe ratio.

    Args:
        returns: Series of period returns
        window: Rolling window size
        risk_free_rate: Annual risk-free rate

    Returns:
        Series of rolling Sharpe ratios
    """
    excess = returns - risk_free_rate / 252

    rolling_mean = excess.rolling(window).mean() * 252
    rolling_std = returns.rolling(window).std() * np.sqrt(252)

    return rolling_mean / rolling_std


def performance_summary(
    returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    risk_free_rate: float = 0.05,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """
    Calculate comprehensive performance summary.

    Args:
        returns: Series of period returns
        benchmark_returns: Optional benchmark returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year

    Returns:
        Dictionary of performance metrics
    """
    metrics = {
        "total_return": total_return(returns),
        "cagr": cagr(returns, periods_per_year),
        "annualized_volatility": annualized_volatility(returns, periods_per_year),
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate, periods_per_year),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate, periods_per_year),
        "calmar_ratio": calmar_ratio(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "win_rate": win_rate(returns),
        "profit_factor": profit_factor(returns),
        "avg_win_loss_ratio": avg_win_loss_ratio(returns),
        "num_periods": len(returns),
    }

    if benchmark_returns is not None:
        metrics["information_ratio"] = information_ratio(
            returns, benchmark_returns, periods_per_year
        )
        metrics["beta"] = calculate_beta(returns, benchmark_returns)
        metrics["alpha"] = calculate_alpha(
            returns, benchmark_returns, risk_free_rate, periods_per_year
        )

    return metrics


def calculate_beta(
    returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    """
    Calculate beta (sensitivity to benchmark).

    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns

    Returns:
        Beta coefficient
    """
    common_idx = returns.index.intersection(benchmark_returns.index)
    returns = returns.loc[common_idx]
    benchmark_returns = benchmark_returns.loc[common_idx]

    covariance = returns.cov(benchmark_returns)
    variance = benchmark_returns.var()

    if variance == 0:
        return 0.0

    return float(covariance / variance)


def calculate_alpha(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    Calculate Jensen's alpha.

    Args:
        returns: Series of strategy returns
        benchmark_returns: Series of benchmark returns
        risk_free_rate: Annual risk-free rate
        periods_per_year: Number of periods per year

    Returns:
        Alpha (annualized)
    """
    beta = calculate_beta(returns, benchmark_returns)

    strategy_return = annualized_return(returns, periods_per_year)
    benchmark_return = annualized_return(benchmark_returns, periods_per_year)

    return float(strategy_return - risk_free_rate - beta * (benchmark_return - risk_free_rate))
