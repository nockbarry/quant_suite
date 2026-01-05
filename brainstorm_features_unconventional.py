#!/usr/bin/env python3
"""
Feature Engineering Brainstorm: Unconventional Features for Alpha Discovery

Goes beyond traditional technical indicators to identify overlooked feature domains
that could drive predictive signals.
"""

import sys
sys.path.insert(0, "/home/nock/projects/quant_suite")

from src.data.feature_engineering.feature_discovery import FeatureDomain, FeatureIdea
from workflows.research.session_tracker import get_tracker
from datetime import datetime


def generate_unconventional_features():
    """Generate unconventional feature ideas organized by domain."""

    ideas = []

    # ========================================================================
    # VOLATILITY DOMAIN - Underexplored aspects
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="volatility_term_structure_slope",
            domain=FeatureDomain.VOLATILITY,
            description=(
                "Slope of implied vol curve across strikes (VIX calls cheaper than puts = risk-off pricing). "
                "Measures skew in tail risk expectations. When slope steepens (puts expensive), "
                "market expects downside shock. Predictive of next-week returns."
            ),
            rationale=(
                "Options markets price tail risk better than spot; skew changes lead spot returns by 2-5 days. "
                "High skew = elevated tail risk = mean-reversion pressure. "
                "Currently overlooked because IV data is expensive; retail traders don't access it."
            ),
            formula="(IV_put_otm - IV_call_otm) / IV_atm for 1m options",
            data_requirements=["Options data (IV surface)", "VIX term structure"],
            priority=0.75,
            source="discovery",
            metadata={
                "lookback_days": 20,
                "rebalance_frequency": "daily",
                "typical_ic": 0.08,
                "comment": "Requires real-time options vol feed; not accessible to retail without paid API",
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="realized_volatility_vs_implied_vol_spread",
            domain=FeatureDomain.VOLATILITY,
            description=(
                "Difference between realized vol (actual price moves, last 20 days) "
                "and implied vol (market expectation from options). "
                "When realized > implied, market is surprised by volatility; mean-revert by staying calm. "
                "When implied > realized, options expensive; tailwind for vol sellers."
            ),
            rationale=(
                "Vol basis (IV - RV) is mean-reverting. When basis extreme (+50bps), "
                "either IV collapses or RV rises. This predicts next 5-10 trading days well. "
                "Overlooked because requires both price data AND options data (not integrated in most retail tools)."
            ),
            formula="IV_20d - realized_vol_20d",
            data_requirements=["Options data (IV)", "High-frequency price data"],
            priority=0.7,
            source="discovery",
            metadata={
                "lookback_days": 20,
                "mean_reversion_halflife": "7 days",
                "typical_ic": 0.07,
            },
        )
    )

    # ========================================================================
    # SENTIMENT DOMAIN - Granular social signals
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="sentiment_change_rate_acceleration",
            domain=FeatureDomain.SENTIMENT,
            description=(
                "Not just sentiment level, but the ACCELERATION of sentiment change. "
                "When sentiment improves rapidly (>3x normal daily change), it signals exhaustion of good news. "
                "Contrarian signal: next week reversal likely."
            ),
            rationale=(
                "Sentiment extremes are brief; rapid swings unsustainable. "
                "Market tends to consolidate after fast sentiment moves. "
                "Overlooked because most sentiment models use level, not acceleration."
            ),
            formula="(sentiment_today - sentiment_5d_ago) / std(daily_changes_20d)",
            data_requirements=["Daily sentiment scores (FinBERT, Reddit, stocktwits)", "20-day baseline"],
            priority=0.65,
            source="discovery",
            metadata={
                "lookback_days": 20,
                "rebalance_frequency": "daily",
                "mean_reversion_days": 5,
                "typical_ic": 0.06,
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="bullish_call_ratio_divergence",
            domain=FeatureDomain.SENTIMENT,
            description=(
                "Options flow sentiment: ratio of bullish calls bought vs bearish puts bought. "
                "When bullish calls spike relative to bearish puts, retail traders are euphoric. "
                "Contrarian: next 2-5 days show mean-reversion (small pullback)."
            ),
            rationale=(
                "Retail option buying is predictably wrong near-term. When they're most bullish, "
                "market reverses. Also, flow-based (not price-based), so less efficiently priced. "
                "Overlooked because retail flow data is proprietary (need broker access)."
            ),
            formula="(bullish_calls_bought / total_calls) / (bearish_puts_bought / total_puts)",
            data_requirements=["Options flow data (ISE EQUITY PUT/CALL RATIO, CBOE)", "Intraday updates"],
            priority=0.6,
            source="discovery",
            metadata={
                "lookback_days": 10,
                "rebalance_frequency": "daily",
                "typical_ic": 0.05,
                "note": "Public data available via CBOE; not real-time without paid feed",
            },
        )
    )

    # ========================================================================
    # FLOW DOMAIN - Capital movement patterns
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="sector_rotation_momentum_score",
            domain=FeatureDomain.FLOW,
            description=(
                "Not rotation (which direction), but SPEED of rotation. "
                "When capital moves fast between sectors (e.g., out of tech, into energy), "
                "it indicates conviction shift. Predicts next month's sector leadership."
            ),
            rationale=(
                "Slow rotations = uncertain market; fast rotations = risk-off or risk-on conviction. "
                "Speed of flows predicts magnitude of next move better than direction alone. "
                "Overlooked because hard to quantify 'speed'; most traders look at price levels."
            ),
            formula="sum_of_abs_sector_weight_changes_weekly / baseline_volatility",
            data_requirements=["Sector ETF flows (XLV, XLK, XLI, XLE, XLC, XLRE, XLU, XLP)", "Weekly rebalance"],
            priority=0.65,
            source="discovery",
            metadata={
                "lookback_days": 20,
                "rebalance_frequency": "weekly",
                "typical_ic": 0.07,
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="etf_inflow_outflow_divergence",
            domain=FeatureDomain.FLOW,
            description=(
                "When opposite-tracking ETFs see divergent flows (QQQ inflows strong, SQQQ inflows weak), "
                "it signals retail hedge removal or conviction buy. Predicts next week directional move."
            ),
            rationale=(
                "ETF flows reveal true capital intent. When QQQ gets inflows while hedges (SQQQ, PSQ) "
                "see outflows, it's conviction long (not panic covering). Overlooked because flow data "
                "is delayed (weekly/monthly) and requires specialized data source."
            ),
            formula="(QQQ_inflows - SQQQ_inflows) / (QQQ_assets + SQQQ_assets)",
            data_requirements=[
                "ETF daily inflows (Morningstar, Bloomberg)",
                "QQQ, SQQQ, PSQ flows (weekly)",
            ],
            priority=0.55,
            source="discovery",
            metadata={
                "lookback_days": 5,
                "rebalance_frequency": "weekly",
                "forward_lag": "5-10 days",
                "typical_ic": 0.06,
            },
        )
    )

    # ========================================================================
    # CROSS-ASSET DOMAIN - Multi-market correlations
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="bonds_equity_correlation_break",
            domain=FeatureDomain.CROSS_ASSET,
            description=(
                "Bonds and equities normally negatively correlated (bonds rally when stocks fall). "
                "When correlation flips (both sell off together), it signals inflation shock or stagflation. "
                "This is a regime-change indicator; predict 10%+ equity drawdown within 1 month."
            ),
            rationale=(
                "Bond-equity correlation = inflation expectations. When breaks positive, "
                "market is pricing stagflation (growth + inflation). This is predictive 4+ weeks ahead. "
                "Overlooked because correlation is subtle; traders don't monitor correlation regime explicitly."
            ),
            formula="rolling_30d_correlation(SPY_returns, TLT_returns); flag if >0 for >5 days",
            data_requirements=["SPY prices", "TLT (long-duration bonds) prices", "20-60 day rolling window"],
            priority=0.7,
            source="discovery",
            metadata={
                "lookback_days": 60,
                "rebalance_frequency": "daily",
                "predictive_horizon": "20-30 days",
                "typical_ic": 0.08,
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="commodity_dividend_yield_spread",
            domain=FeatureDomain.CROSS_ASSET,
            description=(
                "Difference between commodity yields (oil futures contango) and dividend yields (SPY yield). "
                "When commodities expensive relative to equities (positive spread), it signals risk-on. "
                "When negative, risk-off. Predicts next 5-10 day directional bias."
            ),
            rationale=(
                "Commodity contango = carry cost = willingness to hold physical. "
                "When commodities expensive vs equities, real assets preferred; risk-on signal. "
                "Overlooked because requires modeling both commodity AND equity yields simultaneously."
            ),
            formula="(oil_contango_implied_yield - SPY_dividend_yield)",
            data_requirements=["Oil futures curve (CLZ, CLM)", "SPY dividend yield", "Spot prices"],
            priority=0.6,
            source="discovery",
            metadata={
                "lookback_days": 20,
                "rebalance_frequency": "daily",
                "typical_ic": 0.05,
            },
        )
    )

    # ========================================================================
    # PRICE ACTION DOMAIN - Micro-structure alpha
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="intraday_momentum_exhaustion_signal",
            domain=FeatureDomain.PRICE_ACTION,
            description=(
                "When stock rallies >3% intraday but closes near the lows, it signals "
                "'bull trap'. Price tried to break out but couldn't hold. Predicts next-day weakness (5% probability of +1% day)."
            ),
            rationale=(
                "Intraday failure patterns reveal hidden selling. When price rallies but volume"
                " low and close weak, it's capitulation attempt. Overlooked because requires "
                "intraday OHLC data (not available in daily-only systems)."
            ),
            formula=(
                "IF (high - open) > 3*avg_daily_range AND (close - open) < 1*avg_daily_range "
                "THEN signal = 1 ELSE 0"
            ),
            data_requirements=["Intraday OHLC (hourly or 15-min)", "Average daily range (20-day)"],
            priority=0.55,
            source="discovery",
            metadata={
                "lookback_days": 20,
                "rebalance_frequency": "daily (end-of-day scan)",
                "forward_lag": "1-3 days",
                "typical_ic": 0.04,
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="support_resistance_break_momentum",
            domain=FeatureDomain.PRICE_ACTION,
            description=(
                "When price breaks above 200-day moving average on high volume, "
                "it's a 'true breakout' signal. Next 20-day returns +2-4% on average. "
                "But if volume LOW on break, it's a 'false breakout' (50% chance of reversal within 5 days)."
            ),
            rationale=(
                "Volume confirmation of breakouts is key. Most traders look at price level "
                "but ignore volume. High volume breakouts are genuine; low volume are traps. "
                "This requires volume normalization (OBV, volume/20-day avg)."
            ),
            formula=(
                "IF price > 200ma AND volume > 1.5*avg_volume_20d THEN signal=1 "
                "ELSE IF price > 200ma AND volume < 0.8*avg_volume_20d THEN signal=-1"
            ),
            data_requirements=["Price (close, high, low)", "Volume (daily)", "200-day MA"],
            priority=0.6,
            source="discovery",
            metadata={
                "lookback_days": 200,
                "rebalance_frequency": "daily",
                "forward_lag": "5-20 days",
                "typical_ic": 0.06,
            },
        )
    )

    # ========================================================================
    # ALTERNATIVE DATA DOMAIN - Non-traditional signals
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="semiconductor_wafer_fab_utilization_lead",
            domain=FeatureDomain.ALTERNATIVE,
            description=(
                "Fab utilization (% of fab capacity used, published by SEMI monthly) "
                "leads semiconductor stock returns by 3-4 months. When utilization spikes, "
                "chip shortage ends soon; price pressure emerges later."
            ),
            rationale=(
                "Fabs run at high capacity during shortages, low capacity during gluts. "
                "Monthly SEMI data (free!) reveals cycle direction 3+ months before spot prices. "
                "Overlooked because lag is long (need to hold positions 3+ months) and signal is subtle."
            ),
            formula="fab_utilization_rate; 3-month forward correlation with MU, NVDA returns",
            data_requirements=[
                "SEMI Fab Utilization Index (free, monthly)",
                "Semiconductor stock prices (MU, NVDA, AMD, QCOM)",
            ],
            priority=0.75,
            source="discovery",
            metadata={
                "lookback_days": 180,
                "rebalance_frequency": "monthly",
                "forward_lag": "90-120 days",
                "typical_ic": 0.09,
                "comment": "Very long lag; requires patience and capital allocation planning",
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="commercial_real_estate_transaction_velocity",
            domain=FeatureDomain.ALTERNATIVE,
            description=(
                "Volume of commercial real estate transactions (office, retail, industrial) "
                "predicts REIT returns 6-12 months ahead. When transaction volume crashes, "
                "it signals sector stress coming. When volume spikes, it signals recovery."
            ),
            rationale=(
                "CRE transactions are leading indicator of investor sentiment. "
                "Public CRE transaction data available via CoStar, CBRE reports (paid). "
                "Overlooked because requires non-stock data; hard to integrate into trading systems."
            ),
            formula=(
                "transaction_volume_quarterly / baseline; "
                "compare to REIT prices 6-12 months forward"
            ),
            data_requirements=[
                "CRE transaction volume (CoStar, CBRE reports)",
                "REIT ETF prices (VNO, SLG, IRM, XLRE)",
            ],
            priority=0.55,
            source="discovery",
            metadata={
                "lookback_days": 365,
                "rebalance_frequency": "quarterly",
                "forward_lag": "180-360 days",
                "typical_ic": 0.07,
            },
        )
    )

    # ========================================================================
    # SEASONAL DOMAIN - Underexploited calendar effects
    # ========================================================================

    ideas.append(
        FeatureIdea(
            name="fiscal_calendar_driven_rebalancing",
            domain=FeatureDomain.SEASONAL,
            description=(
                "Institutional asset managers rebalance quarterly (Mar 31, Jun 30, Sep 30, Dec 31). "
                "This creates predictable buying/selling patterns 2 weeks before quarter-end. "
                "Underweight assets get bought (rebalance in), overweight assets get sold. "
                "Typically +0.5-1.0% moves for 1-2 weeks before quarter-end."
            ),
            rationale=(
                "Rebalancing is mechanical; predictable. But it's treated as noise. "
                "Most traders focus on earnings, not calendar mechanics. "
                "Overlooked because effect is small but consistent; hard to profitably trade."
            ),
            formula=(
                "IF within_10_days_of_quarter_end AND "
                "asset_ytd_return > target_allocation THEN signal=-1 (sell pressure)"
            ),
            data_requirements=[
                "Fiscal quarter calendar (fixed dates)",
                "YTD returns by asset class",
                "Target allocations (60/40 typical)",
            ],
            priority=0.5,
            source="discovery",
            metadata={
                "lookback_days": 90,
                "rebalance_frequency": "quarterly",
                "forward_lag": "5-15 days",
                "typical_ic": 0.04,
            },
        )
    )

    ideas.append(
        FeatureIdea(
            name="january_dividend_payment_flow",
            domain=FeatureDomain.SEASONAL,
            description=(
                "January typically sees highest dividend payments (many companies pay in Jan for tax reasons). "
                "This creates mechanical inflows to dividend stocks. Jan dividend flows "
                "typically +20-30% higher than other months. Predicts dividend stock outperformance in Jan."
            ),
            rationale=(
                "Tax-driven dividend timing creates predictable flows. "
                "Most traders miss this because it's micro-structure, not macro. "
                "But 20%+ higher inflows = real buying pressure for dividend stocks (XLP, XLRE)."
            ),
            formula=(
                "IF month == 1 THEN dividend_stock_allocation_increase = +2-3% of portfolio "
                "ELSE normal rebalancing"
            ),
            data_requirements=[
                "Dividend calendar by stock (SEC filings, Yahoo Finance)",
                "Dividend stock ETF flows (XLP, XLRE, SCHD)",
                "Seasonal dividend data",
            ],
            priority=0.45,
            source="discovery",
            metadata={
                "lookback_days": 365,
                "rebalance_frequency": "monthly",
                "forward_lag": "5-10 days",
                "typical_ic": 0.03,
                "note": "Small effect; more for context than standalone alpha",
            },
        )
    )

    return ideas


def main():
    """Generate and log unconventional feature ideas."""
    tracker = get_tracker()

    ideas = generate_unconventional_features()

    print("=" * 80)
    print("FEATURE ENGINEERING BRAINSTORM: UNCONVENTIONAL FEATURES")
    print("=" * 80)
    print()

    # Log each idea
    for idea in ideas:
        tracker.log_insight(
            title=f"Feature: {idea.name}",
            description=idea.description,
            category="feature",
            evidence={
                "rationale": idea.rationale,
                "formula": idea.formula,
                "data_requirements": idea.data_requirements,
                "priority": idea.priority,
                "typical_ic": idea.metadata.get("typical_ic"),
                "lookback_days": idea.metadata.get("lookback_days"),
                "forward_lag": idea.metadata.get("forward_lag"),
                "comment": idea.metadata.get("comment", ""),
            },
            session_id="brainstorm_features_jan_2026",
            tags=[idea.domain.value, "unconventional", "feature_engineering"],
            confidence=idea.priority,
        )

    # Print summary by domain
    by_domain = {}
    for idea in ideas:
        if idea.domain not in by_domain:
            by_domain[idea.domain] = []
        by_domain[idea.domain].append(idea)

    for domain in sorted(by_domain.keys(), key=lambda x: x.value):
        domain_ideas = by_domain[domain]
        print(f"\n{domain.value.upper()} ({len(domain_ideas)} features)")
        print("-" * 80)
        for idea in domain_ideas:
            print(f"\n  {idea.name}")
            print(f"    Priority: {idea.priority:.0%}")
            print(f"    Typical IC: {idea.metadata.get('typical_ic', 'N/A')}")
            print(f"    Lookback: {idea.metadata.get('lookback_days', 'N/A')} days")
            print(f"    Description: {idea.description[:70]}...")

    # Print top ideas by priority
    print("\n" + "=" * 80)
    print("TOP FEATURES BY PRIORITY")
    print("=" * 80)
    top_ideas = sorted(ideas, key=lambda x: x.priority, reverse=True)[:8]
    for i, idea in enumerate(top_ideas, 1):
        print(f"\n{i}. {idea.name} ({idea.priority:.0%} priority)")
        print(f"   Domain: {idea.domain.value}")
        print(f"   Typical IC: {idea.metadata.get('typical_ic'):.3f}")
        print(f"   Data: {', '.join(idea.data_requirements[:1])}...")

    # Statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"\nTotal features proposed: {len(ideas)}")
    print(f"Average priority: {sum(i.priority for i in ideas) / len(ideas):.0%}")
    print(f"Average typical IC: {sum(i.metadata.get('typical_ic', 0.05) for i in ideas) / len(ideas):.3f}")

    # Domain breakdown
    print("\nBy Domain:")
    for domain in sorted(by_domain.keys(), key=lambda x: x.value):
        count = len(by_domain[domain])
        avg_priority = sum(i.priority for i in by_domain[domain]) / count
        print(f"  {domain.value:20} : {count:2} features (avg priority {avg_priority:.0%})")

    print(f"\n\nSession tracker updated with {len(ideas)} feature ideas")


if __name__ == "__main__":
    main()
