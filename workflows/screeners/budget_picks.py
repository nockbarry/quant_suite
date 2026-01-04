"""Budget Picks Screener - Alt-data driven screener for small capital traders.

Designed for $200-$2,000 accounts. Identifies opportunities that:
1. Are affordable (price $1-100, fractional-share friendly)
2. Have sufficient liquidity (>200k daily volume)
3. Are small/mid cap ($500M-$10B) - higher growth potential
4. Show positive alternative data signals (insider buying, social sentiment)
5. Aren't overbought (RSI < 50, no recent price run-up)

This screener combines fundamental universe filtering with alternative data
signals to find high-conviction opportunities that can't be detected from
price data alone.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np
import pandas as pd
import yfinance as yf

from src.core import SP500_TOP_50
from src.core.universe_manager import (
    AssetMetadata,
    LiquidityTier,
    MarketCapTier,
    UniverseFilters,
    UniverseManager,
)

logger = logging.getLogger(__name__)


@dataclass
class BudgetPickSignal:
    """Individual signal for a budget pick candidate."""

    source: str
    signal: Literal["bullish", "bearish", "neutral"]
    strength: float  # 0-1
    confidence: float  # 0-1
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "signal": self.signal,
            "strength": self.strength,
            "confidence": self.confidence,
            "details": self.details,
        }


@dataclass
class BudgetPick:
    """A stock identified as a potential budget pick."""

    symbol: str
    score: float  # -1 to 1, overall composite score
    rating: Literal["strong_buy", "buy", "watch", "neutral", "avoid"]
    metadata: AssetMetadata | None = None
    signals: list[BudgetPickSignal] = field(default_factory=list)
    price_data: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @property
    def bullish_count(self) -> int:
        return sum(1 for s in self.signals if s.signal == "bullish")

    @property
    def bearish_count(self) -> int:
        return sum(1 for s in self.signals if s.signal == "bearish")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "rating": self.rating,
            "bullish_signals": self.bullish_count,
            "bearish_signals": self.bearish_count,
            "price": self.price_data.get("price"),
            "market_cap_tier": self.metadata.market_cap_tier.value if self.metadata else None,
            "sector": self.metadata.sector if self.metadata else None,
            "reason": self.reason,
            "signals": [s.to_dict() for s in self.signals],
            "price_data": self.price_data,
        }


class BudgetPicksScreener:
    """
    Screener for finding budget-friendly stock opportunities.

    Criteria:
    - Market cap: $500M - $10B (small/mid cap, higher growth potential)
    - Price: $1 - $100 (affordable for small accounts)
    - Volume: > 200k shares/day (adequate liquidity)
    - Not in sectors: Real Estate, Utilities (low growth for small accounts)

    Signal Sources:
    - Insider buying (highest weight - Form 4 purchases)
    - Reddit sentiment (contrarian indicator when combined with fundamentals)
    - Price momentum (looking for beaten-down but not broken stocks)
    - RSI (avoiding overbought conditions)
    - Sector momentum (sector tailwinds)
    """

    def __init__(
        self,
        universe_manager: UniverseManager | None = None,
        signal_weights: dict[str, float] | None = None,
    ):
        """
        Initialize the budget picks screener.

        Args:
            universe_manager: UniverseManager instance for filtering
            signal_weights: Custom weights for signal sources
        """
        self.universe_manager = universe_manager or UniverseManager()
        self.weights = signal_weights or {
            "insider": 0.35,  # Highest weight - informed buyers
            "reddit": 0.15,  # Contrarian/sentiment
            "momentum": 0.20,  # Price momentum (negative is good for entry)
            "rsi": 0.15,  # Not overbought
            "sector": 0.15,  # Sector tailwinds
        }

        # Budget-specific filters
        self.budget_filters = UniverseFilters(
            min_price=1.0,
            max_price=100.0,
            min_volume=200_000,
            min_market_cap=500_000_000,
            max_market_cap=10_000_000_000,
            exclude_sectors=["Real Estate", "Utilities"],  # Low growth for budget
        )

    async def screen(
        self,
        symbols: list[str],
        lookback_days: int = 60,
        top_n: int = 10,
    ) -> list[BudgetPick]:
        """
        Screen symbols for budget picks.

        Args:
            symbols: List of symbols to screen
            lookback_days: Days of history to analyze
            top_n: Number of top picks to return

        Returns:
            List of BudgetPick objects, sorted by score
        """
        logger.info(f"Screening {len(symbols)} symbols for budget picks")

        # Step 1: Filter universe by budget criteria
        eligible_symbols = self._filter_universe(symbols)
        logger.info(f"{len(eligible_symbols)} symbols pass budget filters")

        if not eligible_symbols:
            return []

        # Step 2: Get metadata for eligible symbols
        metadata_map = self.universe_manager.get_metadata_batch(eligible_symbols)

        # Step 3: Get price data and compute technical signals
        price_data = await self._get_price_data(eligible_symbols, lookback_days)

        # Step 4: Get alternative data signals
        insider_signals = await self._get_insider_signals(eligible_symbols, lookback_days)
        reddit_signals = await self._get_reddit_signals(eligible_symbols)

        # Step 5: Score each symbol
        picks = []
        for symbol in eligible_symbols:
            pick = self._score_symbol(
                symbol,
                metadata_map.get(symbol),
                price_data.get(symbol, {}),
                insider_signals.get(symbol, {}),
                reddit_signals.get(symbol, {}),
            )
            if pick.score > -0.5:  # Filter out strong avoids
                picks.append(pick)

        # Sort by score and return top N
        picks.sort(key=lambda p: p.score, reverse=True)
        return picks[:top_n]

    def _filter_universe(self, symbols: list[str]) -> list[str]:
        """Filter symbols by budget criteria."""
        return self.universe_manager.filter_universe(symbols, self.budget_filters)

    async def _get_price_data(
        self,
        symbols: list[str],
        lookback_days: int,
    ) -> dict[str, dict[str, Any]]:
        """Get price data and compute technical indicators."""
        result = {}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date)

                if hist.empty:
                    continue

                close = hist["Close"]
                current_price = float(close.iloc[-1])

                # Compute RSI
                rsi = self._compute_rsi(close, period=14)

                # Compute momentum (rate of change)
                momentum_1m = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0
                momentum_3m = (close.iloc[-1] / close.iloc[0] - 1) * 100

                # Compute volatility
                returns = close.pct_change().dropna()
                volatility = float(returns.std() * np.sqrt(252) * 100)

                result[symbol] = {
                    "price": current_price,
                    "rsi": rsi,
                    "momentum_1m": float(momentum_1m),
                    "momentum_3m": float(momentum_3m),
                    "volatility": volatility,
                    "avg_volume": float(hist["Volume"].mean()),
                    "52w_high": float(close.max()),
                    "52w_low": float(close.min()),
                    "pct_from_high": ((current_price / close.max()) - 1) * 100,
                }
            except Exception as e:
                logger.warning(f"Failed to get price data for {symbol}: {e}")
                continue

        return result

    def _compute_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Compute RSI (Relative Strength Index)."""
        if len(prices) < period + 1:
            return 50.0  # Neutral if insufficient data

        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    async def _get_insider_signals(
        self,
        symbols: list[str],
        lookback_days: int,
    ) -> dict[str, dict[str, Any]]:
        """
        Get insider trading signals.

        Looks for:
        - Net buying activity (buys > sells)
        - C-suite buying (CEO, CFO, COO)
        - Cluster buying (multiple insiders)
        """
        result = {}

        try:
            from src.data.sources.alternative.insider import InsiderDataSource

            insider_source = InsiderDataSource()

            for symbol in symbols:
                try:
                    transactions = await insider_source.get_transactions(
                        symbol,
                        days=lookback_days,
                    )

                    if not transactions:
                        result[symbol] = {"has_data": False}
                        continue

                    # Compute metrics
                    buys = [t for t in transactions if t.is_purchase]
                    sells = [t for t in transactions if t.is_sale]

                    buy_value = sum(t.value for t in buys)
                    sell_value = sum(t.value for t in sells)

                    # C-suite activity
                    csuite_roles = ["CEO", "CFO", "COO", "President"]
                    csuite_buys = [t for t in buys if t.insider_role.value in csuite_roles]

                    result[symbol] = {
                        "has_data": True,
                        "buy_count": len(buys),
                        "sell_count": len(sells),
                        "net_buys": len(buys) - len(sells),
                        "buy_value": buy_value,
                        "sell_value": sell_value,
                        "net_value": buy_value - sell_value,
                        "csuite_buys": len(csuite_buys),
                        "unique_buyers": len(set(t.insider_name for t in buys)),
                    }
                except Exception as e:
                    logger.debug(f"No insider data for {symbol}: {e}")
                    result[symbol] = {"has_data": False}

        except ImportError:
            logger.warning("InsiderDataSource not available")
            for symbol in symbols:
                result[symbol] = {"has_data": False}

        return result

    async def _get_reddit_signals(
        self,
        symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        """
        Get Reddit sentiment signals.

        Uses Reddit mentions and sentiment as a contrarian indicator.
        Extreme bullishness on Reddit often precedes pullbacks.
        """
        result = {}

        try:
            from src.data.sources.alternative.reddit import RedditDataSource

            reddit_source = RedditDataSource()

            for symbol in symbols:
                try:
                    sentiment = await reddit_source.get_sentiment_summary(symbol)

                    if sentiment:
                        result[symbol] = {
                            "has_data": True,
                            "mentions": sentiment.get("mentions", 0),
                            "sentiment_score": sentiment.get("sentiment_score", 0),
                            "bullish_ratio": sentiment.get("bullish_ratio", 0.5),
                        }
                    else:
                        result[symbol] = {"has_data": False}
                except Exception as e:
                    logger.debug(f"No Reddit data for {symbol}: {e}")
                    result[symbol] = {"has_data": False}

        except ImportError:
            logger.warning("RedditDataSource not available")
            for symbol in symbols:
                result[symbol] = {"has_data": False}

        return result

    def _score_symbol(
        self,
        symbol: str,
        metadata: AssetMetadata | None,
        price_data: dict[str, Any],
        insider_data: dict[str, Any],
        reddit_data: dict[str, Any],
    ) -> BudgetPick:
        """Score a symbol based on all signals."""
        signals = []
        total_score = 0.0
        reasons = []

        # 1. Insider signal
        insider_signal = self._score_insider(insider_data)
        signals.append(insider_signal)
        total_score += insider_signal.strength * self.weights["insider"] * (1 if insider_signal.signal == "bullish" else -1 if insider_signal.signal == "bearish" else 0)

        if insider_signal.signal == "bullish" and insider_signal.strength > 0.5:
            reasons.append("Strong insider buying")

        # 2. Reddit signal (contrarian - extreme bullish is bearish for us)
        reddit_signal = self._score_reddit(reddit_data)
        signals.append(reddit_signal)
        # Invert for contrarian signal
        reddit_contribution = reddit_signal.strength * self.weights["reddit"]
        if reddit_signal.signal == "bearish":
            total_score += reddit_contribution  # Contrarian: Reddit bearish = bullish for us
        elif reddit_signal.signal == "bullish":
            total_score -= reddit_contribution * 0.5  # Mild negative

        # 3. Momentum signal (prefer beaten-down stocks)
        momentum_signal = self._score_momentum(price_data)
        signals.append(momentum_signal)
        total_score += momentum_signal.strength * self.weights["momentum"] * (1 if momentum_signal.signal == "bullish" else -1 if momentum_signal.signal == "bearish" else 0)

        if momentum_signal.signal == "bullish":
            reasons.append(f"Beaten-down price ({price_data.get('momentum_3m', 0):.1f}% off highs)")

        # 4. RSI signal (prefer not overbought)
        rsi_signal = self._score_rsi(price_data)
        signals.append(rsi_signal)
        total_score += rsi_signal.strength * self.weights["rsi"] * (1 if rsi_signal.signal == "bullish" else -1 if rsi_signal.signal == "bearish" else 0)

        if rsi_signal.signal == "bullish":
            reasons.append(f"Not overbought (RSI {price_data.get('rsi', 50):.0f})")

        # 5. Sector signal
        sector_signal = self._score_sector(metadata)
        signals.append(sector_signal)
        total_score += sector_signal.strength * self.weights["sector"] * (1 if sector_signal.signal == "bullish" else -1 if sector_signal.signal == "bearish" else 0)

        # Determine rating
        if total_score >= 0.5:
            rating = "strong_buy"
        elif total_score >= 0.2:
            rating = "buy"
        elif total_score >= 0:
            rating = "watch"
        elif total_score >= -0.3:
            rating = "neutral"
        else:
            rating = "avoid"

        return BudgetPick(
            symbol=symbol,
            score=total_score,
            rating=rating,
            metadata=metadata,
            signals=signals,
            price_data=price_data,
            reason="; ".join(reasons) if reasons else "Mixed signals",
        )

    def _score_insider(self, data: dict[str, Any]) -> BudgetPickSignal:
        """Score insider trading activity."""
        if not data.get("has_data"):
            return BudgetPickSignal(
                source="insider",
                signal="neutral",
                strength=0.0,
                confidence=0.1,
                details={"status": "no_data"},
            )

        net_buys = data.get("net_buys", 0)
        csuite_buys = data.get("csuite_buys", 0)
        unique_buyers = data.get("unique_buyers", 0)

        # Scoring logic
        score = 0.0
        if net_buys > 0:
            score += min(net_buys * 0.2, 0.5)  # Up to 0.5 for buying
        if csuite_buys > 0:
            score += min(csuite_buys * 0.3, 0.6)  # C-suite is highly weighted
        if unique_buyers >= 2:
            score += 0.2  # Cluster buying

        score = min(score, 1.0)

        if score >= 0.4:
            signal = "bullish"
        elif score <= -0.2 or data.get("net_value", 0) < -100000:
            signal = "bearish"
        else:
            signal = "neutral"

        return BudgetPickSignal(
            source="insider",
            signal=signal,
            strength=abs(score),
            confidence=min(0.3 + unique_buyers * 0.1 + csuite_buys * 0.2, 0.9),
            details={
                "net_buys": net_buys,
                "csuite_buys": csuite_buys,
                "unique_buyers": unique_buyers,
            },
        )

    def _score_reddit(self, data: dict[str, Any]) -> BudgetPickSignal:
        """Score Reddit sentiment (contrarian indicator)."""
        if not data.get("has_data"):
            return BudgetPickSignal(
                source="reddit",
                signal="neutral",
                strength=0.0,
                confidence=0.1,
                details={"status": "no_data"},
            )

        bullish_ratio = data.get("bullish_ratio", 0.5)
        mentions = data.get("mentions", 0)

        # High bullishness on Reddit is a contrarian sell signal
        if bullish_ratio > 0.8:
            signal = "bullish"  # Extreme bullish = contrarian bearish
            strength = 0.7
        elif bullish_ratio > 0.6:
            signal = "bullish"
            strength = 0.3
        elif bullish_ratio < 0.3:
            signal = "bearish"  # Low bullish = contrarian bullish
            strength = 0.5
        else:
            signal = "neutral"
            strength = 0.1

        # Adjust confidence based on mention volume
        confidence = min(0.2 + mentions / 100 * 0.3, 0.7)

        return BudgetPickSignal(
            source="reddit",
            signal=signal,
            strength=strength,
            confidence=confidence,
            details={
                "bullish_ratio": bullish_ratio,
                "mentions": mentions,
            },
        )

    def _score_momentum(self, data: dict[str, Any]) -> BudgetPickSignal:
        """Score price momentum (prefer beaten-down stocks)."""
        if not data:
            return BudgetPickSignal(
                source="momentum",
                signal="neutral",
                strength=0.0,
                confidence=0.1,
            )

        momentum_3m = data.get("momentum_3m", 0)
        pct_from_high = data.get("pct_from_high", 0)

        # We want stocks that are down but not in freefall
        # Sweet spot: -10% to -30% from 3-month high
        if -30 <= pct_from_high <= -10:
            signal = "bullish"
            strength = 0.7
        elif -40 <= pct_from_high < -10 or (0 > pct_from_high > -10):
            signal = "neutral"
            strength = 0.3
        elif pct_from_high > 0:
            signal = "bearish"  # At highs, avoid
            strength = 0.5
        else:  # More than -40%
            signal = "bearish"  # Freefall, avoid
            strength = 0.6

        return BudgetPickSignal(
            source="momentum",
            signal=signal,
            strength=strength,
            confidence=0.6,
            details={
                "momentum_3m": momentum_3m,
                "pct_from_high": pct_from_high,
            },
        )

    def _score_rsi(self, data: dict[str, Any]) -> BudgetPickSignal:
        """Score RSI - prefer not overbought."""
        if not data:
            return BudgetPickSignal(
                source="rsi",
                signal="neutral",
                strength=0.0,
                confidence=0.1,
            )

        rsi = data.get("rsi", 50)

        if rsi < 30:
            signal = "bullish"  # Oversold
            strength = 0.8
        elif rsi < 50:
            signal = "bullish"  # Normal, not overbought
            strength = 0.4
        elif rsi < 70:
            signal = "neutral"
            strength = 0.2
        else:
            signal = "bearish"  # Overbought
            strength = 0.7

        return BudgetPickSignal(
            source="rsi",
            signal=signal,
            strength=strength,
            confidence=0.5,
            details={"rsi": rsi},
        )

    def _score_sector(self, metadata: AssetMetadata | None) -> BudgetPickSignal:
        """Score based on sector."""
        if not metadata or not metadata.sector:
            return BudgetPickSignal(
                source="sector",
                signal="neutral",
                strength=0.0,
                confidence=0.1,
            )

        # Sectors favorable for budget growth investors
        bullish_sectors = {"Technology", "Consumer Cyclical", "Healthcare", "Communication Services"}
        neutral_sectors = {"Financial Services", "Industrials", "Consumer Defensive"}
        bearish_sectors = {"Utilities", "Real Estate", "Energy"}  # Less suitable for budget

        sector = metadata.sector
        if sector in bullish_sectors:
            signal = "bullish"
            strength = 0.5
        elif sector in bearish_sectors:
            signal = "bearish"
            strength = 0.4
        else:
            signal = "neutral"
            strength = 0.2

        return BudgetPickSignal(
            source="sector",
            signal=signal,
            strength=strength,
            confidence=0.4,
            details={"sector": sector},
        )


async def run_budget_screener(
    symbols: list[str] | None = None,
    top_n: int = 10,
) -> list[BudgetPick]:
    """
    Run the budget picks screener.

    Args:
        symbols: List of symbols to screen (defaults to SP500 top 50)
        top_n: Number of picks to return

    Returns:
        List of BudgetPick objects
    """
    if symbols is None:
        symbols = SP500_TOP_50

    screener = BudgetPicksScreener()
    return await screener.screen(symbols, top_n=top_n)


def print_picks(picks: list[BudgetPick]) -> None:
    """Print budget picks in a formatted table."""
    print("\n" + "=" * 80)
    print("BUDGET PICKS SCREENER RESULTS")
    print("=" * 80)

    if not picks:
        print("No picks found matching criteria.")
        return

    for i, pick in enumerate(picks, 1):
        print(f"\n{i}. {pick.symbol} - {pick.rating.upper()}")
        print(f"   Score: {pick.score:.2f}")
        print(f"   Price: ${pick.price_data.get('price', 'N/A'):.2f}" if pick.price_data.get('price') else "   Price: N/A")
        if pick.metadata:
            print(f"   Sector: {pick.metadata.sector}")
            print(f"   Market Cap: {pick.metadata.market_cap_tier.value}")
        print(f"   Reason: {pick.reason}")
        print(f"   Signals: {pick.bullish_count} bullish, {pick.bearish_count} bearish")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    import asyncio

    async def main():
        picks = await run_budget_screener(top_n=10)
        print_picks(picks)

    asyncio.run(main())
