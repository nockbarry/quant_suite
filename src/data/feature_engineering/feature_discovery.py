"""Automated feature discovery engine.

Proposes new features based on:
- Domain knowledge and patterns
- Successful strategy analysis
- Academic literature inspiration
- Gap analysis of current features
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FeatureDomain(Enum):
    """Feature domain categories."""

    PRICE_ACTION = "price_action"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    MOMENTUM = "momentum"
    SENTIMENT = "sentiment"
    MACRO = "macro"
    ALTERNATIVE = "alternative"
    CROSS_ASSET = "cross_asset"
    SEASONAL = "seasonal"
    OPTIONS = "options"
    FLOW = "flow"


@dataclass
class FeatureIdea:
    """A proposed feature idea."""

    name: str
    domain: FeatureDomain
    description: str
    rationale: str
    formula: str | None = None
    data_requirements: list[str] = field(default_factory=list)
    priority: float = 0.5  # 0-1 priority score
    source: str = "discovery"  # 'discovery', 'literature', 'success_analysis'
    tested: bool = False
    ic_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "domain": self.domain.value,
            "description": self.description,
            "rationale": self.rationale,
            "formula": self.formula,
            "data_requirements": self.data_requirements,
            "priority": self.priority,
            "source": self.source,
            "tested": self.tested,
            "ic_score": self.ic_score,
            **self.metadata,
        }


@dataclass
class FeatureGap:
    """Identified gap in feature coverage."""

    domain: FeatureDomain
    gap_description: str
    current_count: int
    suggested_features: list[str]
    priority: float


class FeatureDiscoveryEngine:
    """
    Automated feature discovery engine.

    Proposes new features through:
    - Domain-specific pattern templates
    - Academic literature inspiration
    - Analysis of successful strategies
    - Gap analysis of current feature set
    """

    # Domain-specific feature templates
    DOMAIN_TEMPLATES = {
        FeatureDomain.PRICE_ACTION: [
            FeatureIdea(
                name="price_range_ratio",
                domain=FeatureDomain.PRICE_ACTION,
                description="Ratio of today's range to N-day average range",
                rationale="Wide range days often indicate breakouts or reversals",
                formula="(high - low) / rolling_mean(high - low, N)",
                data_requirements=["high", "low"],
            ),
            FeatureIdea(
                name="close_location_value",
                domain=FeatureDomain.PRICE_ACTION,
                description="Where close is within the day's range (0-1)",
                rationale="Close near high is bullish, near low is bearish",
                formula="(close - low) / (high - low)",
                data_requirements=["open", "high", "low", "close"],
            ),
            FeatureIdea(
                name="gap_and_go",
                domain=FeatureDomain.PRICE_ACTION,
                description="Gap followed by continuation in same direction",
                rationale="Gaps often indicate institutional activity",
                formula="sign(open - prev_close) * (close - open) / atr",
                data_requirements=["open", "high", "low", "close"],
            ),
            FeatureIdea(
                name="doji_pattern",
                domain=FeatureDomain.PRICE_ACTION,
                description="Doji candlestick pattern indicator",
                rationale="Dojis indicate indecision, often precede reversals",
                formula="abs(close - open) / (high - low + 1e-8)",
                data_requirements=["open", "high", "low", "close"],
            ),
        ],
        FeatureDomain.VOLUME: [
            FeatureIdea(
                name="volume_price_trend",
                domain=FeatureDomain.VOLUME,
                description="Cumulative volume weighted by price change",
                rationale="Strong volume on up days vs down days",
                formula="cumsum(volume * sign(close - prev_close))",
                data_requirements=["close", "volume"],
            ),
            FeatureIdea(
                name="relative_volume_profile",
                domain=FeatureDomain.VOLUME,
                description="Volume relative to same time-of-day average",
                rationale="Unusual intraday volume patterns",
                formula="volume / rolling_mean_by_time(volume)",
                data_requirements=["volume", "timestamp"],
            ),
            FeatureIdea(
                name="volume_breakout",
                domain=FeatureDomain.VOLUME,
                description="Volume exceeds N standard deviations",
                rationale="Volume spikes often precede price moves",
                formula="(volume - mean) / std > threshold",
                data_requirements=["volume"],
            ),
        ],
        FeatureDomain.VOLATILITY: [
            FeatureIdea(
                name="volatility_regime",
                domain=FeatureDomain.VOLATILITY,
                description="Current volatility vs long-term average",
                rationale="Mean reversion in volatility",
                formula="rolling_std(returns, 20) / rolling_std(returns, 100)",
                data_requirements=["close"],
            ),
            FeatureIdea(
                name="garman_klass_volatility",
                domain=FeatureDomain.VOLATILITY,
                description="More efficient volatility estimator using OHLC",
                rationale="Better than close-to-close volatility",
                formula="sqrt(0.5 * log(H/L)^2 - (2*log(2)-1) * log(C/O)^2)",
                data_requirements=["open", "high", "low", "close"],
            ),
            FeatureIdea(
                name="volatility_of_volatility",
                domain=FeatureDomain.VOLATILITY,
                description="Rolling std of rolling volatility",
                rationale="Captures regime change dynamics",
                formula="rolling_std(rolling_std(returns, 20), 60)",
                data_requirements=["close"],
            ),
        ],
        FeatureDomain.MOMENTUM: [
            FeatureIdea(
                name="acceleration",
                domain=FeatureDomain.MOMENTUM,
                description="Change in momentum (2nd derivative)",
                rationale="Acceleration/deceleration of price trends",
                formula="momentum(T) - momentum(T-N)",
                data_requirements=["close"],
            ),
            FeatureIdea(
                name="multi_timeframe_momentum",
                domain=FeatureDomain.MOMENTUM,
                description="Momentum alignment across timeframes",
                rationale="Strong trends align across timeframes",
                formula="sign(mom_5) + sign(mom_20) + sign(mom_60)",
                data_requirements=["close"],
            ),
            FeatureIdea(
                name="mean_reversion_score",
                domain=FeatureDomain.MOMENTUM,
                description="Distance from mean normalized by vol",
                rationale="Extreme deviations tend to revert",
                formula="(price - sma) / (N * std)",
                data_requirements=["close"],
            ),
        ],
        FeatureDomain.SENTIMENT: [
            FeatureIdea(
                name="sentiment_momentum",
                domain=FeatureDomain.SENTIMENT,
                description="Change in sentiment over time",
                rationale="Improving/deteriorating sentiment matters",
                formula="sentiment(T) - sentiment(T-N)",
                data_requirements=["news_data"],
            ),
            FeatureIdea(
                name="sentiment_price_divergence",
                domain=FeatureDomain.SENTIMENT,
                description="Price moves opposite to sentiment",
                rationale="Divergences can signal reversals",
                formula="sign(price_change) != sign(sentiment)",
                data_requirements=["close", "news_data"],
            ),
            FeatureIdea(
                name="news_volume_interaction",
                domain=FeatureDomain.SENTIMENT,
                description="Sentiment impact weighted by volume",
                rationale="High volume validates sentiment signals",
                formula="sentiment * volume_zscore",
                data_requirements=["news_data", "volume"],
            ),
        ],
        FeatureDomain.CROSS_ASSET: [
            FeatureIdea(
                name="sector_relative_strength",
                domain=FeatureDomain.CROSS_ASSET,
                description="Stock performance vs sector ETF",
                rationale="Outperformers tend to continue outperforming",
                formula="stock_return - sector_etf_return",
                data_requirements=["close", "sector_etf_close"],
            ),
            FeatureIdea(
                name="beta_adjusted_momentum",
                domain=FeatureDomain.CROSS_ASSET,
                description="Momentum adjusted for market beta",
                rationale="Alpha generation vs pure beta",
                formula="return - beta * market_return",
                data_requirements=["close", "market_close"],
            ),
            FeatureIdea(
                name="correlation_breakdown",
                domain=FeatureDomain.CROSS_ASSET,
                description="Rolling correlation with SPY breaking down",
                rationale="Decorrelation events can be significant",
                formula="rolling_corr(stock, SPY, 20) - rolling_corr(stock, SPY, 60)",
                data_requirements=["close", "spy_close"],
            ),
        ],
        FeatureDomain.SEASONAL: [
            FeatureIdea(
                name="month_of_year_effect",
                domain=FeatureDomain.SEASONAL,
                description="Historical performance in current month",
                rationale="Sell in May, January effect, etc.",
                formula="avg_return_by_month[current_month]",
                data_requirements=["close", "date"],
            ),
            FeatureIdea(
                name="earnings_proximity",
                domain=FeatureDomain.SEASONAL,
                description="Days until next earnings announcement",
                rationale="Pre-earnings drift, post-earnings momentum",
                formula="days_until_earnings",
                data_requirements=["earnings_dates"],
            ),
            FeatureIdea(
                name="quarter_end_effect",
                domain=FeatureDomain.SEASONAL,
                description="Proximity to quarter end (window dressing)",
                rationale="Institutional rebalancing at quarter end",
                formula="days_until_quarter_end / 90",
                data_requirements=["date"],
            ),
        ],
        FeatureDomain.OPTIONS: [
            FeatureIdea(
                name="put_call_skew",
                domain=FeatureDomain.OPTIONS,
                description="Implied vol difference between puts and calls",
                rationale="Skew indicates directional hedging",
                formula="put_iv - call_iv",
                data_requirements=["options_data"],
            ),
            FeatureIdea(
                name="gamma_exposure",
                domain=FeatureDomain.OPTIONS,
                description="Dealer gamma at current price level",
                rationale="Gamma hedging amplifies or dampens moves",
                formula="sum(open_interest * gamma)",
                data_requirements=["options_data"],
            ),
        ],
        FeatureDomain.FLOW: [
            FeatureIdea(
                name="smart_money_indicator",
                domain=FeatureDomain.FLOW,
                description="Last hour vs first hour performance",
                rationale="Smart money trades at close",
                formula="last_hour_return - first_hour_return",
                data_requirements=["intraday_close"],
            ),
            FeatureIdea(
                name="block_trade_ratio",
                domain=FeatureDomain.FLOW,
                description="Ratio of large trades to small trades",
                rationale="Institutional vs retail activity",
                formula="large_trade_volume / small_trade_volume",
                data_requirements=["trade_data"],
            ),
        ],
        FeatureDomain.ALTERNATIVE: [
            FeatureIdea(
                name="google_trends_zscore",
                domain=FeatureDomain.ALTERNATIVE,
                description="Search volume z-score relative to 90-day average",
                rationale="Retail attention spikes often precede moves",
                formula="(search_volume - mean_90d) / std_90d",
                data_requirements=["google_trends"],
            ),
            FeatureIdea(
                name="short_interest_change",
                domain=FeatureDomain.ALTERNATIVE,
                description="Week-over-week change in short interest",
                rationale="Rising shorts can indicate smart money bearishness or squeeze setup",
                formula="short_interest(t) / short_interest(t-5) - 1",
                data_requirements=["short_interest"],
            ),
            FeatureIdea(
                name="short_squeeze_potential",
                domain=FeatureDomain.ALTERNATIVE,
                description="Composite score for squeeze candidates",
                rationale="High short interest + rising price = potential squeeze",
                formula="short_pct_float * days_to_cover * momentum_5d",
                data_requirements=["short_interest", "close", "volume"],
            ),
            FeatureIdea(
                name="insider_buy_sell_ratio",
                domain=FeatureDomain.ALTERNATIVE,
                description="Ratio of insider buys to sells over past 30 days",
                rationale="Insiders often buy before positive news",
                formula="insider_buys_30d / (insider_sells_30d + 1)",
                data_requirements=["insider_transactions"],
            ),
            FeatureIdea(
                name="finbert_sentiment_momentum",
                domain=FeatureDomain.ALTERNATIVE,
                description="Change in FinBERT sentiment over past week",
                rationale="Improving sentiment often leads price",
                formula="finbert_sentiment(t) - finbert_sentiment(t-5)",
                data_requirements=["news_data", "finbert_model"],
            ),
            FeatureIdea(
                name="earnings_call_uncertainty",
                domain=FeatureDomain.ALTERNATIVE,
                description="Uncertainty word frequency in latest earnings call",
                rationale="High uncertainty language predicts volatility",
                formula="count(uncertainty_words) / total_words",
                data_requirements=["earnings_transcripts"],
            ),
            FeatureIdea(
                name="patent_filing_momentum",
                domain=FeatureDomain.ALTERNATIVE,
                description="Recent patent filings relative to 1-year average",
                rationale="Innovation activity can precede growth",
                formula="patents_90d / patents_365d_avg",
                data_requirements=["patent_data"],
            ),
            FeatureIdea(
                name="hiring_velocity",
                domain=FeatureDomain.ALTERNATIVE,
                description="Change in job postings over past month",
                rationale="Hiring growth signals business expansion",
                formula="job_postings(t) / job_postings(t-30) - 1",
                data_requirements=["job_postings"],
            ),
        ],
    }

    # Literature-inspired features
    LITERATURE_FEATURES = [
        FeatureIdea(
            name="fama_french_momentum",
            domain=FeatureDomain.MOMENTUM,
            description="12-1 month momentum (Jegadeesh & Titman)",
            rationale="Academic momentum factor",
            formula="return(t-12, t-1)",
            data_requirements=["close"],
            source="literature",
            metadata={"paper": "Jegadeesh & Titman 1993"},
        ),
        FeatureIdea(
            name="short_term_reversal",
            domain=FeatureDomain.MOMENTUM,
            description="1-week reversal factor",
            rationale="Short-term mean reversion",
            formula="-return(t-5, t)",
            data_requirements=["close"],
            source="literature",
            metadata={"paper": "Lehmann 1990"},
        ),
        FeatureIdea(
            name="idiosyncratic_volatility",
            domain=FeatureDomain.VOLATILITY,
            description="Residual volatility after removing market beta",
            rationale="Low IVOL anomaly",
            formula="std(return - beta * market_return)",
            data_requirements=["close", "market_close"],
            source="literature",
            metadata={"paper": "Ang et al. 2006"},
        ),
        FeatureIdea(
            name="betting_against_beta",
            domain=FeatureDomain.CROSS_ASSET,
            description="Long low-beta, short high-beta",
            rationale="BAB factor",
            formula="1 / beta",
            data_requirements=["close", "market_close"],
            source="literature",
            metadata={"paper": "Frazzini & Pedersen 2014"},
        ),
        FeatureIdea(
            name="max_return",
            domain=FeatureDomain.PRICE_ACTION,
            description="Maximum daily return in past month",
            rationale="Lottery stock effect",
            formula="max(daily_returns, 20)",
            data_requirements=["close"],
            source="literature",
            metadata={"paper": "Bali et al. 2011"},
        ),
    ]

    def __init__(
        self,
        existing_features: list[str] | None = None,
    ):
        """
        Initialize feature discovery engine.

        Args:
            existing_features: List of already implemented features
        """
        self.existing_features = set(existing_features or [])
        self.proposed_features: list[FeatureIdea] = []
        self.tested_features: dict[str, float] = {}  # name -> IC score

    def discover_from_domain(
        self,
        domain: FeatureDomain,
    ) -> list[FeatureIdea]:
        """
        Get feature ideas for a specific domain.

        Args:
            domain: Feature domain to explore

        Returns:
            List of feature ideas
        """
        templates = self.DOMAIN_TEMPLATES.get(domain, [])

        # Filter out already implemented features
        new_ideas = [
            idea for idea in templates
            if idea.name not in self.existing_features
        ]

        self.proposed_features.extend(new_ideas)
        return new_ideas

    def discover_from_literature(self) -> list[FeatureIdea]:
        """
        Get academically-inspired feature ideas.

        Returns:
            List of literature-based feature ideas
        """
        new_ideas = [
            idea for idea in self.LITERATURE_FEATURES
            if idea.name not in self.existing_features
        ]

        self.proposed_features.extend(new_ideas)
        return new_ideas

    def discover_from_successes(
        self,
        successful_strategies: list[dict[str, Any]],
    ) -> list[FeatureIdea]:
        """
        Generate feature ideas based on successful strategies.

        Args:
            successful_strategies: List of strategy results with features used

        Returns:
            List of feature ideas inspired by successes
        """
        ideas = []

        # Analyze what features successful strategies use
        feature_counts = {}
        for strategy in successful_strategies:
            features_used = strategy.get("features", [])
            for feature in features_used:
                feature_counts[feature] = feature_counts.get(feature, 0) + 1

        # Create variations of successful features
        for feature, count in sorted(feature_counts.items(), key=lambda x: -x[1]):
            # Propose variations
            variations = [
                f"{feature}_lag5",
                f"{feature}_momentum",
                f"{feature}_zscore",
            ]

            for var in variations:
                if var not in self.existing_features:
                    ideas.append(FeatureIdea(
                        name=var,
                        domain=FeatureDomain.MOMENTUM,  # Generic
                        description=f"Variation of successful feature {feature}",
                        rationale=f"Based on {count} successful strategies using {feature}",
                        formula=f"transformation({feature})",
                        priority=min(1.0, count / 5),
                        source="success_analysis",
                    ))

        self.proposed_features.extend(ideas)
        return ideas

    def analyze_gaps(
        self,
        current_features: dict[str, FeatureDomain],
    ) -> list[FeatureGap]:
        """
        Analyze gaps in current feature coverage.

        Args:
            current_features: Dict of feature_name -> domain

        Returns:
            List of identified gaps
        """
        # Count features per domain
        domain_counts = {}
        for domain in FeatureDomain:
            domain_counts[domain] = 0

        for name, domain in current_features.items():
            if domain in domain_counts:
                domain_counts[domain] += 1

        # Identify underrepresented domains
        gaps = []
        total = sum(domain_counts.values())
        avg_per_domain = total / len(FeatureDomain) if len(FeatureDomain) > 0 else 0

        for domain, count in domain_counts.items():
            if count < avg_per_domain * 0.5:
                # This domain is underrepresented
                templates = self.DOMAIN_TEMPLATES.get(domain, [])
                suggested = [t.name for t in templates[:3]]

                gaps.append(FeatureGap(
                    domain=domain,
                    gap_description=f"{domain.value} has only {count} features, below average of {avg_per_domain:.1f}",
                    current_count=count,
                    suggested_features=suggested,
                    priority=1.0 - (count / max(1, avg_per_domain)),
                ))

        # Sort by priority
        gaps.sort(key=lambda x: -x.priority)

        return gaps

    def rank_by_novelty(
        self,
        ideas: list[FeatureIdea],
        embeddings: np.ndarray | None = None,
        existing_embeddings: np.ndarray | None = None,
    ) -> list[FeatureIdea]:
        """
        Rank feature ideas by novelty using embeddings.

        Args:
            ideas: Feature ideas to rank
            embeddings: Embeddings for new ideas (optional)
            existing_embeddings: Embeddings for existing features (optional)

        Returns:
            Ranked list of ideas (most novel first)
        """
        if embeddings is None or existing_embeddings is None:
            # Without embeddings, use simple domain diversity
            domain_counts = {}
            for feature in self.existing_features:
                domain = FeatureDomain.PRICE_ACTION  # Default
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            # Prioritize underrepresented domains
            for idea in ideas:
                count = domain_counts.get(idea.domain, 0)
                idea.priority = 1.0 / (1 + count)

        else:
            # Use cosine distance to existing features
            from sklearn.metrics.pairwise import cosine_similarity

            for i, idea in enumerate(ideas):
                if i < len(embeddings):
                    # Find minimum similarity to existing features
                    sims = cosine_similarity([embeddings[i]], existing_embeddings)[0]
                    min_sim = sims.min() if len(sims) > 0 else 0
                    idea.priority = 1.0 - min_sim  # Higher priority for lower similarity

        # Sort by priority
        ideas.sort(key=lambda x: -x.priority)
        return ideas

    def generate_discovery_report(self) -> dict[str, Any]:
        """
        Generate a comprehensive discovery report.

        Returns:
            Dictionary with discovery summary
        """
        # Collect all ideas
        all_ideas = []
        for domain in FeatureDomain:
            all_ideas.extend(self.discover_from_domain(domain))
        all_ideas.extend(self.discover_from_literature())

        # Deduplicate
        seen = set()
        unique_ideas = []
        for idea in all_ideas:
            if idea.name not in seen:
                seen.add(idea.name)
                unique_ideas.append(idea)

        # Group by domain
        by_domain = {}
        for idea in unique_ideas:
            domain_name = idea.domain.value
            if domain_name not in by_domain:
                by_domain[domain_name] = []
            by_domain[domain_name].append(idea.to_dict())

        return {
            "generated_at": datetime.now().isoformat(),
            "total_ideas": len(unique_ideas),
            "by_domain": by_domain,
            "top_10_by_priority": [
                idea.to_dict()
                for idea in sorted(unique_ideas, key=lambda x: -x.priority)[:10]
            ],
            "existing_features_count": len(self.existing_features),
        }


def suggest_features_for_symbol(
    symbol: str,
    sector: str | None = None,
) -> list[FeatureIdea]:
    """
    Suggest features tailored for a specific symbol.

    Args:
        symbol: Stock symbol
        sector: Sector classification

    Returns:
        List of relevant feature ideas
    """
    ideas = []

    # High volatility stocks
    if symbol in ["TSLA", "NVDA", "AMD", "GME", "AMC"]:
        ideas.append(FeatureIdea(
            name="intraday_volatility_ratio",
            domain=FeatureDomain.VOLATILITY,
            description="Intraday vol vs overnight vol",
            rationale=f"{symbol} has high intraday swings",
            formula="(high-low)/(open-prev_close)",
            data_requirements=["open", "high", "low", "close"],
        ))

    # Sector-specific
    if sector == "Technology":
        ideas.append(FeatureIdea(
            name="tech_momentum_spread",
            domain=FeatureDomain.CROSS_ASSET,
            description="Stock momentum vs QQQ momentum",
            rationale="Tech stocks co-move with sector",
            formula="stock_mom - qqq_mom",
            data_requirements=["close", "qqq_close"],
        ))

    # ETFs
    if symbol in ["SPY", "QQQ", "IWM", "DIA"]:
        ideas.append(FeatureIdea(
            name="etf_premium_discount",
            domain=FeatureDomain.PRICE_ACTION,
            description="ETF trading above/below NAV",
            rationale="Arbitrage opportunities",
            formula="price - nav",
            data_requirements=["close", "nav"],
        ))

    return ideas
