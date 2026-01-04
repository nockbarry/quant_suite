"""
Hypothesis Generator

Automatically generates trading hypotheses from:
- Detected anomalies in price/volume
- News and SEC filing analysis
- Successful pattern extrapolation
- Correlation regime changes
- Cross-asset divergences

Produces ranked, testable hypotheses with expected signals.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

class HypothesisType(Enum):
    """Types of trading hypotheses."""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    SENTIMENT = "sentiment"
    CORRELATION = "correlation"
    EVENT_DRIVEN = "event_driven"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    ALTERNATIVE = "alternative"


class SignalDirection(Enum):
    """Expected signal direction."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class Hypothesis:
    """A trading hypothesis to test."""
    id: str
    title: str
    description: str
    hypothesis_type: HypothesisType
    symbol: str
    signal_direction: SignalDirection
    confidence: float  # 0 to 1
    expected_return: float  # Expected return if correct
    timeframe_days: int
    rationale: str
    evidence: list = field(default_factory=list)
    test_criteria: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    priority_score: float = 0.0
    source: str = ""


@dataclass
class Anomaly:
    """A detected market anomaly."""
    symbol: str
    anomaly_type: str
    severity: float  # 0 to 1
    description: str
    detected_at: datetime
    data: dict = field(default_factory=dict)


@dataclass
class CorrelationBreak:
    """A detected correlation regime change."""
    asset1: str
    asset2: str
    historical_correlation: float
    current_correlation: float
    change_magnitude: float
    detected_at: datetime


# =============================================================================
# HYPOTHESIS GENERATOR
# =============================================================================

class HypothesisGenerator:
    """
    Generate trading hypotheses from data and patterns.

    Usage:
        from workflows.research.knowledge_base import KnowledgeBase

        kb = KnowledgeBase()
        generator = HypothesisGenerator(kb)

        # Generate from anomalies
        hypotheses = generator.generate_from_anomalies()

        # Generate from news
        hypotheses = generator.generate_from_news("AAPL")

        # Get ranked daily hypotheses
        ranked = generator.get_daily_hypotheses(n=10)
    """

    UNIVERSE = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "JPM", "V", "JNJ", "WMT", "PG", "UNH", "HD", "MA", "DIS",
        "PYPL", "ADBE", "NFLX", "CRM", "INTC", "AMD", "QCOM", "AVGO",
    ]

    def __init__(self, knowledge_base=None):
        self.kb = knowledge_base
        self._hypothesis_counter = 0

    def _next_id(self) -> str:
        """Generate unique hypothesis ID."""
        self._hypothesis_counter += 1
        return f"H_{datetime.now().strftime('%Y%m%d')}_{self._hypothesis_counter:04d}"

    # -------------------------------------------------------------------------
    # ANOMALY DETECTION
    # -------------------------------------------------------------------------

    def detect_anomalies(self, lookback_days: int = 5) -> list[Anomaly]:
        """
        Detect market anomalies across the universe.

        Types detected:
        - Volume spikes (>2x average)
        - Price gaps (>3%)
        - Unusual volatility
        - RSI extremes (<20 or >80)
        """
        import yfinance as yf

        anomalies = []

        for symbol in self.UNIVERSE[:20]:  # Limit for speed
            try:
                df = yf.download(symbol, period="60d", progress=False)
                if df.empty:
                    continue

                df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

                # Volume spike
                avg_volume = df["volume"].rolling(20).mean().iloc[-1]
                current_volume = df["volume"].iloc[-1]
                if current_volume > avg_volume * 2:
                    anomalies.append(Anomaly(
                        symbol=symbol,
                        anomaly_type="volume_spike",
                        severity=min(1.0, current_volume / avg_volume / 4),
                        description=f"Volume {current_volume/avg_volume:.1f}x average",
                        detected_at=datetime.now(),
                        data={"volume_ratio": current_volume / avg_volume},
                    ))

                # Price gap
                gap = (df["open"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]
                if abs(gap) > 0.03:
                    anomalies.append(Anomaly(
                        symbol=symbol,
                        anomaly_type="price_gap",
                        severity=min(1.0, abs(gap) / 0.1),
                        description=f"Gap {'up' if gap > 0 else 'down'} {abs(gap)*100:.1f}%",
                        detected_at=datetime.now(),
                        data={"gap_pct": gap},
                    ))

                # RSI extreme
                delta = df["close"].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1]

                if current_rsi < 20 or current_rsi > 80:
                    anomalies.append(Anomaly(
                        symbol=symbol,
                        anomaly_type="rsi_extreme",
                        severity=abs(current_rsi - 50) / 50,
                        description=f"RSI {'oversold' if current_rsi < 30 else 'overbought'} at {current_rsi:.0f}",
                        detected_at=datetime.now(),
                        data={"rsi": current_rsi},
                    ))

            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")
                continue

        logger.info(f"Detected {len(anomalies)} anomalies")
        return anomalies

    def generate_from_anomalies(self) -> list[Hypothesis]:
        """Generate hypotheses from detected anomalies."""
        anomalies = self.detect_anomalies()
        hypotheses = []

        for anomaly in anomalies:
            if anomaly.anomaly_type == "volume_spike":
                # High volume often precedes directional moves
                hypotheses.append(Hypothesis(
                    id=self._next_id(),
                    title=f"{anomaly.symbol} Volume Breakout",
                    description=f"Unusual volume detected in {anomaly.symbol}, potential for momentum follow-through",
                    hypothesis_type=HypothesisType.MOMENTUM,
                    symbol=anomaly.symbol,
                    signal_direction=SignalDirection.LONG,  # Would need price direction to determine
                    confidence=0.55,
                    expected_return=0.03,
                    timeframe_days=5,
                    rationale="Volume spikes often precede significant price moves",
                    evidence=[f"Volume {anomaly.data['volume_ratio']:.1f}x normal"],
                    source="anomaly_detection",
                ))

            elif anomaly.anomaly_type == "rsi_extreme":
                rsi = anomaly.data["rsi"]
                direction = SignalDirection.LONG if rsi < 30 else SignalDirection.SHORT

                hypotheses.append(Hypothesis(
                    id=self._next_id(),
                    title=f"{anomaly.symbol} RSI Mean Reversion",
                    description=f"{anomaly.symbol} showing extreme RSI, potential for mean reversion",
                    hypothesis_type=HypothesisType.MEAN_REVERSION,
                    symbol=anomaly.symbol,
                    signal_direction=direction,
                    confidence=0.60,
                    expected_return=0.04,
                    timeframe_days=10,
                    rationale="Extreme RSI levels often revert to mean",
                    evidence=[f"RSI at {rsi:.0f}"],
                    source="anomaly_detection",
                ))

            elif anomaly.anomaly_type == "price_gap":
                gap = anomaly.data["gap_pct"]
                # Gaps often get filled
                direction = SignalDirection.SHORT if gap > 0 else SignalDirection.LONG

                hypotheses.append(Hypothesis(
                    id=self._next_id(),
                    title=f"{anomaly.symbol} Gap Fill",
                    description=f"{anomaly.symbol} has {abs(gap)*100:.1f}% gap that may fill",
                    hypothesis_type=HypothesisType.MEAN_REVERSION,
                    symbol=anomaly.symbol,
                    signal_direction=direction,
                    confidence=0.50,
                    expected_return=abs(gap) * 0.5,
                    timeframe_days=5,
                    rationale="Price gaps often get filled",
                    evidence=[f"Gap of {gap*100:.1f}%"],
                    source="anomaly_detection",
                ))

        return hypotheses

    # -------------------------------------------------------------------------
    # NEWS-BASED HYPOTHESES
    # -------------------------------------------------------------------------

    def generate_from_news(self, symbol: str) -> list[Hypothesis]:
        """Generate hypotheses from recent news for a symbol."""
        hypotheses = []

        try:
            from src.data.feature_engineering.text_embeddings import get_embedder

            embedder = get_embedder()
            shift = embedder.track_narrative_shift(symbol, window_days=7)

            if shift.shift_magnitude > 0.3:
                # Significant narrative shift
                hypotheses.append(Hypothesis(
                    id=self._next_id(),
                    title=f"{symbol} Narrative Shift",
                    description=f"Significant change in news narrative for {symbol}",
                    hypothesis_type=HypothesisType.SENTIMENT,
                    symbol=symbol,
                    signal_direction=SignalDirection.NEUTRAL,
                    confidence=0.55,
                    expected_return=0.05,
                    timeframe_days=14,
                    rationale="Major narrative shifts often precede price moves",
                    evidence=[
                        f"Shift magnitude: {shift.shift_magnitude:.2f}",
                        f"Topics: {', '.join(shift.dominant_topics[:3])}",
                    ],
                    source="narrative_analysis",
                ))

        except Exception as e:
            logger.debug(f"Error generating news hypotheses for {symbol}: {e}")

        return hypotheses

    # -------------------------------------------------------------------------
    # PATTERN EXTRAPOLATION
    # -------------------------------------------------------------------------

    def generate_from_patterns(self) -> list[Hypothesis]:
        """Generate hypotheses by extrapolating successful patterns."""
        hypotheses = []

        if self.kb is None:
            return hypotheses

        try:
            # Get successful strategies
            successes = self.kb.get_successful_strategies(min_sharpe=1.5)

            # Group by strategy
            strategy_successes = {}
            for s in successes:
                if s.strategy_name not in strategy_successes:
                    strategy_successes[s.strategy_name] = []
                strategy_successes[s.strategy_name].append(s)

            # For each successful strategy, suggest new symbols
            for strategy, results in strategy_successes.items():
                winning_symbols = set(r.symbol for r in results)
                avg_sharpe = np.mean([r.val_sharpe for r in results])

                # Find similar symbols not yet tested
                untested = [s for s in self.UNIVERSE if s not in winning_symbols]

                for symbol in untested[:3]:  # Limit suggestions
                    hypotheses.append(Hypothesis(
                        id=self._next_id(),
                        title=f"Test {strategy} on {symbol}",
                        description=f"{strategy} has worked on similar symbols, test on {symbol}",
                        hypothesis_type=HypothesisType.TECHNICAL,
                        symbol=symbol,
                        signal_direction=SignalDirection.NEUTRAL,
                        confidence=0.50,
                        expected_return=0.03,
                        timeframe_days=20,
                        rationale=f"Strategy shows {avg_sharpe:.1f} avg Sharpe on {len(winning_symbols)} symbols",
                        evidence=[
                            f"Winning symbols: {', '.join(list(winning_symbols)[:5])}",
                            f"Avg Sharpe: {avg_sharpe:.2f}",
                        ],
                        test_criteria={"strategy": strategy},
                        source="pattern_extrapolation",
                    ))

        except Exception as e:
            logger.debug(f"Error generating pattern hypotheses: {e}")

        return hypotheses

    # -------------------------------------------------------------------------
    # CORRELATION BREAKS
    # -------------------------------------------------------------------------

    def detect_correlation_breaks(self, lookback_days: int = 60) -> list[CorrelationBreak]:
        """Detect significant changes in asset correlations."""
        import yfinance as yf

        breaks = []

        # Key pairs to monitor
        pairs = [
            ("SPY", "QQQ"),
            ("SPY", "TLT"),
            ("SPY", "GLD"),
            ("XLF", "XLK"),
            ("VIX", "SPY"),
        ]

        for asset1, asset2 in pairs:
            try:
                data = yf.download([asset1, asset2], period="120d", progress=False)
                if data.empty:
                    continue

                returns1 = data["Close"][asset1].pct_change().dropna()
                returns2 = data["Close"][asset2].pct_change().dropna()

                if len(returns1) < lookback_days:
                    continue

                # Historical vs recent correlation
                historical = returns1[:-20].corr(returns2[:-20])
                recent = returns1[-20:].corr(returns2[-20:])

                change = abs(recent - historical)

                if change > 0.3:  # Significant change
                    breaks.append(CorrelationBreak(
                        asset1=asset1,
                        asset2=asset2,
                        historical_correlation=historical,
                        current_correlation=recent,
                        change_magnitude=change,
                        detected_at=datetime.now(),
                    ))

            except Exception as e:
                logger.debug(f"Error checking correlation {asset1}/{asset2}: {e}")
                continue

        return breaks

    def generate_from_correlation_breaks(self) -> list[Hypothesis]:
        """Generate hypotheses from correlation regime changes."""
        breaks = self.detect_correlation_breaks()
        hypotheses = []

        for brk in breaks:
            hypotheses.append(Hypothesis(
                id=self._next_id(),
                title=f"{brk.asset1}/{brk.asset2} Correlation Break",
                description=f"Correlation between {brk.asset1} and {brk.asset2} has changed significantly",
                hypothesis_type=HypothesisType.CORRELATION,
                symbol=brk.asset1,
                signal_direction=SignalDirection.NEUTRAL,
                confidence=0.55,
                expected_return=0.04,
                timeframe_days=20,
                rationale="Correlation regime changes often signal market transitions",
                evidence=[
                    f"Historical corr: {brk.historical_correlation:.2f}",
                    f"Current corr: {brk.current_correlation:.2f}",
                    f"Change: {brk.change_magnitude:.2f}",
                ],
                source="correlation_analysis",
            ))

        return hypotheses

    # -------------------------------------------------------------------------
    # RANKING AND AGGREGATION
    # -------------------------------------------------------------------------

    def rank_hypotheses(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Rank hypotheses by expected value and testability."""
        for h in hypotheses:
            # Priority score = confidence * expected_return * urgency_factor
            urgency = 1.0 / max(h.timeframe_days, 1)  # Shorter timeframes = higher urgency
            h.priority_score = h.confidence * h.expected_return * urgency * 100

        return sorted(hypotheses, key=lambda h: h.priority_score, reverse=True)

    def get_daily_hypotheses(self, n: int = 10) -> list[Hypothesis]:
        """
        Get top N hypotheses for today.

        Combines:
        - Anomaly-based hypotheses
        - Pattern extrapolation
        - Correlation breaks
        """
        all_hypotheses = []

        # Generate from all sources
        all_hypotheses.extend(self.generate_from_anomalies())
        all_hypotheses.extend(self.generate_from_patterns())
        all_hypotheses.extend(self.generate_from_correlation_breaks())

        # Rank and return top N
        ranked = self.rank_hypotheses(all_hypotheses)
        return ranked[:n]

    def generate_hypothesis_report(self, hypotheses: list[Hypothesis]) -> str:
        """Generate markdown report of hypotheses."""
        lines = [
            "# Daily Hypothesis Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Total Hypotheses: {len(hypotheses)}",
            "",
            "## Top Hypotheses",
            "",
        ]

        for i, h in enumerate(hypotheses[:10], 1):
            lines.extend([
                f"### {i}. {h.title}",
                f"**Symbol**: {h.symbol} | **Direction**: {h.signal_direction.value} | **Confidence**: {h.confidence:.0%}",
                f"**Type**: {h.hypothesis_type.value} | **Timeframe**: {h.timeframe_days} days",
                "",
                f"**Description**: {h.description}",
                "",
                f"**Rationale**: {h.rationale}",
                "",
                "**Evidence**:",
                *[f"- {e}" for e in h.evidence],
                "",
                f"Priority Score: {h.priority_score:.2f}",
                "",
                "---",
                "",
            ])

        return "\n".join(lines)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_daily_hypotheses(n: int = 10) -> list[Hypothesis]:
    """Quick access to daily hypotheses."""
    generator = HypothesisGenerator()
    return generator.get_daily_hypotheses(n)


def generate_hypothesis_report() -> str:
    """Generate and save daily hypothesis report."""
    generator = HypothesisGenerator()
    hypotheses = generator.get_daily_hypotheses(10)
    return generator.generate_hypothesis_report(hypotheses)
