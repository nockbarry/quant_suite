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

logger = logging.getLogger(__name__)


@dataclass
class AggregatedSignal:
    """All signals for one symbol, unified."""

    symbol: str
    timestamp: datetime

    # From existing strategies (-1 to 1 scale)
    swing_signal: float = 0.0
    intraday_signal: float = 0.0
    ml_signal: float = 0.0

    # From existing alt data (-1 to 1 scale)
    congressional_signal: float = 0.0
    insider_signal: float = 0.0
    options_flow_signal: float = 0.0
    sentiment_signal: float = 0.0

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
    WEIGHTS = {
        "swing": 0.25,
        "intraday": 0.15,
        "ml": 0.15,
        "congressional": 0.10,
        "insider": 0.10,
        "options_flow": 0.10,
        "sentiment": 0.05,
        "technical": 0.10,
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
        """Get swing strategy signal."""
        # TODO: Integrate with src/strategies/swing/
        # For now, return None (signal not available)
        return None

    def _get_intraday_signal(self, symbol: str) -> Optional[float]:
        """Get intraday strategy signal."""
        # TODO: Integrate with src/strategies/intraday/
        return None

    def _get_congressional_signal(self, symbol: str) -> Optional[float]:
        """Get congressional trading signal."""
        try:
            from src.data.sources.alternative.congressional_trades import (
                find_congressional_clusters,
            )
            # This is async, would need to be called differently
            # For synchronous context, return None
        except ImportError:
            pass
        return None

    def _get_insider_signal(self, symbol: str) -> Optional[float]:
        """Get insider trading signal."""
        try:
            from src.data.sources.alternative.insider import get_insider_signal
            # Similar async consideration
        except ImportError:
            pass
        return None

    def _get_options_flow_signal(self, symbol: str) -> Optional[float]:
        """Get unusual options activity signal."""
        try:
            from src.data.sources.alternative.options_flow import get_options_flow_signal
        except ImportError:
            pass
        return None

    def _get_sentiment_signal(self, symbol: str) -> Optional[float]:
        """Get sentiment signal."""
        # Could integrate with sentiment.py or text_research
        return None

    def _compute_composite(self, signal: AggregatedSignal) -> float:
        """Compute weighted composite score."""
        weighted_sum = 0.0
        total_weight = 0.0

        # Map signal types to values
        signal_values = {
            "swing": signal.swing_signal,
            "intraday": signal.intraday_signal,
            "ml": signal.ml_signal,
            "congressional": signal.congressional_signal,
            "insider": signal.insider_signal,
            "options_flow": signal.options_flow_signal,
            "sentiment": signal.sentiment_signal,
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
        base = min(len(signal.signals_available) / 5, 1.0) * 0.5

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

        return "; ".join(notes) if notes else "No notable signals"
