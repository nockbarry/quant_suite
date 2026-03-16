"""Signal Aggregator - Combines all signal sources into unified view.

Pulls from:
- Feature engine (50+ technical features)
- Swing/intraday strategies
- Alternative data (congressional, insider, options flow)
- Sentiment indicators

Outputs AggregatedSignal per symbol with composite score.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import logging

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class AggregatedSignal:
    """All signals for one symbol, unified."""

    symbol: str
    timestamp: datetime

    # From existing strategies (-1 to 1 scale)
    swing_signal: float = 0.0
    intraday_signal: float = 0.0
    ml_signal: float = 0.0  # TODO: Not yet integrated - requires trained models (P2 enhancement)

    # From existing alt data (-1 to 1 scale)
    congressional_signal: float = 0.0
    insider_signal: float = 0.0
    options_flow_signal: float = 0.0
    sentiment_signal: float = 0.0

    # NEW: Market regime signals (-1 to 1 scale)
    vix_structure_signal: float = 0.0  # -1 = sell vol/risk-on, +1 = buy vol/risk-off
    breadth_signal: float = 0.0        # -1 = weak breadth, +1 = strong breadth
    put_call_signal: float = 0.0       # -1 = extreme greed, +1 = extreme fear (contrarian)

    # NEW: Sentiment extremes (-1 to 1 scale)
    aaii_signal: float = 0.0           # -1 = too bullish (contrarian sell), +1 = too bearish (contrarian buy)
    cot_signal: float = 0.0            # -1 = speculators bullish, +1 = commercials bullish

    # NEW: Short interest
    short_squeeze_score: float = 0.0   # 0 to 1, higher = more squeeze potential

    # From existing technicals
    technical_bias: str = "neutral"  # bullish, bearish, neutral
    rsi: float = 50.0
    macd_histogram: float = 0.0
    trend_strength: float = 0.0

    # Support/Resistance
    support: Optional[float] = None
    resistance: Optional[float] = None
    current_price: Optional[float] = None
    distance_to_support_pct: Optional[float] = None
    distance_to_resistance_pct: Optional[float] = None

    # Composite scores
    composite_score: float = 0.0  # Weighted combination (-1 to 1)
    signal_agreement: float = 0.0  # How aligned are signals (0 to 1)
    confidence: float = 0.0  # Overall confidence (0 to 1)

    # Metadata
    signals_available: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "swing_signal": self.swing_signal,
            "intraday_signal": self.intraday_signal,
            "ml_signal": self.ml_signal,
            "congressional_signal": self.congressional_signal,
            "insider_signal": self.insider_signal,
            "options_flow_signal": self.options_flow_signal,
            "sentiment_signal": self.sentiment_signal,
            # NEW: Market regime signals
            "vix_structure_signal": self.vix_structure_signal,
            "breadth_signal": self.breadth_signal,
            "put_call_signal": self.put_call_signal,
            # NEW: Sentiment extremes
            "aaii_signal": self.aaii_signal,
            "cot_signal": self.cot_signal,
            # NEW: Short interest
            "short_squeeze_score": self.short_squeeze_score,
            "technical_bias": self.technical_bias,
            "rsi": self.rsi,
            "macd_histogram": self.macd_histogram,
            "trend_strength": self.trend_strength,
            "support": self.support,
            "resistance": self.resistance,
            "current_price": self.current_price,
            "distance_to_support_pct": self.distance_to_support_pct,
            "distance_to_resistance_pct": self.distance_to_resistance_pct,
            "composite_score": self.composite_score,
            "signal_agreement": self.signal_agreement,
            "confidence": self.confidence,
            "signals_available": self.signals_available,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AggregatedSignal":
        return cls(
            symbol=data["symbol"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            swing_signal=data.get("swing_signal", 0.0),
            intraday_signal=data.get("intraday_signal", 0.0),
            ml_signal=data.get("ml_signal", 0.0),
            congressional_signal=data.get("congressional_signal", 0.0),
            insider_signal=data.get("insider_signal", 0.0),
            options_flow_signal=data.get("options_flow_signal", 0.0),
            sentiment_signal=data.get("sentiment_signal", 0.0),
            # NEW: Market regime signals
            vix_structure_signal=data.get("vix_structure_signal", 0.0),
            breadth_signal=data.get("breadth_signal", 0.0),
            put_call_signal=data.get("put_call_signal", 0.0),
            # NEW: Sentiment extremes
            aaii_signal=data.get("aaii_signal", 0.0),
            cot_signal=data.get("cot_signal", 0.0),
            # NEW: Short interest
            short_squeeze_score=data.get("short_squeeze_score", 0.0),
            technical_bias=data.get("technical_bias", "neutral"),
            rsi=data.get("rsi", 50.0),
            macd_histogram=data.get("macd_histogram", 0.0),
            trend_strength=data.get("trend_strength", 0.0),
            support=data.get("support"),
            resistance=data.get("resistance"),
            current_price=data.get("current_price"),
            distance_to_support_pct=data.get("distance_to_support_pct"),
            distance_to_resistance_pct=data.get("distance_to_resistance_pct"),
            composite_score=data.get("composite_score", 0.0),
            signal_agreement=data.get("signal_agreement", 0.0),
            confidence=data.get("confidence", 0.0),
            signals_available=data.get("signals_available", []),
            notes=data.get("notes", ""),
        )


class SignalAggregator:
    """
    Combines all signal sources into unified AggregatedSignal per symbol.

    Integrates with existing infrastructure:
    - src/data/pipeline/features.py - Technical features
    - src/strategies/swing/ - Swing signals
    - src/strategies/intraday/ - Intraday signals
    - src/data/sources/alternative/ - Alt data signals
    - src/data/pipeline/sentiment.py - Sentiment
    - src/data/pipeline/intraday_technicals.py - Technicals
    """

    # Signal weights for composite score
    # Note: Weights are normalized when computing composite, so they don't need to sum to 1.0
    WEIGHTS = {
        # Existing signals
        "swing": 0.20,
        "intraday": 0.10,
        "ml": 0.10,
        "congressional": 0.08,
        "insider": 0.08,
        "options_flow": 0.08,
        "sentiment": 0.04,
        "technical": 0.08,
        # NEW: Market regime signals
        "vix_structure": 0.05,
        "breadth": 0.05,
        "put_call": 0.04,
        # NEW: Sentiment extremes
        "aaii": 0.03,
        "cot": 0.04,
        # NEW: Short interest
        "short_interest": 0.03,
    }

    def __init__(self, watchlist: Optional[list[str]] = None):
        """Initialize aggregator.

        Args:
            watchlist: Symbols to aggregate signals for.
                      If None, will be set when aggregate() is called.
        """
        self.watchlist = watchlist or []
        self._cache: dict[str, tuple[datetime, AggregatedSignal]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    def aggregate(
        self,
        symbols: Optional[list[str]] = None,
        include_alt_data: bool = True,
        include_technicals: bool = True,
    ) -> dict[str, AggregatedSignal]:
        """
        Aggregate signals for given symbols.

        Args:
            symbols: Symbols to aggregate. Defaults to watchlist.
            include_alt_data: Whether to fetch alternative data signals.
            include_technicals: Whether to compute technical signals.

        Returns:
            Dictionary mapping symbol to AggregatedSignal.
        """
        symbols = symbols or self.watchlist
        if not symbols:
            logger.warning("No symbols provided for aggregation")
            return {}

        results = {}
        now = datetime.now()

        for symbol in symbols:
            try:
                signal = self._aggregate_symbol(
                    symbol,
                    include_alt_data=include_alt_data,
                    include_technicals=include_technicals,
                )
                results[symbol] = signal
            except Exception as e:
                logger.error(f"Failed to aggregate signals for {symbol}: {e}")
                # Return empty signal on error
                results[symbol] = AggregatedSignal(
                    symbol=symbol,
                    timestamp=now,
                    notes=f"Error: {str(e)}",
                )

        return results

    def _aggregate_symbol(
        self,
        symbol: str,
        include_alt_data: bool = True,
        include_technicals: bool = True,
    ) -> AggregatedSignal:
        """Aggregate all signals for a single symbol."""
        now = datetime.now()

        signal = AggregatedSignal(symbol=symbol, timestamp=now)
        available_signals = []

        # 1. Technical indicators
        if include_technicals:
            try:
                tech = self._get_technicals(symbol)
                if tech:
                    signal.technical_bias = tech.get("bias", "neutral")
                    signal.rsi = tech.get("rsi", 50.0)
                    signal.macd_histogram = tech.get("macd_histogram", 0.0)
                    signal.trend_strength = tech.get("trend_strength", 0.0)
                    signal.support = tech.get("support")
                    signal.resistance = tech.get("resistance")
                    signal.current_price = tech.get("price")

                    # Compute distances
                    if signal.current_price and signal.support:
                        signal.distance_to_support_pct = (
                            (signal.current_price - signal.support) / signal.current_price * 100
                        )
                    if signal.current_price and signal.resistance:
                        signal.distance_to_resistance_pct = (
                            (signal.resistance - signal.current_price) / signal.current_price * 100
                        )

                    available_signals.append("technical")
            except Exception as e:
                logger.debug(f"Technical signals unavailable for {symbol}: {e}")

        # 2. Swing strategy signal
        try:
            swing = self._get_swing_signal(symbol)
            if swing is not None:
                signal.swing_signal = swing
                available_signals.append("swing")
        except Exception as e:
            logger.debug(f"Swing signal unavailable for {symbol}: {e}")

        # 3. Intraday strategy signal
        try:
            intraday = self._get_intraday_signal(symbol)
            if intraday is not None:
                signal.intraday_signal = intraday
                available_signals.append("intraday")
        except Exception as e:
            logger.debug(f"Intraday signal unavailable for {symbol}: {e}")

        # 4. Alternative data signals
        if include_alt_data:
            # Congressional
            try:
                cong = self._get_congressional_signal(symbol)
                if cong is not None:
                    signal.congressional_signal = cong
                    available_signals.append("congressional")
            except Exception as e:
                logger.debug(f"Congressional signal unavailable for {symbol}: {e}")

            # Insider
            try:
                insider = self._get_insider_signal(symbol)
                if insider is not None:
                    signal.insider_signal = insider
                    available_signals.append("insider")
            except Exception as e:
                logger.debug(f"Insider signal unavailable for {symbol}: {e}")

            # Options flow
            try:
                flow = self._get_options_flow_signal(symbol)
                if flow is not None:
                    signal.options_flow_signal = flow
                    available_signals.append("options_flow")
            except Exception as e:
                logger.debug(f"Options flow signal unavailable for {symbol}: {e}")

        # 5. Sentiment
        try:
            sent = self._get_sentiment_signal(symbol)
            if sent is not None:
                signal.sentiment_signal = sent
                available_signals.append("sentiment")
        except Exception as e:
            logger.debug(f"Sentiment signal unavailable for {symbol}: {e}")

        # 6. NEW: Market regime signals (market-wide, applied to all symbols)
        try:
            vix_sig = self._get_vix_structure_signal()
            if vix_sig is not None:
                signal.vix_structure_signal = vix_sig
                available_signals.append("vix_structure")
        except Exception as e:
            logger.debug(f"VIX structure signal unavailable: {e}")

        try:
            breadth_sig = self._get_breadth_signal()
            if breadth_sig is not None:
                signal.breadth_signal = breadth_sig
                available_signals.append("breadth")
        except Exception as e:
            logger.debug(f"Breadth signal unavailable: {e}")

        try:
            pc_sig = self._get_put_call_signal()
            if pc_sig is not None:
                signal.put_call_signal = pc_sig
                available_signals.append("put_call")
        except Exception as e:
            logger.debug(f"Put/Call signal unavailable: {e}")

        # 7. NEW: Sentiment extremes
        try:
            aaii_sig = self._get_aaii_signal()
            if aaii_sig is not None:
                signal.aaii_signal = aaii_sig
                available_signals.append("aaii")
        except Exception as e:
            logger.debug(f"AAII signal unavailable: {e}")

        try:
            cot_sig = self._get_cot_signal(symbol)
            if cot_sig is not None:
                signal.cot_signal = cot_sig
                available_signals.append("cot")
        except Exception as e:
            logger.debug(f"COT signal unavailable for {symbol}: {e}")

        # 8. NEW: Short interest
        try:
            squeeze = self._get_short_squeeze_score(symbol)
            if squeeze is not None:
                signal.short_squeeze_score = squeeze
                available_signals.append("short_interest")
        except Exception as e:
            logger.debug(f"Short interest unavailable for {symbol}: {e}")

        # Compute composite
        signal.signals_available = available_signals
        signal.composite_score = self._compute_composite(signal)
        signal.signal_agreement = self._compute_agreement(signal)
        signal.confidence = self._compute_confidence(signal)

        # Generate notes
        signal.notes = self._generate_notes(signal)

        return signal

    def _get_technicals(self, symbol: str) -> Optional[dict]:
        """Get technical indicators from intraday_technicals.py."""
        try:
            from src.data.pipeline.intraday_technicals import IntradayTechnicalAnalyzer

            analyzer = IntradayTechnicalAnalyzer([symbol])
            tech = analyzer.get_technicals(symbol)
            if tech:
                return {
                    "bias": tech.bias,
                    "rsi": tech.rsi_14,
                    "macd_histogram": tech.macd_histogram,
                    "trend_strength": tech.trend_strength,
                    "support": tech.nearest_support,
                    "resistance": tech.nearest_resistance,
                    "price": tech.price,
                }
        except ImportError:
            pass
        return None

    def _get_swing_signal(self, symbol: str) -> Optional[float]:
        """Get swing strategy signal from mean reversion strategies."""
        try:
            import yfinance as yf
            import pandas as pd

            # Fetch recent data for signal calculation
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="30d")

            if df.empty or len(df) < 20:
                return None

            # Calculate Bollinger Bands
            close = df["Close"]
            sma = close.rolling(20).mean()
            std = close.rolling(20).std()
            upper = sma + 2 * std
            lower = sma - 2 * std

            current = close.iloc[-1]
            upper_val = upper.iloc[-1]
            lower_val = lower.iloc[-1]
            sma_val = sma.iloc[-1]

            # Calculate %B (position within bands)
            pct_b = (current - lower_val) / (upper_val - lower_val) if (upper_val - lower_val) > 0 else 0.5

            # Calculate RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # Generate signal
            # Oversold (near lower band + low RSI) = bullish
            if pct_b < 0.2 and current_rsi < 35:
                return 0.3 + (0.2 - pct_b) * 2  # 0.3 to 0.7
            # Overbought (near upper band + high RSI) = bearish
            elif pct_b > 0.8 and current_rsi > 65:
                return -0.3 - (pct_b - 0.8) * 2  # -0.3 to -0.7
            # Neutral zone
            else:
                return (pct_b - 0.5) * 0.4  # -0.2 to 0.2

        except Exception as e:
            logger.debug(f"Swing signal error for {symbol}: {e}")
            return None

    def _get_intraday_signal(self, symbol: str) -> Optional[float]:
        """Get intraday strategy signal from momentum."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="1h")

            if df.empty or len(df) < 20:
                return None

            close = df["Close"]
            volume = df["Volume"]

            # Short-term momentum (last 5 hours)
            momentum_5h = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0

            # Volume confirmation
            avg_volume = volume.rolling(20).mean().iloc[-1]
            current_volume = volume.iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # MACD on hourly
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12 - ema26
            macd_signal = macd.ewm(span=9).mean()
            macd_hist = (macd - macd_signal).iloc[-1]

            # Combine signals
            signal = 0.0

            # Momentum component (capped at 0.3)
            signal += max(-0.3, min(0.3, momentum_5h / 3))

            # MACD component (capped at 0.3)
            macd_normalized = max(-0.3, min(0.3, macd_hist / close.iloc[-1] * 10))
            signal += macd_normalized

            # Volume confirmation boost
            if volume_ratio > 1.5 and abs(signal) > 0.1:
                signal *= 1.2

            return max(-1.0, min(1.0, signal))

        except Exception as e:
            logger.debug(f"Intraday signal error for {symbol}: {e}")
            return None

    def _get_congressional_signal(self, symbol: str) -> Optional[float]:
        """Get congressional cluster trading signal."""
        try:
            import pandas as pd
            from pathlib import Path
            from datetime import datetime, timedelta

            # Load congressional trades data
            archive_path = paths.base / "congressional_archive" / "processed" / "all_trades.parquet"

            if not archive_path.exists():
                return None

            df = pd.read_parquet(archive_path)

            # Filter to target symbol and recent trades (last 60 days)
            df = df[df["symbol"] == symbol.upper()]

            if df.empty:
                return None

            # Convert dates
            df["transaction_date"] = pd.to_datetime(df["transaction_date"])
            cutoff = datetime.now() - timedelta(days=60)
            recent = df[df["transaction_date"] >= cutoff]

            if recent.empty:
                return None

            # Detect cluster buying (multiple unique politicians buying)
            purchases = recent[recent["trade_type"].str.contains("purchase", case=False, na=False)]

            if purchases.empty:
                return None

            unique_buyers = purchases["politician"].nunique()
            total_volume = purchases["amount_estimate"].sum()

            # Generate signal based on cluster strength
            # 5+ politicians = strong signal
            # 4 politicians = moderate signal
            # 3 politicians = weak signal
            if unique_buyers >= 5:
                signal = 0.7
            elif unique_buyers >= 4:
                signal = 0.5
            elif unique_buyers >= 3:
                signal = 0.3
            else:
                signal = 0.0

            # Boost for high volume
            if total_volume >= 500000:
                signal += 0.1

            # Check for sales to offset
            sales = recent[recent["trade_type"].str.contains("sale", case=False, na=False)]
            if not sales.empty:
                unique_sellers = sales["politician"].nunique()
                if unique_sellers >= unique_buyers:
                    signal *= 0.5  # Mixed signals

            return min(1.0, signal)

        except Exception as e:
            logger.debug(f"Congressional signal error for {symbol}: {e}")
            return None

    def _get_insider_signal(self, symbol: str) -> Optional[float]:
        """Get insider trading signal from Form 4 data."""
        try:
            import asyncio
            from src.data.sources.alternative.insider import InsiderDataSource
            from datetime import datetime, timedelta

            # Try to get cached signal or compute
            cache_key = f"insider_signal:{symbol}"
            if cache_key in self._cache:
                ts, val = self._cache[cache_key]
                if (datetime.now() - ts).seconds < 3600:  # 1 hour cache
                    return val

            # For synchronous context, use simple heuristic from file if exists
            import pandas as pd
            from pathlib import Path

            insider_cache = paths.live_research / "insider_signals.json"
            if insider_cache.exists():
                import json
                with open(insider_cache) as f:
                    data = json.load(f)
                if symbol in data:
                    return data[symbol].get("signal", 0.0)

            return None

        except Exception as e:
            logger.debug(f"Insider signal error for {symbol}: {e}")
            return None

    def _get_options_flow_signal(self, symbol: str) -> Optional[float]:
        """Get unusual options activity signal."""
        try:
            import yfinance as yf
            from datetime import datetime, timedelta

            ticker = yf.Ticker(symbol)

            # Get options chain
            try:
                exp_dates = ticker.options
                if not exp_dates:
                    return None

                # Use nearest expiration
                chain = ticker.option_chain(exp_dates[0])
                calls = chain.calls
                puts = chain.puts

                if calls.empty or puts.empty:
                    return None

                # Calculate put/call ratio for this symbol
                total_call_oi = calls["openInterest"].sum()
                total_put_oi = puts["openInterest"].sum()

                if total_call_oi == 0:
                    return None

                pc_ratio = total_put_oi / total_call_oi

                # Calculate signal
                # Low P/C (<0.5) = bullish options flow
                # High P/C (>1.5) = bearish options flow
                if pc_ratio < 0.5:
                    return 0.3 + (0.5 - pc_ratio) * 0.4  # 0.3 to 0.5
                elif pc_ratio > 1.5:
                    return -0.3 - (pc_ratio - 1.5) * 0.2  # -0.3 to -0.5
                else:
                    return (1.0 - pc_ratio) * 0.3  # -0.15 to 0.15

            except Exception:
                return None

        except Exception as e:
            logger.debug(f"Options flow signal error for {symbol}: {e}")
            return None

    def _get_sentiment_signal(self, symbol: str) -> Optional[float]:
        """Get sentiment signal from cached research data."""
        try:
            import json
            from pathlib import Path

            # Check for pre-computed sentiment in research folder
            sentiment_file = paths.live_research / "sentiment.json"

            if sentiment_file.exists():
                with open(sentiment_file) as f:
                    data = json.load(f)
                if symbol in data:
                    sent = data[symbol]
                    # Normalize to -1 to 1
                    score = sent.get("score", 0.5)
                    return (score - 0.5) * 2

            # Fallback: Use Fear & Greed as proxy (market-wide sentiment)
            state_file = paths.live_state
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)

                sentiment = state.get("sentiment", {})
                fear_greed = sentiment.get("fear_greed_index", 50)

                # Contrarian signal: extreme fear = bullish, extreme greed = bearish
                if fear_greed < 25:
                    return 0.4  # Extreme fear = buy signal
                elif fear_greed > 75:
                    return -0.4  # Extreme greed = sell signal
                else:
                    return (50 - fear_greed) / 100  # -0.25 to 0.25

            return None

        except Exception as e:
            logger.debug(f"Sentiment signal error for {symbol}: {e}")
            return None

    def _get_vix_structure_signal(self) -> Optional[float]:
        """Get VIX term structure signal (market-wide, not per-symbol)."""
        try:
            from src.data.sources.alternative.vix_structure import VIXStructureSource
            import asyncio

            source = VIXStructureSource()
            # Try to get cached signal first
            signal = source.get_signal()
            if signal != 0.0:
                return signal
            # If no cache, return None (will be populated by daemon)
            return None
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"VIX structure signal unavailable: {e}")
        return None

    def _get_breadth_signal(self) -> Optional[float]:
        """Get market breadth signal (market-wide, not per-symbol)."""
        try:
            from src.data.pipeline.market_breadth import MarketBreadth

            breadth = MarketBreadth()
            data = breadth.get_breadth()
            if data:
                # Convert breadth to -1 to 1 signal
                # Strong breadth (>60% advancing) = bullish
                # Weak breadth (<40% advancing) = bearish
                advance_pct = data.get("advance_pct", 50.0)
                if advance_pct >= 60:
                    return (advance_pct - 50) / 50  # 0 to 1
                elif advance_pct <= 40:
                    return (advance_pct - 50) / 50  # -1 to 0
                return 0.0
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Breadth signal unavailable: {e}")
        return None

    def _get_put_call_signal(self) -> Optional[float]:
        """Get put/call ratio signal (market-wide, not per-symbol)."""
        try:
            from src.data.sources.alternative.put_call import PutCallSource

            source = PutCallSource()
            # Try to get cached signal first
            signal = source.get_signal()
            if signal != 0.0:
                return signal
            return None
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Put/Call signal unavailable: {e}")
        return None

    def _get_aaii_signal(self) -> Optional[float]:
        """Get AAII sentiment signal (market-wide, not per-symbol)."""
        try:
            from src.data.sources.alternative.aaii_sentiment import AAIISentimentSource

            source = AAIISentimentSource()
            # Try to get cached signal first
            signal = source.get_signal()
            if signal != 0.0:
                return signal
            return None
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"AAII signal unavailable: {e}")
        return None

    def _get_cot_signal(self, symbol: str) -> Optional[float]:
        """Get Commitment of Traders signal for a symbol."""
        try:
            from src.data.sources.alternative.cot_report import COTSource

            source = COTSource()
            # Try to get cached signal first
            signal = source.get_signal(symbol)
            if signal != 0.0:
                return signal
            return None
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"COT signal unavailable for {symbol}: {e}")
        return None

    def _get_newsletter_signal(self) -> Optional[float]:
        """Get newsletter sentiment signal (market-wide, not per-symbol)."""
        try:
            from src.data.sources.alternative.newsletter_sentiment import NewsletterSentimentSource

            source = NewsletterSentimentSource()
            # Try to get cached signal first
            signal = source.get_signal()
            if signal != 0.0:
                return signal
            return None
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Newsletter signal unavailable: {e}")
        return None

    def _get_short_squeeze_score(self, symbol: str) -> Optional[float]:
        """Get short squeeze potential score for a symbol."""
        try:
            from src.data.sources.alternative.short_interest import get_short_interest

            # Check if short interest data is available
            data = get_short_interest(symbol)
            if data:
                # Calculate squeeze score based on:
                # - High short interest % float (>20%)
                # - Low days to cover (<2 days)
                # - Recent price momentum
                short_pct = data.get("short_pct_float", 0)
                days_to_cover = data.get("days_to_cover", 10)

                if short_pct > 30 and days_to_cover < 2:
                    return 0.9  # Very high squeeze potential
                elif short_pct > 20 and days_to_cover < 3:
                    return 0.6  # High squeeze potential
                elif short_pct > 10:
                    return 0.3  # Moderate squeeze potential
                return 0.0
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Short interest data unavailable for {symbol}: {e}")
        return None

    def _compute_composite(self, signal: AggregatedSignal) -> float:
        """Compute weighted composite score."""
        weighted_sum = 0.0
        total_weight = 0.0

        # Map signal types to values
        signal_values = {
            # Existing signals
            "swing": signal.swing_signal,
            "intraday": signal.intraday_signal,
            "ml": signal.ml_signal,
            "congressional": signal.congressional_signal,
            "insider": signal.insider_signal,
            "options_flow": signal.options_flow_signal,
            "sentiment": signal.sentiment_signal,
            # NEW: Market regime signals
            "vix_structure": signal.vix_structure_signal,
            "breadth": signal.breadth_signal,
            "put_call": signal.put_call_signal,
            # NEW: Sentiment extremes
            "aaii": signal.aaii_signal,
            "cot": signal.cot_signal,
            # NEW: Short interest (0-1 scale, convert to -1 to 1)
            # High squeeze score is bullish (shorts may cover)
            "short_interest": signal.short_squeeze_score * 2 - 1 if signal.short_squeeze_score > 0 else 0.0,
        }

        # Technical bias as signal
        tech_signal = 0.0
        if signal.technical_bias == "bullish":
            tech_signal = 0.5 + (signal.trend_strength * 0.5)
        elif signal.technical_bias == "bearish":
            tech_signal = -0.5 - (signal.trend_strength * 0.5)
        signal_values["technical"] = tech_signal

        # Compute weighted average of available signals
        for sig_type in signal.signals_available:
            if sig_type in signal_values and sig_type in self.WEIGHTS:
                value = signal_values[sig_type]
                weight = self.WEIGHTS[sig_type]
                weighted_sum += value * weight
                total_weight += weight

        if total_weight > 0:
            return weighted_sum / total_weight
        return 0.0

    def _compute_agreement(self, signal: AggregatedSignal) -> float:
        """Compute how aligned signals are (0 = conflicting, 1 = agreement)."""
        signals = []

        if "swing" in signal.signals_available:
            signals.append(signal.swing_signal)
        if "intraday" in signal.signals_available:
            signals.append(signal.intraday_signal)
        if "technical" in signal.signals_available:
            if signal.technical_bias == "bullish":
                signals.append(0.5)
            elif signal.technical_bias == "bearish":
                signals.append(-0.5)
            else:
                signals.append(0.0)

        # NEW: Include market regime signals in agreement calculation
        if "vix_structure" in signal.signals_available:
            signals.append(signal.vix_structure_signal)
        if "breadth" in signal.signals_available:
            signals.append(signal.breadth_signal)
        if "put_call" in signal.signals_available:
            signals.append(signal.put_call_signal)
        if "aaii" in signal.signals_available:
            signals.append(signal.aaii_signal)

        if len(signals) < 2:
            return 0.5  # Not enough signals to measure agreement

        # Agreement = 1 - normalized variance
        mean = sum(signals) / len(signals)
        variance = sum((s - mean) ** 2 for s in signals) / len(signals)
        # Normalize: max variance is 1 (signals at -1 and 1)
        normalized_variance = min(variance, 1.0)
        return 1.0 - normalized_variance

    def _compute_confidence(self, signal: AggregatedSignal) -> float:
        """Compute overall confidence based on signal availability and agreement."""
        # Base confidence from number of available signals
        # With new signals we have up to 14 signal types, so use 8 as the target
        base = min(len(signal.signals_available) / 8, 1.0) * 0.5

        # Boost from agreement
        agreement_boost = signal.signal_agreement * 0.3

        # Boost from strong composite score
        strength_boost = abs(signal.composite_score) * 0.2

        return min(base + agreement_boost + strength_boost, 1.0)

    def _generate_notes(self, signal: AggregatedSignal) -> str:
        """Generate human-readable notes about the signal."""
        notes = []

        # Composite direction
        if signal.composite_score > 0.3:
            notes.append("Strong bullish composite")
        elif signal.composite_score > 0.1:
            notes.append("Mild bullish lean")
        elif signal.composite_score < -0.3:
            notes.append("Strong bearish composite")
        elif signal.composite_score < -0.1:
            notes.append("Mild bearish lean")
        else:
            notes.append("Neutral composite")

        # Agreement
        if signal.signal_agreement > 0.7:
            notes.append("signals aligned")
        elif signal.signal_agreement < 0.3:
            notes.append("conflicting signals")

        # Technical levels
        if signal.distance_to_support_pct is not None:
            if signal.distance_to_support_pct < 2:
                notes.append(f"near support ({signal.distance_to_support_pct:.1f}%)")
        if signal.distance_to_resistance_pct is not None:
            if signal.distance_to_resistance_pct < 2:
                notes.append(f"near resistance ({signal.distance_to_resistance_pct:.1f}%)")

        # RSI
        if signal.rsi > 70:
            notes.append("overbought (RSI)")
        elif signal.rsi < 30:
            notes.append("oversold (RSI)")

        # NEW: Market regime notes
        if "vix_structure" in signal.signals_available:
            if signal.vix_structure_signal > 0.5:
                notes.append("VIX backwardation (fear)")
            elif signal.vix_structure_signal < -0.5:
                notes.append("VIX steep contango (complacency)")

        if "put_call" in signal.signals_available:
            if signal.put_call_signal > 0.5:
                notes.append("extreme P/C fear (contrarian buy)")
            elif signal.put_call_signal < -0.5:
                notes.append("extreme P/C greed (contrarian sell)")

        if "aaii" in signal.signals_available:
            if signal.aaii_signal > 0.5:
                notes.append("AAII extreme bearish (contrarian buy)")
            elif signal.aaii_signal < -0.5:
                notes.append("AAII extreme bullish (contrarian sell)")

        if "short_interest" in signal.signals_available:
            if signal.short_squeeze_score > 0.6:
                notes.append(f"squeeze potential ({signal.short_squeeze_score:.0%})")

        return "; ".join(notes) if notes else "No notable signals"
