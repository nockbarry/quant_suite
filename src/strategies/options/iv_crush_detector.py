#!/usr/bin/env python3
"""
IV Crush Detector

Detects IV crush opportunities around earnings and events.
Based on research: 30-40% IV crush typical within days of earnings.

Usage:
    from src.strategies.options.iv_crush_detector import IVCrushDetector

    detector = IVCrushDetector()
    opportunities = detector.scan_earnings_plays()
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class IVCrushOpportunity:
    """Potential IV crush trading opportunity."""
    symbol: str
    earnings_date: datetime
    days_until_earnings: int
    current_iv: float
    historical_iv_avg: float
    iv_premium_pct: float  # How elevated IV is vs historical
    expected_iv_crush: float  # Expected % IV decline
    strategy_recommendation: str
    confidence: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "earnings_date": self.earnings_date.isoformat(),
            "days_until_earnings": self.days_until_earnings,
            "current_iv": self.current_iv,
            "historical_iv_avg": self.historical_iv_avg,
            "iv_premium_pct": self.iv_premium_pct,
            "expected_iv_crush": self.expected_iv_crush,
            "strategy_recommendation": self.strategy_recommendation,
            "confidence": self.confidence,
            "notes": self.notes,
        }


class IVCrushDetector:
    """Detect IV crush opportunities around earnings."""

    # Venezuela thesis stocks with known earnings
    WATCHLIST = {
        "VLO": {"earnings_date": "2026-01-29", "sector": "refiner"},
        "HAL": {"earnings_date": "2026-01-21", "sector": "oilfield_services"},
        "SLB": {"earnings_date": "2026-01-17", "sector": "oilfield_services"},
        "PSX": {"earnings_date": "2026-01-31", "sector": "refiner"},
        "BKR": {"earnings_date": "2026-01-23", "sector": "oilfield_services"},
    }

    def __init__(self):
        self.iv_cache = {}

    def _get_realized_vol(self, symbol: str, days: int = 30) -> float:
        """Calculate realized volatility."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if hist.empty:
                return 0.30  # Default 30%

            returns = hist["Close"].pct_change().dropna()
            rv = returns.tail(days).std() * np.sqrt(252)
            return rv

        except Exception as e:
            logger.warning(f"Error getting RV for {symbol}: {e}")
            return 0.30

    def _get_current_atm_iv(self, symbol: str) -> float:
        """Get current ATM implied volatility."""
        try:
            ticker = yf.Ticker(symbol)
            current_price = ticker.history(period="1d")["Close"].iloc[-1]

            # Get nearest expiration
            expirations = ticker.options
            if not expirations:
                raise ValueError("No options data")

            # Find expiration ~30 days out
            target_date = datetime.now() + timedelta(days=30)
            nearest_exp = min(
                expirations[:5],
                key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d") - target_date).days)
            )

            chain = ticker.option_chain(nearest_exp)

            # Get ATM options
            calls = chain.calls
            calls_sorted = calls.iloc[(calls['strike'] - current_price).abs().argsort()]

            if len(calls_sorted) > 0:
                atm = calls_sorted.iloc[0]
                iv = atm.get("impliedVolatility", 0)
                if iv and iv > 0.01:  # Filter placeholder values
                    return iv

            # Fallback to realized vol * 1.15
            return self._get_realized_vol(symbol) * 1.15

        except Exception as e:
            logger.warning(f"Error getting IV for {symbol}: {e}")
            return self._get_realized_vol(symbol) * 1.15

    def _get_historical_iv_avg(self, symbol: str) -> float:
        """Estimate historical average IV from realized vol."""
        # Use 1-year realized vol as proxy for average IV
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")
        if hist.empty:
            return 0.30

        returns = hist["Close"].pct_change().dropna()

        # 20-day rolling vol, then average
        rolling_vol = returns.rolling(20).std() * np.sqrt(252)
        avg_rv = rolling_vol.mean()

        # IV typically trades at 10-20% premium to RV
        return avg_rv * 1.15

    def _calculate_expected_crush(
        self,
        current_iv: float,
        historical_avg: float,
        days_to_earnings: int
    ) -> float:
        """
        Calculate expected IV crush based on research.

        Research findings:
        - Pre-earnings IV typically 20-50% above historical
        - Post-earnings crush is 30-40% within 1-2 days
        - Crush magnitude correlates with IV premium
        """
        iv_premium = (current_iv - historical_avg) / historical_avg

        # Base crush estimate (30-40% range)
        if iv_premium > 0.40:
            base_crush = 0.40  # Heavy premium = heavy crush
        elif iv_premium > 0.20:
            base_crush = 0.35
        elif iv_premium > 0.10:
            base_crush = 0.30
        else:
            base_crush = 0.20  # Low premium = smaller crush

        # Adjust for days to earnings
        if days_to_earnings > 10:
            # IV hasn't fully inflated yet
            base_crush *= 0.7
        elif days_to_earnings < 3:
            # Maximum crush expected
            base_crush *= 1.1

        return min(base_crush, 0.50)  # Cap at 50%

    def analyze_symbol(self, symbol: str) -> IVCrushOpportunity | None:
        """Analyze a symbol for IV crush opportunity."""
        config = self.WATCHLIST.get(symbol)
        if not config:
            return None

        try:
            earnings_date = datetime.strptime(config["earnings_date"], "%Y-%m-%d")
        except:
            return None

        days_until = (earnings_date - datetime.now()).days
        if days_until < 0:
            return None  # Earnings passed

        current_iv = self._get_current_atm_iv(symbol)
        historical_avg = self._get_historical_iv_avg(symbol)
        iv_premium = (current_iv - historical_avg) / historical_avg
        expected_crush = self._calculate_expected_crush(current_iv, historical_avg, days_until)

        # Determine strategy recommendation
        notes = []

        if days_until > 7:
            if iv_premium > 0.20:
                strategy = "WAIT - IV elevated but too early. Monitor for entry post-earnings."
                confidence = 0.60
                notes.append("Entry window: 1-2 days after earnings")
            else:
                strategy = "WATCH - IV not yet elevated. May build closer to earnings."
                confidence = 0.50
                notes.append("IV typically inflates 5-7 days before earnings")
        elif days_until > 2:
            if iv_premium > 0.30:
                strategy = "PRE-EARNINGS SELL - IV richly priced. Consider iron condor or short straddle."
                confidence = 0.70
                notes.append("High IV premium = good for selling premium")
            elif iv_premium > 0.15:
                strategy = "NEUTRAL - IV moderately elevated. Wait for post-earnings entry."
                confidence = 0.55
            else:
                strategy = "BUY PRE-EARNINGS - IV relatively cheap. Consider long straddle."
                confidence = 0.50
                notes.append("Low IV = cheap options for directional bet")
        else:
            strategy = "IMMINENT EARNINGS - Avoid new positions. Wait for crush."
            confidence = 0.40
            notes.append("Max uncertainty. Spreads very wide.")

        # Add sector context
        if config["sector"] == "refiner":
            notes.append("Refiner: Watch for margin guidance on Venezuelan crude access")
        elif config["sector"] == "oilfield_services":
            notes.append("Oilfield services: Watch for contract pipeline commentary")

        return IVCrushOpportunity(
            symbol=symbol,
            earnings_date=earnings_date,
            days_until_earnings=days_until,
            current_iv=current_iv,
            historical_iv_avg=historical_avg,
            iv_premium_pct=iv_premium * 100,
            expected_iv_crush=expected_crush * 100,
            strategy_recommendation=strategy,
            confidence=confidence,
            notes=notes,
        )

    def scan_earnings_plays(self) -> list[IVCrushOpportunity]:
        """Scan watchlist for IV crush opportunities."""
        opportunities = []

        for symbol in self.WATCHLIST:
            opp = self.analyze_symbol(symbol)
            if opp:
                opportunities.append(opp)

        # Sort by days until earnings
        opportunities.sort(key=lambda x: x.days_until_earnings)

        return opportunities

    def print_earnings_calendar(self) -> None:
        """Print formatted earnings calendar with IV analysis."""
        opportunities = self.scan_earnings_plays()

        print("\n" + "=" * 80)
        print("VENEZUELA THESIS - EARNINGS IV CRUSH CALENDAR")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)

        if not opportunities:
            print("\nNo upcoming earnings in watchlist.")
            return

        print(f"\n{'Symbol':<8} {'Earnings':<12} {'Days':<6} {'IV Now':<8} {'IV Avg':<8} {'Premium':<10} {'Exp Crush':<10}")
        print("-" * 80)

        for opp in opportunities:
            print(
                f"{opp.symbol:<8} "
                f"{opp.earnings_date.strftime('%Y-%m-%d'):<12} "
                f"{opp.days_until_earnings:<6} "
                f"{opp.current_iv:.1%}   "
                f"{opp.historical_iv_avg:.1%}   "
                f"{opp.iv_premium_pct:+.0f}%      "
                f"{opp.expected_iv_crush:.0f}%"
            )

        print("\n" + "=" * 80)
        print("TRADING RECOMMENDATIONS")
        print("=" * 80)

        for opp in opportunities:
            print(f"\n{opp.symbol} (Earnings: {opp.earnings_date.strftime('%b %d')}, {opp.days_until_earnings} days)")
            print(f"  Strategy: {opp.strategy_recommendation}")
            print(f"  Confidence: {opp.confidence:.0%}")
            for note in opp.notes:
                print(f"  - {note}")

        # Highlight best opportunities
        best = [o for o in opportunities if o.confidence >= 0.65]
        if best:
            print("\n" + "=" * 80)
            print("TOP OPPORTUNITIES")
            print("=" * 80)
            for opp in best:
                print(f"\n  {opp.symbol}: {opp.strategy_recommendation}")


def main():
    """Run IV crush scanner."""
    detector = IVCrushDetector()
    detector.print_earnings_calendar()


if __name__ == "__main__":
    main()
