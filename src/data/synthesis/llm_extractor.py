"""
LLM-Powered Insight Extraction

Extracts structured insights from unstructured text:
- Price predictions
- Supply/demand signals
- Affected symbols
- Testable hypotheses
- Causal relationships

Tracks which sources provide real alpha over time.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from src.core.paths import paths
from typing import Any, Literal

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class SignalType(Enum):
    """Types of tradeable signals extracted."""
    PRICE_PREDICTION = "price_prediction"
    SUPPLY_DEMAND = "supply_demand"
    COMPETITIVE_DYNAMICS = "competitive_dynamics"
    MACRO_IMPACT = "macro_impact"
    SENTIMENT_SHIFT = "sentiment_shift"
    CAUSAL_RELATIONSHIP = "causal_relationship"


class Direction(Enum):
    """Signal direction."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class ExtractedInsight:
    """A structured insight extracted from text."""

    id: str
    source: str  # e.g., 'semianalysis', 'sec_filing'
    source_url: str
    signal_type: SignalType
    direction: Direction
    confidence: float  # 0-1
    symbols: list[str]  # Affected stock symbols
    summary: str  # One-line summary
    evidence: str  # Supporting quote from text
    timeframe: str  # e.g., 'short_term', 'medium_term', 'long_term'
    extracted_at: datetime
    published_at: datetime | None

    # For testable hypotheses
    hypothesis: str = ""
    test_criteria: str = ""  # How to test if this was correct
    expected_magnitude: float = 0.0  # Expected % move

    # Metadata
    tags: list[str] = field(default_factory=list)
    raw_text_hash: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signal_type"] = self.signal_type.value
        d["direction"] = self.direction.value
        d["extracted_at"] = self.extracted_at.isoformat()
        d["published_at"] = self.published_at.isoformat() if self.published_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractedInsight":
        d["signal_type"] = SignalType(d["signal_type"])
        d["direction"] = Direction(d["direction"])
        d["extracted_at"] = datetime.fromisoformat(d["extracted_at"])
        if d.get("published_at"):
            d["published_at"] = datetime.fromisoformat(d["published_at"])
        return cls(**d)


@dataclass
class ResearchIdea:
    """A testable research idea generated from insights."""

    id: str
    hypothesis: str
    target_assets: list[str]
    data_requirements: list[str]  # What data is needed
    test_methodology: str  # How to test
    expected_edge: str  # What edge we expect
    priority: float  # 0-1, higher = more promising
    generated_from: str  # Source insight ID
    generated_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["generated_at"] = self.generated_at.isoformat()
        return d


# =============================================================================
# RULE-BASED EXTRACTOR
# =============================================================================

class RuleBasedExtractor:
    """
    Rule-based insight extraction.

    Works without LLM API - uses patterns and keywords.
    Good for quick extraction of obvious signals.
    """

    # Signal patterns
    BULLISH_PATTERNS = [
        r"(?:expect|forecast|predict)(?:s|ed|ing)?\s+(?:to\s+)?(?:rise|increase|grow|surge|outperform)",
        r"(?:price|revenue|earnings)\s+(?:will|should|could)\s+(?:rise|increase|grow)",
        r"(?:bullish|positive|optimistic)\s+(?:on|for|about)",
        r"(?:upgrade|raise)(?:s|d)?\s+(?:price\s+)?target",
        r"(?:strong|robust|accelerating)\s+(?:demand|growth|momentum)",
        r"(?:beat|exceed|surpass)(?:s|ed|ing)?\s+(?:expectations|estimates)",
    ]

    BEARISH_PATTERNS = [
        r"(?:expect|forecast|predict)(?:s|ed|ing)?\s+(?:to\s+)?(?:fall|decline|drop|decrease|underperform)",
        r"(?:price|revenue|earnings)\s+(?:will|should|could)\s+(?:fall|decline|drop)",
        r"(?:bearish|negative|pessimistic)\s+(?:on|for|about)",
        r"(?:downgrade|lower)(?:s|d)?\s+(?:price\s+)?target",
        r"(?:weak|slowing|decelerating)\s+(?:demand|growth|momentum)",
        r"(?:miss|disappoint)(?:s|ed|ing)?",
    ]

    SUPPLY_PATTERNS = [
        r"(?:supply|inventory)\s+(?:shortage|glut|surplus|constraint)",
        r"(?:production|capacity)\s+(?:increase|decrease|expansion|cut)",
        r"(?:wafer|chip|fab)\s+(?:shortage|capacity|allocation)",
    ]

    CAUSAL_PATTERNS = [
        r"(\w+(?:\s+\w+)?)\s+(?:leads?|drives?|causes?|affects?|impacts?)\s+(\w+(?:\s+\w+)?)",
        r"(?:when|if)\s+(\w+(?:\s+\w+)?)\s+(?:rises?|falls?|increases?|decreases?),?\s+(\w+(?:\s+\w+)?)\s+(?:tends?|usually)",
        r"(\w+(?:\s+\w+)?)\s+is\s+a\s+(?:leading|lagging)\s+indicator\s+(?:of|for)\s+(\w+(?:\s+\w+)?)",
    ]

    # Symbol patterns
    SYMBOL_PATTERNS = [
        r'\$([A-Z]{1,5})\b',
        r'\b([A-Z]{2,5})\s+(?:stock|shares?|price)',
        r'\b(?:ticker|symbol):\s*([A-Z]{2,5})\b',
    ]

    # Timeframe patterns
    TIMEFRAME_PATTERNS = {
        "short_term": [r"(?:near|short)\s*term", r"(?:next|this)\s+(?:week|month)", r"Q[1-4]"],
        "medium_term": [r"(?:medium|mid)\s*term", r"(?:next|this)\s+(?:quarter|year)", r"6\s+months?"],
        "long_term": [r"(?:long)\s*term", r"(?:next|over)\s+(?:few\s+)?years?", r"202[5-9]"],
    }

    def extract_insights(
        self,
        text: str,
        source: str = "unknown",
        source_url: str = "",
        published_at: datetime | None = None,
    ) -> list[ExtractedInsight]:
        """Extract insights from text using rules."""
        insights = []
        now = datetime.now()

        # Extract symbols mentioned
        symbols = self._extract_symbols(text)

        # Check for bullish signals
        for pattern in self.BULLISH_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context = self._get_context(text, match.start(), match.end())
                local_symbols = self._extract_symbols(context) or symbols[:3]

                if local_symbols:
                    insight = ExtractedInsight(
                        id=f"rule_{now.timestamp()}_{len(insights)}",
                        source=source,
                        source_url=source_url,
                        signal_type=SignalType.PRICE_PREDICTION,
                        direction=Direction.BULLISH,
                        confidence=0.6,
                        symbols=local_symbols[:5],
                        summary=f"Bullish signal for {', '.join(local_symbols[:3])}",
                        evidence=context,
                        timeframe=self._detect_timeframe(context),
                        extracted_at=now,
                        published_at=published_at,
                        hypothesis=f"{local_symbols[0]} will outperform in coming period",
                        test_criteria="Compare returns vs benchmark",
                        tags=["rule_based", "bullish"],
                    )
                    insights.append(insight)
                    break  # One insight per pattern

        # Check for bearish signals
        for pattern in self.BEARISH_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context = self._get_context(text, match.start(), match.end())
                local_symbols = self._extract_symbols(context) or symbols[:3]

                if local_symbols:
                    insight = ExtractedInsight(
                        id=f"rule_{now.timestamp()}_{len(insights)}",
                        source=source,
                        source_url=source_url,
                        signal_type=SignalType.PRICE_PREDICTION,
                        direction=Direction.BEARISH,
                        confidence=0.6,
                        symbols=local_symbols[:5],
                        summary=f"Bearish signal for {', '.join(local_symbols[:3])}",
                        evidence=context,
                        timeframe=self._detect_timeframe(context),
                        extracted_at=now,
                        published_at=published_at,
                        hypothesis=f"{local_symbols[0]} will underperform in coming period",
                        test_criteria="Compare returns vs benchmark",
                        tags=["rule_based", "bearish"],
                    )
                    insights.append(insight)
                    break

        # Check for supply/demand signals
        for pattern in self.SUPPLY_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context = self._get_context(text, match.start(), match.end())
                local_symbols = self._extract_symbols(context) or symbols[:3]

                if local_symbols:
                    is_shortage = "shortage" in match.group().lower() or "constraint" in match.group().lower()
                    insight = ExtractedInsight(
                        id=f"rule_{now.timestamp()}_{len(insights)}",
                        source=source,
                        source_url=source_url,
                        signal_type=SignalType.SUPPLY_DEMAND,
                        direction=Direction.BULLISH if is_shortage else Direction.BEARISH,
                        confidence=0.7,
                        symbols=local_symbols[:5],
                        summary=f"{'Supply shortage' if is_shortage else 'Supply surplus'} signal",
                        evidence=context,
                        timeframe=self._detect_timeframe(context),
                        extracted_at=now,
                        published_at=published_at,
                        hypothesis=f"Supply dynamics to affect {local_symbols[0]}",
                        test_criteria="Monitor price relative to supply changes",
                        tags=["rule_based", "supply_demand"],
                    )
                    insights.append(insight)
                    break

        # Check for causal relationships
        for pattern in self.CAUSAL_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    cause, effect = match.groups()[:2]
                    context = self._get_context(text, match.start(), match.end())

                    insight = ExtractedInsight(
                        id=f"rule_{now.timestamp()}_{len(insights)}",
                        source=source,
                        source_url=source_url,
                        signal_type=SignalType.CAUSAL_RELATIONSHIP,
                        direction=Direction.NEUTRAL,
                        confidence=0.5,
                        symbols=self._extract_symbols(context)[:5],
                        summary=f"Causal: {cause} → {effect}",
                        evidence=context,
                        timeframe="unknown",
                        extracted_at=now,
                        published_at=published_at,
                        hypothesis=f"{cause} is a leading indicator of {effect}",
                        test_criteria="Test lag correlation between cause and effect",
                        tags=["rule_based", "causal"],
                    )
                    insights.append(insight)

        return insights

    def _extract_symbols(self, text: str) -> list[str]:
        """Extract stock symbols from text."""
        symbols = set()
        for pattern in self.SYMBOL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                sym = match.upper()
                if 2 <= len(sym) <= 5 and sym.isalpha():
                    symbols.add(sym)
        return list(symbols)

    def _get_context(self, text: str, start: int, end: int, window: int = 200) -> str:
        """Get context around a match."""
        ctx_start = max(0, start - window)
        ctx_end = min(len(text), end + window)

        # Extend to sentence boundaries
        while ctx_start > 0 and text[ctx_start] not in ".!?":
            ctx_start -= 1
        while ctx_end < len(text) and text[ctx_end] not in ".!?":
            ctx_end += 1

        return text[ctx_start:ctx_end + 1].strip()

    def _detect_timeframe(self, text: str) -> str:
        """Detect timeframe from text."""
        for timeframe, patterns in self.TIMEFRAME_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return timeframe
        return "unknown"


# =============================================================================
# LLM EXTRACTOR (Uses Claude API if available)
# =============================================================================

class LLMExtractor:
    """
    LLM-powered insight extraction.

    Uses Claude API for sophisticated understanding.
    Falls back to rule-based extraction if API unavailable.
    """

    EXTRACTION_PROMPT = """Analyze the following text and extract tradeable insights.

For each insight, provide:
1. signal_type: price_prediction, supply_demand, competitive_dynamics, macro_impact, sentiment_shift, or causal_relationship
2. direction: bullish, bearish, or neutral
3. symbols: list of affected stock tickers (use standard symbols like NVDA, AMD, TSM)
4. summary: one-line summary
5. evidence: supporting quote from the text
6. timeframe: short_term (days-weeks), medium_term (weeks-months), or long_term (months-years)
7. hypothesis: a testable statement
8. confidence: 0.0 to 1.0

Return as JSON array. Only extract clear, actionable insights.

Text:
{text}
"""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | None = None,
    ):
        self.api_key = api_key
        self.cache_dir = cache_dir or paths.base / "insights"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._rule_extractor = RuleBasedExtractor()
        self._has_api = api_key is not None

        # Track extraction history
        self._extraction_log: list[dict] = []

    async def extract(
        self,
        text: str,
        source: str = "unknown",
        source_url: str = "",
        published_at: datetime | None = None,
        use_llm: bool = True,
    ) -> list[ExtractedInsight]:
        """
        Extract insights from text.

        Args:
            text: Text to analyze
            source: Source identifier
            source_url: URL of source
            published_at: When the text was published
            use_llm: Whether to use LLM (falls back to rules if False or unavailable)

        Returns:
            List of extracted insights
        """
        # Try LLM first if available and requested
        if use_llm and self._has_api:
            try:
                insights = await self._extract_with_llm(
                    text, source, source_url, published_at
                )
                if insights:
                    return insights
            except Exception as e:
                logger.warning(f"LLM extraction failed: {e}")

        # Fall back to rule-based
        return self._rule_extractor.extract_insights(
            text, source, source_url, published_at
        )

    async def _extract_with_llm(
        self,
        text: str,
        source: str,
        source_url: str,
        published_at: datetime | None,
    ) -> list[ExtractedInsight]:
        """Extract using Claude API."""
        # This would use the Claude API
        # For now, return empty list (rule-based fallback will be used)
        logger.info("LLM extraction not implemented - using rule-based fallback")
        return []

    def generate_hypotheses(
        self,
        insights: list[ExtractedInsight],
    ) -> list[ResearchIdea]:
        """Generate testable research ideas from insights."""
        ideas = []
        now = datetime.now()

        # Group insights by direction and symbols
        bullish_insights = [i for i in insights if i.direction == Direction.BULLISH]
        bearish_insights = [i for i in insights if i.direction == Direction.BEARISH]
        causal_insights = [i for i in insights if i.signal_type == SignalType.CAUSAL_RELATIONSHIP]

        # Generate momentum ideas from bullish signals
        for insight in bullish_insights[:5]:
            if insight.symbols:
                ideas.append(ResearchIdea(
                    id=f"idea_{now.timestamp()}_{len(ideas)}",
                    hypothesis=f"Momentum strategy on {insight.symbols[0]} based on {insight.signal_type.value}",
                    target_assets=insight.symbols,
                    data_requirements=["price_data", "volume_data"],
                    test_methodology="Compare long-only returns over next 30 days",
                    expected_edge=f"Positive returns based on {insight.summary}",
                    priority=insight.confidence,
                    generated_from=insight.id,
                    generated_at=now,
                ))

        # Generate mean-reversion ideas from bearish signals
        for insight in bearish_insights[:5]:
            if insight.symbols:
                ideas.append(ResearchIdea(
                    id=f"idea_{now.timestamp()}_{len(ideas)}",
                    hypothesis=f"Short or avoid {insight.symbols[0]} based on {insight.signal_type.value}",
                    target_assets=insight.symbols,
                    data_requirements=["price_data", "volume_data"],
                    test_methodology="Compare short returns or underperformance vs benchmark",
                    expected_edge=f"Underperformance based on {insight.summary}",
                    priority=insight.confidence,
                    generated_from=insight.id,
                    generated_at=now,
                ))

        # Generate causal strategy ideas
        for insight in causal_insights[:5]:
            ideas.append(ResearchIdea(
                id=f"idea_{now.timestamp()}_{len(ideas)}",
                hypothesis=insight.hypothesis,
                target_assets=insight.symbols,
                data_requirements=["price_data", "causal_factor_data"],
                test_methodology="Test lead-lag correlation, build predictive model",
                expected_edge=f"Leading indicator advantage: {insight.summary}",
                priority=insight.confidence * 1.2,  # Boost causal ideas
                generated_from=insight.id,
                generated_at=now,
            ))

        return sorted(ideas, key=lambda x: x.priority, reverse=True)

    def save_insights(self, insights: list[ExtractedInsight], filename: str) -> Path:
        """Save insights to file."""
        filepath = self.cache_dir / f"{filename}.json"
        data = [i.to_dict() for i in insights]
        filepath.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved {len(insights)} insights to {filepath}")
        return filepath

    def load_insights(self, filename: str) -> list[ExtractedInsight]:
        """Load insights from file."""
        filepath = self.cache_dir / f"{filename}.json"
        if not filepath.exists():
            return []
        data = json.loads(filepath.read_text())
        return [ExtractedInsight.from_dict(d) for d in data]


# =============================================================================
# INTEGRATION WITH KNOWLEDGE BASE
# =============================================================================

class InsightTracker:
    """
    Track which insights led to profitable trades.

    Learns over time which sources and signal types have real alpha.
    """

    def __init__(self, knowledge_base_path: Path | None = None):
        self.kb_path = knowledge_base_path or paths.knowledge
        self._predictions: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load prediction history."""
        filepath = self.kb_path / "insight_predictions.json"
        if filepath.exists():
            self._predictions = json.loads(filepath.read_text())

    def _save(self) -> None:
        """Save prediction history."""
        filepath = self.kb_path / "insight_predictions.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(self._predictions, indent=2))

    def record_prediction(
        self,
        insight: ExtractedInsight,
        prediction_date: datetime,
        target_return: float | None = None,
    ) -> str:
        """Record a prediction based on an insight."""
        pred_id = f"pred_{prediction_date.timestamp()}"

        self._predictions.append({
            "id": pred_id,
            "insight_id": insight.id,
            "source": insight.source,
            "signal_type": insight.signal_type.value,
            "direction": insight.direction.value,
            "symbols": insight.symbols,
            "predicted_at": prediction_date.isoformat(),
            "target_return": target_return,
            "actual_return": None,
            "resolved": False,
        })
        self._save()
        return pred_id

    def resolve_prediction(
        self,
        pred_id: str,
        actual_return: float,
    ) -> None:
        """Record the actual outcome of a prediction."""
        for pred in self._predictions:
            if pred["id"] == pred_id:
                pred["actual_return"] = actual_return
                pred["resolved"] = True
                break
        self._save()

    def get_source_performance(self) -> dict[str, dict]:
        """Get performance by source."""
        resolved = [p for p in self._predictions if p["resolved"]]

        by_source = {}
        for pred in resolved:
            source = pred["source"]
            if source not in by_source:
                by_source[source] = {
                    "n_predictions": 0,
                    "correct": 0,
                    "total_return": 0.0,
                }

            by_source[source]["n_predictions"] += 1
            by_source[source]["total_return"] += pred["actual_return"]

            # Check if direction was correct
            expected_positive = pred["direction"] == "bullish"
            actual_positive = pred["actual_return"] > 0
            if expected_positive == actual_positive:
                by_source[source]["correct"] += 1

        # Calculate hit rates
        for source, stats in by_source.items():
            n = stats["n_predictions"]
            stats["hit_rate"] = stats["correct"] / n if n > 0 else 0
            stats["avg_return"] = stats["total_return"] / n if n > 0 else 0

        return by_source


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def extract_from_text(
    text: str,
    source: str = "unknown",
) -> list[ExtractedInsight]:
    """Quick extraction using rule-based extractor."""
    extractor = RuleBasedExtractor()
    return extractor.extract_insights(text, source)


def generate_ideas_from_article(
    title: str,
    content: str,
    source: str = "unknown",
) -> list[ResearchIdea]:
    """Generate research ideas from an article."""
    extractor = LLMExtractor()
    insights = extractor._rule_extractor.extract_insights(
        f"{title}\n\n{content}",
        source,
    )
    return extractor.generate_hypotheses(insights)
