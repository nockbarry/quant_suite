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


class RouteAction:
    """Routing decision codes for route_signal()."""
    UPDATE_CONVICTION = "update_conviction"
    ADD_TO_THESIS = "add_to_thesis"
    CREATE_NEW = "create_new"
    SKIP = "skip"


@dataclass
class RoutedSignal:
    """Outcome of route_signal() — where a fresh document signal should land."""
    signal_id: str
    symbol: str
    action: str  # one of RouteAction constants
    thesis_id: Optional[str] = None
    thesis_name: Optional[str] = None
    score: float = 0.0  # confidence in the routing decision
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "action": self.action,
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "score": self.score,
            "reason": self.reason,
        }


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

    SUGGESTIONS_PATH = paths.base / "suggestions" / "thesis_suggestions.json"
    RESEARCH_QUEUE_PATH = paths.base / "scheduler" / "research_queue.json"
    MIN_SIGNALS_FOR_SUGGESTION = 2
    MIN_CONFIDENCE = 0.5
    AUTO_CREATE_THRESHOLD = 0.75  # Min confidence for auto-creation
    MAX_AUTO_PER_WEEK = 2  # Prevent thesis sprawl

    # Exploration-thesis pathway: convert untested research-queue hypotheses
    # into small-size live positions so the 20+ backlog becomes real-money
    # discovery instead of dead docs.
    EXPLORATION_MAX_ACTIVE = 4          # Cap concurrent exploration theses
    EXPLORATION_MAX_PER_WEEK = 2        # Throttle creation rate
    EXPLORATION_CONVICTION = 40         # Low initial conviction → small size
    EXPLORATION_SIZE_PCT = 3.0          # Max position size for exploration
    EXPLORATION_MIN_PRIORITY = 0.7      # Only promote high-priority hypotheses
    EXPLORATION_AUTO_INVALIDATE_DAYS = 30

    # Source weights for confidence calculation.
    # EARNINGS_CALL (1.25): SEC 8-K item 2.02 — high quality, slight lag (3 weeks
    #   post-quarter), management's own forward guidance and quotable language.
    # INFERRED (0.6): supply chain propagation. Low weight because it's derivative
    #   evidence — convergence requires multiple distinct root_signal_ids
    #   (see find_convergences for the dedup rule).
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
        SignalSource.EARNINGS_CALL: 1.25,
        SignalSource.INFERRED: 0.6,
        SignalSource.MONTHLY_REVENUE: 1.30,  # higher than EARNINGS_CALL — much fresher (10-day reporting lag vs ~30-day for 8-K)
        SignalSource.PATENT: 1.10,  # leading indicator (~6-12mo lead) but noisy — middle weight
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
                        # Composite key (symbol_direction) to preserve
                        # opposing-direction convergences. Legacy entries
                        # without direction fall back to symbol-only.
                        key = (
                            f"{suggestion.symbol}_{suggestion.direction}"
                            if suggestion.direction
                            else suggestion.symbol
                        )
                        self.suggestions[key] = suggestion
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

    # ------------------------------------------------------------------
    # v2: route a fresh document signal to existing/related/new thesis
    # ------------------------------------------------------------------

    # Tokens we ignore in thematic matching — too generic to discriminate.
    # Expanded after the AMD-routes-to-Uranium false positive: generic
    # finance/business terms ("signals", "investments", "strategic") show up
    # in nearly every thesis and earnings text and produce spurious matches.
    _STOPWORDS = frozenset({
        "the", "a", "an", "of", "to", "in", "for", "and", "or", "with",
        "at", "by", "is", "be", "been", "are", "was", "from", "on", "as",
        "this", "that", "these", "those", "we", "our", "their", "its",
        "thesis", "play", "trade", "long", "short", "bullish", "bearish",
        "growth", "increase", "decrease", "guidance", "company", "results",
        "quarter", "fiscal", "year", "revenue", "earnings",
        # Generic finance / management speak — added 2026-04-26 after AMD →
        # Uranium misroute via "signals" coincidence.
        "signals", "signal", "investments", "investment", "strategic",
        "support", "term", "scaling", "continued", "cfo", "ceo", "management",
        "outlook", "forward", "looking",
    })
    # Min thematic-overlap score to route as ADD_TO_THESIS (vs CREATE_NEW)
    THEMATIC_MIN_SCORE = 0.15

    def route_signal(self, signal: SignalProvenance) -> RoutedSignal:
        """Decide where a fresh signal should land.

        Three outcomes (most common first):
          UPDATE_CONVICTION — symbol already in an active thesis.
            Caller should feed the signal into belief_updater to nudge conviction.
          ADD_TO_THESIS — symbol not in any thesis but thematically aligned with
            one. Caller should propose adding the symbol to that thesis (operator
            review). This is the path that absorbs most document signals — it
            avoids competing for the MAX_AUTO_PER_WEEK=2 new-thesis budget.
          CREATE_NEW — symbol unrelated to any active thesis. Falls through to
            normal generate_suggestions() pipeline (which will rate-limit).
        """
        active = self.thesis_tracker.get_active_theses()

        # 1) Symbol-direct match
        for thesis in active:
            if signal.symbol in thesis.positions:
                return RoutedSignal(
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    action=RouteAction.UPDATE_CONVICTION,
                    thesis_id=thesis.id,
                    thesis_name=thesis.name,
                    score=1.0,
                    reason=f"{signal.symbol} is already a position in '{thesis.name}'",
                )

        # 2) Thematic match against name + summary + bull_case
        signal_tokens = self._tokenize(signal.initial_description)
        if not signal_tokens:
            return RoutedSignal(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                action=RouteAction.CREATE_NEW,
                reason="Empty signal description",
            )

        scored: list[tuple[float, Thesis]] = []
        for thesis in active:
            thesis_text = " ".join([
                thesis.name or "",
                thesis.summary or "",
                thesis.bull_case or "",
            ])
            thesis_tokens = self._tokenize(thesis_text)
            if not thesis_tokens:
                continue
            score = self._jaccard(signal_tokens, thesis_tokens)
            if score >= self.THEMATIC_MIN_SCORE:
                scored.append((score, thesis))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_thesis = scored[0]
            # All current Athena theses are implicitly long/bullish. A BEARISH
            # signal that thematically matches a bullish thesis is contradictory
            # evidence — it should push the thesis conviction DOWN, not be added
            # as supporting evidence. Route to UPDATE_CONVICTION so the belief
            # updater handles it as a thesis-weakening signal.
            if signal.initial_direction == "bearish":
                return RoutedSignal(
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    action=RouteAction.UPDATE_CONVICTION,
                    thesis_id=best_thesis.id,
                    thesis_name=best_thesis.name,
                    score=best_score,
                    reason=(
                        f"Bearish signal thematically opposite to bullish thesis "
                        f"'{best_thesis.name}' (jaccard={best_score:.2f}) — "
                        f"feed to belief updater to weaken conviction"
                    ),
                )
            return RoutedSignal(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                action=RouteAction.ADD_TO_THESIS,
                thesis_id=best_thesis.id,
                thesis_name=best_thesis.name,
                score=best_score,
                reason=(
                    f"Thematic overlap (jaccard={best_score:.2f}) between signal "
                    f"and thesis '{best_thesis.name}'"
                ),
            )

        # 3) Fall through — normal new-thesis suggestion pipeline
        return RoutedSignal(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            action=RouteAction.CREATE_NEW,
            reason=f"No active thesis covers or thematically matches {signal.symbol}",
        )

    # Short technical acronyms / tickers that carry strong semantic weight
    # despite being below the normal min-length filter. Adding to this set
    # restores them as match tokens.
    _IMPORTANT_SHORT_TOKENS = frozenset({
        "ai", "ml", "5g", "6g", "vr", "ar", "ev", "ip",
        "hbm", "gpu", "cpu", "cpu", "tpu", "asic", "fpga",
        "saas", "iaas", "paas", "ott", "lng", "ree", "smr",
    })

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        """Lowercase alpha tokens, filtered against stopwords.

        Length filter is relaxed for important short acronyms ("AI", "GPU",
        "HBM", etc.) — these are high-signal tokens for semis/AI matching
        that the previous len>=4 rule silently dropped.
        """
        if not text:
            return set()
        import re
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        out = set()
        for t in tokens:
            if t in cls._STOPWORDS:
                continue
            if len(t) >= 4 or t in cls._IMPORTANT_SHORT_TOKENS:
                out.add(t)
        return out

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        """Max of Jaccard and coverage-of-smaller-set.

        Coverage handles cases where a short signal description (e.g. memory
        thematic) is fully contained in a longer thesis text — Jaccard would
        dilute the score, but coverage correctly captures the semantic match.
        Same approach used in memory_drift._match_thesis.
        """
        if not a or not b:
            return 0.0
        inter = len(a & b)
        if inter == 0:
            return 0.0
        union = len(a | b)
        jaccard = inter / union
        coverage = inter / min(len(a), len(b))
        return max(jaccard, coverage)

    # ------------------------------------------------------------------

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

    def find_convergences(
        self, max_age_days: int = 14
    ) -> dict[tuple[str, str], list[SignalProvenance]]:
        """Find converging signal groups, keyed by (symbol, direction).

        Returns a dict whose keys are tuples (symbol, direction) so that a
        symbol with BOTH bullish and bearish convergences (e.g. INTC after a
        capex pivot — earlier filings bullish, recent filing slashed guidance)
        produces TWO entries, not one overwriting the other.

        v3 INDEPENDENCE RULE: signals are deduplicated by `root_signal_id`
        before counting toward MIN_SIGNALS_FOR_SUGGESTION. A single root
        document cannot manufacture convergence via supply chain propagation.
        """
        # Get recent signals
        all_signals = []
        for signal in self.provenance._cache.values():
            if signal.signal_age_days <= max_age_days:
                if signal.outcome.value == "pending":  # Only active signals
                    all_signals.append(signal)

        # Group by (symbol, direction)
        convergences: dict[tuple[str, str], list[SignalProvenance]] = {}
        for signal in all_signals:
            key = (signal.symbol, signal.initial_direction)
            if key not in convergences:
                convergences[key] = []
            convergences[key].append(signal)

        # Filter to those with enough INDEPENDENT root signals
        result: dict[tuple[str, str], list[SignalProvenance]] = {}
        for key, signals in convergences.items():
            unique_roots = {(s.root_signal_id or s.signal_id) for s in signals}
            if len(unique_roots) >= self.MIN_SIGNALS_FOR_SUGGESTION:
                result[key] = signals

        return result

    def generate_suggestions(self) -> list[ThesisSuggestion]:
        """Generate thesis suggestions from current signals.

        Note: a symbol can produce BOTH a bullish and a bearish suggestion
        if it has convergent signals in both directions (e.g. INTC after
        a guidance pivot). The suggestion store keys these as
        f"{symbol}_{direction}" to keep them distinct.
        """
        # Get symbols already covered
        covered_symbols = self._get_symbols_with_thesis()

        # Find convergences
        convergences = self.find_convergences()

        new_suggestions = []

        for (symbol, direction), signals in convergences.items():
            # Suggestion store key — preserves direction so opposing-direction
            # convergences for the same symbol can both produce suggestions.
            sugg_key = f"{symbol}_{direction}"

            # Skip if symbol already has an active thesis covering it AND
            # the existing thesis direction matches this convergence (we
            # don't want to suggest a redundant thesis for already-covered
            # bullish positions, but a CONFLICTING bearish convergence on
            # the same symbol IS worth surfacing — the operator should see it).
            if symbol in covered_symbols and direction == "bullish":
                # TODO: check thesis direction; for now assume covered =
                # already-bullish (true for current portfolio)
                continue

            # Skip if already suggested and pending
            if sugg_key in self.suggestions:
                existing = self.suggestions[sugg_key]
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

            self.suggestions[sugg_key] = suggestion
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
            bull_case=f"Auto-suggested: {suggestion.signal_count} converging {suggestion.direction} signals from {', '.join(set(suggestion.signal_sources))}",
            bear_case="Signals may be transient or already priced in",
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

    def auto_create_from_suggestions(self) -> list:
        """Auto-create theses from high-confidence suggestions.

        Gates:
        - confidence_score >= AUTO_CREATE_THRESHOLD (0.75)
        - Max 2 auto-created per week
        - No similar thesis already exists (fuzzy name match)

        Returns list of created Thesis objects.
        """
        recent_auto = self._count_recent_auto_created(days=7)
        if recent_auto >= self.MAX_AUTO_PER_WEEK:
            logger.info(
                f"Auto-create skipped: {recent_auto} already created this week "
                f"(max {self.MAX_AUTO_PER_WEEK})"
            )
            return []

        suggestions = self.get_pending_suggestions()
        created = []

        for suggestion in sorted(
            suggestions, key=lambda s: s.confidence_score, reverse=True
        ):
            if suggestion.confidence_score < self.AUTO_CREATE_THRESHOLD:
                continue

            if self._similar_thesis_exists(suggestion.suggested_name):
                logger.info(
                    f"Auto-create skipped for '{suggestion.suggested_name}': "
                    f"similar thesis already exists"
                )
                continue

            # Create the thesis
            thesis = self.accept_suggestion(suggestion.symbol)
            if thesis:
                self._log_auto_creation(thesis, suggestion)
                created.append(thesis)
                logger.info(
                    f"Auto-created thesis: {thesis.name} "
                    f"(confidence={suggestion.confidence_score:.0%})"
                )

                if len(created) + recent_auto >= self.MAX_AUTO_PER_WEEK:
                    break

        return created

    # ---------------------- Exploration thesis pathway ----------------------

    def _load_research_queue(self) -> list[dict]:
        """Load research queue JSON (list of hypothesis/check items)."""
        if not self.RESEARCH_QUEUE_PATH.exists():
            return []
        try:
            with open(self.RESEARCH_QUEUE_PATH) as f:
                data = json.load(f)
            return data if isinstance(data, list) else data.get("queue", [])
        except Exception as e:
            logger.warning(f"Could not load research queue: {e}")
            return []

    def _save_research_queue(self, queue: list[dict]):
        """Persist research queue after marking items promoted."""
        try:
            with open(self.RESEARCH_QUEUE_PATH, "w") as f:
                json.dump(queue, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save research queue: {e}")

    @staticmethod
    def _is_exploration(t) -> bool:
        return (t.name or "").startswith("[EXP] ")

    @staticmethod
    def _exploration_notes_tag(notes) -> str:
        """Extract an exploration tag line from a thesis' notes list."""
        if not notes:
            return ""
        if isinstance(notes, str):
            return notes if notes.startswith("[exploration]") else ""
        for n in notes:
            if isinstance(n, str) and n.startswith("[exploration]"):
                return n
        return ""

    def _count_active_exploration(self) -> int:
        """Count exploration theses still active."""
        return sum(1 for t in self.thesis_tracker.get_active_theses() if self._is_exploration(t))

    def _count_recent_exploration(self, days: int = 7) -> int:
        """Count exploration theses created in recent days."""
        cutoff = datetime.now() - timedelta(days=days)
        count = 0
        for t in self.thesis_tracker.get_active_theses():
            if self._is_exploration(t) and t.created and t.created > cutoff:
                count += 1
        return count

    def promote_hypotheses_to_exploration(self, max_new: Optional[int] = None) -> list:
        """Convert high-priority untested research-queue hypotheses into small
        exploration theses sized at EXPLORATION_SIZE_PCT.

        Gates:
        - Hypothesis must have at least one symbol in `symbols`
        - Priority ≥ EXPLORATION_MIN_PRIORITY
        - Hypothesis status in {pending, untested, queued} and not tested
        - No duplicate by symbol across active theses
        - Respects EXPLORATION_MAX_ACTIVE and EXPLORATION_MAX_PER_WEEK

        Returns: list of created Thesis objects.
        """
        queue = self._load_research_queue()
        if not queue:
            return []

        active_count = self._count_active_exploration()
        recent_count = self._count_recent_exploration(days=7)
        slots_by_active = max(0, self.EXPLORATION_MAX_ACTIVE - active_count)
        slots_by_week = max(0, self.EXPLORATION_MAX_PER_WEEK - recent_count)
        slots = min(slots_by_active, slots_by_week)
        if max_new is not None:
            slots = min(slots, max_new)
        if slots <= 0:
            logger.info(
                f"Exploration promotion skipped: active={active_count}, "
                f"recent={recent_count}, no slots"
            )
            return []

        covered_symbols = self._get_symbols_with_thesis()

        # Candidates: pending/untested, priority >= threshold, has symbol
        candidates = []
        for item in queue:
            status = item.get("status", "pending")
            if item.get("tested") or status == "completed":
                continue
            if status not in ("pending", "untested", "queued"):
                continue
            pri = item.get("priority", 0)
            try:
                pri = float(pri)
            except (TypeError, ValueError):
                continue
            if pri < self.EXPLORATION_MIN_PRIORITY:
                continue
            symbols = item.get("symbols") or []
            if not symbols or not isinstance(symbols, list):
                continue
            # First symbol not already in a thesis
            sym = next((s for s in symbols if s and s not in covered_symbols), None)
            if not sym:
                continue
            candidates.append((pri, sym, item))

        candidates.sort(key=lambda x: -x[0])

        created = []
        for pri, sym, item in candidates[:slots]:
            try:
                desc = item.get("description", "")[:200]
                expiry = (datetime.now() + timedelta(days=self.EXPLORATION_AUTO_INVALIDATE_DAYS)).strftime("%Y-%m-%d")
                thesis = self.thesis_tracker.create_thesis(
                    name=f"[EXP] {sym} — {desc[:60]}",
                    summary=f"Exploration thesis from research queue hypothesis {item.get('id', '?')}. "
                            f"Auto-invalidates {expiry} if no signpost triggers.",
                    bull_case=f"Research hypothesis (priority {pri:.2f}): {desc}",
                    bear_case="Unvalidated — may be noise. Capped at 3% size to limit downside.",
                    conviction=self.EXPLORATION_CONVICTION,
                    signposts=[{
                        "description": f"Hypothesis validated or invalidated by {expiry}",
                        "bullish_if": "Backtest or observed returns confirm hypothesis",
                        "bearish_if": "Backtest rejects or 30 days pass without signal",
                        "target_date": expiry,
                    }],
                    invalidation_triggers=[
                        f"30 days elapsed without hypothesis validation (auto-invalidate {expiry})",
                        "Hypothesis test returns null/negative result",
                    ],
                    positions=[sym],
                    review_interval_days=7,
                )
                # Tag as exploration via notes list (Thesis.notes is list[str])
                tag = f"[exploration] queue_id={item.get('id', '')} priority={pri:.2f} expires={expiry}"
                if isinstance(thesis.notes, list):
                    thesis.notes.append(tag)
                else:
                    thesis.notes = [tag]
                self.thesis_tracker._save_thesis(thesis)

                # Mark the queue item as promoted so we don't re-create
                item["status"] = "promoted_to_exploration"
                item["promoted_thesis_id"] = thesis.id
                item["promoted_at"] = datetime.now().isoformat()

                # Audit log
                log_file = paths.base / "logs" / "auto_thesis_creation.jsonl"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(log_file, "a") as f:
                    f.write(json.dumps({
                        "event": "exploration_thesis_created",
                        "timestamp": datetime.now().isoformat(),
                        "thesis_id": thesis.id,
                        "thesis_name": thesis.name,
                        "symbol": sym,
                        "priority": pri,
                        "hypothesis_id": item.get("id", ""),
                        "size_cap_pct": self.EXPLORATION_SIZE_PCT,
                    }) + "\n")

                logger.info(
                    f"Exploration thesis created: {thesis.name} "
                    f"(sym={sym}, priority={pri:.2f}, size_cap={self.EXPLORATION_SIZE_PCT}%)"
                )
                created.append(thesis)
            except Exception as e:
                logger.warning(f"Failed to promote hypothesis {item.get('id')}: {e}")

        if created:
            self._save_research_queue(queue)
        return created

    def invalidate_expired_exploration(self) -> list:
        """Auto-invalidate exploration theses past their 30-day window."""
        invalidated = []
        now = datetime.now()
        for t in self.thesis_tracker.get_active_theses():
            if not self._is_exploration(t):
                continue
            tag = self._exploration_notes_tag(getattr(t, "notes", None))
            # Parse expires=YYYY-MM-DD from the tag line
            expires = None
            for token in tag.split():
                if token.startswith("expires="):
                    try:
                        expires = datetime.strptime(token.split("=", 1)[1], "%Y-%m-%d")
                    except ValueError:
                        pass
            if expires is None or expires > now:
                continue
            t.status = "invalidated"
            t.conviction = 0
            self.thesis_tracker._save_thesis(t)
            invalidated.append(t)
            logger.info(f"Exploration thesis auto-invalidated (expired): {t.name}")
        return invalidated

    def _similar_thesis_exists(self, name: str) -> bool:
        """Check if a thesis with similar name already exists using token overlap."""
        if not name:
            return False
        name_tokens = set(name.lower().split())
        # Remove common words
        stop_words = {
            "the", "a", "an", "in", "on", "at", "to", "for",
            "of", "and", "or", "is", "are",
        }
        name_tokens -= stop_words

        if not name_tokens:
            return False

        for thesis in self.thesis_tracker.get_active_theses():
            thesis_tokens = set(thesis.name.lower().split()) - stop_words
            if not thesis_tokens:
                continue
            # Jaccard similarity
            overlap = len(name_tokens & thesis_tokens)
            union = len(name_tokens | thesis_tokens)
            if union > 0 and overlap / union > 0.5:
                return True
        return False

    def _count_recent_auto_created(self, days: int = 7) -> int:
        """Count auto-created theses in recent days by reading the auto-creation log."""
        cutoff = datetime.now() - timedelta(days=days)
        log_file = paths.base / "logs" / "auto_thesis_creation.jsonl"
        if not log_file.exists():
            return 0

        count = 0
        try:
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry["timestamp"])
                        if ts > cutoff:
                            count += 1
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.warning(f"Could not read auto-creation log: {e}")
        return count

    def _log_auto_creation(self, thesis, suggestion):
        """Log auto-creation as a process event."""
        log_entry = {
            "event": "thesis_auto_created",
            "timestamp": datetime.now().isoformat(),
            "thesis_id": thesis.id,
            "thesis_name": thesis.name,
            "suggestion_symbol": suggestion.symbol,
            "suggestion_confidence": suggestion.confidence_score,
            "sources": suggestion.signal_sources[:5] if suggestion.signal_sources else [],
        }

        log_file = paths.base / "logs" / "auto_thesis_creation.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

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
