#!/usr/bin/env python3
"""Earnings Surprise Predictor - Predict likely earnings beats/misses.

Uses multiple signals to estimate earnings surprise probability:
1. Pre-earnings price action (momentum, volume)
2. Options implied move vs historical
3. Analyst revision trends
4. Sector/peer performance
5. Insider trading activity
6. Management guidance patterns
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from src.core.paths import paths
import asyncio

import pandas as pd
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class EarningsSignal:
    """Individual signal for earnings prediction."""
    name: str
    value: float  # -1 (miss) to +1 (beat)
    confidence: float  # 0 to 1
    description: str

    @property
    def weighted_value(self) -> float:
        return self.value * self.confidence


@dataclass
class EarningsPrediction:
    """Earnings surprise prediction for a symbol."""
    symbol: str
    earnings_date: datetime
    days_until: int

    # Prediction
    predicted_direction: str  # beat, miss, inline
    confidence: float
    expected_move_pct: float

    # Component signals
    signals: list[EarningsSignal]

    # Historical context
    beat_rate_4q: float  # Beat rate last 4 quarters
    avg_surprise_pct: float
    implied_move: float  # Options-implied move

    # Risk factors
    risk_factors: list[str]

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "earnings_date": self.earnings_date.isoformat() if self.earnings_date else None,
            "days_until": self.days_until,
            "predicted_direction": self.predicted_direction,
            "confidence": self.confidence,
            "expected_move_pct": self.expected_move_pct,
            "signals": [
                {"name": s.name, "value": s.value, "confidence": s.confidence, "description": s.description}
                for s in self.signals
            ],
            "beat_rate_4q": self.beat_rate_4q,
            "avg_surprise_pct": self.avg_surprise_pct,
            "implied_move": self.implied_move,
            "risk_factors": self.risk_factors,
        }


class EarningsPredictor:
    """Predict earnings surprises using multiple signals."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or paths.base / "earnings"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Signal weights (sum to 1)
        self.signal_weights = {
            "price_momentum": 0.15,
            "volume_trend": 0.10,
            "analyst_revisions": 0.20,
            "options_skew": 0.15,
            "insider_activity": 0.15,
            "sector_performance": 0.10,
            "historical_pattern": 0.15,
        }

    async def get_earnings_calendar(self, symbols: list[str]) -> dict[str, datetime]:
        """Get upcoming earnings dates for symbols."""
        earnings_dates = {}

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                calendar = ticker.calendar

                if calendar is not None and not calendar.empty:
                    # Get earnings date
                    if "Earnings Date" in calendar.index:
                        date = calendar.loc["Earnings Date"]
                        if isinstance(date, pd.Series):
                            date = date.iloc[0]
                        if pd.notna(date):
                            earnings_dates[symbol] = pd.Timestamp(date).to_pydatetime()
            except Exception as e:
                logger.warning(f"Could not get earnings date for {symbol}: {e}")

        return earnings_dates

    def _calculate_price_momentum(self, symbol: str, days: int = 20) -> EarningsSignal:
        """Calculate pre-earnings price momentum signal."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{days + 5}d")

            if len(hist) < days:
                return EarningsSignal("price_momentum", 0, 0.3, "Insufficient data")

            # Calculate momentum
            returns = hist["Close"].pct_change().dropna()
            momentum = returns.tail(days).mean() * 252  # Annualized

            # Normalize to -1 to +1
            signal_value = np.clip(momentum / 0.5, -1, 1)  # 50% annualized = max

            direction = "bullish" if signal_value > 0 else "bearish"

            return EarningsSignal(
                name="price_momentum",
                value=signal_value,
                confidence=0.6,
                description=f"Pre-earnings momentum: {momentum:.1%} annualized ({direction})"
            )

        except Exception as e:
            logger.warning(f"Price momentum error for {symbol}: {e}")
            return EarningsSignal("price_momentum", 0, 0.2, f"Error: {e}")

    def _calculate_volume_trend(self, symbol: str, days: int = 10) -> EarningsSignal:
        """Calculate pre-earnings volume trend signal."""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="60d")

            if len(hist) < 30:
                return EarningsSignal("volume_trend", 0, 0.3, "Insufficient data")

            # Compare recent volume to 50-day average
            avg_volume = hist["Volume"].tail(50).mean()
            recent_volume = hist["Volume"].tail(days).mean()

            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1

            # Higher volume often precedes moves
            # But could be either direction
            signal_value = np.clip((volume_ratio - 1) * 2, -1, 1)

            return EarningsSignal(
                name="volume_trend",
                value=abs(signal_value) * 0.5,  # Volume is directionally ambiguous
                confidence=0.4,
                description=f"Volume {volume_ratio:.1f}x average (elevated activity)"
            )

        except Exception as e:
            return EarningsSignal("volume_trend", 0, 0.2, f"Error: {e}")

    def _calculate_analyst_revisions(self, symbol: str) -> EarningsSignal:
        """Calculate analyst revision trend signal."""
        try:
            ticker = yf.Ticker(symbol)

            # Get analyst recommendations
            recs = ticker.recommendations
            if recs is None or recs.empty:
                return EarningsSignal("analyst_revisions", 0, 0.3, "No analyst data")

            # Get recent recommendations
            recent = recs.tail(10)

            # Score based on grades
            grade_scores = {
                "Strong Buy": 1.0, "Buy": 0.5, "Overweight": 0.3,
                "Hold": 0, "Neutral": 0, "Equal-Weight": 0,
                "Underweight": -0.3, "Sell": -0.5, "Strong Sell": -1.0,
            }

            if "To Grade" in recent.columns:
                scores = recent["To Grade"].map(lambda x: grade_scores.get(x, 0))
                avg_score = scores.mean() if len(scores) > 0 else 0
            else:
                avg_score = 0

            return EarningsSignal(
                name="analyst_revisions",
                value=avg_score,
                confidence=0.7,
                description=f"Analyst sentiment: {avg_score:.2f} ({len(recent)} recent)"
            )

        except Exception as e:
            return EarningsSignal("analyst_revisions", 0, 0.2, f"Error: {e}")

    def _calculate_options_skew(self, symbol: str) -> EarningsSignal:
        """Calculate options skew signal (put-call implied vol difference)."""
        try:
            ticker = yf.Ticker(symbol)

            # Get options chain
            if not ticker.options:
                return EarningsSignal("options_skew", 0, 0.3, "No options data")

            # Get nearest expiration
            expiry = ticker.options[0]
            chain = ticker.option_chain(expiry)

            calls = chain.calls
            puts = chain.puts

            if calls.empty or puts.empty:
                return EarningsSignal("options_skew", 0, 0.3, "No options data")

            # Get ATM options
            current_price = ticker.info.get("regularMarketPrice", 0)
            if current_price == 0:
                return EarningsSignal("options_skew", 0, 0.3, "No price data")

            # Find ATM strike
            atm_strike = calls["strike"].iloc[(calls["strike"] - current_price).abs().argmin()]

            atm_call = calls[calls["strike"] == atm_strike]
            atm_put = puts[puts["strike"] == atm_strike]

            if atm_call.empty or atm_put.empty:
                return EarningsSignal("options_skew", 0, 0.3, "No ATM options")

            call_iv = atm_call["impliedVolatility"].iloc[0]
            put_iv = atm_put["impliedVolatility"].iloc[0]

            # Put-call skew: positive = bearish (more put demand)
            skew = put_iv - call_iv
            signal_value = -np.clip(skew * 10, -1, 1)  # Flip sign for directional

            return EarningsSignal(
                name="options_skew",
                value=signal_value,
                confidence=0.6,
                description=f"Put-call IV skew: {skew:.2%} ({'bearish' if skew > 0 else 'bullish'})"
            )

        except Exception as e:
            return EarningsSignal("options_skew", 0, 0.2, f"Error: {e}")

    def _calculate_insider_activity(self, symbol: str) -> EarningsSignal:
        """Calculate insider trading signal."""
        try:
            ticker = yf.Ticker(symbol)

            # Get insider transactions
            insiders = ticker.insider_transactions
            if insiders is None or insiders.empty:
                return EarningsSignal("insider_activity", 0, 0.3, "No insider data")

            # Look at recent activity (last 90 days)
            recent = insiders.tail(20)

            # Count buys vs sells
            if "Transaction" in recent.columns:
                buys = recent[recent["Transaction"].str.contains("Buy|Purchase", case=False, na=False)]
                sells = recent[recent["Transaction"].str.contains("Sale|Sell", case=False, na=False)]

                buy_count = len(buys)
                sell_count = len(sells)

                if buy_count + sell_count == 0:
                    return EarningsSignal("insider_activity", 0, 0.3, "No recent activity")

                # Net signal
                signal_value = (buy_count - sell_count) / (buy_count + sell_count)

                return EarningsSignal(
                    name="insider_activity",
                    value=signal_value,
                    confidence=0.7,
                    description=f"Insider activity: {buy_count} buys, {sell_count} sells"
                )

            return EarningsSignal("insider_activity", 0, 0.3, "Unknown transaction format")

        except Exception as e:
            return EarningsSignal("insider_activity", 0, 0.2, f"Error: {e}")

    def _calculate_sector_performance(self, symbol: str, days: int = 20) -> EarningsSignal:
        """Calculate sector relative performance signal."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            sector = info.get("sector", "")

            # Map sectors to ETFs
            sector_etfs = {
                "Technology": "XLK",
                "Healthcare": "XLV",
                "Financial Services": "XLF",
                "Consumer Cyclical": "XLY",
                "Consumer Defensive": "XLP",
                "Energy": "XLE",
                "Industrials": "XLI",
                "Basic Materials": "XLB",
                "Utilities": "XLU",
                "Real Estate": "XLRE",
                "Communication Services": "XLC",
            }

            sector_etf = sector_etfs.get(sector, "SPY")

            # Get relative performance
            stock_hist = ticker.history(period=f"{days + 5}d")
            etf_ticker = yf.Ticker(sector_etf)
            etf_hist = etf_ticker.history(period=f"{days + 5}d")

            if len(stock_hist) < days or len(etf_hist) < days:
                return EarningsSignal("sector_performance", 0, 0.3, "Insufficient data")

            stock_return = (stock_hist["Close"].iloc[-1] / stock_hist["Close"].iloc[-days] - 1)
            etf_return = (etf_hist["Close"].iloc[-1] / etf_hist["Close"].iloc[-days] - 1)

            relative_return = stock_return - etf_return
            signal_value = np.clip(relative_return * 5, -1, 1)

            return EarningsSignal(
                name="sector_performance",
                value=signal_value,
                confidence=0.5,
                description=f"vs {sector_etf}: {relative_return:+.1%} ({days}d)"
            )

        except Exception as e:
            return EarningsSignal("sector_performance", 0, 0.2, f"Error: {e}")

    def _calculate_historical_pattern(self, symbol: str) -> EarningsSignal:
        """Calculate historical earnings pattern signal."""
        try:
            ticker = yf.Ticker(symbol)

            # Get earnings history
            earnings = ticker.earnings_history
            if earnings is None or earnings.empty:
                return EarningsSignal("historical_pattern", 0, 0.3, "No earnings history")

            recent = earnings.tail(8)  # Last 8 quarters

            if "Surprise(%)" in recent.columns:
                surprises = recent["Surprise(%)"].dropna()

                if len(surprises) < 4:
                    return EarningsSignal("historical_pattern", 0, 0.4, "Limited history")

                # Beat rate
                beats = (surprises > 0).sum()
                beat_rate = beats / len(surprises)

                # Average surprise
                avg_surprise = surprises.mean()

                # Signal: companies that beat tend to keep beating
                signal_value = np.clip((beat_rate - 0.5) * 2, -1, 1)

                return EarningsSignal(
                    name="historical_pattern",
                    value=signal_value,
                    confidence=0.65,
                    description=f"Beat rate: {beat_rate:.0%} (avg surprise: {avg_surprise:+.1%})"
                )

            return EarningsSignal("historical_pattern", 0, 0.3, "No surprise data")

        except Exception as e:
            return EarningsSignal("historical_pattern", 0, 0.2, f"Error: {e}")

    def _get_implied_move(self, symbol: str) -> float:
        """Calculate options-implied earnings move."""
        try:
            ticker = yf.Ticker(symbol)

            if not ticker.options:
                return 0

            # Get nearest expiration (hopefully post-earnings)
            expiry = ticker.options[0]
            chain = ticker.option_chain(expiry)

            current_price = ticker.info.get("regularMarketPrice", 0)
            if current_price == 0:
                return 0

            # ATM straddle price approximates implied move
            atm_strike = chain.calls["strike"].iloc[
                (chain.calls["strike"] - current_price).abs().argmin()
            ]

            atm_call = chain.calls[chain.calls["strike"] == atm_strike]
            atm_put = chain.puts[chain.puts["strike"] == atm_strike]

            if atm_call.empty or atm_put.empty:
                return 0

            straddle_price = atm_call["lastPrice"].iloc[0] + atm_put["lastPrice"].iloc[0]
            implied_move = straddle_price / current_price

            return implied_move

        except Exception as e:
            logger.warning(f"Implied move error for {symbol}: {e}")
            return 0

    async def predict(self, symbol: str, earnings_date: Optional[datetime] = None) -> EarningsPrediction:
        """Generate earnings surprise prediction for a symbol."""
        # Calculate all signals
        signals = [
            self._calculate_price_momentum(symbol),
            self._calculate_volume_trend(symbol),
            self._calculate_analyst_revisions(symbol),
            self._calculate_options_skew(symbol),
            self._calculate_insider_activity(symbol),
            self._calculate_sector_performance(symbol),
            self._calculate_historical_pattern(symbol),
        ]

        # Calculate weighted prediction
        total_weight = 0
        weighted_sum = 0

        for signal in signals:
            weight = self.signal_weights.get(signal.name, 0.1)
            weighted_sum += signal.weighted_value * weight
            total_weight += weight * signal.confidence

        prediction_score = weighted_sum / total_weight if total_weight > 0 else 0

        # Determine direction
        if prediction_score > 0.15:
            direction = "beat"
        elif prediction_score < -0.15:
            direction = "miss"
        else:
            direction = "inline"

        # Calculate confidence (based on signal agreement)
        signal_values = [s.value for s in signals if s.confidence > 0.3]
        if signal_values:
            agreement = 1 - np.std(signal_values)  # Higher agreement = higher confidence
            confidence = np.clip(0.3 + agreement * 0.4, 0.3, 0.8)
        else:
            confidence = 0.3

        # Get implied move and historical context
        implied_move = self._get_implied_move(symbol)

        # Get beat rate
        hist_signal = next((s for s in signals if s.name == "historical_pattern"), None)
        beat_rate = 0.5
        avg_surprise = 0
        if hist_signal and "Beat rate" in hist_signal.description:
            try:
                beat_rate = float(hist_signal.description.split(":")[1].split("%")[0]) / 100
            except:
                pass

        # Calculate days until earnings
        if earnings_date:
            days_until = (earnings_date - datetime.now()).days
        else:
            days_until = -1

        # Identify risk factors
        risk_factors = []
        if implied_move > 0.08:
            risk_factors.append(f"High implied move ({implied_move:.1%})")
        if confidence < 0.5:
            risk_factors.append("Low signal confidence")
        if any(s.confidence < 0.3 for s in signals):
            risk_factors.append("Some signals unavailable")

        return EarningsPrediction(
            symbol=symbol,
            earnings_date=earnings_date,
            days_until=days_until,
            predicted_direction=direction,
            confidence=confidence,
            expected_move_pct=implied_move * 100,
            signals=signals,
            beat_rate_4q=beat_rate,
            avg_surprise_pct=avg_surprise,
            implied_move=implied_move,
            risk_factors=risk_factors,
        )

    async def scan_upcoming(self, symbols: list[str], days_ahead: int = 14) -> list[EarningsPrediction]:
        """Scan for upcoming earnings and generate predictions."""
        predictions = []

        # Get earnings dates
        earnings_dates = await self.get_earnings_calendar(symbols)

        # Filter to upcoming
        now = datetime.now()
        cutoff = now + timedelta(days=days_ahead)

        upcoming = {
            s: d for s, d in earnings_dates.items()
            if d and now <= d <= cutoff
        }

        logger.info(f"Found {len(upcoming)} symbols with earnings in next {days_ahead} days")

        # Generate predictions
        for symbol, date in upcoming.items():
            try:
                pred = await self.predict(symbol, date)
                predictions.append(pred)
            except Exception as e:
                logger.warning(f"Prediction error for {symbol}: {e}")

        # Sort by confidence
        predictions.sort(key=lambda x: x.confidence, reverse=True)

        return predictions

    def generate_report(self, predictions: list[EarningsPrediction]) -> str:
        """Generate human-readable earnings predictions report."""
        lines = [
            "Earnings Surprise Predictions",
            "=" * 50,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        if not predictions:
            lines.append("No upcoming earnings found.")
            return "\n".join(lines)

        for pred in predictions:
            emoji = {"beat": "📈", "miss": "📉", "inline": "➡️"}.get(pred.predicted_direction, "❓")
            date_str = pred.earnings_date.strftime("%m/%d") if pred.earnings_date else "TBD"

            lines.extend([
                f"\n{emoji} {pred.symbol} - {date_str} ({pred.days_until}d)",
                f"   Prediction: {pred.predicted_direction.upper()} ({pred.confidence:.0%} confidence)",
                f"   Implied Move: {pred.expected_move_pct:.1f}%",
                f"   Historical Beat Rate: {pred.beat_rate_4q:.0%}",
            ])

            # Top signals
            top_signals = sorted(pred.signals, key=lambda s: abs(s.weighted_value), reverse=True)[:3]
            lines.append("   Key Signals:")
            for sig in top_signals:
                direction = "+" if sig.value > 0 else "-" if sig.value < 0 else "="
                lines.append(f"     {direction} {sig.description}")

            if pred.risk_factors:
                lines.append(f"   Risks: {', '.join(pred.risk_factors)}")

        return "\n".join(lines)


async def main():
    """Test earnings predictor."""
    predictor = EarningsPredictor()

    # Test symbols
    test_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

    print("Scanning upcoming earnings...")
    predictions = await predictor.scan_upcoming(test_symbols, days_ahead=30)

    if predictions:
        print(predictor.generate_report(predictions))

        # Save predictions
        output_file = predictor.cache_dir / f"predictions_{datetime.now().strftime('%Y%m%d')}.json"
        with open(output_file, "w") as f:
            json.dump([p.to_dict() for p in predictions], f, indent=2)
        print(f"\nSaved to: {output_file}")
    else:
        print("No upcoming earnings found for test symbols")

        # Generate single prediction
        print("\nGenerating prediction for AAPL:")
        pred = await predictor.predict("AAPL")
        print(predictor.generate_report([pred]))


if __name__ == "__main__":
    asyncio.run(main())
