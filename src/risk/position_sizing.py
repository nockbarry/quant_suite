"""Position sizing algorithms for risk management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from ..core import Portfolio, Signal, Symbol


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation."""

    symbol: Symbol
    target_quantity: Decimal
    target_value: Decimal
    target_weight: float
    method: str
    metadata: dict[str, Any]


class PositionSizer(ABC):
    """Abstract base class for position sizing algorithms."""

    name: str = "base"

    @abstractmethod
    def calculate(
        self,
        signal: Signal,
        portfolio: Portfolio,
        price: Decimal,
        **kwargs: Any,
    ) -> PositionSizeResult:
        """
        Calculate position size for a signal.

        Args:
            signal: Trading signal
            portfolio: Current portfolio state
            price: Current asset price
            **kwargs: Additional parameters

        Returns:
            PositionSizeResult with target position
        """
        ...


class FixedFractionalSizer(PositionSizer):
    """
    Fixed fractional position sizing.

    Allocates a fixed percentage of portfolio to each position.
    """

    name = "fixed_fractional"

    def __init__(
        self,
        fraction: float = 0.10,
        max_fraction: float = 0.25,
        scale_by_strength: bool = True,
    ):
        """
        Initialize fixed fractional sizer.

        Args:
            fraction: Base fraction of portfolio per position
            max_fraction: Maximum fraction per position
            scale_by_strength: Scale position by signal strength
        """
        self.fraction = fraction
        self.max_fraction = max_fraction
        self.scale_by_strength = scale_by_strength

    def calculate(
        self,
        signal: Signal,
        portfolio: Portfolio,
        price: Decimal,
        **kwargs: Any,
    ) -> PositionSizeResult:
        """Calculate fixed fractional position size."""
        portfolio_value = portfolio.total_value

        # Base allocation
        target_fraction = self.fraction

        # Scale by signal strength
        if self.scale_by_strength:
            target_fraction *= abs(signal.strength)

        # Apply maximum
        target_fraction = min(target_fraction, self.max_fraction)

        # Calculate target value and quantity
        target_value = Decimal(str(float(portfolio_value) * target_fraction))
        target_quantity = target_value / price

        # Apply direction
        if signal.strength < 0:
            target_quantity = -target_quantity

        return PositionSizeResult(
            symbol=signal.symbol,
            target_quantity=target_quantity,
            target_value=abs(target_value),
            target_weight=target_fraction,
            method=self.name,
            metadata={
                "base_fraction": self.fraction,
                "signal_strength": signal.strength,
                "scaled_fraction": target_fraction,
            },
        )


class VolatilityTargetSizer(PositionSizer):
    """
    Volatility targeting position sizing.

    Sizes positions to achieve a target volatility contribution.
    """

    name = "volatility_target"

    def __init__(
        self,
        target_volatility: float = 0.15,
        lookback_days: int = 20,
        max_weight: float = 0.25,
        annualization_factor: float = 252.0,
    ):
        """
        Initialize volatility target sizer.

        Args:
            target_volatility: Target annualized volatility
            lookback_days: Days for volatility calculation
            max_weight: Maximum position weight
            annualization_factor: Factor to annualize volatility
        """
        self.target_volatility = target_volatility
        self.lookback_days = lookback_days
        self.max_weight = max_weight
        self.annualization_factor = annualization_factor

    def calculate(
        self,
        signal: Signal,
        portfolio: Portfolio,
        price: Decimal,
        returns: pd.Series | None = None,
        volatility: float | None = None,
        **kwargs: Any,
    ) -> PositionSizeResult:
        """
        Calculate volatility-targeted position size.

        Args:
            signal: Trading signal
            portfolio: Current portfolio
            price: Current price
            returns: Historical returns series (optional)
            volatility: Pre-calculated volatility (optional)
        """
        # Get or calculate volatility
        if volatility is not None:
            asset_vol = volatility
        elif returns is not None:
            asset_vol = float(returns.tail(self.lookback_days).std() * np.sqrt(self.annualization_factor))
        else:
            # Default to moderate volatility
            asset_vol = 0.20

        # Avoid division by zero
        if asset_vol < 0.01:
            asset_vol = 0.01

        # Calculate target weight
        # Weight = TargetVol / AssetVol * SignalStrength
        target_weight = (self.target_volatility / asset_vol) * abs(signal.strength)

        # Apply maximum
        target_weight = min(target_weight, self.max_weight)

        # Calculate target value and quantity
        portfolio_value = portfolio.total_value
        target_value = Decimal(str(float(portfolio_value) * target_weight))
        target_quantity = target_value / price

        # Apply direction
        if signal.strength < 0:
            target_quantity = -target_quantity

        return PositionSizeResult(
            symbol=signal.symbol,
            target_quantity=target_quantity,
            target_value=abs(target_value),
            target_weight=target_weight,
            method=self.name,
            metadata={
                "target_volatility": self.target_volatility,
                "asset_volatility": asset_vol,
                "signal_strength": signal.strength,
                "raw_weight": (self.target_volatility / asset_vol) * abs(signal.strength),
            },
        )


class KellySizer(PositionSizer):
    """
    Kelly Criterion position sizing.

    Calculates optimal position size based on win rate and payoff ratio.
    """

    name = "kelly"

    def __init__(
        self,
        kelly_fraction: float = 0.25,
        max_weight: float = 0.25,
        min_trades: int = 30,
    ):
        """
        Initialize Kelly sizer.

        Args:
            kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly)
            max_weight: Maximum position weight
            min_trades: Minimum trades required for Kelly calculation
        """
        self.kelly_fraction = kelly_fraction
        self.max_weight = max_weight
        self.min_trades = min_trades

    def calculate(
        self,
        signal: Signal,
        portfolio: Portfolio,
        price: Decimal,
        win_rate: float | None = None,
        avg_win: float | None = None,
        avg_loss: float | None = None,
        trade_history: pd.Series | None = None,
        **kwargs: Any,
    ) -> PositionSizeResult:
        """
        Calculate Kelly position size.

        Args:
            signal: Trading signal
            portfolio: Current portfolio
            price: Current price
            win_rate: Win rate (0-1)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return (positive number)
            trade_history: Historical trade returns
        """
        # Calculate Kelly inputs from history if not provided
        if trade_history is not None and len(trade_history) >= self.min_trades:
            wins = trade_history[trade_history > 0]
            losses = trade_history[trade_history < 0]

            win_rate = len(wins) / len(trade_history) if len(trade_history) > 0 else 0.5
            avg_win = float(wins.mean()) if len(wins) > 0 else 0.01
            avg_loss = float(abs(losses.mean())) if len(losses) > 0 else 0.01

        # Use defaults if still not available
        if win_rate is None:
            win_rate = 0.5
        if avg_win is None:
            avg_win = 0.02
        if avg_loss is None:
            avg_loss = 0.02

        # Calculate Kelly percentage
        # Kelly % = W - (1-W)/R where W=win rate, R=win/loss ratio
        if avg_loss > 0:
            win_loss_ratio = avg_win / avg_loss
            kelly_pct = win_rate - (1 - win_rate) / win_loss_ratio
        else:
            kelly_pct = 0

        # Apply fraction and bounds
        kelly_pct = max(0, kelly_pct)  # No negative Kelly
        target_weight = kelly_pct * self.kelly_fraction * abs(signal.strength)
        target_weight = min(target_weight, self.max_weight)

        # Calculate target value and quantity
        portfolio_value = portfolio.total_value
        target_value = Decimal(str(float(portfolio_value) * target_weight))
        target_quantity = target_value / price

        # Apply direction
        if signal.strength < 0:
            target_quantity = -target_quantity

        return PositionSizeResult(
            symbol=signal.symbol,
            target_quantity=target_quantity,
            target_value=abs(target_value),
            target_weight=target_weight,
            method=self.name,
            metadata={
                "full_kelly": kelly_pct,
                "kelly_fraction": self.kelly_fraction,
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "win_loss_ratio": avg_win / avg_loss if avg_loss > 0 else 0,
            },
        )


class EqualWeightSizer(PositionSizer):
    """
    Equal weight position sizing.

    Allocates equal weight to all positions in the portfolio.
    """

    name = "equal_weight"

    def __init__(
        self,
        max_positions: int = 10,
        min_weight: float = 0.02,
    ):
        """
        Initialize equal weight sizer.

        Args:
            max_positions: Maximum number of positions
            min_weight: Minimum weight per position
        """
        self.max_positions = max_positions
        self.min_weight = min_weight

    def calculate(
        self,
        signal: Signal,
        portfolio: Portfolio,
        price: Decimal,
        num_signals: int = 1,
        **kwargs: Any,
    ) -> PositionSizeResult:
        """Calculate equal weight position size."""
        # Weight per position
        effective_positions = min(num_signals, self.max_positions)
        target_weight = 1.0 / effective_positions

        # Apply minimum
        if target_weight < self.min_weight:
            target_weight = self.min_weight

        # Scale by signal strength (optional - keeps positions somewhat equal)
        strength_scale = 0.5 + 0.5 * abs(signal.strength)  # 0.5 to 1.0
        target_weight *= strength_scale

        # Calculate target value and quantity
        portfolio_value = portfolio.total_value
        target_value = Decimal(str(float(portfolio_value) * target_weight))
        target_quantity = target_value / price

        # Apply direction
        if signal.strength < 0:
            target_quantity = -target_quantity

        return PositionSizeResult(
            symbol=signal.symbol,
            target_quantity=target_quantity,
            target_value=abs(target_value),
            target_weight=target_weight,
            method=self.name,
            metadata={
                "max_positions": self.max_positions,
                "num_signals": num_signals,
                "base_weight": 1.0 / effective_positions,
                "strength_scale": strength_scale,
            },
        )


class RiskParitySizer(PositionSizer):
    """
    Risk parity position sizing.

    Sizes positions so each contributes equally to portfolio risk.
    """

    name = "risk_parity"

    def __init__(
        self,
        target_volatility: float = 0.10,
        max_weight: float = 0.30,
    ):
        """
        Initialize risk parity sizer.

        Args:
            target_volatility: Target portfolio volatility
            max_weight: Maximum position weight
        """
        self.target_volatility = target_volatility
        self.max_weight = max_weight

    def calculate(
        self,
        signal: Signal,
        portfolio: Portfolio,
        price: Decimal,
        volatilities: dict[Symbol, float] | None = None,
        asset_volatility: float | None = None,
        **kwargs: Any,
    ) -> PositionSizeResult:
        """
        Calculate risk parity position size.

        Args:
            signal: Trading signal
            portfolio: Current portfolio
            price: Current price
            volatilities: Dictionary of asset volatilities
            asset_volatility: Volatility for this specific asset
        """
        # Get asset volatility
        if asset_volatility is not None:
            vol = asset_volatility
        elif volatilities is not None and signal.symbol in volatilities:
            vol = volatilities[signal.symbol]
        else:
            vol = 0.20  # Default

        # Avoid division by zero
        if vol < 0.01:
            vol = 0.01

        # Calculate inverse vol weight
        # In full risk parity, we'd use all assets' vols
        # Here we use a simplified single-asset version
        inv_vol_weight = 1.0 / vol

        # Normalize to achieve target volatility
        # Weight = TargetVol / AssetVol (simplified)
        target_weight = self.target_volatility / vol

        # Scale by signal strength
        target_weight *= abs(signal.strength)

        # Apply maximum
        target_weight = min(target_weight, self.max_weight)

        # Calculate target value and quantity
        portfolio_value = portfolio.total_value
        target_value = Decimal(str(float(portfolio_value) * target_weight))
        target_quantity = target_value / price

        # Apply direction
        if signal.strength < 0:
            target_quantity = -target_quantity

        return PositionSizeResult(
            symbol=signal.symbol,
            target_quantity=target_quantity,
            target_value=abs(target_value),
            target_weight=target_weight,
            method=self.name,
            metadata={
                "asset_volatility": vol,
                "inverse_vol_weight": inv_vol_weight,
                "target_volatility": self.target_volatility,
            },
        )


def get_position_sizer(method: str, **kwargs: Any) -> PositionSizer:
    """
    Factory function to get a position sizer by name.

    Args:
        method: Sizer method name
        **kwargs: Sizer configuration

    Returns:
        PositionSizer instance
    """
    sizers = {
        "fixed_fractional": FixedFractionalSizer,
        "volatility_target": VolatilityTargetSizer,
        "kelly": KellySizer,
        "equal_weight": EqualWeightSizer,
        "risk_parity": RiskParitySizer,
    }

    if method not in sizers:
        raise ValueError(f"Unknown position sizing method: {method}")

    return sizers[method](**kwargs)
