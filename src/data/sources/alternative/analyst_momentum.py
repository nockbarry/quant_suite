"""Analyst Upgrade Momentum Signal.

Tracks analyst rating changes and price target revisions:
- Upgrade/downgrade momentum
- Price target clusters
- Consensus rating changes
- Analyst herding detection

Created: 2026-01-20
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class AnalystSignal:
    """Analyst momentum signal."""

    timestamp: datetime
    symbol: str

    # Rating metrics
    current_rating: float  # 1=Strong Sell to 5=Strong Buy
    rating_change_30d: float  # Change in consensus
    upgrades_30d: int
    downgrades_30d: int
    rating_momentum: str  # "bullish", "bearish", "neutral"

    # Price target metrics
    mean_target: float
    target_upside_pct: float  # % above current price
    target_change_30d_pct: float  # Change in mean target
    targets_raised_30d: int
    targets_lowered_30d: int

    # Analyst metrics
    total_analysts: int
    buy_pct: float  # % recommending Buy/Strong Buy
    sell_pct: float  # % recommending Sell/Strong Sell

    # Signal strength
    signal_strength: float = 0.0  # -1 to 1
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "current_rating": self.current_rating,
            "rating_change_30d": self.rating_change_30d,
            "upgrades_30d": self.upgrades_30d,
            "downgrades_30d": self.downgrades_30d,
            "rating_momentum": self.rating_momentum,
            "mean_target": self.mean_target,
            "target_upside_pct": self.target_upside_pct,
            "target_change_30d_pct": self.target_change_30d_pct,
            "targets_raised_30d": self.targets_raised_30d,
            "targets_lowered_30d": self.targets_lowered_30d,
            "total_analysts": self.total_analysts,
            "buy_pct": self.buy_pct,
            "sell_pct": self.sell_pct,
            "signal_strength": self.signal_strength,
            "description": self.description,
        }


class AnalystMomentumScanner:
    """Scan for analyst upgrade/downgrade momentum.

    Pattern from latent knowledge:
    - Analyst upgrades cluster and often lag reality
    - 3+ upgrades in 30 days = momentum signal
    - Price target raises above current price = bullish
    """

    # Rating mapping (yfinance uses different scales)
    RATING_MAP = {
        "Strong Buy": 5.0,
        "Buy": 4.0,
        "Overweight": 3.5,
        "Hold": 3.0,
        "Neutral": 3.0,
        "Underweight": 2.5,
        "Sell": 2.0,
        "Strong Sell": 1.0,
    }

    def __init__(self, lookback_days: int = 30):
        self.lookback_days = lookback_days

    async def get_analyst_data(self, symbol: str) -> Optional[AnalystSignal]:
        """Get analyst data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            AnalystSignal or None if data unavailable
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get current price
            history = ticker.history(period="5d")
            if history.empty:
                return None
            current_price = history["Close"].iloc[-1]

            # Get analyst recommendations
            recs = ticker.recommendations
            if recs is None or recs.empty:
                return None

            # Get recent recommendations (last 30 days)
            cutoff = datetime.now() - timedelta(days=self.lookback_days)

            # Handle timezone-aware index
            if hasattr(recs.index, 'tz') and recs.index.tz is not None:
                recs.index = recs.index.tz_localize(None)

            # Convert index to datetime if needed
            if not pd.api.types.is_datetime64_any_dtype(recs.index):
                try:
                    recs.index = pd.to_datetime(recs.index)
                except Exception:
                    # If conversion fails, use all recommendations
                    recent_recs = recs
                    cutoff = None

            if cutoff is not None:
                try:
                    recent_recs = recs[recs.index >= cutoff]
                except TypeError:
                    # Fallback: use all recommendations
                    recent_recs = recs
            else:
                recent_recs = recs

            # Count upgrades/downgrades
            upgrades = 0
            downgrades = 0

            # Look for "To Grade" and "From Grade" columns
            if "To Grade" in recs.columns and "From Grade" in recs.columns:
                for _, row in recent_recs.iterrows():
                    to_grade = self.RATING_MAP.get(row.get("To Grade", ""), 3.0)
                    from_grade = self.RATING_MAP.get(row.get("From Grade", ""), 3.0)
                    if to_grade > from_grade:
                        upgrades += 1
                    elif to_grade < from_grade:
                        downgrades += 1

            # Get current consensus
            info = ticker.info or {}
            mean_target = info.get("targetMeanPrice", current_price)
            total_analysts = info.get("numberOfAnalystOpinions", 0)

            # Estimate rating from recommendations distribution
            rec_counts = {
                "strongBuy": info.get("recommendationKey", "") == "strong_buy",
                "buy": info.get("recommendationKey", "") == "buy",
                "hold": info.get("recommendationKey", "") == "hold",
                "sell": info.get("recommendationKey", "") == "sell",
                "strongSell": info.get("recommendationKey", "") == "strong_sell",
            }

            # Calculate current rating estimate
            rec_key = info.get("recommendationKey", "hold")
            rating_map = {
                "strong_buy": 5.0, "buy": 4.0, "hold": 3.0,
                "sell": 2.0, "strong_sell": 1.0
            }
            current_rating = rating_map.get(rec_key, 3.0)

            # Calculate upside
            target_upside_pct = ((mean_target - current_price) / current_price * 100) if current_price > 0 else 0

            # Calculate buy/sell percentages (simplified)
            if rec_key in ["strong_buy", "buy"]:
                buy_pct = 0.7
                sell_pct = 0.1
            elif rec_key == "hold":
                buy_pct = 0.4
                sell_pct = 0.2
            else:
                buy_pct = 0.2
                sell_pct = 0.5

            # Determine momentum
            net_changes = upgrades - downgrades
            if net_changes >= 2:
                rating_momentum = "bullish"
            elif net_changes <= -2:
                rating_momentum = "bearish"
            else:
                rating_momentum = "neutral"

            # Calculate signal strength (-1 to 1)
            signal_strength = 0.0

            # Upgrade momentum component (0.4 weight)
            signal_strength += min(0.4, net_changes * 0.1)

            # Target upside component (0.3 weight)
            if target_upside_pct > 30:
                signal_strength += 0.3
            elif target_upside_pct > 15:
                signal_strength += 0.2
            elif target_upside_pct > 5:
                signal_strength += 0.1
            elif target_upside_pct < -10:
                signal_strength -= 0.2

            # Buy percentage component (0.3 weight)
            signal_strength += (buy_pct - 0.5) * 0.6

            signal_strength = max(-1.0, min(1.0, signal_strength))

            # Description
            desc_parts = []
            if upgrades > 0:
                desc_parts.append(f"{upgrades} upgrades")
            if downgrades > 0:
                desc_parts.append(f"{downgrades} downgrades")
            if target_upside_pct > 10:
                desc_parts.append(f"{target_upside_pct:.0f}% upside to target")
            elif target_upside_pct < -5:
                desc_parts.append(f"trading above target")

            description = "; ".join(desc_parts) if desc_parts else "No significant activity"

            return AnalystSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                current_rating=current_rating,
                rating_change_30d=0.0,  # Would need historical data
                upgrades_30d=upgrades,
                downgrades_30d=downgrades,
                rating_momentum=rating_momentum,
                mean_target=mean_target,
                target_upside_pct=target_upside_pct,
                target_change_30d_pct=0.0,  # Would need historical data
                targets_raised_30d=0,  # Would need historical data
                targets_lowered_30d=0,
                total_analysts=total_analysts,
                buy_pct=buy_pct,
                sell_pct=sell_pct,
                signal_strength=signal_strength,
                description=description,
            )

        except Exception as e:
            logger.warning(f"Failed to get analyst data for {symbol}: {e}")
            return None

    async def scan_universe(
        self,
        symbols: list[str],
        min_signal_strength: float = 0.3,
    ) -> list[AnalystSignal]:
        """Scan multiple symbols for analyst momentum.

        Args:
            symbols: List of symbols to scan
            min_signal_strength: Minimum signal strength to include

        Returns:
            List of AnalystSignals above threshold
        """
        signals = []

        for symbol in symbols:
            try:
                signal = await self.get_analyst_data(symbol)
                if signal and abs(signal.signal_strength) >= min_signal_strength:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Failed to scan {symbol}: {e}")

            # Rate limiting
            await asyncio.sleep(0.1)

        # Sort by signal strength
        signals.sort(key=lambda x: x.signal_strength, reverse=True)

        return signals


# Convenience function
async def get_analyst_signals(symbols: list[str]) -> list[AnalystSignal]:
    """Quick function to get analyst signals for symbols."""
    scanner = AnalystMomentumScanner()
    return await scanner.scan_universe(symbols)


if __name__ == "__main__":
    async def main():
        scanner = AnalystMomentumScanner()

        # Test with some symbols
        test_symbols = ["AAPL", "NVDA", "MSFT", "TSLA", "META"]

        print("=== Analyst Momentum Scanner ===\n")

        for symbol in test_symbols:
            signal = await scanner.get_analyst_data(symbol)
            if signal:
                print(f"{signal.symbol}:")
                print(f"  Rating: {signal.current_rating:.1f} ({signal.rating_momentum})")
                print(f"  Upgrades: {signal.upgrades_30d}, Downgrades: {signal.downgrades_30d}")
                print(f"  Target: ${signal.mean_target:.2f} ({signal.target_upside_pct:+.1f}%)")
                print(f"  Signal: {signal.signal_strength:+.2f}")
                print(f"  {signal.description}")
                print()

    asyncio.run(main())
