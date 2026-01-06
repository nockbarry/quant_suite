"""Position Risk Monitor for real-time portfolio risk assessment.

Provides:
- Position-level risk metrics (VaR, correlation, concentration)
- Portfolio-level Greeks exposure (for options)
- Correlation analysis and diversification scoring
- Risk limit monitoring and alerts
- Hedge recommendations

Usage:
    from src.risk.position_monitor import PositionRiskMonitor

    monitor = PositionRiskMonitor(risk_limits={
        'max_position_pct': 25,
        'max_sector_pct': 50,
        'max_daily_loss_pct': 5,
    })

    portfolio_risk = monitor.get_portfolio_risk()
    print(portfolio_risk.get_summary())
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Sector mapping for concentration analysis
SYMBOL_SECTORS = {
    # Energy
    "XOM": "Energy", "CVX": "Energy", "SLB": "Energy", "HAL": "Energy",
    "BKR": "Energy", "OXY": "Energy", "COP": "Energy", "VLO": "Energy",
    "MPC": "Energy", "PSX": "Energy", "EOG": "Energy", "XLE": "Energy",
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMD": "Technology", "INTC": "Technology", "CRM": "Technology",
    "ORCL": "Technology", "ADBE": "Technology", "XLK": "Technology",
    # Financials
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS": "Financials", "MS": "Financials", "XLF": "Financials",
    # Healthcare
    "JNJ": "Healthcare", "UNH": "Healthcare", "PFE": "Healthcare",
    "MRK": "Healthcare", "ABBV": "Healthcare", "XLV": "Healthcare",
    # Consumer
    "WMT": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "MCD": "Consumer Discretionary",
    # Travel/Cruise
    "CCL": "Consumer Discretionary", "RCL": "Consumer Discretionary",
    "NCLH": "Consumer Discretionary",
    # Commodities
    "GLD": "Commodities", "SLV": "Commodities", "USO": "Commodities",
}


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""

    symbol: str
    position_type: str  # "equity" or "option"
    quantity: int
    current_price: float
    market_value: float
    weight_pct: float

    # Price Risk
    var_1d_95: float  # 1-day 95% VaR
    var_1d_99: float  # 1-day 99% VaR
    max_loss: float  # Worst case (for options = full premium)

    # Volatility
    historical_vol: float  # 20-day annualized
    beta: float  # vs SPY

    # For Options
    delta_exposure: float = 0.0
    theta_exposure: float = 0.0
    gamma_exposure: float = 0.0
    vega_exposure: float = 0.0

    # Correlation
    correlation_to_spy: float = 0.0
    correlation_to_portfolio: float = 0.0

    # Sector
    sector: str = "Unknown"

    # Risk Flags
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "position_type": self.position_type,
            "quantity": self.quantity,
            "current_price": round(self.current_price, 2),
            "market_value": round(self.market_value, 2),
            "weight_pct": round(self.weight_pct, 2),
            "var_1d_95": round(self.var_1d_95, 2),
            "var_1d_99": round(self.var_1d_99, 2),
            "max_loss": round(self.max_loss, 2),
            "historical_vol": round(self.historical_vol, 4),
            "beta": round(self.beta, 2),
            "delta_exposure": round(self.delta_exposure, 2),
            "theta_exposure": round(self.theta_exposure, 2),
            "gamma_exposure": round(self.gamma_exposure, 4),
            "vega_exposure": round(self.vega_exposure, 2),
            "correlation_to_spy": round(self.correlation_to_spy, 2),
            "correlation_to_portfolio": round(self.correlation_to_portfolio, 2),
            "sector": self.sector,
            "flags": self.flags,
        }


@dataclass
class LimitStatus:
    """Status of a single risk limit."""

    name: str
    current: float
    limit: float
    status: str  # "ok", "warning", "violated"
    pct_used: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current": round(self.current, 2),
            "limit": round(self.limit, 2),
            "status": self.status,
            "pct_used": round(self.pct_used, 1),
        }


@dataclass
class PortfolioRisk:
    """Complete portfolio risk assessment."""

    timestamp: datetime

    # Portfolio Value
    total_equity: float
    total_options: float
    total_value: float
    cash: float
    cash_pct: float

    # Concentration
    largest_position: str
    largest_position_pct: float
    top_5_concentration: float
    sector_concentration: dict[str, float] = field(default_factory=dict)

    # Correlation Risk
    avg_correlation: float = 0.0
    max_correlation_pair: tuple[str, str] | None = None
    max_correlation: float = 0.0
    diversification_score: float = 50.0  # 0-100

    # Greeks Exposure (Options)
    total_delta: float = 0.0
    total_theta_daily: float = 0.0
    total_vega: float = 0.0
    total_gamma: float = 0.0

    # VaR
    portfolio_var_1d_95: float = 0.0
    portfolio_var_1d_99: float = 0.0

    # Drawdown
    current_drawdown: float = 0.0
    max_drawdown_30d: float = 0.0

    # Limits
    limits: list[LimitStatus] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Position Details
    positions: list[PositionRisk] = field(default_factory=list)

    # Recommendations
    reduce_positions: list[str] = field(default_factory=list)
    hedge_suggestions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_equity": round(self.total_equity, 2),
            "total_options": round(self.total_options, 2),
            "total_value": round(self.total_value, 2),
            "cash": round(self.cash, 2),
            "cash_pct": round(self.cash_pct, 1),
            "largest_position": self.largest_position,
            "largest_position_pct": round(self.largest_position_pct, 1),
            "top_5_concentration": round(self.top_5_concentration, 1),
            "sector_concentration": {k: round(v, 1) for k, v in self.sector_concentration.items()},
            "avg_correlation": round(self.avg_correlation, 2),
            "max_correlation_pair": self.max_correlation_pair,
            "max_correlation": round(self.max_correlation, 2),
            "diversification_score": round(self.diversification_score, 0),
            "total_delta": round(self.total_delta, 2),
            "total_theta_daily": round(self.total_theta_daily, 2),
            "total_vega": round(self.total_vega, 2),
            "total_gamma": round(self.total_gamma, 4),
            "portfolio_var_1d_95": round(self.portfolio_var_1d_95, 2),
            "portfolio_var_1d_99": round(self.portfolio_var_1d_99, 2),
            "current_drawdown": round(self.current_drawdown, 2),
            "max_drawdown_30d": round(self.max_drawdown_30d, 2),
            "limits": [l.to_dict() for l in self.limits],
            "violations": self.violations,
            "warnings": self.warnings,
            "positions": [p.to_dict() for p in self.positions],
            "reduce_positions": self.reduce_positions,
            "hedge_suggestions": self.hedge_suggestions,
            "notes": self.notes,
        }

    def get_summary(self) -> str:
        """Get human-readable summary for LLM consumption."""
        lines = [
            f"PORTFOLIO RISK REPORT - {self.timestamp.strftime('%H:%M ET')}",
            "=" * 50,
            "",
            f"VALUE: ${self.total_value:,.2f}",
            f"  Equity: ${self.total_equity:,.0f} ({self.total_equity/self.total_value*100:.0f}%)" if self.total_value > 0 else "",
            f"  Options: ${self.total_options:,.0f} ({self.total_options/self.total_value*100:.0f}%)" if self.total_options > 0 else "",
            f"  Cash: ${self.cash:,.0f} ({self.cash_pct:.0f}%)",
        ]

        # Concentration
        lines.extend([
            "",
            "CONCENTRATION:",
            f"  Largest Position: {self.largest_position} {self.largest_position_pct:.1f}%",
            f"  Top 5: {self.top_5_concentration:.1f}%",
        ])

        if self.sector_concentration:
            top_sector = max(self.sector_concentration.items(), key=lambda x: x[1])
            lines.append(f"  Top Sector: {top_sector[0]} {top_sector[1]:.1f}%")

        # Correlation
        lines.extend([
            "",
            "CORRELATION:",
            f"  Avg Correlation: {self.avg_correlation:.2f}",
            f"  Diversification Score: {self.diversification_score:.0f}/100",
        ])

        if self.max_correlation_pair and self.max_correlation > 0.7:
            lines.append(
                f"  ⚠️ High: {self.max_correlation_pair[0]}-{self.max_correlation_pair[1]}: {self.max_correlation:.2f}"
            )

        # Options Greeks
        if self.total_delta != 0 or self.total_theta_daily != 0:
            lines.extend([
                "",
                "OPTIONS GREEKS:",
                f"  Net Delta: ${self.total_delta:+,.0f}",
                f"  Daily Theta: ${self.total_theta_daily:+,.2f}",
                f"  Total Vega: ${self.total_vega:+,.0f}",
            ])

        # VaR
        lines.extend([
            "",
            "VALUE AT RISK (95% confidence):",
            f"  1-Day VaR: ${self.portfolio_var_1d_95:,.0f} ({self.portfolio_var_1d_95/self.total_value*100:.1f}%)" if self.total_value > 0 else "",
        ])

        if self.total_options > 0:
            lines.append(f"  Max Loss (options): ${self.total_options:,.0f}")

        # Limits
        lines.extend(["", "LIMIT STATUS:"])
        for limit in self.limits:
            emoji = "✅" if limit.status == "ok" else "⚠️" if limit.status == "warning" else "🚨"
            lines.append(f"  {emoji} {limit.name}: {limit.current:.1f}% / {limit.limit:.1f}%")

        # Violations and Warnings
        if self.violations:
            lines.extend(["", "🚨 VIOLATIONS:"])
            for v in self.violations:
                lines.append(f"  - {v}")

        if self.warnings:
            lines.extend(["", "⚠️ WARNINGS:"])
            for w in self.warnings:
                lines.append(f"  - {w}")

        # Recommendations
        if self.reduce_positions:
            lines.extend(["", "RECOMMENDATIONS - REDUCE:"])
            for r in self.reduce_positions[:3]:
                lines.append(f"  - {r}")

        if self.hedge_suggestions:
            lines.extend(["", "HEDGE SUGGESTIONS:"])
            for h in self.hedge_suggestions[:3]:
                lines.append(f"  - {h}")

        return "\n".join(lines)


class PositionRiskMonitor:
    """
    Real-time position and portfolio risk monitor.

    Tracks position-level and portfolio-level risk metrics,
    monitors risk limits, and generates recommendations.
    """

    def __init__(
        self,
        risk_limits: dict[str, float] | None = None,
    ):
        """
        Initialize risk monitor.

        Args:
            risk_limits: Risk limit thresholds
                - max_position_pct: Max single position as % of portfolio
                - max_sector_pct: Max sector concentration as % of portfolio
                - max_daily_loss_pct: Max daily loss as % of portfolio
                - max_correlation: Max correlation between positions
                - max_drawdown_pct: Max drawdown before alert
        """
        self.risk_limits = risk_limits or {
            "max_position_pct": 25.0,
            "max_sector_pct": 50.0,
            "max_daily_loss_pct": 5.0,
            "max_correlation": 0.80,
            "max_drawdown_pct": 10.0,
        }

        self._price_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._cache_ttl = timedelta(minutes=5)

    def _get_price_history(self, symbol: str, period: str = "60d") -> pd.DataFrame | None:
        """Get price history with caching."""
        cache_key = f"{symbol}_{period}"
        if cache_key in self._price_cache:
            cached_time, cached_data = self._price_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_data

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            if len(hist) > 0:
                self._price_cache[cache_key] = (datetime.now(), hist)
                return hist
        except Exception as e:
            logger.warning(f"Failed to get history for {symbol}: {e}")

        return None

    def _calculate_var(self, returns: pd.Series, value: float, confidence: float = 0.95) -> float:
        """Calculate Value at Risk."""
        if len(returns) < 20:
            return value * 0.05  # Default 5% VaR

        var_pct = np.percentile(returns, (1 - confidence) * 100)
        return abs(var_pct * value)

    def _calculate_beta(self, symbol_returns: pd.Series, spy_returns: pd.Series) -> float:
        """Calculate beta vs SPY."""
        if len(symbol_returns) < 20 or len(spy_returns) < 20:
            return 1.0

        # Align indices
        aligned = pd.concat([symbol_returns, spy_returns], axis=1, join="inner")
        if len(aligned) < 20:
            return 1.0

        cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
        var = aligned.iloc[:, 1].var()

        if var == 0:
            return 1.0

        return float(cov / var)

    def _calculate_correlation_matrix(self, positions: list[dict]) -> pd.DataFrame:
        """Calculate correlation matrix for positions."""
        symbols = [p["symbol"] for p in positions]
        if len(symbols) < 2:
            return pd.DataFrame()

        # Get returns for each symbol
        returns_data = {}
        for symbol in symbols:
            hist = self._get_price_history(symbol)
            if hist is not None and len(hist) > 0:
                returns_data[symbol] = hist["Close"].pct_change().dropna()

        if len(returns_data) < 2:
            return pd.DataFrame()

        # Create DataFrame and calculate correlation
        returns_df = pd.DataFrame(returns_data)
        return returns_df.corr()

    def get_position_risk(
        self,
        symbol: str,
        quantity: int,
        current_price: float,
        portfolio_value: float,
        position_type: str = "equity",
    ) -> PositionRisk:
        """
        Calculate risk metrics for a single position.

        Args:
            symbol: Stock symbol
            quantity: Number of shares/contracts
            current_price: Current price
            portfolio_value: Total portfolio value
            position_type: "equity" or "option"

        Returns:
            PositionRisk with all metrics
        """
        market_value = quantity * current_price
        weight_pct = (market_value / portfolio_value * 100) if portfolio_value > 0 else 0

        # Get historical data
        hist = self._get_price_history(symbol)
        spy_hist = self._get_price_history("SPY")

        # Calculate returns
        if hist is not None and len(hist) > 20:
            returns = hist["Close"].pct_change().dropna()
            historical_vol = float(returns.std() * np.sqrt(252))
            var_1d_95 = self._calculate_var(returns, market_value, 0.95)
            var_1d_99 = self._calculate_var(returns, market_value, 0.99)
        else:
            historical_vol = 0.30
            var_1d_95 = market_value * 0.03
            var_1d_99 = market_value * 0.05

        # Calculate beta
        if hist is not None and spy_hist is not None:
            symbol_returns = hist["Close"].pct_change().dropna()
            spy_returns = spy_hist["Close"].pct_change().dropna()
            beta = self._calculate_beta(symbol_returns, spy_returns)
            correlation_to_spy = float(symbol_returns.corr(spy_returns)) if len(symbol_returns) > 20 else 0.5
        else:
            beta = 1.0
            correlation_to_spy = 0.5

        # Max loss
        if position_type == "option":
            max_loss = market_value  # Options can go to zero
        else:
            max_loss = market_value  # Simplified - equity can also go to zero

        # Sector
        sector = SYMBOL_SECTORS.get(symbol.upper(), "Unknown")

        # Risk flags
        flags = []
        if weight_pct > self.risk_limits["max_position_pct"] * 0.8:
            flags.append("HIGH_CONCENTRATION")
        if historical_vol > 0.50:
            flags.append("HIGH_VOLATILITY")
        if beta > 1.5:
            flags.append("HIGH_BETA")

        return PositionRisk(
            symbol=symbol,
            position_type=position_type,
            quantity=quantity,
            current_price=current_price,
            market_value=market_value,
            weight_pct=weight_pct,
            var_1d_95=var_1d_95,
            var_1d_99=var_1d_99,
            max_loss=max_loss,
            historical_vol=historical_vol,
            beta=beta,
            correlation_to_spy=correlation_to_spy,
            sector=sector,
            flags=flags,
        )

    def get_portfolio_risk(
        self,
        positions: list[dict] | None = None,
        cash: float = 0.0,
    ) -> PortfolioRisk:
        """
        Calculate comprehensive portfolio risk.

        Args:
            positions: List of position dicts with keys:
                - symbol: Stock symbol
                - quantity: Number of shares/contracts
                - price: Current price
                - type: "equity" or "option" (optional)
                - delta: Option delta (optional)
                - theta: Option theta (optional)
            cash: Cash balance

        Returns:
            PortfolioRisk with all metrics
        """
        timestamp = datetime.now()

        if not positions:
            return PortfolioRisk(
                timestamp=timestamp,
                total_equity=0,
                total_options=0,
                total_value=cash,
                cash=cash,
                cash_pct=100.0,
                largest_position="",
                largest_position_pct=0,
                top_5_concentration=0,
            )

        # Calculate position risks
        position_risks = []
        total_equity = 0.0
        total_options = 0.0

        for pos in positions:
            pos_type = pos.get("type", "equity")
            market_value = pos["quantity"] * pos["price"]

            if pos_type == "option":
                total_options += market_value
            else:
                total_equity += market_value

        total_value = total_equity + total_options + cash

        # Calculate risk for each position
        for pos in positions:
            pos_type = pos.get("type", "equity")
            risk = self.get_position_risk(
                symbol=pos["symbol"],
                quantity=pos["quantity"],
                current_price=pos["price"],
                portfolio_value=total_value,
                position_type=pos_type,
            )

            # Add options Greeks if provided
            if pos_type == "option":
                risk.delta_exposure = pos.get("delta", 0) * 100 * pos["price"]
                risk.theta_exposure = pos.get("theta", 0) * 100
                risk.gamma_exposure = pos.get("gamma", 0)
                risk.vega_exposure = pos.get("vega", 0) * 100

            position_risks.append(risk)

        # Sort by weight
        position_risks.sort(key=lambda x: x.weight_pct, reverse=True)

        # Concentration metrics
        largest = position_risks[0] if position_risks else None
        top_5 = sum(p.weight_pct for p in position_risks[:5])

        # Sector concentration
        sector_values: dict[str, float] = {}
        for risk in position_risks:
            sector_values[risk.sector] = sector_values.get(risk.sector, 0) + risk.weight_pct

        # Correlation analysis
        corr_matrix = self._calculate_correlation_matrix(positions)
        avg_correlation = 0.0
        max_correlation = 0.0
        max_corr_pair = None

        if not corr_matrix.empty:
            # Get upper triangle (excluding diagonal)
            mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
            upper_corr = corr_matrix.where(mask)

            # Find average and max
            correlations = upper_corr.values.flatten()
            correlations = correlations[~np.isnan(correlations)]

            if len(correlations) > 0:
                avg_correlation = float(np.mean(correlations))
                max_correlation = float(np.max(correlations))

                # Find max pair
                max_idx = np.unravel_index(np.argmax(upper_corr.values), upper_corr.shape)
                max_corr_pair = (corr_matrix.index[max_idx[0]], corr_matrix.columns[max_idx[1]])

        # Diversification score (100 = perfectly diversified)
        diversification_score = max(0, min(100, (1 - avg_correlation) * 100))

        # Aggregate options Greeks
        total_delta = sum(p.delta_exposure for p in position_risks)
        total_theta = sum(p.theta_exposure for p in position_risks)
        total_vega = sum(p.vega_exposure for p in position_risks)
        total_gamma = sum(p.gamma_exposure for p in position_risks)

        # Portfolio VaR (simplified - sum of individual VaRs with correlation adjustment)
        individual_vars = [p.var_1d_95 for p in position_risks]
        if individual_vars:
            # Simple diversification factor
            div_factor = 1 - (avg_correlation * 0.3)  # Reduce VaR if diversified
            portfolio_var_95 = sum(individual_vars) * div_factor
            portfolio_var_99 = portfolio_var_95 * 1.3
        else:
            portfolio_var_95 = 0
            portfolio_var_99 = 0

        # Check limits
        limits = []
        violations = []
        warnings = []

        # Position size limit
        pos_limit = self.risk_limits["max_position_pct"]
        largest_pct = largest.weight_pct if largest else 0
        limits.append(LimitStatus(
            name="Position Size",
            current=largest_pct,
            limit=pos_limit,
            status="violated" if largest_pct > pos_limit else "warning" if largest_pct > pos_limit * 0.8 else "ok",
            pct_used=largest_pct / pos_limit * 100 if pos_limit > 0 else 0,
        ))
        if largest_pct > pos_limit:
            violations.append(f"{largest.symbol} exceeds position limit ({largest_pct:.1f}% > {pos_limit}%)")
        elif largest_pct > pos_limit * 0.8:
            warnings.append(f"{largest.symbol} approaching position limit ({largest_pct:.1f}%)")

        # Sector limit
        sector_limit = self.risk_limits["max_sector_pct"]
        if sector_values:
            max_sector = max(sector_values.items(), key=lambda x: x[1])
            limits.append(LimitStatus(
                name=f"Sector ({max_sector[0]})",
                current=max_sector[1],
                limit=sector_limit,
                status="violated" if max_sector[1] > sector_limit else "warning" if max_sector[1] > sector_limit * 0.8 else "ok",
                pct_used=max_sector[1] / sector_limit * 100 if sector_limit > 0 else 0,
            ))
            if max_sector[1] > sector_limit:
                violations.append(f"{max_sector[0]} sector exceeds limit ({max_sector[1]:.1f}% > {sector_limit}%)")

        # Correlation limit
        corr_limit = self.risk_limits["max_correlation"]
        if max_corr_pair and max_correlation > corr_limit:
            limits.append(LimitStatus(
                name="Correlation",
                current=max_correlation * 100,
                limit=corr_limit * 100,
                status="violated",
                pct_used=max_correlation / corr_limit * 100 if corr_limit > 0 else 0,
            ))
            violations.append(f"High correlation: {max_corr_pair[0]}-{max_corr_pair[1]} ({max_correlation:.2f})")

        # Generate recommendations
        reduce_positions = []
        hedge_suggestions = []
        notes = []

        # Recommend reducing high concentration
        for risk in position_risks:
            if risk.weight_pct > pos_limit * 0.8:
                reduce_positions.append(f"Consider reducing {risk.symbol} ({risk.weight_pct:.1f}% of portfolio)")

        # Recommend reducing correlated positions
        if max_correlation > 0.7 and max_corr_pair:
            reduce_positions.append(
                f"High correlation between {max_corr_pair[0]} and {max_corr_pair[1]} - consider reducing one"
            )

        # Hedge suggestions
        if total_delta > total_value * 0.5:
            hedge_suggestions.append(f"Net long delta ${total_delta:,.0f} - consider puts for protection")

        if abs(total_theta) > total_value * 0.001:  # More than 0.1% per day
            notes.append(f"Theta decay: ${abs(total_theta):.2f}/day")

        if avg_correlation > 0.6:
            hedge_suggestions.append("Low diversification - consider adding uncorrelated assets")

        return PortfolioRisk(
            timestamp=timestamp,
            total_equity=total_equity,
            total_options=total_options,
            total_value=total_value,
            cash=cash,
            cash_pct=(cash / total_value * 100) if total_value > 0 else 100,
            largest_position=largest.symbol if largest else "",
            largest_position_pct=largest.weight_pct if largest else 0,
            top_5_concentration=top_5,
            sector_concentration=sector_values,
            avg_correlation=avg_correlation,
            max_correlation_pair=max_corr_pair,
            max_correlation=max_correlation,
            diversification_score=diversification_score,
            total_delta=total_delta,
            total_theta_daily=total_theta,
            total_vega=total_vega,
            total_gamma=total_gamma,
            portfolio_var_1d_95=portfolio_var_95,
            portfolio_var_1d_99=portfolio_var_99,
            limits=limits,
            violations=violations,
            warnings=warnings,
            positions=position_risks,
            reduce_positions=reduce_positions,
            hedge_suggestions=hedge_suggestions,
            notes=notes,
        )

    def check_limits(self, portfolio_risk: PortfolioRisk) -> dict[str, LimitStatus]:
        """Check all risk limits and return status."""
        return {limit.name: limit for limit in portfolio_risk.limits}

    def get_correlations(self, positions: list[dict]) -> pd.DataFrame:
        """Get correlation matrix for positions."""
        return self._calculate_correlation_matrix(positions)

    def get_recommendations(self, portfolio_risk: PortfolioRisk) -> list[str]:
        """Get all risk reduction recommendations."""
        return portfolio_risk.reduce_positions + portfolio_risk.hedge_suggestions

    def get_summary(self, positions: list[dict], cash: float = 0.0) -> str:
        """Get human-readable summary for LLM consumption."""
        risk = self.get_portfolio_risk(positions, cash)
        return risk.get_summary()
