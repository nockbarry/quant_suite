#!/usr/bin/env python3
"""Thesis Suggester - Auto-suggest theses from converging signals.

Monitors signals from multiple sources and suggests thesis creation when:
- 3+ signals converge on same symbol/direction
- Social signals show early momentum
- Cross-platform convergence detected

Outputs suggestions for human review before thesis creation.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.knowledge.signal_provenance import (
    SignalProvenanceTracker,
    SignalProvenance,
    SignalSource,
    get_provenance_tracker,
)
from src.knowledge.thesis import ThesisTracker, Thesis

logger = logging.getLogger(__name__)


@dataclass
class ThesisSuggestion:
    """A suggested thesis based on converging signals."""
    symbol: str
    suggested_name: str
    suggested_summary: str
    direction: str  # bullish, bearish
    confidence_score: float  # 0-1 based on convergence

    # Supporting signals
    signal_ids: list = field(default_factory=list)
    signal_sources: list = field(default_factory=list)
    signal_count: int = 0

    # Suggested signposts
    suggested_signposts: list = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, accepted, dismissed, watched
    dismissal_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "suggested_name": self.suggested_name,
            "suggested_summary": self.suggested_summary,
            "direction": self.direction,
            "confidence_score": self.confidence_score,
            "signal_ids": self.signal_ids,
            "signal_sources": self.signal_sources,
            "signal_count": self.signal_count,
            "suggested_signposts": self.suggested_signposts,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "dismissal_reason": self.dismissal_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThesisSuggestion":
        return cls(
            symbol=data["symbol"],
            suggested_name=data["suggested_name"],
            suggested_summary=data["suggested_summary"],
            direction=data["direction"],
            confidence_score=data["confidence_score"],
            signal_ids=data.get("signal_ids", []),
            signal_sources=data.get("signal_sources", []),
            signal_count=data.get("signal_count", 0),
            suggested_signposts=data.get("suggested_signposts", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            status=data.get("status", "pending"),
            dismissal_reason=data.get("dismissal_reason", ""),
        )


class ThesisSuggester:
    """Generate thesis suggestions from converging signals."""

    SUGGESTIONS_PATH = Path.home() / "quant_results" / "suggestions" / "thesis_suggestions.json"
    MIN_SIGNALS_FOR_SUGGESTION = 2
    MIN_CONFIDENCE = 0.5

    # Source weights for confidence calculation
    SOURCE_WEIGHTS = {
        SignalSource.WSB: 0.8,
        SignalSource.STOCKTWITS: 0.7,
        SignalSource.TWITTER: 0.6,
        SignalSource.NEWS: 1.0,
        SignalSource.STATISTICAL: 1.2,
        SignalSource.AGENT: 1.1,
        SignalSource.INSIDER: 1.3,
        SignalSource.CONGRESSIONAL: 1.4,
        SignalSource.OPTIONS: 1.1,
    }

    def __init__(
        self,
        provenance_tracker: SignalProvenanceTracker = None,
        thesis_tracker: ThesisTracker = None,
    ):
        self.provenance = provenance_tracker or get_provenance_tracker()
        self.thesis_tracker = thesis_tracker or ThesisTracker(paths.theses)
        self.suggestions: dict[str, ThesisSuggestion] = {}
        self._load_suggestions()

    def _load_suggestions(self):
        """Load existing suggestions."""
        if self.SUGGESTIONS_PATH.exists():
            try:
                with open(self.SUGGESTIONS_PATH) as f:
                    data = json.load(f)
                    for item in data.get("suggestions", []):
                        suggestion = ThesisSuggestion.from_dict(item)
                        self.suggestions[suggestion.symbol] = suggestion
            except Exception as e:
                logger.warning(f"Could not load suggestions: {e}")

    def _save_suggestions(self):
        """Save suggestions to disk."""
        self.SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "updated_at": datetime.now().isoformat(),
            "suggestions": [s.to_dict() for s in self.suggestions.values()],
        }

        with open(self.SUGGESTIONS_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def _get_symbols_with_thesis(self) -> set[str]:
        """Get symbols that already have an active thesis."""
        symbols = set()
        for thesis in self.thesis_tracker.get_active_theses():
            for position in thesis.positions:
                symbols.add(position)
        return symbols

    def _generate_thesis_name(self, symbol: str, signals: list[SignalProvenance]) -> str:
        """Generate a suggested thesis name from signals."""
        # Look for common themes in signal descriptions
        descriptions = [s.initial_description.lower() for s in signals]
        all_text = " ".join(descriptions)

        # Common themes
        if "squeeze" in all_text or "short" in all_text:
            return f"{symbol} Short Squeeze"
        elif "earnings" in all_text:
            return f"{symbol} Earnings Play"
        elif "spin" in all_text or "split" in all_text:
            return f"{symbol} Corporate Action"
        elif "fda" in all_text or "approval" in all_text:
            return f"{symbol} FDA Catalyst"
        elif "acquisition" in all_text or "merger" in all_text:
            return f"{symbol} M&A Play"
        elif "momentum" in all_text or "breakout" in all_text:
            return f"{symbol} Momentum"
        else:
            direction = signals[0].initial_direction.capitalize()
            return f"{symbol} {direction} Thesis"

    def _generate_thesis_summary(self, signals: list[SignalProvenance]) -> str:
        """Generate a thesis summary from converging signals."""
        sources = set(s.source.value for s in signals)
        directions = [s.initial_direction for s in signals]

        direction = "bullish" if directions.count("bullish") > directions.count("bearish") else "bearish"
        source_str = ", ".join(sorted(sources))

        return f"Multiple signals ({len(signals)}) from {source_str} point to {direction} opportunity."

    def _suggest_signposts(self, symbol: str, signals: list[SignalProvenance]) -> list[dict]:
        """Suggest signposts based on signal types."""
        signposts = []

        sources = set(s.source for s in signals)

        if SignalSource.WSB in sources or SignalSource.STOCKTWITS in sources:
            signposts.append({
                "description": "Social volume peaks / declines significantly",
                "bullish_if": "Continued momentum with high engagement",
                "bearish_if": "Volume drops sharply or sentiment reverses",
            })

        if SignalSource.OPTIONS in sources:
            signposts.append({
                "description": "Options flow confirms direction",
                "bullish_if": "Call volume remains elevated",
                "bearish_if": "Put volume spikes",
            })

        if SignalSource.INSIDER in sources or SignalSource.CONGRESSIONAL in sources:
            signposts.append({
                "description": "Additional insider/institutional activity",
                "bullish_if": "More buys from insiders",
                "bearish_if": "Insider selling appears",
            })

        # Default signposts
        signposts.append({
            "description": "Price action validates thesis",
            "bullish_if": "Price breaks above resistance",
            "bearish_if": "Price breaks below support",
        })

        return signposts

    def _calculate_confidence(self, signals: list[SignalProvenance]) -> float:
        """Calculate confidence score from converging signals."""
        if not signals:
            return 0.0

        # Base score from number of signals
        count_score = min(len(signals) / 5, 1.0)  # Max at 5 signals

        # Source diversity bonus
        unique_sources = len(set(s.source for s in signals))
        diversity_score = min(unique_sources / 3, 1.0)  # Max at 3 sources

        # Weighted average confidence from signals
        total_weight = 0
        weighted_conf = 0
        for signal in signals:
            weight = self.SOURCE_WEIGHTS.get(signal.source, 1.0)
            weighted_conf += signal.current_confidence * weight
            total_weight += weight

        avg_confidence = weighted_conf / total_weight if total_weight > 0 else 0

        # Recency bonus (more recent signals = higher confidence)
        recent_count = sum(
            1 for s in signals
            if s.signal_age_days <= 3
        )
        recency_score = recent_count / len(signals)

        # Final score
        confidence = (
            count_score * 0.3 +
            diversity_score * 0.25 +
            avg_confidence * 0.3 +
            recency_score * 0.15
        )

        return min(confidence, 1.0)

    def find_convergences(self, max_age_days: int = 14) -> dict[str, list[SignalProvenance]]:
        """Find symbols with multiple converging signals."""
        # Get recent signals
        all_signals = []
        for signal in self.provenance._cache.values():
            if signal.signal_age_days <= max_age_days:
                if signal.outcome.value == "pending":  # Only active signals
                    all_signals.append(signal)

        # Group by symbol and direction
        convergences = {}
        for signal in all_signals:
            key = (signal.symbol, signal.initial_direction)
            if key not in convergences:
                convergences[key] = []
            convergences[key].append(signal)

        # Filter to those with enough signals
        result = {}
        for (symbol, direction), signals in convergences.items():
            if len(signals) >= self.MIN_SIGNALS_FOR_SUGGESTION:
                result[symbol] = signals

        return result

    def generate_suggestions(self) -> list[ThesisSuggestion]:
        """Generate thesis suggestions from current signals."""
        # Get symbols already covered
        covered_symbols = self._get_symbols_with_thesis()

        # Find convergences
        convergences = self.find_convergences()

        new_suggestions = []

        for symbol, signals in convergences.items():
            # Skip if already has thesis
            if symbol in covered_symbols:
                continue

            # Skip if already suggested and pending
            if symbol in self.suggestions:
                existing = self.suggestions[symbol]
                if existing.status == "pending":
                    continue

            # Calculate confidence
            confidence = self._calculate_confidence(signals)
            if confidence < self.MIN_CONFIDENCE:
                continue

            # Generate suggestion
            suggestion = ThesisSuggestion(
                symbol=symbol,
                suggested_name=self._generate_thesis_name(symbol, signals),
                suggested_summary=self._generate_thesis_summary(signals),
                direction=signals[0].initial_direction,  # Dominant direction
                confidence_score=confidence,
                signal_ids=[s.signal_id for s in signals],
                signal_sources=[s.source.value for s in signals],
                signal_count=len(signals),
                suggested_signposts=self._suggest_signposts(symbol, signals),
            )

            self.suggestions[symbol] = suggestion
            new_suggestions.append(suggestion)

        self._save_suggestions()
        return new_suggestions

    def get_pending_suggestions(self) -> list[ThesisSuggestion]:
        """Get suggestions awaiting action."""
        return [
            s for s in self.suggestions.values()
            if s.status == "pending"
        ]

    def accept_suggestion(self, symbol: str) -> Optional[Thesis]:
        """Accept a suggestion and create the thesis."""
        if symbol not in self.suggestions:
            return None

        suggestion = self.suggestions[symbol]
        suggestion.status = "accepted"

        # Create thesis
        thesis = self.thesis_tracker.create_thesis(
            name=suggestion.suggested_name,
            summary=suggestion.suggested_summary,
            conviction=int(suggestion.confidence_score * 100),
            signposts=suggestion.suggested_signposts,
            positions=[symbol],
        )

        # Link signals to thesis
        for signal_id in suggestion.signal_ids:
            self.provenance.link_signal_to_thesis(
                signal_id=signal_id,
                thesis_id=thesis.id,
                thesis_name=thesis.name,
                is_new_thesis=True,
            )

        self._save_suggestions()
        logger.info(f"Created thesis from suggestion: {thesis.name}")

        return thesis

    def dismiss_suggestion(self, symbol: str, reason: str = ""):
        """Dismiss a suggestion."""
        if symbol in self.suggestions:
            self.suggestions[symbol].status = "dismissed"
            self.suggestions[symbol].dismissal_reason = reason
            self._save_suggestions()

    def watch_suggestion(self, symbol: str):
        """Mark suggestion for watching (not ready for thesis yet)."""
        if symbol in self.suggestions:
            self.suggestions[symbol].status = "watched"
            self._save_suggestions()

    def generate_report(self) -> str:
        """Generate ASCII report of thesis suggestions."""
        pending = self.get_pending_suggestions()

        lines = [
            "THESIS SUGGESTIONS",
            "═" * 70,
            "",
        ]

        if not pending:
            lines.append("No pending thesis suggestions.")
            lines.append("")
            lines.append("Run generate_suggestions() to scan for convergences.")
        else:
            for suggestion in sorted(pending, key=lambda s: s.confidence_score, reverse=True):
                direction_icon = "📈" if suggestion.direction == "bullish" else "📉"

                lines.extend([
                    f"{direction_icon} {suggestion.symbol}: {suggestion.suggested_name}",
                    f"   Confidence: {suggestion.confidence_score:.0%} | Signals: {suggestion.signal_count}",
                    f"   Sources: {', '.join(set(suggestion.signal_sources))}",
                    f"   Summary: {suggestion.suggested_summary[:60]}...",
                    "",
                    "   Suggested Signposts:",
                ])

                for sp in suggestion.suggested_signposts[:2]:
                    lines.append(f"     - {sp['description']}")

                lines.extend([
                    "",
                    f"   Actions: [Accept] [Dismiss] [Watch]",
                    "─" * 50,
                    "",
                ])

        lines.extend(["", "═" * 70])
        return "\n".join(lines)


# Singleton instance
_thesis_suggester: Optional[ThesisSuggester] = None


def get_thesis_suggester() -> ThesisSuggester:
    """Get singleton instance."""
    global _thesis_suggester
    if _thesis_suggester is None:
        _thesis_suggester = ThesisSuggester()
    return _thesis_suggester


if __name__ == "__main__":
    suggester = ThesisSuggester()
    suggestions = suggester.generate_suggestions()
    print(f"Generated {len(suggestions)} new suggestions")
    print(suggester.generate_report())
