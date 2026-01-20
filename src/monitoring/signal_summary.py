"""
Signal Summary Module - Aggregate all data sources into actionable signals.

Combines 40+ data sources into a unified signal view:
- Insider/Institutional: Congressional trades, Form 4 filings, ETF flows
- Options/Technical: Options flow, squeeze candidates, max pain
- Sentiment/Regime: AAII, put/call, Fear & Greed, VIX structure
- Catalysts: Earnings, FDA dates, economic calendar, geopolitical

Used by the operator loop and morning briefing for decision support.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """A single actionable signal."""
    type: str  # "insider", "congressional", "options", "technical", "catalyst", "sentiment"
    symbol: str | None  # None for market-wide signals
    direction: str  # "bullish", "bearish", "neutral"
    strength: float  # 0.0 - 1.0
    source: str  # Specific data source
    description: str  # Human-readable description
    timestamp: datetime
    expires_at: datetime | None = None  # When signal becomes stale
    thesis_id: str | None = None  # Linked thesis if applicable
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "symbol": self.symbol,
            "direction": self.direction,
            "strength": self.strength,
            "source": self.source,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "thesis_id": self.thesis_id,
            "metadata": self.metadata,
        }


@dataclass
class ConvergenceSignal:
    """Signal convergence - 3+ independent signals aligned on same symbol/direction."""
    symbol: str
    direction: str  # "bullish" or "bearish"
    signals: list[Signal]
    convergence_score: float  # Average strength
    confidence: float  # Based on signal diversity
    description: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "signal_count": len(self.signals),
            "signal_types": list(set(s.type for s in self.signals)),
            "convergence_score": self.convergence_score,
            "confidence": self.confidence,
            "description": self.description,
            "signals": [s.to_dict() for s in self.signals],
        }


@dataclass
class Catalyst:
    """Upcoming catalyst event."""
    date: datetime
    type: str  # "earnings", "fda", "fomc", "economic", "geopolitical"
    symbol: str | None  # None for market-wide
    event: str  # Event description
    impact: str  # "high", "medium", "low"
    exposure: float | None = None  # Portfolio exposure in dollars
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "type": self.type,
            "symbol": self.symbol,
            "event": self.event,
            "impact": self.impact,
            "exposure": self.exposure,
            "metadata": self.metadata,
        }


@dataclass
class SignalSummary:
    """Complete signal summary from all sources."""
    timestamp: datetime

    # Top signals by category
    insider_signals: list[Signal] = field(default_factory=list)
    options_signals: list[Signal] = field(default_factory=list)
    technical_signals: list[Signal] = field(default_factory=list)
    sentiment_signals: list[Signal] = field(default_factory=list)
    social_signals: list[Signal] = field(default_factory=list)

    # Convergences (3+ aligned signals)
    convergences: list[ConvergenceSignal] = field(default_factory=list)

    # Upcoming catalysts
    catalysts: list[Catalyst] = field(default_factory=list)

    # Market regime summary
    regime: str = "unknown"  # "risk_on", "risk_off", "neutral", "volatile"
    regime_signals: list[str] = field(default_factory=list)

    # Top actionable signals across all sources
    top_signals: list[Signal] = field(default_factory=list)

    # Thesis-relevant signals
    thesis_signals: dict[str, list[Signal]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "regime": self.regime,
            "regime_signals": self.regime_signals,
            "top_signals": [s.to_dict() for s in self.top_signals[:10]],
            "convergences": [c.to_dict() for c in self.convergences],
            "catalysts": [c.to_dict() for c in self.catalysts[:10]],
            "signal_counts": {
                "insider": len(self.insider_signals),
                "options": len(self.options_signals),
                "technical": len(self.technical_signals),
                "sentiment": len(self.sentiment_signals),
                "social": len(self.social_signals),
            },
            "thesis_signals": {
                tid: [s.to_dict() for s in signals]
                for tid, signals in self.thesis_signals.items()
            },
        }

    def get_all_signals(self) -> list[Signal]:
        """Get all signals flattened."""
        return (
            self.insider_signals +
            self.options_signals +
            self.technical_signals +
            self.sentiment_signals +
            self.social_signals
        )


class SignalAggregator:
    """
    Aggregates signals from all data sources into actionable intelligence.

    Sources checked:
    - state.json: Market data, sentiment, portfolio
    - alt_data.json: Congressional, insider, options flow, social
    - signals.json: Pre-computed technical signals
    - theses/*.yaml: Active investment theses
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.live_dir = self.results_dir / "live"
        self.theses_dir = self.results_dir / "theses"
        self.research_dir = self.live_dir / "research"

    def get_signal_summary(self) -> SignalSummary:
        """Get complete signal summary from all sources."""
        now = datetime.now()
        summary = SignalSummary(timestamp=now)

        # Load all data sources
        state = self._load_json(self.live_dir / "state.json")
        alt_data = self._load_json(self.research_dir / "alt_data.json")
        signals_data = self._load_json(self.research_dir / "signals.json")
        theses = self._load_theses()

        # Extract signals by category
        summary.insider_signals = self._extract_insider_signals(alt_data, state)
        summary.options_signals = self._extract_options_signals(alt_data, signals_data)
        summary.technical_signals = self._extract_technical_signals(signals_data, state)
        summary.sentiment_signals = self._extract_sentiment_signals(state)
        summary.social_signals = self._extract_social_signals(alt_data)

        # Extract catalysts
        summary.catalysts = self._extract_catalysts(state)

        # Determine market regime
        summary.regime, summary.regime_signals = self._determine_regime(state)

        # Find convergences (3+ aligned signals on same symbol)
        summary.convergences = self._find_convergences(summary.get_all_signals())

        # Extract thesis-relevant signals
        summary.thesis_signals = self._extract_thesis_signals(
            summary.get_all_signals(), theses
        )

        # Compile top signals
        summary.top_signals = self._rank_top_signals(summary)

        return summary

    def _load_json(self, path: Path) -> dict:
        """Load JSON file safely."""
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return {}

    def _load_theses(self) -> list[dict]:
        """Load all active theses."""
        theses = []
        if self.theses_dir.exists():
            for thesis_file in self.theses_dir.glob("*.yaml"):
                try:
                    with open(thesis_file) as f:
                        thesis = yaml.safe_load(f)
                        if thesis.get("status") == "active":
                            theses.append(thesis)
                except Exception as e:
                    logger.error(f"Error loading thesis {thesis_file}: {e}")
        return theses

    def _extract_insider_signals(self, alt_data: dict, state: dict) -> list[Signal]:
        """Extract insider/congressional trading signals."""
        signals = []
        now = datetime.now()

        # Congressional trades
        congressional = alt_data.get("congressional", {})
        clusters = congressional.get("clusters", [])

        for cluster in clusters:
            symbol = cluster.get("symbol", "UNK")
            count = cluster.get("count", 0)
            direction = cluster.get("direction", "buy")

            if count >= 3:  # 3+ politicians = strong signal
                signals.append(Signal(
                    type="congressional",
                    symbol=symbol,
                    direction="bullish" if direction == "buy" else "bearish",
                    strength=min(1.0, count / 5),  # 5+ = max strength
                    source="congressional_trades",
                    description=f"{count} politicians {direction}ing {symbol}",
                    timestamp=now,
                    expires_at=now + timedelta(days=30),
                    metadata={"politician_count": count},
                ))

        # Insider trades (Form 4)
        insider = alt_data.get("insider", {})
        recent_buys = insider.get("recent_buys", [])

        for buy in recent_buys:
            symbol = buy.get("symbol", "UNK")
            officer = buy.get("officer", "Unknown")
            amount = buy.get("amount", 0)

            if amount >= 100000:  # $100k+ = notable
                signals.append(Signal(
                    type="insider",
                    symbol=symbol,
                    direction="bullish",
                    strength=min(1.0, amount / 1000000),  # $1M+ = max
                    source="form_4",
                    description=f"{officer} bought ${amount:,.0f} of {symbol}",
                    timestamp=now,
                    expires_at=now + timedelta(days=14),
                    metadata={"officer": officer, "amount": amount},
                ))

        return signals

    def _extract_options_signals(self, alt_data: dict, signals_data: dict) -> list[Signal]:
        """Extract options flow and squeeze signals."""
        signals = []
        now = datetime.now()

        # Options flow from alt_data
        options_flow = alt_data.get("options_flow", {})

        for symbol, flow in options_flow.items():
            if isinstance(flow, dict):
                call_volume = flow.get("call_volume", 0)
                put_volume = flow.get("put_volume", 0)
                unusual = flow.get("unusual", False)

                if unusual and call_volume > put_volume * 2:
                    signals.append(Signal(
                        type="options",
                        symbol=symbol,
                        direction="bullish",
                        strength=0.7,
                        source="options_flow",
                        description=f"Unusual call activity in {symbol}",
                        timestamp=now,
                        expires_at=now + timedelta(days=7),
                        metadata={"call_volume": call_volume, "put_volume": put_volume},
                    ))
                elif unusual and put_volume > call_volume * 2:
                    signals.append(Signal(
                        type="options",
                        symbol=symbol,
                        direction="bearish",
                        strength=0.7,
                        source="options_flow",
                        description=f"Unusual put activity in {symbol}",
                        timestamp=now,
                        expires_at=now + timedelta(days=7),
                    ))

        # Short squeeze candidates from signals
        for symbol, data in signals_data.items():
            if isinstance(data, dict):
                squeeze_score = data.get("short_squeeze_score", 0)
                if squeeze_score > 0.6:
                    signals.append(Signal(
                        type="squeeze",
                        symbol=symbol,
                        direction="bullish",
                        strength=squeeze_score,
                        source="short_interest",
                        description=f"{symbol} squeeze potential: {squeeze_score:.0%}",
                        timestamp=now,
                        expires_at=now + timedelta(days=7),
                        metadata={"squeeze_score": squeeze_score},
                    ))

        return signals

    def _extract_technical_signals(self, signals_data: dict, state: dict) -> list[Signal]:
        """Extract technical analysis signals."""
        signals = []
        now = datetime.now()

        for symbol, data in signals_data.items():
            if not isinstance(data, dict):
                continue

            composite = data.get("composite_score", 0)
            confidence = data.get("confidence", 0.5)
            rsi = data.get("rsi", 50)
            technical_bias = data.get("technical_bias", "neutral")
            notes = data.get("notes", "")

            # Strong technical signals only
            if abs(composite) > 0.3 and confidence > 0.5:
                direction = "bullish" if composite > 0 else "bearish"
                signals.append(Signal(
                    type="technical",
                    symbol=symbol,
                    direction=direction,
                    strength=min(1.0, abs(composite)),
                    source="technical_analysis",
                    description=f"{symbol}: {notes[:100]}",
                    timestamp=now,
                    expires_at=now + timedelta(days=3),
                    metadata={
                        "composite": composite,
                        "rsi": rsi,
                        "bias": technical_bias,
                    },
                ))

            # RSI extremes
            if rsi < 30:
                signals.append(Signal(
                    type="technical",
                    symbol=symbol,
                    direction="bullish",
                    strength=0.6,
                    source="rsi",
                    description=f"{symbol} oversold (RSI: {rsi:.0f})",
                    timestamp=now,
                    expires_at=now + timedelta(days=5),
                    metadata={"rsi": rsi},
                ))
            elif rsi > 70:
                signals.append(Signal(
                    type="technical",
                    symbol=symbol,
                    direction="bearish",
                    strength=0.6,
                    source="rsi",
                    description=f"{symbol} overbought (RSI: {rsi:.0f})",
                    timestamp=now,
                    expires_at=now + timedelta(days=5),
                    metadata={"rsi": rsi},
                ))

        return signals

    def _extract_sentiment_signals(self, state: dict) -> list[Signal]:
        """Extract sentiment-based signals."""
        signals = []
        now = datetime.now()
        sentiment = state.get("sentiment", {})

        # Fear & Greed extremes
        fear_greed = sentiment.get("fear_greed_value", 50)
        if fear_greed < 25:
            signals.append(Signal(
                type="sentiment",
                symbol=None,
                direction="bullish",
                strength=0.7,
                source="fear_greed",
                description=f"Extreme Fear ({fear_greed}) - contrarian bullish",
                timestamp=now,
                expires_at=now + timedelta(days=7),
                metadata={"fear_greed": fear_greed},
            ))
        elif fear_greed > 75:
            signals.append(Signal(
                type="sentiment",
                symbol=None,
                direction="bearish",
                strength=0.7,
                source="fear_greed",
                description=f"Extreme Greed ({fear_greed}) - contrarian bearish",
                timestamp=now,
                expires_at=now + timedelta(days=7),
                metadata={"fear_greed": fear_greed},
            ))

        # Put/call ratio extremes
        pc_ratio = sentiment.get("put_call_ratio", 1.0)
        if pc_ratio > 1.2:
            signals.append(Signal(
                type="sentiment",
                symbol=None,
                direction="bullish",
                strength=0.6,
                source="put_call",
                description=f"Extreme puts ({pc_ratio:.2f}) - contrarian bullish",
                timestamp=now,
                expires_at=now + timedelta(days=3),
                metadata={"put_call_ratio": pc_ratio},
            ))
        elif pc_ratio < 0.6:
            signals.append(Signal(
                type="sentiment",
                symbol=None,
                direction="bearish",
                strength=0.6,
                source="put_call",
                description=f"Extreme calls ({pc_ratio:.2f}) - contrarian bearish",
                timestamp=now,
                expires_at=now + timedelta(days=3),
                metadata={"put_call_ratio": pc_ratio},
            ))

        # VIX structure
        vix_structure = sentiment.get("vix_term_structure", "contango")
        if vix_structure == "backwardation":
            market = state.get("market", {})
            vix = market.get("vix", 15)
            signals.append(Signal(
                type="sentiment",
                symbol=None,
                direction="bearish",
                strength=0.5 if vix < 25 else 0.8,
                source="vix_structure",
                description=f"VIX backwardation (VIX: {vix:.1f}) - elevated fear",
                timestamp=now,
                expires_at=now + timedelta(days=3),
                metadata={"vix": vix, "structure": vix_structure},
            ))

        return signals

    def _extract_social_signals(self, alt_data: dict) -> list[Signal]:
        """Extract social sentiment signals."""
        signals = []
        now = datetime.now()
        social = alt_data.get("social_sentiment", {})
        trending = social.get("trending_tickers", [])

        for ticker in trending:
            symbol = ticker.get("symbol", "")
            mentions = ticker.get("mentions", 0)
            sentiment = ticker.get("sentiment", "neutral")
            sentiment_score = ticker.get("sentiment_score", 0)

            # High mention count with strong sentiment
            if mentions >= 5 and abs(sentiment_score) > 0.3:
                direction = "bullish" if sentiment_score > 0 else "bearish"
                signals.append(Signal(
                    type="social",
                    symbol=symbol,
                    direction=direction,
                    strength=min(1.0, mentions / 10 * abs(sentiment_score)),
                    source="reddit",
                    description=f"{symbol}: {mentions} mentions, {sentiment} sentiment",
                    timestamp=now,
                    expires_at=now + timedelta(days=2),
                    metadata={
                        "mentions": mentions,
                        "sentiment_score": sentiment_score,
                    },
                ))

        return signals

    def _extract_catalysts(self, state: dict) -> list[Catalyst]:
        """Extract upcoming catalyst events."""
        catalysts = []
        now = datetime.now()
        today = now.date()

        # Get calendar events from state
        calendar_events = state.get("calendar_events", [])
        positions = {p.get("symbol"): p for p in state.get("positions", [])}

        for event in calendar_events:
            event_type = event.get("type", "")
            event_date_str = event.get("date", "")
            symbol = event.get("symbol")

            try:
                event_date = datetime.fromisoformat(event_date_str)
            except:
                continue

            # Only upcoming events (next 30 days)
            if event_date.date() < today or (event_date.date() - today).days > 30:
                continue

            # Determine impact
            impact = "low"
            if event_type.lower() in ("fomc", "cpi", "jobs", "gdp", "fed"):
                impact = "high"
            elif event_type.lower() in ("earnings", "fda", "pdufa"):
                impact = "high"
            elif symbol and symbol in positions:
                impact = "medium"

            # Calculate exposure if we have a position
            exposure = None
            if symbol and symbol in positions:
                exposure = positions[symbol].get("market_value", 0)

            catalysts.append(Catalyst(
                date=event_date,
                type=event_type.lower(),
                symbol=symbol,
                event=event.get("description", event_type),
                impact=impact,
                exposure=exposure,
                metadata=event.get("metadata", {}),
            ))

        # Sort by date
        catalysts.sort(key=lambda c: c.date)
        return catalysts

    def _determine_regime(self, state: dict) -> tuple[str, list[str]]:
        """Determine current market regime."""
        regime_signals = []
        market = state.get("market", {})
        sentiment = state.get("sentiment", {})

        vix = market.get("vix", 15)
        spy_change = market.get("spy_change_pct", 0)
        rotation = market.get("rotation_theme", "")
        vix_structure = sentiment.get("vix_term_structure", "contango")

        # Check signals
        if vix > 25:
            regime_signals.append(f"VIX elevated: {vix:.1f}")
        if abs(spy_change) > 2:
            regime_signals.append(f"SPY big move: {spy_change:+.1f}%")
        if vix_structure == "backwardation":
            regime_signals.append("VIX in backwardation")
        if rotation == "defensive":
            regime_signals.append("Defensive sector rotation")
        elif rotation == "cyclical":
            regime_signals.append("Cyclical sector rotation")

        # Determine regime
        if vix > 30 or (vix > 25 and vix_structure == "backwardation"):
            regime = "volatile"
        elif vix > 20 or rotation == "defensive":
            regime = "risk_off"
        elif rotation == "cyclical" and spy_change > 0:
            regime = "risk_on"
        else:
            regime = "neutral"

        return regime, regime_signals

    def _find_convergences(self, all_signals: list[Signal]) -> list[ConvergenceSignal]:
        """Find symbols with 3+ aligned signals."""
        convergences = []

        # Group signals by symbol and direction
        symbol_signals: dict[str, dict[str, list[Signal]]] = {}

        for signal in all_signals:
            if signal.symbol is None:
                continue

            if signal.symbol not in symbol_signals:
                symbol_signals[signal.symbol] = {"bullish": [], "bearish": []}

            symbol_signals[signal.symbol][signal.direction].append(signal)

        # Find convergences (3+ aligned)
        for symbol, directions in symbol_signals.items():
            for direction, signals in directions.items():
                if len(signals) >= 3:
                    # Calculate convergence metrics
                    types = set(s.type for s in signals)
                    avg_strength = sum(s.strength for s in signals) / len(signals)

                    # Confidence based on signal diversity
                    confidence = min(1.0, len(types) / 3)  # More diverse = higher confidence

                    convergences.append(ConvergenceSignal(
                        symbol=symbol,
                        direction=direction,
                        signals=signals,
                        convergence_score=avg_strength,
                        confidence=confidence,
                        description=f"{len(signals)} {direction} signals ({', '.join(types)})",
                    ))

        # Sort by convergence score
        convergences.sort(key=lambda c: c.convergence_score, reverse=True)
        return convergences

    def _extract_thesis_signals(
        self,
        all_signals: list[Signal],
        theses: list[dict],
    ) -> dict[str, list[Signal]]:
        """Group signals by thesis."""
        thesis_signals = {}

        for thesis in theses:
            thesis_id = thesis.get("id", "")
            thesis_name = thesis.get("name", "Unknown")
            positions = thesis.get("positions", [])

            relevant = []
            for signal in all_signals:
                if signal.symbol in positions:
                    signal.thesis_id = thesis_id
                    relevant.append(signal)

            if relevant:
                thesis_signals[thesis_name] = relevant

        return thesis_signals

    def _rank_top_signals(self, summary: SignalSummary) -> list[Signal]:
        """Rank and return top actionable signals."""
        all_signals = summary.get_all_signals()

        # Score signals
        def signal_score(s: Signal) -> float:
            score = s.strength
            # Boost convergence signals
            for conv in summary.convergences:
                if s in conv.signals:
                    score += 0.3
                    break
            # Boost thesis-linked signals
            if s.thesis_id:
                score += 0.2
            return score

        # Sort by score
        all_signals.sort(key=signal_score, reverse=True)
        return all_signals[:20]  # Top 20


# Singleton instance
_aggregator: SignalAggregator | None = None


def get_signal_aggregator() -> SignalAggregator:
    """Get global aggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = SignalAggregator()
    return _aggregator


def get_signal_summary() -> SignalSummary:
    """Convenience function to get signal summary."""
    return get_signal_aggregator().get_signal_summary()


def get_top_signals(limit: int = 10) -> list[dict]:
    """Get top actionable signals as dicts."""
    summary = get_signal_summary()
    return [s.to_dict() for s in summary.top_signals[:limit]]


def get_convergences() -> list[dict]:
    """Get all convergence signals."""
    summary = get_signal_summary()
    return [c.to_dict() for c in summary.convergences]


def get_upcoming_catalysts(days: int = 7) -> list[dict]:
    """Get catalysts within specified days."""
    summary = get_signal_summary()
    cutoff = datetime.now() + timedelta(days=days)
    return [
        c.to_dict() for c in summary.catalysts
        if c.date <= cutoff
    ]
