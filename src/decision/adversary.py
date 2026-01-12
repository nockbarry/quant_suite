"""Adversarial Agent - Challenges every trade before execution.

Forces comprehensive thinking by generating counter-arguments:
- Market structure concerns (who's on the other side?)
- Timing concerns (why now might be wrong)
- Thesis weaknesses (holes in the reasoning)
- Historical failures (similar setups that failed)
- Risk scenarios (worst case analysis)

Every trade should be challenged before commitment.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class AdversarialAnalysis:
    """Result of adversarial challenge to a proposed trade."""

    symbol: str
    proposed_action: str
    timestamp: datetime = field(default_factory=datetime.now)

    # Counter-arguments
    market_structure_concerns: list[str] = field(default_factory=list)
    timing_concerns: list[str] = field(default_factory=list)
    thesis_weaknesses: list[str] = field(default_factory=list)
    historical_failures: list[str] = field(default_factory=list)

    # Risk scenarios
    worst_case: str = ""
    probability_of_ruin: str = ""  # low, medium, high
    max_loss_scenario: str = ""

    # Final assessment
    proceed_recommendation: bool = True
    confidence_adjustment: float = 0.0  # Negative = reduce confidence
    conditions_for_proceed: list[str] = field(default_factory=list)

    # Summary
    overall_concern_level: str = "low"  # low, medium, high, critical
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "proposed_action": self.proposed_action,
            "timestamp": self.timestamp.isoformat(),
            "market_structure_concerns": self.market_structure_concerns,
            "timing_concerns": self.timing_concerns,
            "thesis_weaknesses": self.thesis_weaknesses,
            "historical_failures": self.historical_failures,
            "worst_case": self.worst_case,
            "probability_of_ruin": self.probability_of_ruin,
            "max_loss_scenario": self.max_loss_scenario,
            "proceed_recommendation": self.proceed_recommendation,
            "confidence_adjustment": self.confidence_adjustment,
            "conditions_for_proceed": self.conditions_for_proceed,
            "overall_concern_level": self.overall_concern_level,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AdversarialAnalysis":
        return cls(
            symbol=data["symbol"],
            proposed_action=data["proposed_action"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            market_structure_concerns=data.get("market_structure_concerns", []),
            timing_concerns=data.get("timing_concerns", []),
            thesis_weaknesses=data.get("thesis_weaknesses", []),
            historical_failures=data.get("historical_failures", []),
            worst_case=data.get("worst_case", ""),
            probability_of_ruin=data.get("probability_of_ruin", ""),
            max_loss_scenario=data.get("max_loss_scenario", ""),
            proceed_recommendation=data.get("proceed_recommendation", True),
            confidence_adjustment=data.get("confidence_adjustment", 0.0),
            conditions_for_proceed=data.get("conditions_for_proceed", []),
            overall_concern_level=data.get("overall_concern_level", "low"),
            summary=data.get("summary", ""),
        )

    def get_formatted_challenge(self) -> str:
        """Get formatted adversarial challenge for review."""
        lines = [
            f"# Adversarial Analysis: {self.symbol} {self.proposed_action}",
            "",
            f"**Concern Level:** {self.overall_concern_level.upper()}",
            f"**Recommendation:** {'PROCEED with caution' if self.proceed_recommendation else 'DO NOT PROCEED'}",
            f"**Confidence Adjustment:** {self.confidence_adjustment:+.0%}",
            "",
        ]

        if self.market_structure_concerns:
            lines.append("## Who's on the other side?")
            for c in self.market_structure_concerns:
                lines.append(f"- {c}")
            lines.append("")

        if self.timing_concerns:
            lines.append("## Why now might be wrong")
            for c in self.timing_concerns:
                lines.append(f"- {c}")
            lines.append("")

        if self.thesis_weaknesses:
            lines.append("## Thesis weaknesses")
            for c in self.thesis_weaknesses:
                lines.append(f"- {c}")
            lines.append("")

        if self.historical_failures:
            lines.append("## Similar setups that failed")
            for c in self.historical_failures:
                lines.append(f"- {c}")
            lines.append("")

        if self.worst_case:
            lines.append("## Worst case scenario")
            lines.append(self.worst_case)
            lines.append(f"**Probability of ruin:** {self.probability_of_ruin}")
            lines.append("")

        if self.conditions_for_proceed:
            lines.append("## Conditions for proceeding")
            for c in self.conditions_for_proceed:
                lines.append(f"- {c}")
            lines.append("")

        if self.summary:
            lines.append("## Summary")
            lines.append(self.summary)

        return "\n".join(lines)


class AdversarialAgent:
    """
    Generates adversarial analysis for proposed trades.

    Forces the decision-maker to consider:
    1. Market structure - who is selling to me? Why?
    2. Timing - why is now the right time?
    3. Thesis - what are the holes in my reasoning?
    4. History - what similar setups have failed?
    5. Risk - what's the worst that could happen?
    """

    # Common market structure concerns by action
    MARKET_STRUCTURE_TEMPLATES = {
        "BUY": [
            "Who is selling at this price? Are they distressed or informed?",
            "Is this stock being accumulated or distributed by institutions?",
            "Are market makers widening spreads (low conviction)?",
            "Is there unusual put activity suggesting informed selling?",
        ],
        "SELL": [
            "Who is buying at this price? FOMO retail or informed buyers?",
            "Is there institutional accumulation happening?",
            "Are short sellers covering (creating temporary demand)?",
        ],
    }

    # Common timing concerns
    TIMING_TEMPLATES = [
        "Is this FOMO after a move, or anticipation before one?",
        "Are we early (catalyst not yet confirmed) or late (already priced in)?",
        "Is there a macro event coming that could override this thesis?",
        "Is this the best risk/reward entry, or should we wait for a pullback?",
        "Is the market environment (regime) suitable for this type of trade?",
    ]

    # Historical failure patterns
    FAILURE_PATTERNS = {
        "gap_up_on_news": [
            "Gaps on news often fade 50-80% in the first hour",
            "The 'news is priced in' at market open is a common trap",
            "Smart money sells into gap euphoria",
        ],
        "earnings_play": [
            "IV crush often negates even correct directional calls",
            "Guidance matters more than the beat/miss",
            "Pre-earnings run-ups often reverse post-announcement",
        ],
        "breakout": [
            "Most breakouts fail and return to range",
            "Volume on breakout day is critical - low volume = trap",
            "Breakout in a bear market often fails",
        ],
        "mean_reversion": [
            "Oversold can get more oversold",
            "News-driven moves don't revert quickly",
            "Catching falling knives requires perfect timing",
        ],
        "momentum": [
            "Momentum can reverse violently without warning",
            "Extended stocks tend to gap down on any disappointment",
            "Late-cycle momentum is the most dangerous",
        ],
    }

    def __init__(self):
        """Initialize adversarial agent."""
        self._state_cache = None
        self._state_cache_time = None

    def _get_current_state(self) -> Optional[dict]:
        """Load current unified state for context-aware analysis."""
        from datetime import datetime
        from pathlib import Path
        import json

        # Cache state for 5 minutes
        if self._state_cache and self._state_cache_time:
            if (datetime.now() - self._state_cache_time).seconds < 300:
                return self._state_cache

        try:
            state_path = Path.home() / "quant_results" / "live" / "state.json"
            if state_path.exists():
                with open(state_path) as f:
                    self._state_cache = json.load(f)
                    self._state_cache_time = datetime.now()
                    return self._state_cache
        except Exception as e:
            logger.debug(f"Failed to load state: {e}")

        return None

    def _get_position_for_symbol(self, symbol: str) -> Optional[dict]:
        """Get current position for a symbol."""
        state = self._get_current_state()
        if not state:
            return None

        positions = state.get("positions", [])
        for pos in positions:
            if pos.get("symbol", "").upper() == symbol.upper():
                return pos
        return None

    def _get_thesis_for_symbol(self, symbol: str) -> Optional[dict]:
        """Get active thesis linked to a symbol."""
        state = self._get_current_state()
        if not state:
            return None

        theses = state.get("theses", [])
        for thesis in theses:
            if thesis.get("status") == "active":
                positions = thesis.get("positions", [])
                if symbol.upper() in [p.upper() for p in positions]:
                    return thesis
        return None

    def _calculate_concentration_impact(
        self,
        symbol: str,
        proposed_size_pct: float,
    ) -> dict:
        """Calculate how this trade affects portfolio concentration."""
        state = self._get_current_state()
        if not state:
            return {"error": "No state available"}

        portfolio = state.get("portfolio", {})
        total_equity = portfolio.get("equity", 100000)
        positions = state.get("positions", [])

        # Current position weight
        current_weight = 0.0
        for pos in positions:
            if pos.get("symbol", "").upper() == symbol.upper():
                current_weight = pos.get("market_value", 0) / total_equity * 100

        # Projected weight after trade
        projected_weight = current_weight + proposed_size_pct

        # Thesis concentration
        thesis = self._get_thesis_for_symbol(symbol)
        thesis_weight = 0.0
        if thesis:
            thesis_positions = thesis.get("positions", [])
            for pos in positions:
                if pos.get("symbol", "").upper() in [p.upper() for p in thesis_positions]:
                    thesis_weight += pos.get("market_value", 0) / total_equity * 100
            thesis_weight += proposed_size_pct

        # Sector concentration
        pos_info = self._get_position_for_symbol(symbol)
        sector = pos_info.get("sector", "Unknown") if pos_info else "Unknown"
        sector_weight = 0.0
        for pos in positions:
            if pos.get("sector", "") == sector:
                sector_weight += pos.get("market_value", 0) / total_equity * 100
        sector_weight += proposed_size_pct

        return {
            "current_position_weight": current_weight,
            "projected_position_weight": projected_weight,
            "position_limit": 15.0,
            "position_limit_breach": projected_weight > 15.0,
            "thesis_weight": thesis_weight,
            "thesis_limit": 35.0,
            "thesis_limit_breach": thesis_weight > 35.0,
            "sector_weight": sector_weight,
            "sector_limit": 40.0,
            "sector_limit_breach": sector_weight > 40.0,
            "sector": sector,
            "thesis_name": thesis.get("name") if thesis else None,
        }

    def _check_thesis_health(self, symbol: str) -> dict:
        """Check the health of the thesis linked to this symbol."""
        from datetime import datetime

        thesis = self._get_thesis_for_symbol(symbol)
        if not thesis:
            return {"has_thesis": False}

        result = {
            "has_thesis": True,
            "thesis_name": thesis.get("name"),
            "conviction": thesis.get("conviction", 50),
            "status": thesis.get("status"),
            "concerns": [],
        }

        # Check conviction level
        conviction = thesis.get("conviction", 50)
        if conviction < 50:
            result["concerns"].append(f"Low conviction ({conviction}%) - consider reducing exposure")
        elif conviction < 65:
            result["concerns"].append(f"Moderate conviction ({conviction}%) - size position accordingly")

        # Check for conviction decay
        conviction_history = thesis.get("conviction_history", [])
        if len(conviction_history) >= 2:
            recent_changes = conviction_history[-3:]
            if all(c.get("new_value", 50) <= c.get("old_value", 50) for c in recent_changes):
                result["concerns"].append("Conviction has been declining - reassess thesis")

        # Check signpost status
        signposts = thesis.get("signposts", [])
        pending_signposts = [s for s in signposts if s.get("status") == "pending"]
        triggered_signposts = [s for s in signposts if s.get("status") == "triggered"]

        if not pending_signposts and not triggered_signposts:
            result["concerns"].append("No signposts defined - thesis lacks validation criteria")

        bearish_triggers = [s for s in triggered_signposts if s.get("outcome") == "bearish"]
        if bearish_triggers:
            result["concerns"].append(f"{len(bearish_triggers)} bearish signpost(s) triggered - review thesis")

        # Check last review date
        last_review = thesis.get("last_review")
        if last_review:
            try:
                last_review_dt = datetime.fromisoformat(last_review.replace("Z", "+00:00"))
                days_since_review = (datetime.now() - last_review_dt.replace(tzinfo=None)).days
                if days_since_review > 14:
                    result["concerns"].append(f"Thesis not reviewed in {days_since_review} days")
            except Exception:
                pass

        return result

    def _generate_pre_mortem(
        self,
        symbol: str,
        action: str,
        context: Optional[dict],
    ) -> str:
        """Generate a realistic pre-mortem scenario."""
        scenarios = []

        # Get thesis context
        thesis = self._get_thesis_for_symbol(symbol)

        if action.upper() == "BUY":
            # Position-specific scenarios
            scenarios.append(f"{symbol} announces disappointing guidance in upcoming earnings")
            scenarios.append(f"Sector rotation out of {context.get('sector', 'this sector') if context else 'the sector'}")

            # Thesis-specific scenarios
            if thesis:
                invalidation = thesis.get("invalidation_triggers", [])
                if invalidation:
                    scenarios.append(f"Thesis invalidated: {invalidation[0]}")

            # Market scenarios
            scenarios.append("Macro shock (Fed hawkish pivot, geopolitical event) triggers broad selloff")
            scenarios.append("Position hits stop loss during overnight gap down")

            # Concentration scenarios
            concentration = self._calculate_concentration_impact(symbol, context.get("size_pct", 5) if context else 5)
            if concentration.get("thesis_weight", 0) > 25:
                scenarios.append(f"Thesis ({concentration.get('thesis_name')}) proves wrong, concentrated loss compounds")

        else:  # SELL
            scenarios.append(f"{symbol} announces buyout at 30% premium")
            scenarios.append("Short squeeze as shorts cover on positive catalyst")
            scenarios.append("Position rallies 20% after sale on unexpected positive news")

        return scenarios[0] if scenarios else "Unknown scenario"

    def challenge(
        self,
        symbol: str,
        proposed_action: str,
        reasoning: str,
        confidence: float,
        context: Optional[dict] = None,
        setup_type: Optional[str] = None,
    ) -> AdversarialAnalysis:
        """
        Generate adversarial analysis for a proposed trade.

        Args:
            symbol: Symbol to trade
            proposed_action: BUY, SELL, etc.
            reasoning: The reasoning for the trade
            confidence: Proposed confidence level (0-1)
            context: Optional additional context (state, signals, etc.)
            setup_type: Type of setup (breakout, mean_reversion, earnings_play, etc.)

        Returns:
            AdversarialAnalysis with challenges.
        """
        analysis = AdversarialAnalysis(
            symbol=symbol,
            proposed_action=proposed_action,
        )

        # 1. Market structure concerns (with real portfolio context)
        analysis.market_structure_concerns = self._generate_market_structure_concerns(
            proposed_action, context, symbol
        )

        # 2. Timing concerns
        analysis.timing_concerns = self._generate_timing_concerns(context)

        # 3. Thesis weaknesses (combining static analysis + real thesis health)
        analysis.thesis_weaknesses = self._analyze_thesis_weaknesses(reasoning)

        # Add real thesis health concerns
        thesis_health = self._check_thesis_health(symbol)
        if thesis_health.get("has_thesis"):
            analysis.thesis_weaknesses.extend(thesis_health.get("concerns", []))

        # 4. Historical failures
        if setup_type:
            analysis.historical_failures = self._get_historical_failures(setup_type)
        else:
            # Try to infer setup type from reasoning
            inferred_type = self._infer_setup_type(reasoning)
            if inferred_type:
                analysis.historical_failures = self._get_historical_failures(inferred_type)

        # 5. Risk scenarios (using real portfolio context for pre-mortem)
        analysis.worst_case = self._generate_pre_mortem(symbol, proposed_action, context)
        analysis.probability_of_ruin = self._assess_ruin_probability(confidence, context)
        analysis.max_loss_scenario = self._estimate_max_loss(symbol, proposed_action, context)

        # Add concentration-aware risk assessment
        if proposed_action.upper() == "BUY":
            size_pct = context.get("size_pct", 5) if context else 5
            concentration = self._calculate_concentration_impact(symbol, size_pct)
            if any([
                concentration.get("position_limit_breach"),
                concentration.get("thesis_limit_breach"),
                concentration.get("sector_limit_breach"),
            ]):
                analysis.probability_of_ruin = "high"

        # 6. Overall assessment
        analysis.overall_concern_level = self._assess_concern_level(analysis)
        analysis.confidence_adjustment = self._calculate_confidence_adjustment(analysis)
        analysis.proceed_recommendation = self._should_proceed(analysis, confidence)
        analysis.conditions_for_proceed = self._generate_conditions(analysis)

        # 7. Summary
        analysis.summary = self._generate_summary(analysis)

        return analysis

    def _generate_market_structure_concerns(
        self,
        action: str,
        context: Optional[dict],
        symbol: str = None,
    ) -> list[str]:
        """Generate market structure concerns with real portfolio context."""
        concerns = []

        # Base concerns from templates
        action_key = action.upper()
        if action_key in self.MARKET_STRUCTURE_TEMPLATES:
            concerns.extend(self.MARKET_STRUCTURE_TEMPLATES[action_key][:2])

        # Context-specific concerns
        if context:
            # Volume concerns
            if context.get("volume_ratio", 1.0) < 0.7:
                concerns.append("Volume is below average - limited participation")
            elif context.get("volume_ratio", 1.0) > 2.0:
                concerns.append("Volume spike suggests institutional activity - are you on the right side?")

            # Spread concerns
            if context.get("spread_pct", 0) > 0.5:
                concerns.append("Wide bid-ask spread suggests low liquidity or uncertainty")

            # Options flow
            if context.get("put_call_ratio", 1.0) > 1.5:
                concerns.append("Elevated put/call ratio - are puts being accumulated?")

        # Real portfolio concentration concerns
        if symbol and action_key == "BUY":
            size_pct = context.get("size_pct", 5) if context else 5
            concentration = self._calculate_concentration_impact(symbol, size_pct)

            if concentration.get("position_limit_breach"):
                concerns.append(
                    f"LIMIT BREACH: Position would be {concentration['projected_position_weight']:.1f}% "
                    f"(limit: {concentration['position_limit']}%)"
                )

            if concentration.get("thesis_limit_breach"):
                concerns.append(
                    f"LIMIT BREACH: Thesis '{concentration['thesis_name']}' would be "
                    f"{concentration['thesis_weight']:.1f}% (limit: {concentration['thesis_limit']}%)"
                )

            if concentration.get("sector_limit_breach"):
                concerns.append(
                    f"LIMIT BREACH: Sector '{concentration['sector']}' would be "
                    f"{concentration['sector_weight']:.1f}% (limit: {concentration['sector_limit']}%)"
                )

            # Warning level (approaching limits)
            if concentration.get("thesis_weight", 0) > 25 and not concentration.get("thesis_limit_breach"):
                concerns.append(
                    f"WARNING: Thesis concentration at {concentration['thesis_weight']:.1f}% - approaching 35% limit"
                )

        return concerns

    def _generate_timing_concerns(self, context: Optional[dict]) -> list[str]:
        """Generate timing concerns."""
        concerns = list(self.TIMING_TEMPLATES[:3])  # Always include base concerns

        if context:
            # Calendar concerns
            if context.get("days_to_earnings", 999) < 14:
                concerns.append(f"Earnings in {context['days_to_earnings']} days - binary event risk")

            if context.get("fed_meeting_soon"):
                concerns.append("Fed meeting approaching - macro risk")

            # Technical concerns
            if context.get("rsi", 50) > 70:
                concerns.append("RSI overbought - extended short-term")
            elif context.get("rsi", 50) < 30:
                concerns.append("RSI oversold but can stay oversold longer than expected")

            # Regime concerns
            if context.get("regime") == "risk-off":
                concerns.append("Risk-off regime - longs face headwinds")

        return concerns

    def _analyze_thesis_weaknesses(self, reasoning: str) -> list[str]:
        """Analyze the reasoning for weaknesses."""
        weaknesses = []
        reasoning_lower = reasoning.lower()

        # Check for common weak reasoning patterns
        if "everyone" in reasoning_lower or "consensus" in reasoning_lower:
            weaknesses.append("If everyone agrees, who is left to buy?")

        if "can't go down" in reasoning_lower or "guaranteed" in reasoning_lower:
            weaknesses.append("Nothing is guaranteed in markets")

        if "cheap" in reasoning_lower or "low pe" in reasoning_lower:
            weaknesses.append("Cheap stocks can stay cheap or get cheaper")

        if "should" in reasoning_lower and "news" in reasoning_lower:
            weaknesses.append("Market doesn't always react 'rationally' to news")

        if len(reasoning) < 100:
            weaknesses.append("Thesis seems underdeveloped - more analysis needed?")

        if "momentum" in reasoning_lower and "overbought" not in reasoning_lower:
            weaknesses.append("Momentum works until it doesn't - have you considered exhaustion?")

        # Default weakness
        if not weaknesses:
            weaknesses.append("What are you missing that the seller knows?")
            weaknesses.append("What would change your mind?")

        return weaknesses

    def _get_historical_failures(self, setup_type: str) -> list[str]:
        """Get historical failure patterns for setup type."""
        setup_key = setup_type.lower().replace(" ", "_")
        return self.FAILURE_PATTERNS.get(setup_key, [
            "Similar setups have failed when conviction was highest",
            "The best-looking setups sometimes fail the hardest",
        ])

    def _infer_setup_type(self, reasoning: str) -> Optional[str]:
        """Try to infer setup type from reasoning."""
        reasoning_lower = reasoning.lower()

        if "breakout" in reasoning_lower or "breaking out" in reasoning_lower:
            return "breakout"
        if "oversold" in reasoning_lower or "mean reversion" in reasoning_lower:
            return "mean_reversion"
        if "momentum" in reasoning_lower or "trend" in reasoning_lower:
            return "momentum"
        if "earnings" in reasoning_lower:
            return "earnings_play"
        if "gap" in reasoning_lower and "news" in reasoning_lower:
            return "gap_up_on_news"

        return None

    def _generate_worst_case(
        self,
        symbol: str,
        action: str,
        context: Optional[dict],
    ) -> str:
        """Generate worst case scenario."""
        if action.upper() == "BUY":
            scenarios = [
                "Company announces unexpected negative guidance revision",
                "Sector-wide selloff on macro news",
                "Key thesis assumption proves wrong",
                "Large holder liquidation creates cascade",
            ]
        else:  # SELL
            scenarios = [
                "Buyout announced at significant premium",
                "Earnings massively beat with raised guidance",
                "Short squeeze on position covering",
            ]

        # Pick relevant scenario
        scenario = scenarios[0]

        if context:
            if context.get("days_to_earnings", 999) < 14:
                scenario = "Earnings miss triggers 20%+ gap down"
            if context.get("sector") == "Energy":
                scenario = "Oil price collapse or geopolitical reversal"

        return scenario

    def _assess_ruin_probability(self, confidence: float, context: Optional[dict]) -> str:
        """Assess probability of significant loss."""
        # Higher confidence often means higher risk of overconfidence
        if confidence > 0.9:
            return "medium"  # Overconfidence is dangerous
        if confidence > 0.7:
            return "low"
        return "low"

    def _estimate_max_loss(
        self,
        symbol: str,
        action: str,
        context: Optional[dict],
    ) -> str:
        """Estimate maximum loss scenario."""
        if context and context.get("stop_loss_pct"):
            stop = context["stop_loss_pct"]
            return f"Defined risk: {stop}% if stop is hit. Gap risk could exceed this."
        return "Undefined - consider setting stop loss"

    def _assess_concern_level(self, analysis: AdversarialAnalysis) -> str:
        """Assess overall concern level."""
        total_concerns = (
            len(analysis.market_structure_concerns) +
            len(analysis.timing_concerns) +
            len(analysis.thesis_weaknesses) +
            len(analysis.historical_failures)
        )

        if total_concerns >= 10:
            return "critical"
        if total_concerns >= 7:
            return "high"
        if total_concerns >= 4:
            return "medium"
        return "low"

    def _calculate_confidence_adjustment(self, analysis: AdversarialAnalysis) -> float:
        """Calculate how much to adjust confidence."""
        level_adjustments = {
            "low": -0.05,
            "medium": -0.10,
            "high": -0.20,
            "critical": -0.35,
        }
        return level_adjustments.get(analysis.overall_concern_level, -0.10)

    def _should_proceed(self, analysis: AdversarialAnalysis, confidence: float) -> bool:
        """Determine if trade should proceed."""
        # Always reject if there are limit breaches
        limit_breach_concerns = [
            c for c in analysis.market_structure_concerns
            if "LIMIT BREACH" in c
        ]
        if limit_breach_concerns:
            return False

        if analysis.overall_concern_level == "critical":
            return False
        if analysis.overall_concern_level == "high" and confidence < 0.7:
            return False
        if analysis.probability_of_ruin == "high":
            return False
        return True

    def _generate_conditions(self, analysis: AdversarialAnalysis) -> list[str]:
        """Generate conditions for proceeding with trade."""
        conditions = []

        if analysis.overall_concern_level in ["high", "critical"]:
            conditions.append("Wait for additional confirmation")
            conditions.append("Reduce position size significantly")

        if len(analysis.timing_concerns) > 3:
            conditions.append("Consider better entry timing")

        if len(analysis.thesis_weaknesses) > 2:
            conditions.append("Strengthen thesis before committing")

        if not conditions:
            conditions.append("Proceed with defined risk (stop loss)")
            conditions.append("Monitor thesis signposts actively")

        return conditions

    def _generate_summary(self, analysis: AdversarialAnalysis) -> str:
        """Generate summary of adversarial analysis."""
        if analysis.overall_concern_level == "critical":
            return (
                f"CRITICAL CONCERNS: This trade has significant red flags. "
                f"Consider waiting or finding a better setup."
            )
        if analysis.overall_concern_level == "high":
            return (
                f"HIGH CONCERN: Multiple warning signs. Proceed only with "
                f"reduced size and strict risk management."
            )
        if analysis.overall_concern_level == "medium":
            return (
                f"MODERATE CONCERN: Some valid counter-arguments exist. "
                f"Ensure thesis is robust and risk is defined."
            )
        return (
            f"LOW CONCERN: Trade thesis appears reasonable. "
            f"Standard risk management applies."
        )
