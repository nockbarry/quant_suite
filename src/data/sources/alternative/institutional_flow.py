#!/usr/bin/env python3
"""
Institutional Flow Scorecard

Aggregates signals from options flow, short interest, and analyst ratings
to create a composite institutional sentiment score.

Usage:
    from src.data.sources.alternative.institutional_flow import InstitutionalFlowScorecard

    scorecard = InstitutionalFlowScorecard()
    report = scorecard.generate_report(["SLB", "VLO", "HAL"])
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

OUTPUT_DIR = Path("/home/nock/quant_results/institutional_flow")


@dataclass
class FlowScore:
    """Individual flow signal score."""
    category: str  # "options", "short_interest", "analyst", "etf_flow"
    score: int  # -2 to +2
    signal: str  # Description
    confidence: float  # 0-1
    raw_value: Any = None


@dataclass
class InstitutionalScore:
    """Composite institutional flow score for a symbol."""
    symbol: str
    timestamp: datetime
    composite_score: float  # -10 to +10
    sentiment: str  # "strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"
    scores: list[FlowScore]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "composite_score": self.composite_score,
            "sentiment": self.sentiment,
            "scores": [
                {
                    "category": s.category,
                    "score": s.score,
                    "signal": s.signal,
                    "confidence": s.confidence,
                    "raw_value": s.raw_value,
                }
                for s in self.scores
            ],
            "recommendation": self.recommendation,
        }


class InstitutionalFlowScorecard:
    """Generate institutional flow scorecards for stocks."""

    def __init__(self):
        self.cache: dict[str, dict] = {}

    def _get_options_flow_score(self, symbol: str) -> FlowScore:
        """
        Analyze options flow for institutional positioning.

        Signals:
        - High call volume relative to puts = bullish
        - High put volume relative to calls = bearish
        - Large OI changes = positioning
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get options chain for next few expirations
            expirations = ticker.options[:4] if ticker.options else []

            total_call_volume = 0
            total_put_volume = 0
            total_call_oi = 0
            total_put_oi = 0

            for exp in expirations:
                try:
                    chain = ticker.option_chain(exp)
                    total_call_volume += chain.calls["volume"].sum()
                    total_put_volume += chain.puts["volume"].sum()
                    total_call_oi += chain.calls["openInterest"].sum()
                    total_put_oi += chain.puts["openInterest"].sum()
                except Exception:
                    continue

            if total_put_volume == 0:
                pc_ratio = 0.5  # Default neutral
            else:
                pc_ratio = total_call_volume / max(total_put_volume, 1)

            if total_put_oi == 0:
                oi_ratio = 1.0
            else:
                oi_ratio = total_call_oi / max(total_put_oi, 1)

            # Score based on P/C ratio
            # P/C < 0.7 = bearish (more puts), P/C > 1.3 = bullish (more calls)
            if pc_ratio > 1.5:
                score = 2
                signal = f"Strong call activity (P/C ratio: {pc_ratio:.2f})"
            elif pc_ratio > 1.2:
                score = 1
                signal = f"Bullish call flow (P/C ratio: {pc_ratio:.2f})"
            elif pc_ratio < 0.7:
                score = -2
                signal = f"Strong put activity (P/C ratio: {pc_ratio:.2f})"
            elif pc_ratio < 0.9:
                score = -1
                signal = f"Bearish put flow (P/C ratio: {pc_ratio:.2f})"
            else:
                score = 0
                signal = f"Neutral options flow (P/C ratio: {pc_ratio:.2f})"

            return FlowScore(
                category="options",
                score=score,
                signal=signal,
                confidence=0.7,
                raw_value={"pc_ratio": pc_ratio, "oi_ratio": oi_ratio},
            )

        except Exception as e:
            logger.warning(f"Options flow error for {symbol}: {e}")
            return FlowScore(
                category="options",
                score=0,
                signal="Options data unavailable",
                confidence=0.0,
            )

    def _get_short_interest_score(self, symbol: str) -> FlowScore:
        """
        Estimate short interest sentiment from price/volume patterns.

        Since free short interest data is limited, we use:
        - Days to cover approximation from avg volume
        - Recent price action vs volume (short covering patterns)
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get recent history
            hist = ticker.history(period="3mo")
            if hist.empty or len(hist) < 20:
                raise ValueError("Insufficient data")

            # Calculate metrics
            avg_volume = hist["Volume"].tail(20).mean()
            recent_return = (hist["Close"].iloc[-1] / hist["Close"].iloc[-20]) - 1

            # Check for short covering pattern:
            # Rising price + increasing volume = potential short covering
            price_trend = np.polyfit(range(10), hist["Close"].tail(10).values, 1)[0]
            volume_trend = np.polyfit(range(10), hist["Volume"].tail(10).values, 1)[0]

            # Normalize trends
            price_up = price_trend > 0
            volume_up = volume_trend > 0

            if price_up and volume_up:
                # Rising price + volume = bullish, possible short covering
                score = 1
                signal = "Price rising on volume (bullish)"
            elif price_up and not volume_up:
                # Rising price on declining volume = weak rally
                score = 0
                signal = "Price up on low volume (neutral)"
            elif not price_up and volume_up:
                # Falling price on high volume = distribution/bearish
                score = -1
                signal = "Price falling on volume (bearish)"
            else:
                # Falling price on low volume = neutral
                score = 0
                signal = "Low conviction price action"

            # Boost score if strong recent returns
            if recent_return > 0.10:
                score = min(score + 1, 2)
                signal += " [Strong momentum]"
            elif recent_return < -0.10:
                score = max(score - 1, -2)
                signal += " [Weak momentum]"

            return FlowScore(
                category="short_interest",
                score=score,
                signal=signal,
                confidence=0.5,  # Lower confidence since we're estimating
                raw_value={
                    "recent_return": recent_return,
                    "price_up": price_up,
                    "volume_up": volume_up,
                },
            )

        except Exception as e:
            logger.warning(f"Short interest error for {symbol}: {e}")
            return FlowScore(
                category="short_interest",
                score=0,
                signal="Short interest data unavailable",
                confidence=0.0,
            )

    def _get_analyst_score(self, symbol: str) -> FlowScore:
        """Get analyst recommendation score."""
        try:
            ticker = yf.Ticker(symbol)

            # Get recommendations
            recs = ticker.recommendations
            if recs is None or recs.empty:
                raise ValueError("No recommendations")

            # Get most recent
            recent = recs.tail(10)

            # Count by grade
            buy_count = 0
            hold_count = 0
            sell_count = 0

            for _, row in recent.iterrows():
                grade = str(row.get("To Grade", row.get("toGrade", ""))).lower()
                if any(x in grade for x in ["buy", "outperform", "overweight", "strong buy"]):
                    buy_count += 1
                elif any(x in grade for x in ["sell", "underperform", "underweight"]):
                    sell_count += 1
                else:
                    hold_count += 1

            total = buy_count + hold_count + sell_count
            if total == 0:
                raise ValueError("No valid recommendations")

            buy_pct = buy_count / total
            sell_pct = sell_count / total

            if buy_pct > 0.7:
                score = 2
                signal = f"Strong buy consensus ({buy_count}/{total} buys)"
            elif buy_pct > 0.5:
                score = 1
                signal = f"Moderate buy consensus ({buy_count}/{total} buys)"
            elif sell_pct > 0.5:
                score = -1
                signal = f"Sell consensus ({sell_count}/{total} sells)"
            elif sell_pct > 0.7:
                score = -2
                signal = f"Strong sell consensus ({sell_count}/{total} sells)"
            else:
                score = 0
                signal = f"Mixed analyst views ({buy_count} buy, {hold_count} hold, {sell_count} sell)"

            return FlowScore(
                category="analyst",
                score=score,
                signal=signal,
                confidence=0.6,
                raw_value={"buy": buy_count, "hold": hold_count, "sell": sell_count},
            )

        except Exception as e:
            logger.debug(f"Analyst error for {symbol}: {e}")
            return FlowScore(
                category="analyst",
                score=0,
                signal="Analyst data unavailable",
                confidence=0.0,
            )

    def _get_institutional_ownership_score(self, symbol: str) -> FlowScore:
        """Check institutional ownership changes."""
        try:
            ticker = yf.Ticker(symbol)

            # Get institutional holders
            inst = ticker.institutional_holders
            if inst is None or inst.empty:
                raise ValueError("No institutional data")

            # Calculate total institutional ownership
            total_shares = inst["Shares"].sum() if "Shares" in inst.columns else 0

            # Get info for float
            info = ticker.info
            float_shares = info.get("floatShares", 0)

            if float_shares > 0:
                inst_pct = total_shares / float_shares
            else:
                inst_pct = 0

            # Score based on institutional ownership level
            if inst_pct > 0.80:
                score = 2
                signal = f"Very high institutional ownership ({inst_pct:.0%})"
            elif inst_pct > 0.60:
                score = 1
                signal = f"High institutional ownership ({inst_pct:.0%})"
            elif inst_pct < 0.30:
                score = -1
                signal = f"Low institutional ownership ({inst_pct:.0%})"
            else:
                score = 0
                signal = f"Moderate institutional ownership ({inst_pct:.0%})"

            return FlowScore(
                category="institutional",
                score=score,
                signal=signal,
                confidence=0.7,
                raw_value={"inst_pct": inst_pct, "total_shares": total_shares},
            )

        except Exception as e:
            logger.debug(f"Institutional error for {symbol}: {e}")
            return FlowScore(
                category="institutional",
                score=0,
                signal="Institutional data unavailable",
                confidence=0.0,
            )

    def get_score(self, symbol: str) -> InstitutionalScore:
        """Get composite institutional flow score for a symbol."""
        scores = []

        # Collect all flow scores
        scores.append(self._get_options_flow_score(symbol))
        scores.append(self._get_short_interest_score(symbol))
        scores.append(self._get_analyst_score(symbol))
        scores.append(self._get_institutional_ownership_score(symbol))

        # Calculate weighted composite score
        total_score = 0
        total_weight = 0

        for s in scores:
            if s.confidence > 0:
                weight = s.confidence
                total_score += s.score * weight
                total_weight += weight

        if total_weight > 0:
            composite = total_score / total_weight * 2.5  # Scale to -10 to +10 range
        else:
            composite = 0

        # Determine sentiment
        if composite > 5:
            sentiment = "strong_bullish"
            recommendation = "Institutions appear bullish - consider entering"
        elif composite > 2:
            sentiment = "bullish"
            recommendation = "Moderate institutional interest - watch for entry"
        elif composite < -5:
            sentiment = "strong_bearish"
            recommendation = "Institutions appear bearish - avoid or hedge"
        elif composite < -2:
            sentiment = "bearish"
            recommendation = "Weak institutional interest - caution advised"
        else:
            sentiment = "neutral"
            recommendation = "Mixed institutional signals - wait for clarity"

        return InstitutionalScore(
            symbol=symbol,
            timestamp=datetime.now(),
            composite_score=composite,
            sentiment=sentiment,
            scores=scores,
            recommendation=recommendation,
        )

    def generate_report(self, symbols: list[str]) -> dict[str, InstitutionalScore]:
        """Generate institutional flow report for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.get_score(symbol)
            except Exception as e:
                logger.error(f"Failed to score {symbol}: {e}")
        return results

    def print_report(self, symbols: list[str]) -> None:
        """Print formatted institutional flow report."""
        print("\n" + "=" * 80)
        print("INSTITUTIONAL FLOW SCORECARD")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)

        results = self.generate_report(symbols)

        # Sort by composite score
        sorted_results = sorted(results.values(), key=lambda x: x.composite_score, reverse=True)

        # Summary table
        print(f"\n{'Symbol':<8} {'Score':<8} {'Sentiment':<16} {'Recommendation'}")
        print("-" * 80)

        for r in sorted_results:
            score_display = f"{r.composite_score:+.1f}"
            print(f"{r.symbol:<8} {score_display:<8} {r.sentiment:<16} {r.recommendation}")

        # Detailed breakdown
        print("\n" + "=" * 80)
        print("DETAILED BREAKDOWN")
        print("=" * 80)

        for r in sorted_results:
            print(f"\n{r.symbol} (Composite: {r.composite_score:+.1f})")
            print("-" * 40)
            for s in r.scores:
                conf_pct = f"({s.confidence:.0%} conf)" if s.confidence > 0 else ""
                score_str = f"{s.score:+d}" if s.score != 0 else "0"
                print(f"  {s.category:<15} [{score_str}] {s.signal} {conf_pct}")

        # Trading signals
        bullish = [r for r in sorted_results if r.sentiment in ["bullish", "strong_bullish"]]
        bearish = [r for r in sorted_results if r.sentiment in ["bearish", "strong_bearish"]]

        if bullish:
            print("\n[BULLISH INSTITUTIONAL SIGNALS]")
            for r in bullish:
                print(f"  {r.symbol}: {r.recommendation}")

        if bearish:
            print("\n[BEARISH INSTITUTIONAL SIGNALS]")
            for r in bearish:
                print(f"  {r.symbol}: {r.recommendation}")


def main():
    """Test institutional flow scorecard with Venezuela thesis symbols."""
    scorecard = InstitutionalFlowScorecard()

    # Venezuela thesis symbols
    symbols = ["SLB", "VLO", "HAL", "XLE", "GLD", "FRO", "STNG"]

    scorecard.print_report(symbols)


if __name__ == "__main__":
    main()
