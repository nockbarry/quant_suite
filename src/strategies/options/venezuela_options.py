#!/usr/bin/env python3
"""
Venezuela Thesis Options Strategies

Novel options strategies based on research into:
- Event-driven options for geopolitical catalysts
- Low IV environment optimization
- Historical geopolitical event patterns
- Capital-efficient structures for small accounts

Research Sources:
- Iraq 2003, Libya 2011, Ukraine 2022 historical patterns
- IV crush patterns around earnings/events
- Volatility surface arbitrage opportunities

Usage:
    from src.strategies.options.venezuela_options import VenezuelaOptionsStrategies

    strategies = VenezuelaOptionsStrategies()
    trades = strategies.generate_trades("SLB", account_size=1000)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.paths import paths

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = paths.options_strategies


class StrategyType(Enum):
    """Types of options strategies."""
    DIAGONAL_SPREAD = "diagonal_spread"
    CALENDAR_SPREAD = "calendar_spread"
    IRON_CONDOR = "iron_condor"
    PMCC = "poor_mans_covered_call"
    LEAPS = "leaps"
    RATIO_BACKSPREAD = "ratio_backspread"
    BROKEN_WING_BUTTERFLY = "broken_wing_butterfly"
    RISK_REVERSAL = "risk_reversal"
    STRADDLE = "straddle"
    STRANGLE = "strangle"


@dataclass
class OptionsLeg:
    """Single leg of an options strategy."""
    option_type: str  # "call" or "put"
    strike: float
    expiration: str  # YYYY-MM-DD
    action: str  # "buy" or "sell"
    quantity: int
    estimated_price: float
    delta: float | None = None
    theta: float | None = None
    vega: float | None = None


@dataclass
class OptionsTrade:
    """Complete options trade recommendation."""
    strategy_type: StrategyType
    symbol: str
    legs: list[OptionsLeg]
    total_cost: float  # Positive = debit, negative = credit
    max_profit: float | None
    max_loss: float
    breakeven: list[float]
    probability_of_profit: float
    thesis: str
    entry_criteria: list[str]
    exit_criteria: list[str]
    risk_management: str
    confidence: float
    timeframe_days: int
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_type": self.strategy_type.value,
            "symbol": self.symbol,
            "legs": [
                {
                    "option_type": leg.option_type,
                    "strike": leg.strike,
                    "expiration": leg.expiration,
                    "action": leg.action,
                    "quantity": leg.quantity,
                    "estimated_price": leg.estimated_price,
                    "delta": leg.delta,
                }
                for leg in self.legs
            ],
            "total_cost": self.total_cost,
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "breakeven": self.breakeven,
            "probability_of_profit": self.probability_of_profit,
            "thesis": self.thesis,
            "entry_criteria": self.entry_criteria,
            "exit_criteria": self.exit_criteria,
            "risk_management": self.risk_management,
            "confidence": self.confidence,
            "timeframe_days": self.timeframe_days,
            "created_at": self.created_at.isoformat(),
        }


class VenezuelaOptionsStrategies:
    """Generate options strategies for Venezuela thesis."""

    # Strategy configurations based on research
    THESIS_STOCKS = {
        "SLB": {
            "thesis": "15 rigs already in Venezuela, first-mover on reconstruction",
            "expected_move": 0.30,  # +30%
            "timeframe_days": 180,
            "confidence": 0.75,
            "iv_typically_low": True,
        },
        "VLO": {
            "thesis": "Gulf Coast refiners optimized for Venezuelan heavy crude",
            "expected_move": 0.25,
            "timeframe_days": 365,
            "confidence": 0.80,  # Highest conviction per research
            "iv_typically_low": True,
            "earnings_date": "2026-01-29",  # Key catalyst
        },
        "HAL": {
            "thesis": "Oilfield services, first boots on ground for well repair",
            "expected_move": 0.25,
            "timeframe_days": 180,
            "confidence": 0.70,
            "iv_typically_low": True,
            "earnings_date": "2026-01-21",
        },
        "FRO": {
            "thesis": "Tanker rates elevated from shadow fleet disruption",
            "expected_move": 0.20,
            "timeframe_days": 120,
            "confidence": 0.65,
            "iv_typically_low": True,
        },
        "GLD": {
            "thesis": "Safe haven + Venezuela gold reserves access",
            "expected_move": 0.15,
            "timeframe_days": 180,
            "confidence": 0.60,
            "iv_typically_low": False,
        },
    }

    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_price(self, symbol: str) -> float:
        """Get current stock price."""
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")
        return hist["Close"].iloc[-1] if not hist.empty else 0

    def _get_expiration_dates(self, symbol: str) -> list[str]:
        """Get available options expiration dates."""
        ticker = yf.Ticker(symbol)
        return list(ticker.options) if ticker.options else []

    def _find_nearest_expiration(self, symbol: str, target_days: int) -> str | None:
        """Find expiration closest to target days out."""
        expirations = self._get_expiration_dates(symbol)
        if not expirations:
            return None

        target_date = datetime.now() + timedelta(days=target_days)

        closest = min(
            expirations,
            key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - target_date).days)
        )
        return closest

    def _estimate_option_price(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str,
    ) -> tuple[float, float]:
        """Estimate option price and delta from chain."""
        try:
            ticker = yf.Ticker(symbol)
            chain = ticker.option_chain(expiration)

            if option_type == "call":
                options = chain.calls
            else:
                options = chain.puts

            # Find closest strike
            options_sorted = options.iloc[(options['strike'] - strike).abs().argsort()]
            if len(options_sorted) > 0:
                opt = options_sorted.iloc[0]
                # Use mid price
                bid = opt.get("bid", 0) or 0
                ask = opt.get("ask", 0) or 0
                mid = (bid + ask) / 2 if ask > 0 else opt.get("lastPrice", 1.0)

                # Estimate delta from moneyness
                current = self._get_current_price(symbol)
                moneyness = strike / current
                if option_type == "call":
                    delta = max(0.1, min(0.9, 1.1 - moneyness))
                else:
                    delta = max(-0.9, min(-0.1, moneyness - 1.1))

                return mid, delta

        except Exception as e:
            logger.warning(f"Error getting option price: {e}")

        # Fallback estimate
        return 2.0, 0.50 if option_type == "call" else -0.50

    # =========================================================================
    # STRATEGY 1: DIAGONAL SPREAD
    # Best for: Uncertain catalyst timing, small accounts ($300-500)
    # Research: Combines vertical (direction) + calendar (time flexibility)
    # =========================================================================

    def diagonal_spread(self, symbol: str) -> OptionsTrade:
        """
        Diagonal Call Spread - Best for uncertain catalyst timing.

        Structure: Buy longer-dated ITM call + Sell shorter-dated OTM call
        - Profits from: theta differential, directional move, IV expansion
        - Can roll short leg monthly if catalyst delays
        """
        config = self.THESIS_STOCKS.get(symbol, {})
        current_price = self._get_current_price(symbol)

        # Long leg: 90 days out, slightly ITM (60-70 delta)
        long_exp = self._find_nearest_expiration(symbol, 90)
        long_strike = round(current_price * 0.95, 0)  # 5% ITM

        # Short leg: 30 days out, OTM (30-40 delta)
        short_exp = self._find_nearest_expiration(symbol, 30)
        short_strike = round(current_price * 1.10, 0)  # 10% OTM

        if not long_exp or not short_exp:
            raise ValueError(f"No suitable expirations for {symbol}")

        long_price, long_delta = self._estimate_option_price(symbol, long_strike, long_exp, "call")
        short_price, short_delta = self._estimate_option_price(symbol, short_strike, short_exp, "call")

        total_cost = (long_price - short_price) * 100

        return OptionsTrade(
            strategy_type=StrategyType.DIAGONAL_SPREAD,
            symbol=symbol,
            legs=[
                OptionsLeg("call", long_strike, long_exp, "buy", 1, long_price, long_delta),
                OptionsLeg("call", short_strike, short_exp, "sell", 1, short_price, short_delta),
            ],
            total_cost=total_cost,
            max_profit=None,  # Depends on roll management
            max_loss=total_cost,
            breakeven=[long_strike + (long_price - short_price)],
            probability_of_profit=0.55,
            thesis=config.get("thesis", "Venezuela reconstruction play"),
            entry_criteria=[
                "IV rank < 50% (options relatively cheap)",
                f"Stock price near ${current_price:.2f}",
                "No major earnings within short leg expiration",
            ],
            exit_criteria=[
                "Take profit at 50% of max",
                "Roll short leg if catalyst delays",
                "Exit if thesis invalidates",
            ],
            risk_management="Max loss is debit paid. Roll short leg monthly to reduce cost basis.",
            confidence=config.get("confidence", 0.70),
            timeframe_days=90,
        )

    # =========================================================================
    # STRATEGY 2: CALENDAR SPREAD
    # Best for: Low IV environments (current state), theta harvesting
    # Research: Optimal when IV < 30th percentile, profits from IV mean reversion
    # =========================================================================

    def calendar_spread(self, symbol: str) -> OptionsTrade:
        """
        Calendar Spread - Best for low IV environments.

        Structure: Sell near-term ATM + Buy longer-term ATM (same strike)
        - Profits from: theta differential (short decays faster), IV mean reversion
        - Best when expecting stock to stay range-bound near-term
        """
        config = self.THESIS_STOCKS.get(symbol, {})
        current_price = self._get_current_price(symbol)

        atm_strike = round(current_price, 0)

        # Short leg: 30 days
        short_exp = self._find_nearest_expiration(symbol, 30)
        # Long leg: 60 days
        long_exp = self._find_nearest_expiration(symbol, 60)

        if not short_exp or not long_exp:
            raise ValueError(f"No suitable expirations for {symbol}")

        short_price, _ = self._estimate_option_price(symbol, atm_strike, short_exp, "call")
        long_price, _ = self._estimate_option_price(symbol, atm_strike, long_exp, "call")

        total_cost = (long_price - short_price) * 100

        return OptionsTrade(
            strategy_type=StrategyType.CALENDAR_SPREAD,
            symbol=symbol,
            legs=[
                OptionsLeg("call", atm_strike, long_exp, "buy", 1, long_price),
                OptionsLeg("call", atm_strike, short_exp, "sell", 1, short_price),
            ],
            total_cost=total_cost,
            max_profit=total_cost * 0.50,  # Typically 50% of debit
            max_loss=total_cost,
            breakeven=[atm_strike],  # Max profit at strike
            probability_of_profit=0.50,
            thesis="Term structure arbitrage - sell expensive near-term IV, buy cheaper long-term IV",
            entry_criteria=[
                "IV rank < 30% (current environment)",
                "Front-month IV > back-month IV (backwardation)",
                "Expect stock to stay near current price short-term",
            ],
            exit_criteria=[
                "Take profit at 25-50% of debit",
                "Exit if stock moves >5% from strike",
                "Close before short expiration (avoid assignment)",
            ],
            risk_management="Close if IV term structure inverts (front IV << back IV)",
            confidence=0.70,
            timeframe_days=30,
        )

    # =========================================================================
    # STRATEGY 3: IRON CONDOR
    # Best for: IV mean reversion after geopolitical shock
    # Research: 30-40% IV crush typical within 4-6 weeks post-event
    # =========================================================================

    def iron_condor(self, symbol: str) -> OptionsTrade:
        """
        Iron Condor - Best for capturing IV mean reversion.

        Structure: Sell OTM put spread + Sell OTM call spread
        - Profits from: theta decay, IV contraction
        - Historical pattern: 30-40% IV crush in 4-6 weeks post-geopolitical event
        """
        config = self.THESIS_STOCKS.get(symbol, {})
        current_price = self._get_current_price(symbol)

        # 30-day expiration
        expiration = self._find_nearest_expiration(symbol, 30)
        if not expiration:
            raise ValueError(f"No suitable expiration for {symbol}")

        # Wings at ~10% OTM, protection at ~15% OTM
        put_short = round(current_price * 0.90, 0)
        put_long = round(current_price * 0.85, 0)
        call_short = round(current_price * 1.10, 0)
        call_long = round(current_price * 1.15, 0)

        # Estimate prices
        put_short_price, _ = self._estimate_option_price(symbol, put_short, expiration, "put")
        put_long_price, _ = self._estimate_option_price(symbol, put_long, expiration, "put")
        call_short_price, _ = self._estimate_option_price(symbol, call_short, expiration, "call")
        call_long_price, _ = self._estimate_option_price(symbol, call_long, expiration, "call")

        credit = (put_short_price - put_long_price + call_short_price - call_long_price) * 100
        wing_width = (call_long - call_short) * 100
        max_loss = wing_width - credit

        return OptionsTrade(
            strategy_type=StrategyType.IRON_CONDOR,
            symbol=symbol,
            legs=[
                OptionsLeg("put", put_long, expiration, "buy", 1, put_long_price),
                OptionsLeg("put", put_short, expiration, "sell", 1, put_short_price),
                OptionsLeg("call", call_short, expiration, "sell", 1, call_short_price),
                OptionsLeg("call", call_long, expiration, "buy", 1, call_long_price),
            ],
            total_cost=-credit,  # Credit received
            max_profit=credit,
            max_loss=max_loss,
            breakeven=[put_short - credit/100, call_short + credit/100],
            probability_of_profit=0.65,
            thesis="IV mean reversion - historical pattern shows 30-40% IV crush in 4-6 weeks post-event",
            entry_criteria=[
                "IV rank > 50% (elevated volatility)",
                "Day 5-10 post-event (after initial panic)",
                "No imminent binary catalyst (earnings, major news)",
            ],
            exit_criteria=[
                "Take profit at 50% of max credit",
                "Exit if stock approaches short strikes",
                "Close at 21 DTE to avoid gamma risk",
            ],
            risk_management="Exit immediately if VIX > 30 or thesis-breaking news",
            confidence=0.72,
            timeframe_days=30,
        )

    # =========================================================================
    # STRATEGY 4: POOR MAN'S COVERED CALL (PMCC)
    # Best for: Capital efficiency, accounts $1500+
    # Research: 70-80% capital efficiency vs stock ownership
    # =========================================================================

    def pmcc(self, symbol: str) -> OptionsTrade:
        """
        Poor Man's Covered Call - Capital efficient stock replacement.

        Structure: Buy deep ITM LEAPS (70-80 delta) + Sell monthly OTM calls
        - Reduces capital requirement by 70-80%
        - Generates monthly income while maintaining upside exposure
        """
        config = self.THESIS_STOCKS.get(symbol, {})
        current_price = self._get_current_price(symbol)

        # LEAPS: 9-12 months out, deep ITM (70-80 delta)
        leaps_exp = self._find_nearest_expiration(symbol, 270)  # ~9 months
        leaps_strike = round(current_price * 0.85, 0)  # 15% ITM

        # Short call: 30-45 days, OTM
        short_exp = self._find_nearest_expiration(symbol, 30)
        short_strike = round(current_price * 1.10, 0)  # 10% OTM

        if not leaps_exp or not short_exp:
            raise ValueError(f"No suitable expirations for {symbol}")

        leaps_price, leaps_delta = self._estimate_option_price(symbol, leaps_strike, leaps_exp, "call")
        short_price, _ = self._estimate_option_price(symbol, short_strike, short_exp, "call")

        total_cost = (leaps_price - short_price) * 100
        capital_savings = (current_price * 100) - total_cost

        return OptionsTrade(
            strategy_type=StrategyType.PMCC,
            symbol=symbol,
            legs=[
                OptionsLeg("call", leaps_strike, leaps_exp, "buy", 1, leaps_price, leaps_delta),
                OptionsLeg("call", short_strike, short_exp, "sell", 1, short_price),
            ],
            total_cost=total_cost,
            max_profit=None,  # Depends on roll management
            max_loss=total_cost,
            breakeven=[leaps_strike + (leaps_price - short_price)],
            probability_of_profit=0.60,
            thesis=f"Capital efficient exposure to {symbol}. Saves ${capital_savings:.0f} vs stock.",
            entry_criteria=[
                "LEAPS delta > 0.70 (acts like stock)",
                "IV relatively low for cheap entry",
                "Bullish thesis over 6-12 months",
            ],
            exit_criteria=[
                "Roll short calls monthly for income",
                "Close if stock down >20% (thesis broken)",
                "Take profit if LEAPS up 100%+",
            ],
            risk_management="Roll short call if threatened. Never let short expire ITM without managing.",
            confidence=config.get("confidence", 0.70),
            timeframe_days=270,
        )

    # =========================================================================
    # STRATEGY 5: VLO EARNINGS IV CRUSH PLAY
    # Best for: Highest conviction trade per historical research
    # Research: VLO earnings Jan 29 creates optimal entry during IV crush
    # =========================================================================

    def vlo_earnings_play(self) -> OptionsTrade:
        """
        VLO Post-Earnings Entry - Highest conviction trade.

        Based on research:
        - VLO jumped +5.3% premarket after Maduro capture
        - Gulf Coast refiners optimized for Venezuelan heavy crude
        - Earnings Jan 29 creates IV crush entry opportunity
        - Historical: 30-35% IV crush typical post-earnings
        """
        symbol = "VLO"
        current_price = self._get_current_price(symbol)

        # Entry: Post-earnings (Jan 30-31)
        # Target expirations: Mar 21 (60%) + Apr 18 (40%)
        mar_exp = self._find_nearest_expiration(symbol, 75)  # ~March
        apr_exp = self._find_nearest_expiration(symbol, 105)  # ~April

        if not mar_exp or not apr_exp:
            raise ValueError("Cannot find suitable VLO expirations")

        # Strikes based on price targets: $185 conservative, $200 base, $220 bull
        mar_strike = round(current_price * 1.15, 0)  # ~15% OTM for March
        apr_strike = round(current_price * 1.20, 0)  # ~20% OTM for April

        mar_price, mar_delta = self._estimate_option_price(symbol, mar_strike, mar_exp, "call")
        apr_price, apr_delta = self._estimate_option_price(symbol, apr_strike, apr_exp, "call")

        # 60/40 allocation
        total_cost = (0.6 * mar_price + 0.4 * apr_price) * 100

        return OptionsTrade(
            strategy_type=StrategyType.LEAPS,
            symbol=symbol,
            legs=[
                OptionsLeg("call", mar_strike, mar_exp, "buy", 1, mar_price, mar_delta),
                OptionsLeg("call", apr_strike, apr_exp, "buy", 1, apr_price, apr_delta),
            ],
            total_cost=total_cost,
            max_profit=None,  # Unlimited
            max_loss=total_cost,
            breakeven=[mar_strike + mar_price, apr_strike + apr_price],
            probability_of_profit=0.55,
            thesis=(
                "Gulf Coast refiners benefit from Venezuelan heavy crude access. "
                "VLO historically largest importer. $230M FCC upgrade completing 2026. "
                "Post-earnings IV crush creates optimal entry."
            ),
            entry_criteria=[
                "WAIT until Jan 30-31 (post-earnings IV crush)",
                "Positive margin guidance from earnings call",
                "IV crushed 30-35% from pre-earnings levels",
            ],
            exit_criteria=[
                "Take 50% profit at $185 target",
                "Take 100% profit at $200 target",
                "Take 200% profit at $220 target",
                "Stop loss if VLO breaks $155",
            ],
            risk_management="Position size 5-10% of portfolio. Stop loss at -50% or VLO < $155.",
            confidence=0.80,  # Highest conviction per research
            timeframe_days=90,
        )

    # =========================================================================
    # STRATEGY 6: STRANGLE FOR VOLATILITY EXPANSION
    # Best for: Binary geopolitical events (ELN attacks, policy shifts)
    # Research: 60-65% success rate when IV expands >10%
    # =========================================================================

    def strangle(self, symbol: str) -> OptionsTrade:
        """
        Long Strangle - Profits from volatility expansion.

        Structure: Buy OTM put + Buy OTM call
        - Profits from large move in either direction OR IV spike
        - Enter 2-4 weeks before anticipated catalyst
        - Research: 60-65% success when IV expands >10%
        """
        config = self.THESIS_STOCKS.get(symbol, {})
        current_price = self._get_current_price(symbol)

        # 45-day expiration for catalyst exposure
        expiration = self._find_nearest_expiration(symbol, 45)
        if not expiration:
            raise ValueError(f"No suitable expiration for {symbol}")

        # 30-40 delta wings
        put_strike = round(current_price * 0.92, 0)  # ~8% OTM
        call_strike = round(current_price * 1.08, 0)  # ~8% OTM

        put_price, put_delta = self._estimate_option_price(symbol, put_strike, expiration, "put")
        call_price, call_delta = self._estimate_option_price(symbol, call_strike, expiration, "call")

        total_cost = (put_price + call_price) * 100

        return OptionsTrade(
            strategy_type=StrategyType.STRANGLE,
            symbol=symbol,
            legs=[
                OptionsLeg("put", put_strike, expiration, "buy", 1, put_price, put_delta),
                OptionsLeg("call", call_strike, expiration, "buy", 1, call_price, call_delta),
            ],
            total_cost=total_cost,
            max_profit=None,  # Unlimited
            max_loss=total_cost,
            breakeven=[put_strike - total_cost/100, call_strike + total_cost/100],
            probability_of_profit=0.40,  # Lower POP but high reward
            thesis="Profit from volatility spike on chaos events (ELN attacks, policy shifts)",
            entry_criteria=[
                "IV rank < 50% (cheap options)",
                "Specific catalyst identified 2-4 weeks out",
                "Binary event with uncertain direction",
            ],
            exit_criteria=[
                "Take profit on 50%+ IV spike",
                "Exit if catalyst passes without movement",
                "Close at 14 DTE to avoid theta burn",
            ],
            risk_management="Only use for specific catalyst plays. Max 3% of portfolio per trade.",
            confidence=0.65,
            timeframe_days=45,
        )

    # =========================================================================
    # PORTFOLIO GENERATOR
    # =========================================================================

    def generate_portfolio(self, account_size: float) -> list[OptionsTrade]:
        """
        Generate recommended options portfolio based on account size.

        Research-based allocations:
        - $500-1000: Diagonal spreads only (capital efficient)
        - $1000-2000: Diagonals + Calendars + small LEAPS
        - $2000+: Full suite including PMCC
        """
        trades = []

        if account_size < 500:
            logger.warning("Account too small for options strategies")
            return trades

        if account_size >= 500:
            # Core diagonal on highest conviction
            trades.append(self.diagonal_spread("SLB"))

        if account_size >= 800:
            # Add calendar for IV harvesting
            trades.append(self.calendar_spread("VLO"))

        if account_size >= 1200:
            # Add VLO earnings play (wait for post-earnings entry)
            trades.append(self.vlo_earnings_play())

        if account_size >= 2000:
            # Add PMCC for capital efficiency
            trades.append(self.pmcc("SLB"))

        if account_size >= 3000:
            # Add iron condor for IV mean reversion
            trades.append(self.iron_condor("XLE"))
            # Add strangle for catalyst plays
            trades.append(self.strangle("HAL"))

        return trades

    def print_portfolio_report(self, account_size: float) -> None:
        """Print formatted portfolio recommendation."""
        trades = self.generate_portfolio(account_size)

        print("\n" + "=" * 80)
        print(f"VENEZUELA OPTIONS PORTFOLIO - ${account_size:,.0f} ACCOUNT")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)

        if not trades:
            print("\nAccount size too small for recommended strategies.")
            return

        total_capital_required = 0

        for i, trade in enumerate(trades, 1):
            cost = abs(trade.total_cost)
            total_capital_required += cost

            print(f"\n### TRADE {i}: {trade.strategy_type.value.upper()} - {trade.symbol}")
            print("-" * 60)
            print(f"Thesis: {trade.thesis[:80]}...")
            print(f"Confidence: {trade.confidence:.0%}")
            print(f"Timeframe: {trade.timeframe_days} days")

            print("\nLegs:")
            for leg in trade.legs:
                action = "BUY" if leg.action == "buy" else "SELL"
                print(f"  {action} {leg.quantity}x {trade.symbol} ${leg.strike} {leg.option_type.upper()} ({leg.expiration})")

            print(f"\nCost: ${trade.total_cost:,.0f}")
            print(f"Max Loss: ${trade.max_loss:,.0f}")
            if trade.max_profit:
                print(f"Max Profit: ${trade.max_profit:,.0f}")
            print(f"Probability of Profit: {trade.probability_of_profit:.0%}")

            print("\nEntry Criteria:")
            for criterion in trade.entry_criteria[:3]:
                print(f"  - {criterion}")

            print("\nExit Criteria:")
            for criterion in trade.exit_criteria[:3]:
                print(f"  - {criterion}")

        print("\n" + "=" * 80)
        print("PORTFOLIO SUMMARY")
        print("=" * 80)
        print(f"Total Trades: {len(trades)}")
        print(f"Total Capital Required: ${total_capital_required:,.0f}")
        print(f"Remaining Cash: ${account_size - total_capital_required:,.0f}")
        print(f"Capital Utilization: {total_capital_required/account_size:.0%}")

        # Risk summary
        avg_confidence = sum(t.confidence for t in trades) / len(trades)
        print(f"\nAverage Confidence: {avg_confidence:.0%}")
        print(f"Max Portfolio Risk: ${total_capital_required:,.0f} (if all trades max loss)")

    def save_trades(self, trades: list[OptionsTrade], filename: str = "trades.json") -> None:
        """Save trades to JSON."""
        filepath = self.output_dir / filename
        data = [t.to_dict() for t in trades]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(trades)} trades to {filepath}")


def main():
    """Generate and display Venezuela options strategies."""
    strategies = VenezuelaOptionsStrategies()

    # Test different account sizes
    for account_size in [500, 1000, 2000]:
        strategies.print_portfolio_report(account_size)

    # Save recommended trades
    trades = strategies.generate_portfolio(2000)
    strategies.save_trades(trades, "venezuela_options_trades.json")


if __name__ == "__main__":
    main()
